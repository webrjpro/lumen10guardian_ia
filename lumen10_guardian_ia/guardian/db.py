"""SQLite WAL, transações curtas, todos os recursos vinculados ao tenant.

O banco local não é um limite de segurança contra administradores do host.
"""

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_versions(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tenants(id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS systems(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),name TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS security_profiles(tenant_id TEXT NOT NULL,system_id TEXT NOT NULL,technologies TEXT NOT NULL,versions TEXT NOT NULL,PRIMARY KEY(tenant_id,system_id));
CREATE TABLE IF NOT EXISTS advisory_seen(tenant_id TEXT NOT NULL,fingerprint TEXT NOT NULL,first_seen TEXT NOT NULL,PRIMARY KEY(tenant_id,fingerprint));
CREATE TABLE IF NOT EXISTS threat_reports(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,environment_id TEXT NOT NULL,reviewed_at TEXT NOT NULL,sources TEXT NOT NULL,findings TEXT NOT NULL,diagnosis TEXT NOT NULL,new_count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS credentials(
 hash TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), role TEXT NOT NULL,
 environment_id TEXT, expires_at REAL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS environments(
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), name TEXT NOT NULL,
 kind TEXT NOT NULL, target TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
 auto_ai INTEGER NOT NULL DEFAULT 0, paused INTEGER NOT NULL DEFAULT 0,
 timezone TEXT NOT NULL DEFAULT 'America/Sao_Paulo', maintenance TEXT NOT NULL DEFAULT '01:00',
 config TEXT NOT NULL DEFAULT '{}', last_review REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS samples(
 id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL, environment_id TEXT NOT NULL,
 observed_at TEXT NOT NULL, healthy INTEGER NOT NULL, latency REAL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS samples_env ON samples(tenant_id, environment_id, id DESC);
CREATE TABLE IF NOT EXISTS events(
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, environment_id TEXT NOT NULL,
 observed_at TEXT NOT NULL, kind TEXT NOT NULL, summary TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS incidents(
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, environment_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL, title TEXT NOT NULL, severity TEXT NOT NULL, state TEXT NOT NULL,
 evidence TEXT NOT NULL, diagnosis TEXT, occurrences INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS incidents_tenant ON incidents(tenant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS incident_active ON incidents(tenant_id, environment_id, fingerprint)
 WHERE state NOT IN ('RESOLVIDO','ENCERRADO_SEM_CORRECAO','REVERTIDO');
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, environment_id TEXT NOT NULL,
 incident_id TEXT, kind TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
 attempts INTEGER NOT NULL DEFAULT 0, available_at REAL NOT NULL,
 lease_until REAL, owner TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS job_active ON jobs(tenant_id, environment_id, ifnull(incident_id,''), kind)
 WHERE state IN ('queued','running');
CREATE TABLE IF NOT EXISTS changes(
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, environment_id TEXT NOT NULL,
 incident_id TEXT NOT NULL, state TEXT NOT NULL, artifact TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS specialist_tasks(
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, environment_id TEXT NOT NULL, job_id TEXT NOT NULL,
 specialist TEXT NOT NULL, state TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL, finished_at TEXT);
CREATE TABLE IF NOT EXISTS audit(
 seq INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL, occurred_at TEXT NOT NULL,
 actor TEXT NOT NULL, action TEXT NOT NULL, resource TEXT NOT NULL,
 detail TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runtime(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notification_settings(
 tenant_id TEXT PRIMARY KEY, environment_id TEXT NOT NULL, enabled INTEGER NOT NULL,
 sender TEXT NOT NULL, recipients TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notification_outbox(
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, action TEXT NOT NULL, resource TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 available_at REAL NOT NULL DEFAULT 0, error TEXT, created_at TEXT NOT NULL,
 UNIQUE(tenant_id,action,resource));
"""


def now():
    return datetime.now(UTC).isoformat()


def uid():
    return str(uuid.uuid4())


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO schema_versions VALUES(1,?)", (now(),))
            db.execute("BEGIN IMMEDIATE")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(environments)")}
            if "system_id" not in columns:
                db.execute("ALTER TABLE environments ADD COLUMN system_id TEXT REFERENCES systems(id)")
            db.execute("INSERT OR IGNORE INTO schema_versions VALUES(2,?)", (now(),))
            db.commit()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def rows(self, sql, args=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def one(self, sql, args=()):
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def execute(self, sql, args=()):
        with self.connect() as db:
            return db.execute(sql, args).rowcount

    def audit(self, tenant, actor, action, resource, detail, db=None):
        if db is None:
            with self.transaction() as connection:
                return self.audit(tenant, actor, action, resource, detail, connection)
        previous = db.execute(
            "SELECT hash FROM audit WHERE tenant_id=? ORDER BY seq DESC LIMIT 1", (tenant,)
        ).fetchone()
        previous = previous[0] if previous else "0" * 64
        fields = [tenant, now(), actor, action, resource, encode(detail), previous]
        digest = hashlib.sha256(encode(fields).encode()).hexdigest()
        db.execute(
            "INSERT INTO audit(tenant_id,occurred_at,actor,action,resource,detail,previous_hash,hash) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (*fields, digest),
        )
        if action in {
            "security.advisory",
            "security.feed_failed",
            "incident.detected",
            "release.scheduled",
            "release.started",
            "release.RESOLVIDO",
            "release.REVERTIDO",
            "release.FALHA_DE_IMPLANTACAO",
            "job.failed",
        }:
            db.execute(
                "INSERT OR IGNORE INTO notification_outbox(id,tenant_id,action,resource,created_at) VALUES(?,?,?,?,?)",
                (uid(), tenant, action, resource, now()),
            )

    def verify_audit(self, tenant):
        previous = "0" * 64
        for row in self.rows("SELECT * FROM audit WHERE tenant_id=? ORDER BY seq", (tenant,)):
            fields = [
                row[k] for k in ("tenant_id", "occurred_at", "actor", "action", "resource", "detail", "previous_hash")
            ]
            if row["previous_hash"] != previous or hashlib.sha256(encode(fields).encode()).hexdigest() != row["hash"]:
                return False
            previous = row["hash"]
        return True

    def environment(self, tenant, environment):
        return self.one("SELECT * FROM environments WHERE tenant_id=? AND id=?", (tenant, environment))
