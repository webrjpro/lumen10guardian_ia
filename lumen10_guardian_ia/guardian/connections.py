"""Leitura local autorizada de .env/credenciais.md. Valores nunca retornam ao LLM.

Não interpreta shell, não carrega variáveis no processo, não executa Markdown.
SSH usa chave/OpenSSH; senhas não são passadas em argv.
"""

import re
import unicodedata
from pathlib import Path

from guardian.processes import run_quiet

FIELDS = {
    "SSH_HOST",
    "SSH_USER",
    "SSH_PORT",
    "SSH_KEY_PATH",
    "APP_URL",
    "MOODLE_URL",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_TO",
}
ALIASES = {
    "IP_DO_SERVIDOR": "SSH_HOST",
    "USUARIO": "SSH_USER",
    "PORTA": "SSH_PORT",
    "CHAVE_SSH_CONFIGURADA": "SSH_KEY_PATH",
    "SERVIDOR_SMTP": "SMTP_HOST",
    "USUARIO_SMTP": "SMTP_USER",
    "CHAVE_SENHA_SMTP": "SMTP_PASSWORD",
}


class ProjectConnection:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def values(self):
        result = {}
        for name in ("credenciais.md", ".env"):
            path = self.root / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 262144:
                continue
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                match = re.match(
                    r"^\s*(?:-\s*)?([^:=]{1,80})\s*[:=]\s*(.*?)\s*$", line.replace("**", "").replace("`", "")
                )
                if match:
                    label = unicodedata.normalize("NFKD", match[1]).encode("ascii", "ignore").decode().upper()
                    label = re.sub(r"[^A-Z0-9]+", "_", label).strip("_")
                    field = ALIASES.get(label, label)
                    if field in FIELDS:
                        result[field] = match[2].strip("\"'")
        if result.get("SMTP_HOST"):
            host = re.match(r"^([a-zA-Z0-9.-]+)", result["SMTP_HOST"])
            if host:
                result["SMTP_HOST"] = host[1]
        return result

    def inventory(self):
        from guardian.connectors import discover_project

        values = self.values()
        key = Path(values.get("SSH_KEY_PATH", "__not_configured__")).expanduser()
        if not key.is_absolute():
            key = self.root / key
        return {
            "files": {name: (self.root / name).is_file() for name in (".env", "credenciais.md")},
            "configured_fields": sorted(values),
            "ssh_ready": all(values.get(k) for k in ("SSH_HOST", "SSH_USER", "SSH_KEY_PATH")) and key.is_file(),
            "authentication": "OpenSSH key; host key verification mandatory",
            "project": discover_project(self.root),
        }

    def snapshot(self):
        values = self.values()
        if not all(values.get(k) for k in ("SSH_HOST", "SSH_USER", "SSH_KEY_PATH")):
            raise ValueError("Configure SSH_HOST, SSH_USER e SSH_KEY_PATH no .env do projeto")
        host, user = values["SSH_HOST"], values["SSH_USER"]
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.:-]{0,252}", host):
            raise ValueError("SSH_HOST inválido")
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_-]{0,63}", user):
            raise ValueError("SSH_USER inválido")
        port = int(values.get("SSH_PORT", "22"))
        if not 1 <= port <= 65535:
            raise ValueError("Porta inválida")
        key = Path(values["SSH_KEY_PATH"]).expanduser()
        if not key.is_absolute():
            key = self.root / key
        if not key.is_file():
            raise ValueError("Chave SSH não encontrada")
        # Comando remoto estático de leitura. Sem sudo, SQL, Docker ou comandos do modelo.
        command = "printf 'GUARDIAN_HOST\\n'; uname -s; uptime; df -Pk /; if command -v php >/dev/null; then php -v | head -n 2; fi"
        result = run_quiet(
            [
                "ssh",
                "-T",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "ConnectTimeout=8",
                "-p",
                str(port),
                "-i",
                str(key),
                f"{user}@{host}",
                command,
            ],
            capture_output=True,
            timeout=20,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode:
            raise ValueError("SSH não conectado. Verifique chave, known_hosts e permissões no terminal local")
        from guardian.security import redact

        return redact(result.stdout)

    def source_context(self):
        from guardian.security import redact, safe_source

        result = run_quiet(
            ["git", "-C", str(self.root), "ls-files", "-z"],
            capture_output=True,
            timeout=10,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode:
            return {"status": "Repositório Git não encontrado", "files": {}}
        selected, remaining = {}, 18000
        for name in result.stdout.split("\0"):
            if not safe_source(name):
                continue
            path = self.root / name
            if path.is_symlink() or not path.resolve().is_relative_to(self.root) or not path.is_file():
                continue
            if path.stat().st_size > 24000:
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            if len(content) > remaining:
                continue
            selected[name] = redact(content)
            remaining -= len(content)
            if len(selected) >= 8:
                break
        return {"status": "Contexto inicial limitado; não é análise completa do repositório", "files": selected}
