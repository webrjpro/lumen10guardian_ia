from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


def next_window(tz, maintenance, after=None):
    local = (after or datetime.now(UTC)).astimezone(ZoneInfo(tz))
    hour, minute = map(int, maintenance.split(":"))
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC).isoformat()


def authorize_release(environment, artifact):
    """Apenas releases do fixture local: nenhum adaptador de produção implícito."""
    if environment["paused"]:
        return False, "Mudanças suspensas pelo botão de emergência"
    if environment["kind"] != "fixture":
        return False, "Executor de produção não habilitado; faltam onboarding e validação de infraestrutura"
    if artifact.get("risk") != "low":
        return False, "Risco elevado: revisão humana necessária"
    if not artifact.get("tests_passed") or not artifact.get("commit") or not artifact.get("sha256"):
        return False, "Sem evidência de testes e versão imutável"
    if not artifact.get("backup_verified"):
        return False, "Backup e recuperação não verificados"
    return True, "Release elegível somente no laboratório local"
