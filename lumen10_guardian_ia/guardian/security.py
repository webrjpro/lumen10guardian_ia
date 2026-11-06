import base64
import ctypes
import hashlib
import os
import re
import secrets
import time
from ctypes import wintypes
from pathlib import Path, PurePosixPath

from guardian.db import now, uid


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def redact(value):
    text = str(value)
    text = re.sub(
        r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
        "[SEGREDO REMOVIDO]",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(r"(?i)(bearer\s+)[\w.\-]+", r"\1[REMOVIDO]", text)
    text = re.sub(
        r"""(?i)(["']?(?:password|passwd|senha|secret|segredo|token|api[_-]?key|authorization)["']?\s*[=:]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)""",
        r"\1[REMOVIDO]",
        text,
    )
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REMOVIDO]", text)
    text = re.sub(r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{12,}\b", "[REMOVIDO]", text)
    text = re.sub(r"\b\d{3}\.\d{3}\.\d{3}[-.]\d{2}\b", "[CPF REMOVIDO]", text)
    text = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[EMAIL REMOVIDO]", text, flags=re.IGNORECASE)
    text = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REMOVIDO]@", text)
    return text[:24000]


def safe_source(path):
    p = PurePosixPath(path)
    lowered = path.lower()
    return (
        not p.is_absolute()
        and ".." not in p.parts
        and "\\" not in path
        and ":" not in path
        and all(
            not part.startswith(".")
            and part.lower()
            not in {"uploads", "storage", "backups", "moodledata", "data", "runtime", "output", "cache"}
            for part in p.parts
        )
        and not any(
            word in lowered
            for word in (
                "credencia",
                "config.php",
                "secret",
                "password",
                "lumen10_guardian_ia",
                "node_modules",
                "vendor/",
            )
        )
        and p.suffix.lower()
        in {
            ".py",
            ".php",
            ".js",
            ".ts",
            ".css",
            ".html",
            ".cs",
            ".java",
            ".go",
            ".rs",
            ".rb",
            ".c",
            ".h",
            ".cpp",
            ".hpp",
            ".jsx",
            ".tsx",
            ".scss",
            ".vue",
            ".svelte",
        }
    )


class Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def dpapi(data, decrypt=False):
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    if decrypt:
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)
        )
    else:
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(source), "Guardian", None, None, None, 1, ctypes.byref(target)
        )
    if not ok:
        raise OSError("DPAPI indisponível")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def protect_file(path: Path, value: str):
    payload = dpapi(value.encode()) if os.name == "nt" else value.encode()
    path.write_bytes(base64.b64encode(payload))
    if os.name != "nt":
        path.chmod(0o600)


def read_protected(path):
    payload = base64.b64decode(path.read_bytes())
    return (dpapi(payload, True) if os.name == "nt" else payload).decode()


def issue_credential(store, tenant, role, environment=None, ttl=None, db=None):
    token = secrets.token_urlsafe(40)
    args = (digest(token), tenant, role, environment, time.time() + ttl if ttl else None)
    sql = "INSERT INTO credentials(hash,tenant_id,role,environment_id,expires_at) VALUES(?,?,?,?,?)"
    if db is not None:
        db.execute(sql, args)
    else:
        store.execute(sql, args)
    return token


def authenticate(store, token):
    if not token or len(token) > 200:
        return None
    return store.one(
        "SELECT * FROM credentials WHERE hash=? AND revoked=0 AND (expires_at IS NULL OR expires_at>?)",
        (digest(token), time.time()),
    )


def bootstrap(store, settings):
    existing = store.one("SELECT id FROM tenants ORDER BY created_at LIMIT 1")
    if existing:
        return existing["id"]
    tenant, environment = uid(), uid()
    with store.transaction() as db:
        db.execute("INSERT INTO tenants VALUES(?,?,?)", (tenant, "Lumen10", now()))
        db.execute(
            "INSERT INTO environments(id,tenant_id,name,kind,target,auto_ai) VALUES(?,?,?,?,?,1)",
            (environment, tenant, "Estação Guardian", "local", "localhost"),
        )
        token = issue_credential(store, tenant, "owner", db=db)
        store.audit(tenant, "bootstrap", "tenant.created", tenant, {"mode": "local"}, db)
        protect_file(settings.data / "owner.key", token)
    return tenant
