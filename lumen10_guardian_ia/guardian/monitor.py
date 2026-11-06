import time
from datetime import datetime, timezone

import httpx
import psutil

from guardian.db import encode, now
from guardian.security import redact
from guardian.workflow import record_event


def sample(environment):
    started = time.monotonic()
    if environment["kind"] == "local":
        disk = psutil.disk_usage(psutil.Process().cwd())
        data = {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": disk.percent,
            "disk_free_gb": round(disk.free / 1024**3, 1),
        }
        healthy = data["disk_percent"] < 95 and data["memory_percent"] < 97
    elif environment["kind"] == "http":
        try:
            with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
                with client.stream(
                    "GET", environment["target"], headers={"User-Agent": "Lumen10Guardian/0.1"}
                ) as response:
                    healthy = 200 <= response.status_code < 400
                    data = {
                        "status_code": response.status_code,
                        "server_header": response.headers.get("server", "")[:100],
                        "x_powered_by_header": response.headers.get("x-powered-by", "")[:100],
                    }
        except httpx.HTTPError as exc:
            healthy, data = False, {"error": type(exc).__name__}
    else:
        return None
    return healthy, round((time.monotonic() - started) * 1000, 1), data


class Monitor:
    def __init__(self, store, licensing=None):
        self.store = store
        self.licensing = licensing

    def tick(self):
        for env in self.store.rows("SELECT * FROM environments WHERE enabled=1"):
            active = self.store.one("SELECT value FROM runtime WHERE key=?", ("monitor_enabled:" + env["tenant_id"],))
            if not active or active["value"] != "1":
                continue
            if self.licensing:
                try:
                    self.licensing.require("monitor", env["tenant_id"])
                except ValueError:
                    continue
            try:
                result = sample(env)
                if env["kind"] == "agent":
                    latest = self.store.one(
                        "SELECT observed_at FROM samples WHERE tenant_id=? AND environment_id=? ORDER BY id DESC LIMIT 1",
                        (env["tenant_id"], env["id"]),
                    )
                    if (
                        not latest
                        or (datetime.now(timezone.utc) - datetime.fromisoformat(latest["observed_at"])).total_seconds()
                        > 120
                    ):
                        record_event(
                            self.store,
                            env["tenant_id"],
                            env["id"],
                            "agent_offline",
                            "Agente sem heartbeat recente: " + env["name"],
                            "P1",
                        )
                if result is not None:
                    healthy, latency, data = result
                    self.store.execute(
                        "INSERT INTO samples(tenant_id,environment_id,observed_at,healthy,latency,data) VALUES(?,?,?,?,?,?)",
                        (env["tenant_id"], env["id"], now(), int(healthy), latency, encode(data)),
                    )
                    recent = self.store.rows(
                        "SELECT healthy FROM samples WHERE tenant_id=? AND environment_id=? ORDER BY id DESC LIMIT 2",
                        (env["tenant_id"], env["id"]),
                    )
                    if len(recent) == 2 and all(not item["healthy"] for item in recent):
                        record_event(
                            self.store,
                            env["tenant_id"],
                            env["id"],
                            "health_failed",
                            "Falha persistente de disponibilidade ou recursos no ambiente " + env["name"],
                            "P1",
                        )
            except Exception as exc:
                self.store.audit(
                    env["tenant_id"], "monitor", "monitor.error", env["id"], {"error": redact(type(exc).__name__)}
                )
        self.store.execute("INSERT OR REPLACE INTO runtime VALUES('monitor_heartbeat',?)", (now(),))
        # Retenção limitada; os incidentes mantêm a evidência resumida.
        self.store.execute("DELETE FROM samples WHERE observed_at < datetime('now','-7 days')")
        self.store.execute("DELETE FROM events WHERE observed_at < datetime('now','-30 days')")
        self.store.execute("DELETE FROM credentials WHERE expires_at IS NOT NULL AND expires_at<?", (time.time(),))
