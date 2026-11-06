import json
import logging
import threading

from guardian.ai import CodexProvider
from guardian.db import encode, now, uid
from guardian.laboratory import Laboratory
from guardian.licensing import LicenseGuard
from guardian.monitor import Monitor
from guardian.notifications import NotificationWorker
from guardian.specialists import select_specialist
from guardian.workflow import Queue, set_incident_state

logger = logging.getLogger("guardian")


class Engine:
    def __init__(self, store, settings, provider=None):
        self.store, self.settings = store, settings
        self.provider = provider or CodexProvider(settings)
        self.queue = Queue(store)
        self.lab = Laboratory(store, settings)
        self.stop = threading.Event()
        self.monitor_wake = threading.Event()
        self.threads = []

    def start(self):
        for target in (self.monitor_loop, self.worker_loop, self.notification_loop):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self.threads.append(thread)

    def close(self):
        self.stop.set()
        self.monitor_wake.set()
        for thread in self.threads:
            thread.join(timeout=2)

    def monitor_loop(self):
        monitor = Monitor(self.store, LicenseGuard(self.settings))
        while not self.stop.is_set():
            try:
                monitor.tick()
                from guardian.threat_intelligence import ThreatScheduler

                ThreatScheduler(self.store).tick()
            except Exception:
                logger.exception("Falha no ciclo do monitor")
            self.monitor_wake.wait(self.settings.interval)
            self.monitor_wake.clear()

    def worker_loop(self):
        while not self.stop.is_set():
            try:
                processed = self.run_once()
                self.store.execute("INSERT OR REPLACE INTO runtime VALUES('worker_heartbeat',?)", (now(),))
            except Exception:
                logger.exception("Falha no ciclo do worker")
                processed = False
            if not processed:
                self.stop.wait(2)

    def notification_loop(self):
        worker = NotificationWorker(self.store, self.settings)
        while not self.stop.is_set():
            try:
                worker.tick()
            except Exception:
                logger.exception("Falha no ciclo de notificações")
            self.stop.wait(15)

    def run_once(self):
        job = self.queue.claim()
        if not job:
            return False
        try:
            self.process(job)
            self.queue.finish(job)
        except Exception as exc:
            if job["incident_id"]:
                set_incident_state(
                    self.store, job["tenant_id"], job["incident_id"], "AGUARDANDO_HUMANO", type(exc).__name__
                )
            self.queue.finish(job, str(exc))
        return True

    def process(self, job):
        tenant, incident = job["tenant_id"], job["incident_id"]
        LicenseGuard(self.settings).require("lab" if job["kind"] in {"repair", "release"} else "ai", tenant)
        env = self.store.environment(tenant, job["environment_id"])
        if not env or not env["enabled"]:
            raise ValueError("Ambiente desativado")
        if job["kind"] == "release":
            if env["paused"]:
                raise ValueError("Publicação suspensa")
            change = self.store.one(
                "SELECT id FROM changes WHERE tenant_id=? AND environment_id=? AND incident_id=? AND state='AGENDADO'",
                (tenant, env["id"], incident),
            )
            if not change:
                raise ValueError("Release agendada não encontrada")
            self.lab.deploy(tenant, change["id"])
            return
        record = (
            self.store.one("SELECT * FROM incidents WHERE tenant_id=? AND id=?", (tenant, incident))
            if incident
            else None
        )
        if job["kind"] == "repair":
            if env["paused"]:
                raise ValueError("Mudanças suspensas")
            if not record or not record["diagnosis"]:
                raise ValueError("Diagnóstico ausente; investigue primeiro")
            self.lab.prepare(tenant, env, incident, json.loads(record["diagnosis"]), job["id"])
            return
        # Reserva de orçamento transacional: retries também consomem quota.
        with self.store.transaction() as db:
            used = db.execute(
                "SELECT count(*) FROM audit WHERE tenant_id=? AND action='ai.started' AND occurred_at>=?",
                (tenant, now()[:10]),
            ).fetchone()[0]
            if used >= self.settings.ai_daily_limit:
                raise ValueError("Limite diário local de análises de IA atingido")
            self.store.audit(tenant, "manager", "ai.started", job["id"], {"provider": "codex-chatgpt"}, db)
        if incident:
            set_incident_state(self.store, tenant, incident, "EM_INVESTIGACAO", "Codex via login ChatGPT")
        samples = self.store.rows(
            "SELECT observed_at,healthy,latency,data FROM samples WHERE tenant_id=? AND environment_id=? ORDER BY id DESC LIMIT 10",
            (tenant, env["id"]),
        )
        context = {
            "task": job["kind"],
            "environment": {"name": env["name"], "kind": env["kind"]},
            "incident": json.loads(record["evidence"]) if record else None,
            "telemetry": samples,
            **self.lab.context(env),
        }
        if env["kind"] == "project" and job["kind"] != "threat_review":
            from guardian.connections import ProjectConnection

            connection = ProjectConnection(env["target"])
            context["connection"] = connection.inventory()
            context["repository"] = connection.source_context()
            if context["connection"]["ssh_ready"]:
                context["remote_read_only_snapshot"] = connection.snapshot()
        elif env["kind"] == "remote-source" and job["kind"] != "threat_review":
            from guardian.remote_source import RemoteSourceClient

            context["repository"] = RemoteSourceClient(env, self.settings).context()
        if env.get("system_id") and job["kind"] != "threat_review":
            context["system"] = self.store.one(
                "SELECT name FROM systems WHERE tenant_id=? AND id=?", (tenant, env["system_id"])
            )
            related = self.store.rows(
                "SELECT * FROM environments WHERE tenant_id=? AND system_id=? AND id!=? AND kind IN ('project','remote-source') LIMIT 2",
                (tenant, env["system_id"], env["id"]),
            )
            context["related_projects"] = []
            for project in related:
                if project["kind"] == "project":
                    from guardian.connections import ProjectConnection

                    connection = ProjectConnection(project["target"])
                    context["related_projects"].append(
                        {
                            "name": project["name"],
                            "connection": connection.inventory(),
                            "repository": connection.source_context(),
                        }
                    )
                else:
                    from guardian.remote_source import RemoteSourceClient

                    context["related_projects"].append(
                        {"name": project["name"], "repository": RemoteSourceClient(project, self.settings).context()}
                    )
        intelligence = None
        if job["kind"] == "threat_review":
            from guardian.threat_intelligence import ThreatIntelligence

            intelligence = ThreatIntelligence(self.store).collect(tenant)
            context = {
                "task": "security_review",
                "global_security_intelligence": intelligence,
                "instructions": "Avalie correspondências potenciais, versões desconhecidas, necessidade de atualização e fontes indisponíveis. Não conclua invasão ou segurança completa. Não proponha publicação automática.",
            }
        response = self.provider.diagnose(context)
        specialist = select_specialist(context, response)
        task_id = uid()
        with self.store.transaction() as db:
            used = db.execute(
                "SELECT count(*) FROM audit WHERE tenant_id=? AND action='ai.started' AND occurred_at>=?",
                (tenant, now()[:10]),
            ).fetchone()[0]
            if used >= self.settings.ai_daily_limit:
                raise ValueError("Limite diário antes de criar especialista")
            self.store.audit(
                tenant, "manager", "ai.started", task_id, {"provider": "codex-chatgpt", "specialist": specialist}, db
            )
            db.execute(
                "INSERT INTO specialist_tasks VALUES(?,?,?,?,?,'running',NULL,?,NULL)",
                (task_id, tenant, env["id"], job["id"], specialist, now()),
            )
            self.store.audit(
                tenant, "manager", "specialist.created", task_id, {"specialist": specialist, "job": job["id"]}, db
            )
        try:
            response = self.provider.diagnose({**context, "assignment": specialist, "manager_triage": response})
            response["specialist"] = specialist
            if specialist in {"security", "database"}:
                response["risk"] = "high"
            self.store.execute(
                "UPDATE specialist_tasks SET state='done',result=?,finished_at=? WHERE tenant_id=? AND id=?",
                (encode(response), now(), tenant, task_id),
            )
            self.store.audit(tenant, specialist, "specialist.completed", task_id, {"risk": response["risk"]})
        except Exception:
            self.store.execute(
                "UPDATE specialist_tasks SET state='failed',finished_at=? WHERE tenant_id=? AND id=?",
                (now(), tenant, task_id),
            )
            raise
        if incident:
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE incidents SET diagnosis=?,state='PLANO_PREPARADO',updated_at=? WHERE tenant_id=? AND id=?",
                    (encode(response), now(), tenant, incident),
                )
                self.store.audit(
                    tenant,
                    "manager",
                    "ai.completed",
                    job["id"],
                    {
                        "specialist": response["specialist"],
                        "risk": response["risk"],
                        "confidence": response["confidence"],
                    },
                    db,
                )
        else:
            # Relatório da revisão real disponível no painel de auditoria.
            self.store.audit(tenant, "security", "security.review", env["id"], response)
            if intelligence is not None:
                from guardian.threat_intelligence import ThreatIntelligence

                ThreatIntelligence(self.store).complete(tenant, env["id"], intelligence, response)
