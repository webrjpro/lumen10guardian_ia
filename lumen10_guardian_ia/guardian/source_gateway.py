"""Gateway de código somente leitura, raiz fixa e chave vinculada ao ambiente."""

import hashlib
import os
from pathlib import Path, PurePosixPath

from guardian.security import redact, safe_source

EXCLUDED = {
    "uploads",
    "cache",
    "backups",
    "storage",
    "files",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "moodledata",
    "data",
    "output",
    "runtime",
    "__pycache__",
    "lumen10_guardian_ia",
}


class SourceGateway:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def manifest(self):
        files = []
        for base, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".")
                and d.lower() not in EXCLUDED
                and not (Path(base) / d).is_symlink()
                and (Path(base) / d).resolve().is_relative_to(self.root)
            ]
            for name in sorted(names):
                path = Path(base) / name
                relative = path.relative_to(self.root).as_posix()
                if safe_source(relative) and not path.is_symlink() and path.stat().st_size <= 262144:
                    files.append({"path": relative, "bytes": path.stat().st_size})
                    if len(files) >= 5000:
                        return {"files": files, "truncated": True, "access": "read-only"}
        return {"files": files, "truncated": False, "access": "read-only"}

    def read(self, name):
        if not safe_source(name) or any(part.lower() in EXCLUDED for part in PurePosixPath(name).parts):
            raise ValueError("Arquivo fora do escopo de código permitido")
        path = self.root / name
        if not path.resolve().is_relative_to(self.root) or path.is_symlink() or not path.is_file():
            raise ValueError("Arquivo fora da raiz ou inexistente")
        if path.stat().st_size > 262144:
            raise ValueError("Arquivo excede 256 KB; selecione um escopo menor")
        original = path.read_bytes()
        raw = original.decode("utf-8", errors="replace")
        content = redact(raw)
        return {
            "path": name,
            "content": content,
            "sha256": hashlib.sha256(original).hexdigest(),
            "redaction_applied": content != raw,
            "truncated": len(raw) > 24000,
            "access": "read-only",
        }
