"""Ferramentas de backend não abrem janelas de console no Windows."""

import os
import subprocess


def run_quiet(*args, **kwargs):
    kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    return subprocess.run(*args, **kwargs)
