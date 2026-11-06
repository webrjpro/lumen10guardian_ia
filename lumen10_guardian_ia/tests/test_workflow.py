import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from guardian.db import Store
from guardian.engine import Engine
from guardian.laboratory import BUG, STABLE, Laboratory
from guardian.monitor import Monitor
from guardian.workflow import Queue, enqueue, record_event


class FakeProvider:
    """Somente testes de contrato; não representa validação do Codex real."""

    def __init__(self):
        self.calls = []

    def diagnose(self, context):
        self.calls.append(context)
        return {
            "summary": "Nullable greeting",
            "cause": "None não possui strip",
            "confidence": 0.9,
            "specialist": "qa",
            "risk": "low",
            "changes": [{"path": "app.py", "content": STABLE}],
            "test_plan": ["Regressão para None e espaços"],
        }


def test_git_regression_release_and_rollback(system):
    app, _, tenant, _ = system
    lab = app.state.engine.lab
    fixture = lab.create(tenant)
    env = app.state.store.environment(tenant, fixture["environment_id"])
    proposal = FakeProvider().diagnose({})
    change = lab.prepare(tenant, env, fixture["incident_id"], proposal, "test-run")
    row = app.state.store.one("SELECT * FROM changes WHERE tenant_id=? AND id=?", (tenant, change))
    assert row["state"] == "TESTES_APROVADOS"
    artifact = json.loads(row["artifact"])
    assert "Ran 3 tests" in artifact["test_output"] and artifact["tests_passed"]
    assert lab.deploy(tenant, change) == "RESOLVIDO"
    assert (lab.root(env) / "live/app.py").read_text(encoding="utf8").strip() == STABLE.strip()
    with pytest.raises(ValueError):
        lab.deploy(tenant, change)
    assert lab.rollback(tenant, change) == "REVERTIDO"
    assert (lab.root(env) / "live/app.py").read_text(encoding="utf8") == BUG


def test_failed_regression_blocks_deployment(system):
    app, _, tenant, _ = system
    lab = app.state.engine.lab
    fixture = lab.create(tenant)
    env = app.state.store.environment(tenant, fixture["environment_id"])
    proposal = FakeProvider().diagnose({})
    proposal["changes"][0]["content"] = 'def greeting(name):\n    return "Olá, errado"\n'
    change = lab.prepare(tenant, env, fixture["incident_id"], proposal, "failed-test")
    assert app.state.store.one("SELECT state FROM changes WHERE id=?", (change,))["state"] == "TESTES_REPROVADOS"
    with pytest.raises(ValueError):
        lab.deploy(tenant, change)


def test_artifact_tampering_and_kill_switch(system):
    app, _, tenant, _ = system
    lab = app.state.engine.lab
    fixture = lab.create(tenant)
    env = app.state.store.environment(tenant, fixture["environment_id"])
    change = lab.prepare(tenant, env, fixture["incident_id"], FakeProvider().diagnose({}), "tamper-test")
    archive = lab.root(env) / "artifacts" / (change + ".zip")
    payload = archive.read_bytes()
    archive.write_bytes(payload + b"corrupted")
    with pytest.raises(ValueError, match="Integridade"):
        lab.deploy(tenant, change)
    archive.write_bytes(payload)
    app.state.store.execute("UPDATE environments SET paused=1 WHERE id=?", (env["id"],))
    with pytest.raises(ValueError, match="suspensas"):
        lab.deploy(tenant, change)


def test_failed_smoke_restores_backup(system, monkeypatch):
    app, _, tenant, _ = system
    lab = app.state.engine.lab
    fixture = lab.create(tenant)
    env = app.state.store.environment(tenant, fixture["environment_id"])
    change = lab.prepare(tenant, env, fixture["incident_id"], FakeProvider().diagnose({}), "smoke-test")
    results = iter([False, True])
    monkeypatch.setattr(lab, "_smoke", lambda path: next(results))
    assert lab.deploy(tenant, change) == "REVERTIDO"
    assert (lab.root(env) / "live/app.py").read_text(encoding="utf8") == BUG


