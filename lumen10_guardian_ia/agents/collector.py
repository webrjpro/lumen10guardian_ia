"""Agente de coleta Linux/Windows. HTTP de saída, spool durável, sem shell remoto.

Instale: python -m pip install httpx psutil
Execute: python collector.py --url https://central --environment UUID --token-file /path/token
Para central local use túnel SSH e http://127.0.0.1:8765.
"""

import argparse
import hashlib
import json
import logging
import os
import re
import signal
import sqlite3
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import psutil

logger = logging.getLogger("guardian.collector")
STOP = False


def stop(*_):
    global STOP
    STOP = True


def clean(text):
    text = re.sub(r"(?i)((?:password|passwd|secret|token|api[_-]?key)\s*[=:]\s*)[^\s,;]+", r"\1[REMOVIDO]", text)
    text = re.sub(r"(?i)bearer\s+[\w.\-]+", "Bearer [REMOVIDO]", text)
    text = re.sub(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b", "[EMAIL REMOVIDO]", text)
    return text[:6000]


def run(args):
    url = urlsplit(args.url)
    if url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}):
        raise ValueError("Use HTTPS ou túnel por loopback")
    if url.username or url.password or url.query or url.fragment:
        raise ValueError("URL não aceita credenciais ou query")
    spool = Path(args.spool).resolve()
    spool.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        spool.parent.chmod(0o700)
        if Path(args.token_file).stat().st_mode & 0o077:
            raise ValueError("Arquivo de token deve ter permissão 600")
    db = sqlite3.connect(spool)
    db.execute("CREATE TABLE IF NOT EXISTS pending(id TEXT PRIMARY KEY,route TEXT,body TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS offsets(path TEXT PRIMARY KEY,offset INTEGER)")
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        while not STOP:
            for raw in args.log:
                path = Path(raw)
                if not path.is_file() or path.is_symlink():
                    continue
                saved = db.execute("SELECT offset FROM offsets WHERE path=?", (str(path),)).fetchone()
                size = path.stat().st_size
                offset = min(saved[0], size) if saved else max(0, size - 16000)
                with path.open("rb") as source:
                    source.seek(offset)
                    chunk = source.read(64000)
                    position = source.tell()
                # Retém linha incompleta para o próximo ciclo.
                if b"\n" in chunk:
                    tail = chunk.rsplit(b"\n", 1)[1]
                    position -= len(tail)
                    chunk = chunk[: -len(tail)] if tail else chunk
                for line in chunk.decode("utf-8", errors="replace").splitlines():
                    if not re.search(
                        r"(?i)(fatal|exception|error|SQLSTATE|failed password|injection|denied|warning|notice|deprecated)",
                        line,
                    ):
                        continue
                    kind = (
                        "security_log"
                        if re.search(r"(?i)(failed password|injection|denied)", line)
                        else "php_runtime_error"
                    )
                    summary = clean(line)
                    event_id = hashlib.sha256((str(path) + str(offset) + summary).encode()).hexdigest()
                    body = {
                        "event_id": event_id,
                        "environment_id": args.environment,
                        "kind": kind,
                        "summary": summary,
                        "severity": "P1"
                        if kind == "security_log" or re.search(r"(?i)fatal", line)
                        else ("P3" if re.search(r"(?i)(warning|notice|deprecated)", line) else "P2"),
                    }
                    db.execute(
                        "INSERT OR IGNORE INTO pending VALUES(?,?,?)",
                        (event_id, "/api/v1/telemetry/events", json.dumps(body)),
                    )
                db.execute("INSERT OR REPLACE INTO offsets VALUES(?,?)", (str(path), position))
            heartbeat = {
                "event_id": str(uuid.uuid4()),
                "environment_id": args.environment,
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage(str(spool.anchor)).percent,
            }
            db.execute(
                "INSERT INTO pending VALUES(?,?,?)",
                (heartbeat["event_id"], "/api/v1/telemetry/heartbeat", json.dumps(heartbeat)),
            )
            # Limite explícito. Perdas registradas localmente, nunca filas sem limite.
            count = db.execute("SELECT count(*) FROM pending").fetchone()[0]
            if count > 1000:
                db.execute(
                    "DELETE FROM pending WHERE rowid IN (SELECT rowid FROM pending ORDER BY rowid LIMIT ?)",
                    (count - 1000,),
                )
                logger.warning("Spool atingiu limite; descartados %d eventos antigos", count - 1000)
            db.commit()
            token = Path(args.token_file).read_text().strip()
            for row in db.execute("SELECT id,route,body FROM pending ORDER BY rowid LIMIT 50").fetchall():
                try:
                    response = client.post(
                        args.url.rstrip("/") + row[1],
                        content=row[2],
                        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                    )
                    if response.status_code in {401, 403}:
                        raise RuntimeError("Agente revogado ou escopo inválido; realize novo pareamento")
                    response.raise_for_status()
                except httpx.HTTPError:
                    logger.warning("Central indisponível; mantendo eventos no spool")
                    break
                db.execute("DELETE FROM pending WHERE id=?", (row[0],))
                db.commit()
            for _ in range(args.interval):
                if STOP:
                    break
                time.sleep(1)
    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--spool", default="./guardian-state/spool.db")
    parser.add_argument("--log", action="append", default=[])
    parser.add_argument("--interval", type=int, default=30)
    options = parser.parse_args()
    if options.interval < 10:
        parser.error("Intervalo mínimo: 10 segundos")
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    run(options)
