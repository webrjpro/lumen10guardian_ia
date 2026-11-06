import json
import os
import sys

from guardian.processes import run_quiet


def test_embedding_project_registers_a_system_idempotently(system, tmp_path):
    app, _, tenant, _ = system
    project = tmp_path / "customer-app"
    project.mkdir()
    environment = {**os.environ, "GUARDIAN_DATA": str(app.state.settings.data)}
    command = [sys.executable, "-m", "guardian", "connect", "--path", str(project)]
    first = run_quiet(command, capture_output=True, text=True, encoding="utf-8", env=environment, timeout=20)
    assert first.returncode == 0
    result = json.loads(first.stdout)
    assert result["system_id"]
    second = run_quiet(command, capture_output=True, text=True, encoding="utf-8", env=environment, timeout=20)
    assert json.loads(second.stdout) == result
    assert (
        app.state.store.one("SELECT count(*) AS n FROM systems WHERE tenant_id=? AND name=?", (tenant, "customer-app"))[
            "n"
        ]
        == 1
    )
