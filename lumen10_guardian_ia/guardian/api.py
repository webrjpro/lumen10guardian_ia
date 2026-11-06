import json
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from guardian.ai import provider_status
from guardian.config import Settings
from guardian.connections import ProjectConnection
from guardian.db import Store, encode, now, uid
from guardian.engine import Engine
from guardian.licensing import LicenseGuard
from guardian.policy import authorize_release, next_window
from guardian.processes import run_quiet
from guardian.security import authenticate, bootstrap, digest, issue_credential, redact
from guardian.workflow import enqueue, record_event


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EnvironmentInput(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    kind: str = "http"
    target: str = Field(min_length=1, max_length=2048)
    system_id: str | None = Field(default=None, max_length=64)

    @field_validator("kind")
    @classmethod
    def kind_valid(cls, value):
        if value not in {"http", "project", "agent"}:
            raise ValueError("Tipo permitido: http, project ou agent")
        return value


class PolicyInput(StrictModel):
    paused: bool
    auto_ai: bool
    enabled: bool | None = None
    timezone: str = "America/Sao_Paulo"
    maintenance: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @field_validator("timezone")
    @classmethod
    def tz_valid(cls, value):
        try:
            ZoneInfo(value)
        except (KeyError, ValueError):
            raise ValueError("Fuso IANA inválido") from None
        return value


class EventInput(StrictModel):
    event_id: str = Field(max_length=64)
    environment_id: str = Field(max_length=64)
    kind: str = Field(max_length=80)
    summary: str = Field(min_length=1, max_length=12000)
    severity: str = Field(default="P2", pattern="^P[0-3]$")


class Exchange(StrictModel):
    ticket: str = Field(min_length=30, max_length=200)


class MonitorInput(StrictModel):
    active: bool


class HeartbeatInput(StrictModel):
    event_id: str = Field(max_length=64)
    environment_id: str = Field(max_length=64)
    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    disk_percent: float = Field(ge=0, le=100)


class LicenseInput(StrictModel):
    license_path: str = Field(min_length=1, max_length=2048)
    document_path: str | None = Field(default=None, max_length=2048)


class EmailSettingsInput(StrictModel):
    environment_id: str = Field(max_length=64)
    enabled: bool
    sender: str = Field(max_length=254)
    recipients: list[str] = Field(min_length=1, max_length=5)

    @field_validator("sender")
    @classmethod
    def sender_valid(cls, value):
        if not re.fullmatch(r"[^\s@<>\r\n]+@[^\s@<>\r\n]+\.[^\s@<>\r\n]+", value):
            raise ValueError("E-mail inválido")
        return value

    @field_validator("recipients")
    @classmethod
    def recipients_valid(cls, values):
        return [cls.sender_valid(value) for value in values]


class SourceConnectionInput(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(max_length=2048)
    environment_id: str = Field(pattern=r"^[a-fA-F0-9-]{36}$")
    token: str = Field(min_length=30, max_length=200)


class SystemInput(StrictModel):
    name: str = Field(min_length=1, max_length=100)


class SecurityProfileInput(StrictModel):
    technologies: list[str] = Field(min_length=1, max_length=12)
    versions: dict[str, str] = Field(default_factory=dict)

    @field_validator("technologies")
    @classmethod
    def valid_technologies(cls, values):
        if any(not re.fullmatch(r"[a-z0-9._+-]{1,30}", v) for v in values):
            raise ValueError("Use identificadores simples: php, moodle, nginx, docker...")
        return values

    @field_validator("versions")
    @classmethod
    def valid_versions(cls, values):
        if len(values) > 20 or any(len(k) > 30 or len(v) > 80 for k, v in values.items()):
            raise ValueError("Inventário de versões excede limite")
        return values


def create_app(settings=None, provider=None):
    settings = settings or Settings.load()
    store = Store(settings.database)
    bootstrap(store, settings)
    engine = Engine(store, settings, provider)
    licensing = LicenseGuard(settings)

    @asynccontextmanager
    async def lifespan(app):
        if settings.workers:
            engine.start()
        yield
        engine.close()

    app = FastAPI(
        title="Lumen10 Guardian", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.store, app.state.engine, app.state.settings = store, engine, settings
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        allowed = {f"http://127.0.0.1:{settings.port}", f"http://localhost:{settings.port}"}
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin not in allowed:
            return JSONResponse({"detail": "Origem não permitida"}, status_code=403)
        if int(request.headers.get("content-length", "0")) > 32768:
            return JSONResponse({"detail": "Corpo excede o limite"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({"detail": redact(str(exc))}, status_code=409)

    def principal(request: Request):
        header = request.headers.get("authorization", "")
        token = header[7:] if header.startswith("Bearer ") else request.cookies.get("guardian_session")
        identity = authenticate(store, token)
        if not identity or identity["role"] == "ticket":
            raise HTTPException(401, "Abra o painel pelo script Abrir-Painel.ps1")
        return identity

    def owner(identity=Depends(principal)):
        if identity["role"] != "owner":
            raise HTTPException(403, "Operação restrita ao administrador")
        return identity

    def human(identity=Depends(principal)):
        if identity["role"] not in {"owner", "viewer"}:
            raise HTTPException(403, "Agente não acessa o plano de controle")
        return identity

    def resource(table, tenant, identifier):
        if table not in {"environments", "incidents", "changes", "systems"}:
            raise ValueError("Tabela inválida")
        value = store.one(f"SELECT * FROM {table} WHERE tenant_id=? AND id=?", (tenant, identifier))
        if not value:
            raise HTTPException(404, "Recurso não encontrado")
        return value

    def environment_mutable(tenant, identifier):
        env = resource("environments", tenant, identifier)
        if env["paused"]:
            raise HTTPException(409, "Mudanças suspensas")
        return env

    @app.get("/healthz")
    def health():
        return {"service": "lumen10-guardian", "status": "ok", "version": "0.1.0"}

    @app.post("/auth/exchange")
    def exchange(body: Exchange, response: Response):
        with store.transaction() as db:
            ticket = db.execute(
                "SELECT * FROM credentials WHERE hash=? AND role='ticket' AND revoked=0 AND expires_at>?",
                (digest(body.ticket), time.time()),
            ).fetchone()
            if not ticket:
                raise HTTPException(401, "Acesso expirado. Reabra pelo script")
            db.execute("DELETE FROM credentials WHERE hash=?", (digest(body.ticket),))
            token = issue_credential(store, ticket["tenant_id"], "owner", ttl=28800, db=db)
            store.audit(ticket["tenant_id"], "operator", "session.created", "local", {}, db)
        response.set_cookie("guardian_session", token, httponly=True, samesite="strict", max_age=28800)
        return {"ok": True}

    @app.post("/auth/logout")
    def logout(response: Response, identity=Depends(human)):
        store.execute("UPDATE credentials SET revoked=1 WHERE hash=?", (identity["hash"],))
        response.delete_cookie("guardian_session")
        return {"ok": True}

    @lru_cache(maxsize=1)
    def cached_provider(minute):
        return provider_status()

    @app.get("/api/v1/overview")
    def overview(identity=Depends(human)):
        tenant = identity["tenant_id"]
        envs = store.rows("SELECT * FROM environments WHERE tenant_id=? ORDER BY name", (tenant,))
        for env in envs:
            env["latest"] = store.one(
                "SELECT * FROM samples WHERE tenant_id=? AND environment_id=? ORDER BY id DESC LIMIT 1",
                (tenant, env["id"]),
            )
            counts = store.one(
                "SELECT count(*) AS total,sum(healthy) AS healthy FROM samples WHERE tenant_id=? AND environment_id=?",
                (tenant, env["id"]),
            )
            env["availability"] = (
                round(100 * (counts["healthy"] or 0) / counts["total"], 2) if counts["total"] else None
            )
            env["sample_count"] = counts["total"]
            env["next_window"] = next_window(env["timezone"], env["maintenance"])
            env.pop("config")
        return {
            "tenant": store.one("SELECT * FROM tenants WHERE id=?", (tenant,)),
            "systems": store.rows("SELECT * FROM systems WHERE tenant_id=? ORDER BY name", (tenant,)),
            "security_profiles": store.rows("SELECT * FROM security_profiles WHERE tenant_id=?", (tenant,)),
            "threat_reports": store.rows(
                "SELECT * FROM threat_reports WHERE tenant_id=? ORDER BY reviewed_at DESC LIMIT 12", (tenant,)
            ),
            "environments": envs,
            "incidents": store.rows(
                "SELECT * FROM incidents WHERE tenant_id=? ORDER BY created_at DESC LIMIT 100", (tenant,)
            ),
            "jobs": store.rows("SELECT * FROM jobs WHERE tenant_id=? ORDER BY created_at DESC LIMIT 40", (tenant,)),
            "changes": store.rows(
                "SELECT * FROM changes WHERE tenant_id=? ORDER BY created_at DESC LIMIT 30", (tenant,)
            ),
            "specialists": store.rows(
                "SELECT * FROM specialist_tasks WHERE tenant_id=? ORDER BY created_at DESC LIMIT 30", (tenant,)
            ),
            "audit": store.rows("SELECT * FROM audit WHERE tenant_id=? ORDER BY seq DESC LIMIT 40", (tenant,)),
            "runtime": store.rows(
                "SELECT * FROM runtime WHERE key IN (?,?,?)",
                ("monitor_enabled:" + tenant, "worker_heartbeat", "monitor_heartbeat"),
            ),
            "provider": cached_provider(int(time.time() // 60)),
            "ai_limit": settings.ai_daily_limit,
            "ai_configuration": {
                "model": settings.model,
                "security_model": settings.security_model,
                "reasoning": settings.reasoning,
            },
            "license": licensing.status(),
            "notifications": store.rows(
                "SELECT id,action,resource,state,attempts,error,created_at FROM notification_outbox WHERE tenant_id=? ORDER BY created_at DESC LIMIT 30",
                (tenant,),
            ),
            "notification_channel": store.one("SELECT * FROM notification_settings WHERE tenant_id=?", (tenant,)),
            "ai_used": store.one(
                "SELECT count(*) AS n FROM audit WHERE tenant_id=? AND action='ai.started' AND occurred_at>=?",
                (tenant, now()[:10]),
            )["n"],
            "monitoring_active": (
                store.one("SELECT value FROM runtime WHERE key=?", ("monitor_enabled:" + tenant,)) or {}
            ).get("value")
            == "1",
            "server_time": now(),
        }

    @app.post("/api/v1/system/monitor")
    def switch_monitor(body: MonitorInput, identity=Depends(owner)):
        if body.active:
            licensing.require("monitor", identity["tenant_id"])
        store.execute(
            "INSERT OR REPLACE INTO runtime VALUES(?,?)",
            ("monitor_enabled:" + identity["tenant_id"], "1" if body.active else "0"),
        )
        store.audit(
            identity["tenant_id"], "operator", "monitor.activated" if body.active else "monitor.paused", "local", {}
        )
        engine.monitor_wake.set()
        return {"active": body.active}

    @app.post("/api/v1/environments", status_code=201)
    def create_environment(body: EnvironmentInput, identity=Depends(owner)):
        if body.system_id:
            resource("systems", identity["tenant_id"], body.system_id)
        target = body.target
        if body.kind == "http":
            url = urlsplit(target)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError("Use URL HTTP(S) sem credenciais, query ou fragmento")
        elif body.kind == "project":
            path = Path(target).resolve()
            if not path.is_dir():
                raise ValueError("Pasta do projeto não existe nesta máquina")
            target = str(path)
        identifier = uid()
        with store.transaction() as db:
            count = db.execute(
                "SELECT count(*) FROM environments WHERE tenant_id=?", (identity["tenant_id"],)
            ).fetchone()[0]
            if count >= 20:
                raise ValueError("Limite local de 20 ambientes")
            db.execute(
                "INSERT INTO environments(id,tenant_id,name,kind,target,system_id,auto_ai) VALUES(?,?,?,?,?,?,1)",
                (identifier, identity["tenant_id"], body.name, body.kind, target, body.system_id),
            )
            store.audit(identity["tenant_id"], "operator", "environment.created", identifier, {"kind": body.kind}, db)
        return {"id": identifier}

    @app.post("/api/v1/systems", status_code=201)
    def create_system(body: SystemInput, identity=Depends(owner)):
        identifier = uid()
        store.execute("INSERT INTO systems VALUES(?,?,?,?)", (identifier, identity["tenant_id"], body.name, now()))
        store.audit(identity["tenant_id"], "operator", "system.created", identifier, {"name": body.name})
        return {"id": identifier}

    @app.put("/api/v1/systems/{identifier}/security-profile")
    def security_profile(identifier: str, body: SecurityProfileInput, identity=Depends(owner)):
        resource("systems", identity["tenant_id"], identifier)
        store.execute(
            "INSERT OR REPLACE INTO security_profiles VALUES(?,?,?,?)",
            (identity["tenant_id"], identifier, encode(body.technologies), encode(body.versions)),
        )
        store.audit(
            identity["tenant_id"],
            "operator",
            "security.profile_updated",
            identifier,
            {"technologies": body.technologies},
        )
        return {"saved": True}

    @app.post("/api/v1/security/threat-review", status_code=202)
    def threat_review(identity=Depends(owner)):
        licensing.require("ai", identity["tenant_id"])
        env = store.one(
            "SELECT id FROM environments WHERE tenant_id=? AND enabled=1 ORDER BY CASE WHEN kind='local' THEN 0 ELSE 1 END LIMIT 1",
            (identity["tenant_id"],),
        )
        if not env:
            raise ValueError("Ambiente local ainda não configurado")
        return {"job_id": enqueue(store, identity["tenant_id"], env["id"], None, "threat_review")}

    @app.put("/api/v1/environments/{identifier}/system/{system_id}")
    def group_environment(identifier: str, system_id: str, identity=Depends(owner)):
        resource("systems", identity["tenant_id"], system_id)
        resource("environments", identity["tenant_id"], identifier)
        store.execute(
            "UPDATE environments SET system_id=? WHERE tenant_id=? AND id=?",
            (system_id, identity["tenant_id"], identifier),
        )
        store.audit(identity["tenant_id"], "operator", "environment.grouped", identifier, {"system_id": system_id})
        return {"grouped": True}

    @app.put("/api/v1/environments/{identifier}/policy")
    def policy(identifier: str, body: PolicyInput, identity=Depends(owner)):
        resource("environments", identity["tenant_id"], identifier)
        with store.transaction() as db:
            db.execute(
                "UPDATE environments SET paused=?,auto_ai=?,timezone=?,maintenance=?,enabled=coalesce(?,enabled) WHERE tenant_id=? AND id=?",
                (
                    body.paused,
                    body.auto_ai,
                    body.timezone,
                    body.maintenance,
                    body.enabled,
                    identity["tenant_id"],
                    identifier,
                ),
            )
            store.audit(identity["tenant_id"], "operator", "policy.updated", identifier, body.model_dump(), db)
        return {"ok": True, "next_window": next_window(body.timezone, body.maintenance)}

    @app.get("/api/v1/environments/{identifier}/samples")
    def samples(identifier: str, identity=Depends(human)):
        resource("environments", identity["tenant_id"], identifier)
        return store.rows(
            "SELECT * FROM samples WHERE tenant_id=? AND environment_id=? ORDER BY id DESC LIMIT 120",
            (identity["tenant_id"], identifier),
        )

    @app.get("/api/v1/environments/{identifier}/connection")
    def connection(identifier: str, identity=Depends(owner)):
        env = resource("environments", identity["tenant_id"], identifier)
        if env["kind"] != "project":
            raise ValueError("Cadastre a pasta de um projeto para ler as credenciais")
        return ProjectConnection(env["target"]).inventory()

    @app.post("/api/v1/environments/{identifier}/ssh-snapshot")
    def ssh_snapshot(identifier: str, identity=Depends(owner)):
        licensing.require("ssh_read", identity["tenant_id"])
        env = resource("environments", identity["tenant_id"], identifier)
        if env["kind"] != "project":
            raise ValueError("Ambiente sem conexão de projeto")
        result = ProjectConnection(env["target"]).snapshot()
        store.audit(identity["tenant_id"], "executor", "ssh.snapshot", identifier, {"operation": "host_read_only"})
        return {"output": result}

    @app.post("/api/v1/telemetry/events", status_code=202)
    def telemetry(body: EventInput, identity=Depends(principal)):
        licensing.require("monitor", identity["tenant_id"])
        if identity["role"] != "agent" or identity["environment_id"] != body.environment_id:
            raise HTTPException(403, "Agente sem escopo para este ambiente")
        resource("environments", identity["tenant_id"], body.environment_id)
        incident = record_event(
            store,
            identity["tenant_id"],
            body.environment_id,
            body.kind,
            body.summary,
            body.severity,
            event_id=digest(identity["tenant_id"] + body.environment_id + body.event_id),
        )
        return {"incident_id": incident, "accepted": True}

    @app.post("/api/v1/telemetry/heartbeat", status_code=202)
    def heartbeat(body: HeartbeatInput, identity=Depends(principal)):
        licensing.require("monitor", identity["tenant_id"])
        if identity["role"] != "agent" or identity["environment_id"] != body.environment_id:
            raise HTTPException(403, "Agente sem escopo")
        env = resource("environments", identity["tenant_id"], body.environment_id)
        if env["kind"] != "agent":
            raise ValueError("Heartbeat requer ambiente do tipo agent")
        with store.transaction() as db:
            changed = db.execute(
                "INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?)",
                (
                    digest(identity["tenant_id"] + body.environment_id + body.event_id),
                    identity["tenant_id"],
                    body.environment_id,
                    now(),
                    "agent_heartbeat",
                    "Agent alive",
                ),
            ).rowcount
            if changed:
                db.execute(
                    "INSERT INTO samples(tenant_id,environment_id,observed_at,healthy,latency,data) VALUES(?,?,?,?,?,?)",
                    (
                        identity["tenant_id"],
                        body.environment_id,
                        now(),
                        int(body.disk_percent < 95 and body.memory_percent < 97),
                        None,
                        encode(body.model_dump(exclude={"event_id", "environment_id"})),
                    ),
                )
        if body.memory_percent >= 97 or body.disk_percent >= 95:
            record_event(
                store,
                identity["tenant_id"],
                body.environment_id,
                "resource_pressure",
                "Pressão elevada de memória ou disco no host " + env["name"],
                "P2",
            )
        return {"accepted": True}

    @app.post("/api/v1/environments/{identifier}/agents", status_code=201)
    def enroll(identifier: str, identity=Depends(owner)):
        licensing.require("monitor", identity["tenant_id"])
        resource("environments", identity["tenant_id"], identifier)
        token = issue_credential(store, identity["tenant_id"], "agent", identifier)
        store.audit(identity["tenant_id"], "operator", "agent.enrolled", identifier, {})
        return {"token": token, "credential_id": digest(token), "environment_id": identifier}

    @app.delete("/api/v1/agents/{credential_id}")
    def revoke(credential_id: str, identity=Depends(owner)):
        store.execute(
            "UPDATE credentials SET revoked=1 WHERE tenant_id=? AND hash=? AND role='agent'",
            (identity["tenant_id"], credential_id),
        )
        store.audit(identity["tenant_id"], "operator", "agent.revoked", credential_id, {})
        return {"ok": True}

    @app.post("/api/v1/incidents/{identifier}/{action}", status_code=202)
    def incident_action(identifier: str, action: str, identity=Depends(owner)):
        licensing.require("ai" if action == "investigate" else "lab", identity["tenant_id"])
        incident = resource("incidents", identity["tenant_id"], identifier)
        env = resource("environments", identity["tenant_id"], incident["environment_id"])
        if action not in {"investigate", "repair"}:
            raise HTTPException(404, "Ação inexistente")
        if action == "repair":
            environment_mutable(identity["tenant_id"], env["id"])
            if env["kind"] != "fixture":
                raise ValueError("Correção habilitada somente no laboratório local nesta versão")
        job = enqueue(store, identity["tenant_id"], incident["environment_id"], identifier, action)
        store.audit(identity["tenant_id"], "operator", "job.requested", identifier, {"kind": action})
        return {"job_id": job, "deduplicated": job is None}

    @app.post("/api/v1/environments/{identifier}/review", status_code=202)
    def review(identifier: str, identity=Depends(owner)):
        licensing.require("ai", identity["tenant_id"])
        resource("environments", identity["tenant_id"], identifier)
        return {"job_id": enqueue(store, identity["tenant_id"], identifier, None, "security_review")}

    @app.post("/api/v1/laboratory", status_code=201)
    def laboratory(identity=Depends(owner)):
        licensing.require("lab", identity["tenant_id"])
        total = store.one(
            "SELECT count(*) AS n FROM environments WHERE tenant_id=? AND kind='fixture'", (identity["tenant_id"],)
        )["n"]
        if total >= 5:
            raise ValueError("Limite de cinco laboratórios locais")
        return engine.lab.create(identity["tenant_id"])

    @app.post("/api/v1/changes/{identifier}/{action}")
    def release(identifier: str, action: str, identity=Depends(owner)):
        licensing.require("lab", identity["tenant_id"])
        tenant = identity["tenant_id"]
        change = resource("changes", tenant, identifier)
        if action == "deploy":
            return {"state": engine.lab.deploy(tenant, identifier)}
        if action == "rollback":
            return {"state": engine.lab.rollback(tenant, identifier)}
        if action == "schedule":
            env = environment_mutable(tenant, change["environment_id"])
            allowed, reason = authorize_release(env, json.loads(change["artifact"]))
            if not allowed:
                raise ValueError(reason)
            scheduled = next_window(env["timezone"], env["maintenance"])
            with store.transaction() as db:
                changed = db.execute(
                    "UPDATE changes SET state='AGENDADO' WHERE tenant_id=? AND id=? AND state='TESTES_APROVADOS'",
                    (tenant, identifier),
                ).rowcount
                if not changed:
                    raise ValueError("Release não elegível para agendamento")
                enqueue(
                    store,
                    tenant,
                    env["id"],
                    change["incident_id"],
                    "release",
                    datetime.fromisoformat(scheduled).timestamp(),
                    db,
                )
                store.audit(tenant, "operator", "release.scheduled", identifier, {"scheduled_at": scheduled}, db)
            return {"scheduled_at": scheduled}
        raise HTTPException(404, "Ação inexistente")

    @app.post("/api/v1/powershell/snapshot")
    def powershell(identity=Depends(owner)):
        licensing.require("monitor", identity["tenant_id"])
        import shutil

        executable = shutil.which("pwsh") or shutil.which("powershell")
        if not executable:
            raise ValueError("PowerShell não encontrado")
        script = Path(__file__).parent / "powershell/Snapshot.ps1"
        result = run_quiet(
            [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        store.audit(identity["tenant_id"], "executor", "powershell.snapshot", "local", {"exit_code": result.returncode})
        return {"output": redact(result.stdout), "exit_code": result.returncode}

    @app.get("/api/v1/audit/verify")
    def verify(identity=Depends(owner)):
        return {"valid": store.verify_audit(identity["tenant_id"]), "scope": "hash-chain-local"}

    @app.get("/api/v1/license/activation-request")
    def activation_request(identity=Depends(owner)):
        from guardian.licensing import device_fingerprint

        return {
            "product": "lumen10-guardian",
            "installation_id": licensing.installation,
            "device_fingerprint": device_fingerprint(),
            "tenant_id": identity["tenant_id"],
            "requested_capabilities": ["monitor", "ai", "lab", "ssh_read"],
        }

    @app.put("/api/v1/notifications/settings")
    def notifications_settings(body: EmailSettingsInput, identity=Depends(owner)):
        licensing.require("monitor", identity["tenant_id"])
        env = resource("environments", identity["tenant_id"], body.environment_id)
        if env["kind"] != "project":
            raise ValueError("Escolha a pasta de projeto que contém os campos SMTP")
        values = ProjectConnection(env["target"]).values()
        if body.enabled and not all(values.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")):
            raise ValueError("SMTP_HOST, SMTP_USER e SMTP_PASSWORD ainda não foram encontrados nos arquivos locais")
        store.execute(
            "INSERT OR REPLACE INTO notification_settings VALUES(?,?,?,?,?)",
            (identity["tenant_id"], body.environment_id, body.enabled, body.sender, encode(body.recipients)),
        )
        store.audit(
            identity["tenant_id"],
            "operator",
            "notifications.configured",
            body.environment_id,
            {"enabled": body.enabled, "recipient_count": len(body.recipients)},
        )
        return {"configured": True, "enabled": body.enabled}

    @app.post("/api/v1/environments/{identifier}/source-key", status_code=201)
    def source_key(identifier: str, identity=Depends(owner)):
        licensing.require("ai", identity["tenant_id"])
        env = resource("environments", identity["tenant_id"], identifier)
        if env["kind"] != "project":
            raise ValueError("Chave de leitura requer uma pasta de projeto cadastrada")
        token = issue_credential(store, identity["tenant_id"], "source_reader", identifier, ttl=2592000)
        store.audit(identity["tenant_id"], "operator", "source.key_issued", identifier, {"ttl_days": 30})
        return {
            "token": token,
            "credential_id": digest(token),
            "scope": "source.read",
            "ttl_days": 30,
            "environment_id": identifier,
        }

    @app.post("/api/v1/source-connections", status_code=201)
    def source_connection(body: SourceConnectionInput, identity=Depends(owner)):
        licensing.require("ai", identity["tenant_id"])
        parsed = urlsplit(body.base_url)
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not (
                parsed.scheme == "https" or parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
            )
        ):
            raise ValueError("Use HTTPS ou túnel em loopback, sem credenciais na URL")
        identifier = uid()
        from guardian.security import protect_file

        key_path = settings.data / "source-keys" / (identifier + ".key")
        key_path.parent.mkdir(parents=True, exist_ok=True)
        protect_file(key_path, body.token)
        store.execute(
            "INSERT INTO environments(id,tenant_id,name,kind,target,config) VALUES(?,?,?,?,?,?)",
            (
                identifier,
                identity["tenant_id"],
                body.name,
                "remote-source",
                body.base_url,
                encode({"remote_environment_id": body.environment_id}),
            ),
        )
        store.audit(identity["tenant_id"], "operator", "source.connected", identifier, {"scope": "source.read"})
        return {"environment_id": identifier}

    def source_access(identifier, identity):
        licensing.require("ai", identity["tenant_id"])
        if identity["role"] != "owner" and not (
            identity["role"] == "source_reader" and identity["environment_id"] == identifier
        ):
            raise HTTPException(403, "Chave não autoriza este projeto")
        env = resource("environments", identity["tenant_id"], identifier)
        if env["kind"] != "project":
            raise ValueError("Ambiente sem raiz de código")
        from guardian.source_gateway import SourceGateway

        return SourceGateway(env["target"])

    @app.get("/api/v1/projects/{identifier}/source/manifest")
    def source_manifest(identifier: str, identity=Depends(principal)):
        result = source_access(identifier, identity).manifest()
        store.audit(
            identity["tenant_id"], "source-reader", "source.manifest", identifier, {"file_count": len(result["files"])}
        )
        return result

    @app.get("/api/v1/projects/{identifier}/source/file")
    def source_file(identifier: str, path: str, identity=Depends(principal)):
        result = source_access(identifier, identity).read(path)
        store.audit(identity["tenant_id"], "source-reader", "source.read", identifier, {"path": path})
        return result

    @app.delete("/api/v1/source-keys/{credential_id}")
    def revoke_source_key(credential_id: str, identity=Depends(owner)):
        store.execute(
            "UPDATE credentials SET revoked=1 WHERE tenant_id=? AND hash=? AND role='source_reader'",
            (identity["tenant_id"], credential_id),
        )
        store.audit(identity["tenant_id"], "operator", "source.key_revoked", credential_id, {})
        return {"revoked": True}

    @app.post("/api/v1/license/activate")
    def activate_license(body: LicenseInput, identity=Depends(owner)):
        try:
            result = licensing.install(body.license_path, body.document_path)
        except OSError:
            raise ValueError("Arquivo de licença ou documento não encontrado ou sem acesso") from None
        store.audit(
            identity["tenant_id"],
            "operator",
            "license.activated",
            "local",
            {"edition": result["edition"], "id": result["license_id"]},
        )
        return result

    @app.get("/api/v1/openapi.json")
    def openapi(identity=Depends(human)):
        return app.openapi()

    web = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.get("/")
    def index():
        return FileResponse(web / "index.html")

    return app
