import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from guardian.config import Settings
from guardian.licensing import LicenseGuard, device_fingerprint, installation_id, sign_payload


def setup_guard(tmp_path, monkeypatch):
    settings = Settings(data=tmp_path)
    key = Ed25519PrivateKey.generate()
    public = tmp_path / "public.pem"
    public.write_bytes(
        key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    monkeypatch.setattr("guardian.licensing.PUBLIC_KEY", public)
    guard = LicenseGuard(settings)
    payload = {
        "product": "lumen10-guardian",
        "license_id": "example",
        "edition": "author-development",
        "installation_id": installation_id(settings),
        "device_fingerprint": device_fingerprint(),
        "tenant_ids": ["tenant-a"],
        "capabilities": ["monitor"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }
    return guard, key, payload


def test_signature_tampering_and_machine_binding(tmp_path, monkeypatch):
    guard, key, payload = setup_guard(tmp_path, monkeypatch)
    envelope = sign_payload(key, payload)
    assert guard.verify(envelope)["license_id"] == "example"
    envelope["payload"]["capabilities"].append("ai")
    with pytest.raises(ValueError):
        guard.verify(envelope)
    payload["installation_id"] = "other-device"
    with pytest.raises(ValueError):
        guard.verify(sign_payload(key, payload))


def test_scope_expiration_and_capabilities(tmp_path, monkeypatch):
    guard, key, payload = setup_guard(tmp_path, monkeypatch)
    path = tmp_path / "license.json"
    path.write_text(json.dumps(sign_payload(key, payload)))
    assert guard.require("monitor", "tenant-a")
    with pytest.raises(ValueError):
        guard.require("ai", "tenant-a")
    with pytest.raises(ValueError):
        guard.require("monitor", "tenant-b")
    payload["expires_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    path.write_text(json.dumps(sign_payload(key, payload)))
    assert not guard.status()["valid"]


@pytest.mark.parametrize("method", ["govbr-document-manually-verified", "notarized-document-manually-verified"])
def test_commercial_license_binds_final_document(tmp_path, monkeypatch, method):
    guard, key, payload = setup_guard(tmp_path, monkeypatch)
    # Fixture de contrato de hash. Não é PDF assinado real ou validação do ITI.
    document = tmp_path / "fixture.pdf"
    document.write_bytes(b"%PDF-1.4\nSYNTHETIC CONTRACT FOR UNIT TEST ONLY")
    payload.update(
        edition="commercial",
        authorization={
            "method": method,
            "verification_reference": "SYNTHETIC-TEST-ONLY",
            "document_sha256": hashlib.sha256(document.read_bytes()).hexdigest(),
        },
    )
    envelope = sign_payload(key, payload)
    assert guard.verify(envelope, document)
    document.write_bytes(b"%PDF-1.4\nchanged")
    with pytest.raises(ValueError):
        guard.verify(envelope, document)


def test_unlicensed_install_cannot_activate_monitor_or_ai(system):
    app, client, _, env = system
    (app.state.settings.data / "license.json").unlink()
    assert client.post("/api/v1/system/monitor", json={"active": True}).status_code == 409
    assert client.post("/api/v1/environments/" + env + "/review").status_code == 409
    assert client.post("/api/v1/laboratory").status_code == 409
    assert client.get("/api/v1/overview").status_code == 200


def test_models_and_reasoning_cannot_be_downgraded(tmp_path):
    assert Settings(data=tmp_path).model == "gpt-6.1-sol"
    with pytest.raises(ValueError):
        Settings(data=tmp_path, model="gpt-5")
    with pytest.raises(ValueError):
        Settings(data=tmp_path, reasoning="medium")