@pytest.mark.parametrize(
    "source",
    [
        'import os\ndef greeting(name): return os.getenv("HOME")',
        'def greeting(name): return __import__("os").system(name)',
        "def greeting(name): return name.__class__",
        "def greeting(name):\n    while True: pass",
        'def greeting(name): return f"{name:10000000000}"',
        'def greeting(name): return "{0.__globals__}".format(greeting)',
        "def greeting(name):\n    str = greeting\n    return str(name+name)",
        "def greeting(name):\n    def str(name): return str(name+name)\n    return str(name)",
        "def greeting(name):\n    value = name\n" + "    value = value+value\n" * 20 + "    return value\n",
    ],
)
def test_fixture_does_not_become_generic_shell(source):
    with pytest.raises(ValueError):
        Laboratory._validate_fixture_code(source)


def test_manager_creates_a_second_specialist_session_and_durable_task(system):
    app, _, tenant, _ = system
    store = app.state.store
    fixture = app.state.engine.lab.create(tenant)
    provider = FakeProvider()
    engine = Engine(store, app.state.settings, provider)
    enqueue(store, tenant, fixture["environment_id"], fixture["incident_id"], "investigate")
    assert engine.run_once()
    assert len(provider.calls) == 2 and provider.calls[1]["assignment"] == "qa"
    tasks = store.rows("SELECT * FROM specialist_tasks WHERE tenant_id=?", (tenant,))
    assert len(tasks) == 1 and tasks[0]["state"] == "done"
    incident = store.one("SELECT * FROM incidents WHERE tenant_id=? AND id=?", (tenant, fixture["incident_id"]))
    assert incident["state"] == "PLANO_PREPARADO"
    assert json.loads(incident["diagnosis"])["specialist"] == "qa"


def test_lease_recovery_and_exclusive_claim(system):
    app, _, tenant, env = system
    store = app.state.store
    enqueue(store, tenant, env, None, "security_review")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: Queue(store).claim(), range(2)))
    assert sum(r is not None for r in results) == 1
    store.execute("UPDATE jobs SET lease_until=? WHERE tenant_id=?", (time.time() - 1, tenant))
    recovered = Queue(Store(store.path)).claim()
    assert recovered is not None and recovered["attempts"] == 2


def test_deduplication_and_recurrence(system):
    app, _, tenant, env = system
    store = app.state.store
    first = record_event(store, tenant, env, "error", "Same")
    second = record_event(store, tenant, env, "error", "Same")
    assert first == second
    assert store.one("SELECT occurrences FROM incidents WHERE id=?", (first,))["occurrences"] == 2
    store.execute("UPDATE incidents SET state='RESOLVIDO' WHERE id=?", (first,))
    assert record_event(store, tenant, env, "error", "Same") != first


def test_monitor_activation_is_persistent_and_tenant_scoped(system):
    app, client, tenant, env = system
    monitor = Monitor(app.state.store)
    monitor.tick()
    assert not app.state.store.rows("SELECT * FROM samples")
    assert client.post("/api/v1/system/monitor", json={"active": True}).status_code == 200
    monitor.tick()
    assert len(app.state.store.rows("SELECT * FROM samples WHERE tenant_id=?", (tenant,))) == 1
    client.post("/api/v1/system/monitor", json={"active": False})
    monitor.tick()
    assert len(app.state.store.rows("SELECT * FROM samples")) == 1


def test_powershell_endpoint_has_no_free_form_command(system):
    _, client, _, _ = system
    response = client.post("/api/v1/powershell/snapshot")
    assert response.status_code == 200 and response.json()["exit_code"] == 0
    assert "powershell" in response.json()["output"]
    assert client.post("/api/v1/execute", json={"command": "whoami"}).status_code == 404
