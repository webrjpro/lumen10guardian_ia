from guardian.db import uid
from guardian.notifications import NotificationWorker
from guardian.workflow import record_event


def test_source_key_scoped_read_revocation_and_secret_exclusion(system, tmp_path):
    app, client, tenant, env = system
    project = tmp_path / "application"
    project.mkdir()
    (project / "app.py").write_text('def hello(): return "hello"\n')
    (project / ".env").write_text("PASSWORD=not-for-source-api")
    (project / "credenciais.md").write_text("Senha: not-for-source-api")
    (project / "uploads").mkdir()
    (project / "uploads/private.php").write_text("student-private-upload")
    environment = client.post(
        "/api/v1/environments", json={"name": "App", "kind": "project", "target": str(project)}
    ).json()["id"]
    key = client.post(f"/api/v1/environments/{environment}/source-key").json()
    owner = client.headers["Authorization"]
    client.headers["Authorization"] = "Bearer " + key["token"]
    manifest = client.get(f"/api/v1/projects/{environment}/source/manifest").json()
    assert [f["path"] for f in manifest["files"]] == ["app.py"]
    result = client.get(f"/api/v1/projects/{environment}/source/file", params={"path": "app.py"})
    assert result.status_code == 200 and "def hello" in result.json()["content"]
    for path in [".env", "credenciais.md", "../app.py", "C:/test.py", "uploads/private.php"]:
        assert client.get(f"/api/v1/projects/{environment}/source/file", params={"path": path}).status_code == 409
    assert client.get(f"/api/v1/projects/{env}/source/manifest").status_code == 403
    assert client.get("/api/v1/overview").status_code == 403
    client.headers["Authorization"] = owner
    client.delete("/api/v1/source-keys/" + key["credential_id"])
    client.headers["Authorization"] = "Bearer " + key["token"]
    assert client.get(f"/api/v1/projects/{environment}/source/manifest").status_code == 401


def test_email_outbox_is_disabled_until_configured_and_deduplicates(system, tmp_path):
    app, client, tenant, env = system
    store = app.state.store
    sent = []
    worker = NotificationWorker(store, app.state.settings, lambda config, message: sent.append(message))
    incident = record_event(store, tenant, env, "error", "Example error")
    record_event(store, tenant, env, "error", "Example error")
    worker.tick()
    assert not sent
    project = tmp_path / "smtp-project"
    project.mkdir()
    (project / "credenciais.md").write_text(
        "Servidor SMTP: smtp.example.invalid\nUsuário SMTP: smtp-user\nChave/Senha SMTP: fake-secret-for-test\n",
        encoding="utf-8",
    )
    environment = client.post(
        "/api/v1/environments", json={"name": "SMTP", "kind": "project", "target": str(project)}
    ).json()["id"]
    response = client.put(
        "/api/v1/notifications/settings",
        json={
            "environment_id": environment,
            "enabled": True,
            "sender": "sender@example.invalid",
            "recipients": ["owner@example.invalid"],
        },
    )
    assert response.status_code == 200
    worker.tick()
    assert len(sent) == 1 and "fake-secret-for-test" not in sent[0].as_string()
    worker.tick()
    assert len(sent) == 1
    assert store.one("SELECT state FROM notification_outbox WHERE resource=?", (incident,))["state"] == "sent"


def test_email_retry_limit_and_header_injection(system, tmp_path):
    app, client, tenant, env = system
    project = tmp_path / "mail"
    project.mkdir()
    (project / ".env").write_text("SMTP_HOST=smtp.example.invalid\nSMTP_USER=user\nSMTP_PASSWORD=fake-secret")
    environment = client.post(
        "/api/v1/environments", json={"name": "SMTP", "kind": "project", "target": str(project)}
    ).json()["id"]
    body = {
        "environment_id": environment,
        "enabled": True,
        "sender": "sender@example.invalid",
        "recipients": ["owner@example.invalid"],
    }
    assert client.put("/api/v1/notifications/settings", json=body).status_code == 200
    body["sender"] = "sender@example.invalid\nBcc: victim@example.invalid"
    assert client.put("/api/v1/notifications/settings", json=body).status_code == 422
    record_event(app.state.store, tenant, env, "error", "Example")

    def fail(config, message):
        raise OSError("fake-secret-must-not-leak")

    worker = NotificationWorker(app.state.store, app.state.settings, fail)
    for _ in range(3):
        app.state.store.execute("UPDATE notification_outbox SET available_at=0")
        worker.tick()
    row = app.state.store.one("SELECT * FROM notification_outbox")
    assert row["attempts"] == 3 and row["state"] == "failed" and row["error"] == "OSError"


def test_remote_source_token_is_protected_at_rest(system):
    app, client, tenant, env = system
    token = "test-private-source-token-" + uid()
    response = client.post(
        "/api/v1/source-connections",
        json={"name": "Remote", "base_url": "https://source.example.invalid", "environment_id": env, "token": token},
    )
    assert response.status_code == 201
    identifier = response.json()["environment_id"]
    stored = (app.state.settings.data / "source-keys" / (identifier + ".key")).read_bytes()
    assert token.encode() not in stored
    assert token not in client.get("/api/v1/overview").text


def test_heartbeat_idempotency_and_real_metrics_contract(system):
    app, client, tenant, env = system
    remote = client.post(
        "/api/v1/environments", json={"name": "Remote host", "kind": "agent", "target": "test-host"}
    ).json()["id"]
    key = client.post(f"/api/v1/environments/{remote}/agents").json()["token"]
    client.headers["Authorization"] = "Bearer " + key
    body = {
        "event_id": "heartbeat-1",
        "environment_id": remote,
        "cpu_percent": 12,
        "memory_percent": 40,
        "disk_percent": 20,
    }
    assert client.post("/api/v1/telemetry/heartbeat", json=body).status_code == 202
    assert client.post("/api/v1/telemetry/heartbeat", json=body).status_code == 202
    assert app.state.store.one("SELECT count(*) AS n FROM samples WHERE environment_id=?", (remote,))["n"] == 1
    body["memory_percent"] = 120
    assert client.post("/api/v1/telemetry/heartbeat", json=body).status_code == 422
