"""Aceite opt-in: consome duas análises da conta ChatGPT; altera só fixture local.

Não usa mock. A falha do provedor é registrada como falha, nunca como sucesso.
"""

import json
import shutil
import tempfile
from pathlib import Path

from guardian.ai import provider_status
from guardian.config import Settings
from guardian.db import Store, now
from guardian.engine import Engine
from guardian.security import bootstrap
from guardian.workflow import enqueue


def main():
    base = Settings.load()
    provider = provider_status()
    if not provider.get("authenticated"):
        raise SystemExit("Codex não autenticado com ChatGPT")
    folder = Path(tempfile.mkdtemp(prefix="acceptance-", dir=base.data))
    settings = Settings(data=folder, workers=False)
    from guardian.licensing import LicenseGuard

    if LicenseGuard(base).require("lab")["edition"] != "author-development":
        raise SystemExit("Este aceite isolado exige a licença de desenvolvimento do autor")
    # Harness efêmero na mesma máquina/perfil do autor; não distribui licenças ou login.
    shutil.copyfile(base.data / "license.json", folder / "license.json")
    shutil.copyfile(base.data / "installation.id", folder / "installation.id")
    store = Store(settings.database)
    tenant = bootstrap(store, settings)
    engine = Engine(store, settings)
    fixture = engine.lab.create(tenant)
    print("Fixture criado. Executando gerente e especialista reais pelo Codex...", flush=True)
    enqueue(store, tenant, fixture["environment_id"], fixture["incident_id"], "investigate")
    engine.run_once()
    job = store.one("SELECT * FROM jobs")
    if job["state"] != "done":
        raise SystemExit("Aceite Codex falhou: " + str(job["error"]))
    incident = store.one("SELECT * FROM incidents WHERE id=?", (fixture["incident_id"],))
    diagnosis = json.loads(incident["diagnosis"])
    print("Gerente e especialista concluíram. Criando branch e executando regressão...", flush=True)
    env = store.environment(tenant, fixture["environment_id"])
    change = engine.lab.prepare(tenant, env, fixture["incident_id"], diagnosis, "real-codex")
    row = store.one("SELECT * FROM changes WHERE id=?", (change,))
    if row["state"] != "TESTES_APROVADOS":
        raise SystemExit("Testes de regressão reprovaram a correção real")
    print("Testes aprovados. Validando publicação local e restauração...", flush=True)
    deployed = engine.lab.deploy(tenant, change)
    restored = engine.lab.rollback(tenant, change)
    artifact = json.loads(row["artifact"])
    report = {
        "requested_model": settings.model,
        "reasoning": settings.reasoning,
        "executed_at": now(),
        "provider": "Codex CLI / ChatGPT login / duas sessões reais",
        "synthetic_application": True,
        "production_touched": False,
        "specialist": "qa",
        "tests_passed": artifact["tests_passed"],
        "tests_output": artifact["test_output"],
        "commit": artifact["commit"],
        "artifact_sha256": artifact["sha256"],
        "deployment_state": deployed,
        "rollback_state": restored,
        "audit_valid": store.verify_audit(tenant),
        "evidence_directory": str(folder),
    }
    target = Path(__file__).resolve().parents[1] / "docs" / "aceite-codex-real.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if deployed != "RESOLVIDO" or restored != "REVERTIDO":
        raise SystemExit("Publicação ou recuperação falhou")


if __name__ == "__main__":
    main()
