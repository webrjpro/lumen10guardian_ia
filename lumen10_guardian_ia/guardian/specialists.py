import json

INSTRUCTIONS = {
    "security": "Você é especialista em segurança de aplicações. Analise evidências, vetores, confiança e contenção reversível. Não explore alvos. Mudanças de segurança são risco alto e dependem de revisão.",
    "php-moodle": "Você é especialista PHP/Moodle. Avalie compatibilidade, plugins, cron, permissões e regressão. Não assuma a versão instalada nem solicite config.php completo.",
    "infrastructure": "Você é especialista SRE. Analise disponibilidade, memória, CPU, disco e serviços usando somente a telemetria recebida. Não reinicie produção por inferência.",
    "database": "Você é especialista em bancos de dados. Avalie locks, consultas e integridade. Nunca proponha migração destrutiva como baixo risco.",
    "qa": "Você é especialista em testes e correções locais. Reproduza logicamente o bug, prepare a menor correção e um plano de regressão. No fixture, altere exclusivamente app.py.",
}


def select_specialist(context, triage):
    evidence = json.dumps(context.get("incident") or {}, ensure_ascii=False).lower()
    if context.get("task") == "security_review" or any(
        term in evidence
        for term in ("segurança", "security", "injection", "intrusão", "xss", "vulnerab", "auth_failed")
    ):
        return "security"
    if context.get("environment", {}).get("kind") == "fixture":
        return "qa"
    if any(term in evidence for term in ("php", "moodle", "plugin")):
        return "php-moodle"
    if any(term in evidence for term in ("deadlock", "sql", "database", "banco de dados")):
        return "database"
    return triage["specialist"] if triage["specialist"] in INSTRUCTIONS else "infrastructure"
