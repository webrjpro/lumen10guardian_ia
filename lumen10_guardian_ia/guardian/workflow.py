import hashlib
import re
import time

from guardian.db import encode, now, uid
from guardian.security import redact


def enqueue(store, tenant, environment, incident, kind, available=None, db=None):
    identifier = uid()
    sql = (
        "INSERT OR IGNORE INTO jobs(id,tenant_id,environment_id,incident_id,kind,available_at,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?)"
    )
    args = (identifier, tenant, environment, incident, kind, available or time.time(), now(), now())
    if db is not None:
        changed = db.execute(sql, args).rowcount
    else:
        changed = store.execute(sql, args)
    return identifier if changed else None


def record_event(store, tenant, environment, kind, summary, severity="P2", event_id=None):
    summary = redact(summary)
    normalized = re.sub(r"\b\d{4}-\d{2}-\d{2}[T ][\d:.+Z-]+", "[TIME]", summary)
    normalized = re.sub(r"^\[[^\]]*\d{2}:\d{2}:\d{2}[^\]]*\]\s*", "", normalized)
    fingerprint = hashlib.sha256((kind + normalized).encode()).hexdigest()
    with store.transaction() as db:
        event_id = event_id or uid()
        changed = db.execute(
            "INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?)", (event_id, tenant, environment, now(), kind, summary)
        ).rowcount
        if not changed:
            return None
        active = db.execute(
            "SELECT id FROM incidents WHERE tenant_id=? AND environment_id=? AND fingerprint=? "
            "AND state NOT IN ('RESOLVIDO','ENCERRADO_SEM_CORRECAO','REVERTIDO')",
            (tenant, environment, fingerprint),
        ).fetchone()
        if active:
            db.execute(
                "UPDATE incidents SET occurrences=occurrences+1,updated_at=? WHERE id=? AND tenant_id=?",
                (now(), active["id"], tenant),
            )
            return active["id"]
        incident = uid()
        db.execute(
            "INSERT INTO incidents(id,tenant_id,environment_id,fingerprint,title,severity,state,evidence,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,'DETECTADO',?,?,?)",
            (
                incident,
                tenant,
                environment,
                fingerprint,
                summary[:180],
                severity,
                encode({"kind": kind, "summary": summary}),
                now(),
                now(),
            ),
        )
        env = db.execute(
            "SELECT auto_ai FROM environments WHERE tenant_id=? AND id=?", (tenant, environment)
        ).fetchone()
        if env and env["auto_ai"]:
            enqueue(store, tenant, environment, incident, "investigate", db=db)
        store.audit(tenant, "detector", "incident.detected", incident, {"kind": kind, "severity": severity}, db)
        return incident


class Queue:
    def __init__(self, store):
        self.store = store
        self.owner = uid()

    def claim(self):
        current = time.time()
        with self.store.transaction() as db:
            # Expiração: não repetir automaticamente publicação parcialmente executada.
            db.execute(
                "UPDATE jobs SET state='failed',error='Lease expirada na implantação; reconciliar estado local' "
                "WHERE state='running' AND kind='release' AND lease_until<?",
                (current,),
            )
            db.execute(
                "UPDATE jobs SET state='queued',owner=NULL,available_at=? "
                "WHERE state='running' AND kind!='release' AND lease_until<? AND attempts<3",
                (current, current),
            )
            db.execute(
                "UPDATE jobs SET state='failed',error='Limite de tentativas após interrupção' "
                "WHERE state='running' AND lease_until<? AND attempts>=3",
                (current,),
            )
            row = db.execute(
                "SELECT * FROM jobs WHERE state='queued' AND available_at<=? ORDER BY available_at LIMIT 1", (current,)
            ).fetchone()
            if row is None:
                return None
            db.execute(
                "UPDATE jobs SET state='running',attempts=attempts+1,owner=?,lease_until=?,updated_at=? WHERE id=?",
                (self.owner, current + 1800, now(), row["id"]),
            )
            result = dict(row)
            result["attempts"] += 1
            return result

    def finish(self, job, error=None):
        state = (
            "done" if error is None else ("queued" if job["attempts"] < 3 and job["kind"] != "release" else "failed")
        )
        self.store.execute(
            "UPDATE jobs SET state=?,error=?,available_at=?,lease_until=NULL,owner=NULL,updated_at=? "
            "WHERE id=? AND owner=?",
            (
                state,
                redact(error) if error else None,
                time.time() + 60 * 2 ** job["attempts"],
                now(),
                job["id"],
                self.owner,
            ),
        )
        self.store.audit(
            job["tenant_id"],
            "worker",
            "job." + state,
            job["id"],
            {"kind": job["kind"], "error": redact(error) if error else None},
        )


def set_incident_state(store, tenant, incident, state, reason):
    with store.transaction() as db:
        db.execute(
            "UPDATE incidents SET state=?,updated_at=? WHERE tenant_id=? AND id=?", (state, now(), tenant, incident)
        )
        store.audit(tenant, "workflow", "incident." + state, incident, {"reason": reason}, db)
