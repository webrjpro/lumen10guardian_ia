import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from guardian.api import create_app
from guardian.config import Settings
from guardian.security import read_protected


@pytest.fixture
def system(tmp_path, monkeypatch):
    settings = Settings(data=tmp_path, workers=False)
    from guardian.licensing import device_fingerprint, installation_id, sign_payload

    key = Ed25519PrivateKey.generate()
    public = tmp_path / "test-public.pem"
    public.write_bytes(
        key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    monkeypatch.setattr("guardian.licensing.PUBLIC_KEY", public)
    payload = {
        "product": "lumen10-guardian",
        "license_id": "test-license",
        "edition": "author-development",
        "installation_id": installation_id(settings),
        "device_fingerprint": device_fingerprint(),
        "tenant_ids": ["*"],
        "capabilities": ["monitor", "ai", "lab", "ssh_read"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }
    (tmp_path / "license.json").write_text(json.dumps(sign_payload(key, payload)), encoding="utf-8")
    app = create_app(settings)
    client = TestClient(app)
    token = read_protected(tmp_path / "owner.key")
    client.headers["Authorization"] = "Bearer " + token
    tenant = app.state.store.one("SELECT id FROM tenants")["id"]
    env = app.state.store.one("SELECT id FROM environments")["id"]
    return app, client, tenant, env
