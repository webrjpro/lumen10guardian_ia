"""Licenças assinadas Ed25519. Não emite certificados notariais ou ICP-Brasil.

A chave pública acompanha o produto; a privada fica apenas com o emissor.
Uma autorização comercial representa a conferência documental pelo emissor.
"""

import base64
import getpass
import hashlib
import json
import platform
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from guardian.db import encode

AUTHOR = "Carlos Antonio de Oliveira Piquet"
PUBLIC_KEY = Path(__file__).with_name("issuer-public.pem")
CAPABILITIES = {"monitor", "ai", "lab", "ssh_read"}


def device_fingerprint():
    machine = platform.node()
    if __import__("os").name == "nt":
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            machine = str(winreg.QueryValueEx(key, "MachineGuid")[0])
    elif Path("/etc/machine-id").is_file():
        machine = Path("/etc/machine-id").read_text().strip()
    return hashlib.sha256((machine + "|" + getpass.getuser()).encode()).hexdigest()


def installation_id(settings):
    path = settings.data / "installation.id"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        try:
            with path.open("x", encoding="utf-8") as target:
                target.write(str(uuid.uuid4()))
        except FileExistsError:
            pass
    return path.read_text(encoding="utf-8").strip()


def sign_payload(private_key, payload):
    return {"payload": payload, "signature": base64.b64encode(private_key.sign(encode(payload).encode())).decode()}


class LicenseGuard:
    def __init__(self, settings):
        self.settings = settings
        self.installation = installation_id(settings)

    def verify(self, envelope, document=None):
        try:
            key = serialization.load_pem_public_key(PUBLIC_KEY.read_bytes())
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError("Chave do emissor incompatível")
            payload = envelope["payload"]
            key.verify(base64.b64decode(envelope["signature"], validate=True), encode(payload).encode())
            if payload["product"] != "lumen10-guardian" or payload["installation_id"] != self.installation:
                raise ValueError("Licença pertence a outra instalação")
            if payload["device_fingerprint"] != device_fingerprint():
                raise ValueError("Licença pertence a outra máquina ou usuário")
            if datetime.fromisoformat(payload["expires_at"]) <= datetime.now(timezone.utc):
                raise ValueError("Licença expirada")
            if payload["edition"] not in {"author-development", "commercial"}:
                raise ValueError("Edição inválida")
            if not set(payload["capabilities"]).issubset(CAPABILITIES):
                raise ValueError("Capacidade não suportada")
            if payload["edition"] == "commercial":
                auth = payload["authorization"]
                if (
                    auth["method"] not in {"notarized-document-manually-verified", "govbr-document-manually-verified"}
                    or not auth["verification_reference"]
                ):
                    raise ValueError("Documento assinado não conferido pelo emissor")
                expected = auth["document_sha256"]
                stored = self.settings.data / "license-documents" / (expected + ".pdf")
                document_path = document or stored
                if document_path.stat().st_size > 20_000_000:
                    raise ValueError("Documento excede limite de 20 MB")
                actual = document_path.read_bytes()
                if not actual.startswith(b"%PDF-") or hashlib.sha256(actual).hexdigest() != expected:
                    raise ValueError("Documento de autorização ausente ou diferente do autorizado")
            return payload
        except (OSError, KeyError, TypeError, InvalidSignature, ValueError) as exc:
            if isinstance(exc, ValueError) and str(exc):
                raise ValueError("Licença inválida: " + str(exc)) from None
            raise ValueError("Licença ausente, assinatura inválida ou documento incompleto") from None

    def load(self):
        try:
            path = self.settings.data / "license.json"
            if path.stat().st_size > 32768:
                raise ValueError("Licença excede limite")
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise ValueError("Instalação sem licença assinada do desenvolvedor") from None
        return self.verify(envelope)

    def require(self, capability, tenant=None):
        license = self.load()
        if capability not in license["capabilities"]:
            raise ValueError("Operação não autorizada pela licença")
        if tenant and "*" not in license["tenant_ids"] and tenant not in license["tenant_ids"]:
            raise ValueError("Empresa não coberta pela licença")
        return license

    def status(self):
        try:
            license = self.load()
            return {
                "valid": True,
                "edition": license["edition"],
                "expires_at": license["expires_at"],
                "license_id": license["license_id"],
                "author": AUTHOR,
                "notarial_authorization": license.get("authorization", {}).get("method")
                == "notarized-document-manually-verified",
                "authorization_method": license.get("authorization", {}).get("method"),
                "message": "Desenvolvimento do autor · sem certificação cartorial"
                if license["edition"] == "author-development"
                else "Licença comercial · documento conferido pelo emissor",
            }
        except ValueError as exc:
            return {"valid": False, "author": AUTHOR, "message": str(exc), "installation_id": self.installation}

    def install(self, source, document=None):
        if Path(source).stat().st_size > 32768:
            raise ValueError("Licença excede limite de 32 KB")
        envelope = json.loads(Path(source).read_text(encoding="utf-8"))
        payload = self.verify(envelope, Path(document) if document else None)
        if payload["edition"] == "commercial":
            target = self.settings.data / "license-documents" / (payload["authorization"]["document_sha256"] + ".pdf")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(Path(document).read_bytes())
        temporary = self.settings.data / "license.next"
        temporary.write_text(encode(envelope), encoding="utf-8")
        temporary.replace(self.settings.data / "license.json")
        return self.status()
