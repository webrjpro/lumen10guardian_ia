import argparse
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from guardian.ai import provider_status
from guardian.config import Settings
from guardian.db import Store, now, uid
from guardian.security import bootstrap, issue_credential


def get_store(settings):
    store = Store(settings.database)
    tenant = bootstrap(store, settings)
    return store, tenant


def ticket(settings):
    store, tenant = get_store(settings)
    token = issue_credential(store, tenant, "ticket", ttl=120)
    return {"url": f"http://127.0.0.1:{settings.port}/#ticket={token}", "ticket": token}


def serve(settings):
    import uvicorn

    from guardian.api import create_app

    # Bloqueio exclusivo de processo. Evita dois workers/monitores na mesma base.
    lock = (settings.data / "server.lock").open("a+b")
    lock.seek(0)
    if lock.read(1) == b"":
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit("Guardian já está executando nesta base")
    # Mantém referência viva até o fim do servidor.
    try:
        uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.port, access_log=False, log_level="warning")
    finally:
        lock.close()


def supervisor(settings):
    import httpx

    flag = settings.data / "stop.request"
    if flag.exists():
        flag.unlink()
    try:
        response = httpx.get(f"http://127.0.0.1:{settings.port}/healthz", timeout=2, trust_env=False)
        if response.json().get("service") == "lumen10-guardian":
            return
    except (httpx.HTTPError, ValueError):
        pass
    failures = 0
    log = settings.data / "service.log"
    while not flag.exists():
        if log.exists() and log.stat().st_size > 2_000_000:
            log.replace(settings.data / "service.previous.log")
        with log.open("a", encoding="utf-8") as output:
            process = subprocess.Popen(
                [sys.executable, "-m", "guardian", "serve"],
                stdout=output,
                stderr=output,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            while process.poll() is None and not flag.exists():
                time.sleep(1)
            if flag.exists():
                # O launcher de venv no Windows cria um interpretador filho.
                # Encerrar só o launcher deixa servidor/LLM órfãos.
                import psutil

                try:
                    root = psutil.Process(process.pid)
                    descendants = root.children(recursive=True)
                    for child in reversed(descendants):
                        try:
                            child.terminate()
                        except psutil.NoSuchProcess:
                            pass
                    process.terminate()
                    _, alive = psutil.wait_procs(descendants, timeout=10)
                    for child in alive:
                        try:
                            child.kill()
                        except psutil.NoSuchProcess:
                            pass
                    process.wait(timeout=15)
                except (psutil.NoSuchProcess, ProcessLookupError):
                    pass
                return
        failures += 1
        # Evita restart storm quando porta/lock/configuração estão incorretos.
        if failures >= 10:
            return
        for _ in range(min(60, 2**failures)):
            if flag.exists():
                return
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(prog="guardian")
    parser.add_argument(
        "command",
        choices=["serve", "supervise", "stop", "open", "ticket", "doctor", "tenant", "connect", "lab", "activate"],
    )
    parser.add_argument("--name")
    parser.add_argument("--path")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--license")
    parser.add_argument("--document")
    args = parser.parse_args()
    settings = Settings.load()
    settings.data.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        settings.data.chmod(0o700)
    store, tenant = get_store(settings)
    if args.command == "serve":
        serve(settings)
    elif args.command == "supervise":
        supervisor(settings)
    elif args.command == "stop":
        (settings.data / "stop.request").write_text(now(), encoding="utf-8")
        print("Parada solicitada ao supervisor local")
    elif args.command in {"open", "ticket"}:
        result = ticket(settings)
        if args.command == "open":
            webbrowser.open(result["url"])
            print("Painel aberto com sessão temporária")
        else:
            print(json.dumps(result))
    elif args.command == "doctor":
        from guardian.licensing import LicenseGuard

        result = {
            "python": sys.version.split()[0],
            "data_path": str(settings.data),
            "provider": provider_status(),
            "git": bool(__import__("shutil").which("git")),
            "powershell": bool(__import__("shutil").which("pwsh")),
            "audit_valid": store.verify_audit(tenant),
            "mode": "local; sem API dedicada; produção não habilitada",
            "license": LicenseGuard(settings).status(),
            "ai": {"model": settings.model, "security_model": settings.security_model, "reasoning": settings.reasoning},
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "tenant":
        if not args.name:
            parser.error("--name obrigatório")
        identifier = uid()
        store.execute("INSERT INTO tenants VALUES(?,?,?)", (identifier, args.name, now()))
        # Token de administrador permanece protegido localmente; não é impresso.
        token = issue_credential(store, identifier, "owner")
        from guardian.security import protect_file

        protect_file(settings.data / ("tenant-" + identifier + ".key"), token)
        print(json.dumps({"tenant_id": identifier}))
    elif args.command == "connect":
        if not args.path or not Path(args.path).is_dir():
            parser.error("--path deve apontar para a pasta do projeto")
        target = str(Path(args.path).resolve())
        with store.transaction() as db:
            existing = db.execute(
                "SELECT * FROM environments WHERE tenant_id=? AND target=?", (tenant, target)
            ).fetchone()
            identifier = existing["id"] if existing else uid()
            name = existing["name"] if existing else (args.name or Path(target).name)
            system = existing["system_id"] if existing else None
            if not system:
                found = db.execute("SELECT id FROM systems WHERE tenant_id=? AND name=?", (tenant, name)).fetchone()
                system = found["id"] if found else uid()
                if not found:
                    db.execute("INSERT INTO systems VALUES(?,?,?,?)", (system, tenant, name, now()))
                    store.audit(tenant, "cli", "system.created", system, {"name": name}, db)
            if not existing:
                db.execute(
                    "INSERT INTO environments(id,tenant_id,name,kind,target,system_id) VALUES(?,?,?,?,?,?)",
                    (identifier, tenant, name, "project", target, system),
                )
                store.audit(tenant, "cli", "project.connected", identifier, {"credentials": "local read only"}, db)
            elif not existing["system_id"]:
                db.execute(
                    "UPDATE environments SET system_id=? WHERE tenant_id=? AND id=?", (system, tenant, identifier)
                )
        print(json.dumps({"environment_id": identifier, "system_id": system, "path": target}))
    elif args.command == "lab":
        from guardian.laboratory import Laboratory

        print(json.dumps(Laboratory(store, settings).create(tenant)))
    elif args.command == "activate":
        from guardian.licensing import LicenseGuard

        if not args.license:
            parser.error("--license obrigatório")
        print(json.dumps(LicenseGuard(settings).install(args.license, args.document), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
