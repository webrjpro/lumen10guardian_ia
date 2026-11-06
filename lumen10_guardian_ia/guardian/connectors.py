"""Descoberta somente de leitura. Nunca inclui config.php ou valores do .env."""

import re
from pathlib import Path


def discover_project(root):
    root = Path(root).resolve()
    checks = {
        name: (root / name).exists()
        for name in (
            "version.php",
            "lib/moodlelib.php",
            "composer.json",
            "package.json",
            "pyproject.toml",
            "docker-compose.yml",
            "compose.yaml",
            "config.php",
            ".env",
            "credenciais.md",
        )
    }
    moodle = checks["version.php"] and checks["lib/moodlelib.php"]
    version = None
    if moodle:
        version_file = root / "version.php"
        if not version_file.is_symlink() and version_file.stat().st_size <= 65536:
            text = version_file.read_text(encoding="utf-8", errors="replace")
            match = re.search(r"\$release\s*=\s*['\"]([^'\"]+)['\"]", text)
            version = match[1][:80] if match else None
    return {
        "connector": "moodle" if moodle else "generic-project",
        "moodle_release": version,
        "files_present": checks,
        "capabilities": {
            "discovery": True,
            "sanitized_source_context": True,
            "ssh_read_only": True,
            "production_deploy": False,
            "production_database_access": False,
            "reason": "Homologação, credenciais de infraestrutura e adaptador de release ainda não validados",
        },
    }
