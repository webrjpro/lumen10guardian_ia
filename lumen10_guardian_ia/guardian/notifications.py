"""Notificações transacionais explícitas. Nenhum envio sem canal habilitado."""

import json
import smtplib
import ssl
import time
from email.message import EmailMessage

from guardian.connections import ProjectConnection
from guardian.licensing import LicenseGuard

LABELS = {
    "security.advisory": "Boletim de segurança com novos avisos",
    "security.feed_failed": "Fonte de inteligência de segurança indisponível",
    "incident.detected": "Incidente detectado",
    "release.scheduled": "Manutenção agendada",
    "release.started": "Início de manutenção",
    "release.RESOLVIDO": "Verificação concluída",
    "release.REVERTIDO": "Versão anterior restaurada",
    "release.FALHA_DE_IMPLANTACAO": "Falha de implantação",
    "job.failed": "Tarefa requer atenção",
}


class NotificationWorker:
    def __init__(self, store, settings, transport=None):
        self.store, self.settings = store, settings
        self.transport = transport or self.send

    @staticmethod
    def send(config, message):
        host = config.get("SMTP_HOST", "")
        port = int(config.get("SMTP_PORT", "587"))
        if not host or not config.get("SMTP_USER") or not config.get("SMTP_PASSWORD"):
            raise ValueError("SMTP incompleto nos arquivos locais")
        context = ssl.create_default_context()
        if port == 465:
            connection = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
        elif port == 587:
            connection = smtplib.SMTP(host, port, timeout=15)
            connection.ehlo()
            connection.starttls(context=context)
            connection.ehlo()
        else:
            raise ValueError("SMTP aceita somente portas TLS 465 ou STARTTLS 587")
        with connection as smtp:
            smtp.login(config["SMTP_USER"], config["SMTP_PASSWORD"])
            smtp.send_message(message)

    def tick(self):
        channels = self.store.rows("SELECT * FROM notification_settings WHERE enabled=1")
        for channel in channels:
            try:
                LicenseGuard(self.settings).require("monitor", channel["tenant_id"])
            except ValueError:
                continue
            environment = self.store.environment(channel["tenant_id"], channel["environment_id"])
            if not environment or environment["kind"] != "project":
                continue
            messages = self.store.rows(
                "SELECT * FROM notification_outbox WHERE tenant_id=? AND state IN ('pending','retry') AND available_at<=? ORDER BY created_at LIMIT 3",
                (channel["tenant_id"], time.time()),
            )
            for item in messages:
                severity = "P2"
                environment_id = None
                if item["action"] == "incident.detected":
                    incident = self.store.one(
                        "SELECT severity,environment_id FROM incidents WHERE tenant_id=? AND id=?",
                        (channel["tenant_id"], item["resource"]),
                    )
                    if incident:
                        severity, environment_id = incident["severity"], incident["environment_id"]
                elif item["action"].startswith("release."):
                    release = self.store.one(
                        "SELECT environment_id FROM changes WHERE tenant_id=? AND id=?",
                        (channel["tenant_id"], item["resource"]),
                    )
                    if release:
                        environment_id = release["environment_id"]
                elif item["action"] == "job.failed":
                    job = self.store.one(
                        "SELECT environment_id FROM jobs WHERE tenant_id=? AND id=?",
                        (channel["tenant_id"], item["resource"]),
                    )
                    if job:
                        environment_id = job["environment_id"]
                source = self.store.environment(channel["tenant_id"], environment_id) if environment_id else None
                system = (
                    self.store.one(
                        "SELECT name FROM systems WHERE tenant_id=? AND id=?",
                        (channel["tenant_id"], source["system_id"]),
                    )
                    if source and source.get("system_id")
                    else None
                )
                system_name = (
                    ((system or {}).get("name") or (source or {}).get("name") or "Workspace")
                    .replace("\r", " ")
                    .replace("\n", " ")[:100]
                )
                extra = ""
                if item["action"] in {"security.advisory", "security.feed_failed"}:
                    report = self.store.one(
                        "SELECT * FROM threat_reports WHERE tenant_id=? AND id=?",
                        (channel["tenant_id"], item["resource"]),
                    )
                    if report:
                        findings = json.loads(report["findings"])
                        diagnosis = json.loads(report["diagnosis"])
                        extra = "\nBoletim de segurança global:\n" + diagnosis["summary"] + "\n"
                        for finding in [f for f in findings if f.get("new")][:5]:
                            extra += finding["title"] + "\n" + finding["applicability"] + "\n" + finding["url"] + "\n\n"
                        extra += "Confira a versão instalada e eventuais backports. Este aviso não autoriza atualização automática de produção.\n"
                message = EmailMessage()
                message["From"] = channel["sender"]
                message["To"] = ", ".join(json.loads(channel["recipients"]))
                message["Subject"] = (
                    "[Lumen10 Guardian][" + severity + "][" + system_name + "] " + LABELS[item["action"]]
                )
                message["Message-ID"] = "<" + item["id"] + "@guardian.local>"
                message.set_content(
                    "Lumen10 Guardian AI\n\n"
                    + LABELS[item["action"]]
                    + "\nRecurso: "
                    + item["resource"]
                    + "\nRegistrado (UTC): "
                    + item["created_at"]
                    + extra
                    + "\n\nConsulte o painel autenticado para o diagnóstico, os testes e as autorizações.\nEste aviso não inclui logs de alunos, código-fonte ou credenciais.\n"
                )
                try:
                    self.transport(ProjectConnection(environment["target"]).values(), message)
                    self.store.execute(
                        "UPDATE notification_outbox SET state='sent',attempts=attempts+1,error=NULL WHERE tenant_id=? AND id=?",
                        (channel["tenant_id"], item["id"]),
                    )
                    self.store.audit(
                        channel["tenant_id"], "notifier", "notification.sent", item["id"], {"action": item["action"]}
                    )
                except Exception as exc:
                    attempts = item["attempts"] + 1
                    state = "failed" if attempts >= 3 else "retry"
                    self.store.execute(
                        "UPDATE notification_outbox SET state=?,attempts=?,available_at=?,error=? WHERE tenant_id=? AND id=?",
                        (
                            state,
                            attempts,
                            time.time() + 60 * 2**attempts,
                            type(exc).__name__,
                            channel["tenant_id"],
                            item["id"],
                        ),
                    )
