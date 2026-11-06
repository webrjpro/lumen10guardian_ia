"""Boletins oficiais, duas janelas diárias; evidências não autorizam patches."""

import hashlib
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from guardian.db import encode, now, uid
from guardian.workflow import enqueue

PHP_URL = "https://www.php.net/releases/?json"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
KEV_MIRROR = "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json"
DEFAULT_TECHNOLOGIES = ["php", "moodle", "mariadb", "nginx", "apache", "docker"]


def latest_slot(at=None):
    local = (at or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/Sao_Paulo"))
    if local.hour < 8:
        from datetime import timedelta

        local -= timedelta(days=1)
        hour = 20
    else:
        hour = 20 if local.hour >= 20 else 8
    return local.strftime("%Y-%m-%d") + f":{hour:02d}"


class ThreatScheduler:
    def __init__(self, store):
        self.store = store

    def tick(self, at=None):
        slot = latest_slot(at)
        for tenant in self.store.rows("SELECT id FROM tenants"):
            identifier = tenant["id"]
            active = self.store.one("SELECT value FROM runtime WHERE key=?", ("monitor_enabled:" + identifier,))
            if not active or active["value"] != "1":
                continue
            key = "threat_slot:" + identifier
            previous = self.store.one("SELECT value FROM runtime WHERE key=?", (key,))
            if previous is None:
                # Nova instalação começa na próxima janela, sem rajada de análises passadas.
                self.store.execute("INSERT OR IGNORE INTO runtime VALUES(?,?)", (key, slot))
                continue
            if previous["value"] == slot:
                continue
            env = self.store.one(
                "SELECT id FROM environments WHERE tenant_id=? AND enabled=1 ORDER BY CASE WHEN kind='local' THEN 0 ELSE 1 END LIMIT 1",
                (identifier,),
            )
            if not env:
                continue
            with self.store.transaction() as db:
                enqueue(self.store, identifier, env["id"], None, "threat_review", db=db)
                db.execute("INSERT OR REPLACE INTO runtime VALUES(?,?)", (key, slot))
                self.store.audit(
                    identifier,
                    "scheduler",
                    "security.review_scheduled",
                    env["id"],
                    {"slot": slot, "timezone": "America/Sao_Paulo"},
                    db,
                )


class ThreatIntelligence:
    def __init__(self, store, fetch=None):
        self.store = store
        self.fetch = fetch or self.fetch_json

    @staticmethod
    def fetch_json(url):
        with httpx.Client(timeout=12, trust_env=False, follow_redirects=True) as client:
            with client.stream(
                "GET", url, headers={"User-Agent": "Lumen10Guardian/0.1 security-intelligence"}
            ) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 5_000_000:
                        raise ValueError("Feed excedeu 5 MB")
        return json.loads(content)

    def collect(self, tenant):
        profiles = self.store.rows("SELECT * FROM security_profiles WHERE tenant_id=?", (tenant,))
        technologies = set()
        for profile in profiles:
            technologies.update(json.loads(profile["technologies"]))
        if not technologies:
            technologies.update(DEFAULT_TECHNOLOGIES)
        sources, findings = [], []
        try:
            try:
                kev = self.fetch(KEV_URL)
                source = KEV_URL
            except (httpx.HTTPError, ValueError, OSError):
                kev = self.fetch(KEV_MIRROR)
                source = KEV_MIRROR
            entries = kev.get("vulnerabilities", [])
            if not isinstance(entries, list):
                raise ValueError("Contrato KEV inválido")
            sources.append(
                {"source": "CISA KEV", "url": source, "status": "ok", "catalog_date": kev.get("dateReleased")}
            )
            for entry in sorted(entries, key=lambda v: v.get("dateAdded", ""), reverse=True):
                terms = (
                    str(entry.get("vendorProject", ""))
                    + " "
                    + str(entry.get("product", ""))
                    + " "
                    + str(entry.get("vulnerabilityName", ""))
                ).lower()
                if not any(tech in terms for tech in technologies):
                    continue
                cve = entry.get("cveID", "")
                if not re.fullmatch(r"CVE-\d{4}-\d{4,9}", cve):
                    continue
                findings.append(
                    {
                        "id": cve,
                        "title": str(entry.get("vulnerabilityName", cve))[:220],
                        "source": "CISA KEV",
                        "published_at": entry.get("dateAdded"),
                        "url": "https://www.cve.org/CVERecord?id=" + cve,
                        "applicability": "Potencial correspondência de tecnologia; versão e exposição precisam de confirmação",
                        "required_action": str(entry.get("requiredAction", ""))[:300],
                    }
                )
                if len(findings) >= 15:
                    break
        except (httpx.HTTPError, ValueError, OSError, TypeError) as exc:
            sources.append({"source": "CISA KEV", "url": KEV_URL, "status": "unavailable", "error": type(exc).__name__})
        if "php" in technologies:
            try:
                releases = self.fetch(PHP_URL)
                supported = releases.get("8", {}).get("supported_versions", [])
                sources.append({"source": "PHP releases", "url": PHP_URL, "status": "ok"})
                for branch in supported[:5]:
                    if not re.fullmatch(r"\d+\.\d+", branch):
                        continue
                    release = self.fetch(PHP_URL + "&version=" + branch)
                    version = release.get("version")
                    if not version:
                        candidates = [v for v in release.values() if isinstance(v, dict) and v.get("version")]
                        release = candidates[0] if candidates else {}
                        version = release.get("version")
                    if not version or not re.fullmatch(r"\d+\.\d+\.\d+", version):
                        continue
                    if "security" not in release.get("tags", []):
                        continue
                    findings.append(
                        {
                            "id": "PHP-" + version,
                            "title": "Atualização de segurança PHP " + version,
                            "source": "PHP releases",
                            "published_at": release.get("date"),
                            "url": "https://www.php.net/releases/",
                            "applicability": "Verificar branch, pacote da distribuição e backports; versão instalada não presumida",
                        }
                    )
            except (httpx.HTTPError, ValueError, OSError, TypeError) as exc:
                sources.append(
                    {"source": "PHP releases", "url": PHP_URL, "status": "unavailable", "error": type(exc).__name__}
                )
        profile_context = [
            {
                "system_id": p["system_id"],
                "technologies": json.loads(p["technologies"]),
                "versions_declared": json.loads(p["versions"]),
            }
            for p in profiles
        ]
        for finding in findings:
            finding["fingerprint"] = hashlib.sha256(encode([finding, profile_context]).encode()).hexdigest()
            finding["new"] = not bool(
                self.store.one(
                    "SELECT 1 FROM advisory_seen WHERE tenant_id=? AND fingerprint=?", (tenant, finding["fingerprint"])
                )
            )
        return {
            "observed_at": now(),
            "sources": sources,
            "findings": findings,
            "profiles": profile_context,
            "inventory_warning": "Sem inventário completo, não concluir que a aplicação está vulnerável ou segura",
            "coverage": "Fontes selecionadas; KEV não é catálogo de todas as vulnerabilidades mundiais",
        }

    def complete(self, tenant, environment, collection, diagnosis):
        identifier = uid()
        new_count = sum(bool(f["new"]) for f in collection["findings"])
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO threat_reports VALUES(?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    tenant,
                    environment,
                    now(),
                    encode(collection["sources"]),
                    encode(collection["findings"]),
                    encode(diagnosis),
                    new_count,
                ),
            )
            for finding in collection["findings"]:
                db.execute("INSERT OR IGNORE INTO advisory_seen VALUES(?,?,?)", (tenant, finding["fingerprint"], now()))
            self.store.audit(
                tenant,
                "security",
                "security.intelligence_completed",
                identifier,
                {"new_count": new_count, "sources": collection["sources"]},
                db,
            )
            if new_count:
                self.store.audit(tenant, "security", "security.advisory", identifier, {"new_count": new_count}, db)
            if any(s["status"] == "unavailable" for s in collection["sources"]):
                self.store.audit(tenant, "security", "security.feed_failed", identifier, {"partial_coverage": True}, db)
        return identifier
