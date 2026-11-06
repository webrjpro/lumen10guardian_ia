"""Laboratório real de Git, IA, teste de regressão, artefato e rollback.

Somente fixture próprio. Não executa código de terceiros no host.
"""

import hashlib
import io
import json
import sys
import zipfile

from guardian.db import encode, now, uid
from guardian.licensing import LicenseGuard
from guardian.policy import authorize_release
from guardian.processes import run_quiet
from guardian.security import redact
from guardian.workflow import record_event, set_incident_state

BUG = 'def greeting(name):\n    return "Olá, " + name.strip()\n'
STABLE = 'def greeting(name):\n    return "Olá, " + (name or "visitante").strip()\n'
REGRESSION = """import unittest
from app import greeting
class GreetingTests(unittest.TestCase):
    def test_normal(self): self.assertEqual(greeting("Ana"), "Olá, Ana")
    def test_null(self): self.assertEqual(greeting(None), "Olá, visitante")
    def test_trim(self): self.assertEqual(greeting("  Ana  "), "Olá, Ana")
"""
RUN_TESTS = """import sys, unittest
sys.path.insert(0, sys.argv[1])
suite = unittest.defaultTestLoader.discover(sys.argv[2])
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
"""
SMOKE = """import sys
sys.path.insert(0, sys.argv[1])
from app import greeting
assert greeting("Guardian") == "Olá, Guardian"
"""


def git(root, *args):
    result = run_quiet(
        [
            "git",
            "-c",
            "core.hooksPath=NUL" if sys.platform == "win32" else "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(root),
            *args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError("Operação Git falhou: " + redact(result.stderr)[:500])
    return result.stdout.strip()


class Laboratory:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings

    def root(self, env):
        # Não aceitar caminho de release enviado por API ou pelo modelo.
        return self.settings.data / "fixtures" / env["id"]

    def create(self, tenant):
        LicenseGuard(self.settings).require("lab", tenant)
        identifier = uid()
        root = self.settings.data / "fixtures" / identifier
        repo, trusted, live = root / "repo", root / "trusted-tests", root / "live"
        for path in (repo, trusted, live):
            path.mkdir(parents=True)
        (repo / "app.py").write_text(BUG, encoding="utf-8")
        (trusted / "test_regression.py").write_text(REGRESSION, encoding="utf-8")
        (live / "app.py").write_text(BUG, encoding="utf-8")
        git(repo, "init", "--initial-branch=main")
        git(repo, "add", "app.py")
        git(
            repo,
            "-c",
            "user.name=Guardian Lab",
            "-c",
            "user.email=lab@localhost",
            "commit",
            "-m",
            "fixture: nullable greeting bug",
        )
        self.store.execute(
            "INSERT INTO environments(id,tenant_id,name,kind,target,auto_ai) VALUES(?,?,?,?,?,0)",
            (identifier, tenant, "Laboratório · correção com IA", "fixture", "local-fixture"),
        )
        incident = record_event(
            self.store,
            tenant,
            identifier,
            "fixture_python_error",
            "Fixture local: greeting(None) falha com AttributeError. Esperado: Olá, visitante.",
        )
        self.store.audit(tenant, "operator", "fixture.created", identifier, {"synthetic": True, "incident": incident})
        return {"environment_id": identifier, "incident_id": incident}

    def context(self, environment):
        if environment["kind"] != "fixture":
            return {}
        return {
            "source": {"app.py": git(self.root(environment) / "repo", "show", "HEAD:app.py")},
            "regression_requirements": "greeting(None) == 'Olá, visitante'; greeting('  Ana  ') == 'Olá, Ana'",
        }

    def prepare(self, tenant, environment, incident, diagnosis, run_id):
        LicenseGuard(self.settings).require("lab", tenant)
        if environment["kind"] != "fixture":
            raise ValueError(
                "Correção local executável disponível no laboratório; repositório de produção ainda não conectado"
            )
        if environment["paused"]:
            raise ValueError("Mudanças suspensas")
        changes = diagnosis.get("changes", [])
        if len(changes) != 1 or changes[0]["path"] != "app.py":
            raise ValueError("Fixture permite alterar exclusivamente app.py")
        content = changes[0]["content"]
        # Fixture é um contrato pequeno e auditável, não um runner Python genérico.
        self._validate_fixture_code(content)
        root = self.root(environment)
        worktree = root / "worktrees" / run_id
        worktree.parent.mkdir(exist_ok=True)
        branch = "guardian/" + run_id
        git(root / "repo", "worktree", "add", "-b", branch, str(worktree), "HEAD")
        set_incident_state(self.store, tenant, incident, "CORRECAO_EM_BRANCH", branch)
        try:
            (worktree / "app.py").write_text(content, encoding="utf-8")
            diff = git(worktree, "diff", "--", "app.py")
            if not diff:
                raise ValueError("IA não propôs alteração")
            set_incident_state(
                self.store, tenant, incident, "TESTES_EM_EXECUCAO", "Regressão imutável fora do worktree"
            )
            result = run_quiet(
                [sys.executable, "-I", "-B", "-c", RUN_TESTS, str(worktree), str(root / "trusted-tests")],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            artifact = {
                "branch": branch,
                "diff": diff,
                "test_output": redact(result.stdout + result.stderr),
                "tests_passed": result.returncode == 0,
                "risk": diagnosis["risk"],
                "backup_verified": False,
                "suite": "nullable-greeting-v1",
            }
            identifier = uid()
            if result.returncode == 0:
                git(worktree, "add", "app.py")
                git(
                    worktree,
                    "-c",
                    "user.name=Guardian Lab",
                    "-c",
                    "user.email=lab@localhost",
                    "commit",
                    "-m",
                    f"fix: {incident}",
                )
                commit = git(worktree, "rev-parse", "HEAD")
                target = root / "artifacts" / (identifier + ".zip")
                target.parent.mkdir(exist_ok=True)
                with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
                    bundle.writestr("app.py", git(worktree, "show", commit + ":app.py") + "\n")
                backup = (root / "live/app.py").read_bytes()
                (root / "artifacts" / (identifier + ".backup.py")).write_bytes(backup)
                smoke = self._smoke(root / "live")
                artifact.update(
                    commit=commit,
                    sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                    backup_sha256=hashlib.sha256(backup).hexdigest(),
                    backup_verified=smoke,
                    regression_hash=hashlib.sha256(REGRESSION.encode()).hexdigest(),
                )
                state = "TESTES_APROVADOS"
            else:
                state = "TESTES_REPROVADOS"
            self.store.execute(
                "INSERT INTO changes VALUES(?,?,?,?,?,?,?)",
                (identifier, tenant, environment["id"], incident, state, encode(artifact), now()),
            )
            set_incident_state(self.store, tenant, incident, state, "Resultado real da suíte de regressão")
            self.store.audit(
                tenant,
                "runner",
                "change." + state,
                identifier,
                {"suite": artifact["suite"], "passed": artifact["tests_passed"]},
            )
            return identifier
        finally:
            git(root / "repo", "worktree", "remove", "--force", str(worktree))

    @staticmethod
    def _validate_fixture_code(content):
        import ast

        if len(content) > 3000:
            raise ValueError("Código do fixture excede o limite")
        tree = ast.parse(content)
        # Permite somente uma função pura de strings, sem imports, atributos dinâmicos ou I/O.
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef) or tree.body[0].name != "greeting":
            raise ValueError("Fixture exige apenas a função greeting")
        nodes = list(ast.walk(tree))
        if len(nodes) > 80:
            raise ValueError("Complexidade excedeu o contrato restrito do fixture")
        allowed = (
            ast.Module,
            ast.FunctionDef,
            ast.arguments,
            ast.arg,
            ast.Return,
            ast.If,
            ast.IfExp,
            ast.Assign,
            ast.Name,
            ast.Load,
            ast.Store,
            ast.Constant,
            ast.BinOp,
            ast.Add,
            ast.BoolOp,
            ast.Or,
            ast.And,
            ast.Compare,
            ast.Is,
            ast.IsNot,
            ast.Eq,
            ast.NotEq,
            ast.Call,
            ast.Attribute,
            ast.JoinedStr,
            ast.FormattedValue,
            ast.UnaryOp,
            ast.Not,
            ast.Pass,
        )
        for node in nodes:
            if not isinstance(node, allowed):
                raise ValueError("Operação fora do contrato do fixture: " + type(node).__name__)
            if isinstance(node, ast.Name) and node.id not in {"name", "greeting", "str", "value", "result"}:
                raise ValueError("Identificador não autorizado no fixture")
            if isinstance(node, ast.FunctionDef) and node is not tree.body[0]:
                raise ValueError("Funções aninhadas não autorizadas")
            if (
                isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Store)
                and node.id not in {"name", "value", "result"}
            ):
                raise ValueError("Reatribuição de identificador protegido")
            if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)) and len(node.value) > 1024:
                raise ValueError("Literal excedeu o limite do fixture")
            if isinstance(node, ast.FormattedValue) and node.format_spec is not None:
                raise ValueError("Especificadores de formato não autorizados")
            if isinstance(node, ast.Attribute) and (node.attr != "strip" or not isinstance(node.ctx, ast.Load)):
                raise ValueError("Atributo não autorizado")
            if isinstance(node, ast.Call) and not (
                isinstance(node.func, ast.Attribute) or isinstance(node.func, ast.Name) and node.func.id == "str"
            ):
                raise ValueError("Chamada não autorizada")
        function = tree.body[0]
        if function.decorator_list or function.returns or function.args.defaults or function.args.kw_defaults:
            raise ValueError("Assinatura fora do contrato do fixture")
        arguments = [*function.args.posonlyargs, *function.args.args]
        if (
            len(arguments) != 1
            or arguments[0].arg != "name"
            or arguments[0].annotation
            or function.args.vararg
            or function.args.kwarg
            or function.args.kwonlyargs
        ):
            raise ValueError("O fixture recebe somente o argumento name")

    def _smoke(self, path):
        return (
            run_quiet(
                [sys.executable, "-I", "-B", "-c", SMOKE, str(path)], capture_output=True, timeout=10, encoding="utf-8"
            ).returncode
            == 0
        )

    def deploy(self, tenant, change_id):
        LicenseGuard(self.settings).require("lab", tenant)
        change = self.store.one("SELECT * FROM changes WHERE tenant_id=? AND id=?", (tenant, change_id))
        if not change:
            raise ValueError("Release não encontrada")
        env = self.store.environment(tenant, change["environment_id"])
        artifact = json.loads(change["artifact"])
        allowed, reason = authorize_release(env, artifact)
        if not allowed:
            raise ValueError(reason)
        root = self.root(env)
        archive = root / "artifacts" / (change_id + ".zip")
        if hashlib.sha256(archive.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ValueError("Integridade do artefato inválida")
        backup = (root / "artifacts" / (change_id + ".backup.py")).read_bytes()
        if hashlib.sha256(backup).hexdigest() != artifact["backup_sha256"]:
            raise ValueError("Backup adulterado")
        if hashlib.sha256((root / "live/app.py").read_bytes()).hexdigest() != artifact["backup_sha256"]:
            raise ValueError("Versão local mudou desde os testes; preparar uma nova release")
        with self.store.transaction() as db:
            fresh = db.execute(
                "SELECT paused FROM environments WHERE tenant_id=? AND id=?", (tenant, env["id"])
            ).fetchone()
            if fresh["paused"]:
                raise ValueError("Mudanças suspensas")
            count = db.execute(
                "UPDATE changes SET state='IMPLANTANDO' WHERE tenant_id=? AND id=? "
                "AND state IN ('TESTES_APROVADOS','AGENDADO')",
                (tenant, change_id),
            ).rowcount
            if count != 1:
                raise ValueError("Release já executada ou sem testes aprovados")
            self.store.audit(tenant, "executor", "release.started", change_id, {"sha256": artifact["sha256"]}, db)
        try:
            with zipfile.ZipFile(io.BytesIO(archive.read_bytes())) as bundle:
                if bundle.namelist() != ["app.py"]:
                    raise ValueError("Conteúdo do pacote inválido")
                content = bundle.read("app.py")
                self._validate_fixture_code(content.decode())
            temp = root / "live/app.next"
            temp.write_bytes(content)
            temp.replace(root / "live/app.py")
            if not self._smoke(root / "live"):
                raise ValueError("Smoke test reprovado")
            state = "RESOLVIDO"
        except Exception:
            temp = root / "live/app.restore"
            temp.write_bytes(backup)
            temp.replace(root / "live/app.py")
            state = "REVERTIDO" if self._smoke(root / "live") else "FALHA_DE_IMPLANTACAO"
        self.store.execute("UPDATE changes SET state=? WHERE tenant_id=? AND id=?", (state, tenant, change_id))
        set_incident_state(self.store, tenant, change["incident_id"], state, "Verificação do laboratório local")
        self.store.audit(
            tenant, "executor", "release." + state, change_id, {"sha256": artifact["sha256"], "fixture": True}
        )
        return state

    def rollback(self, tenant, change_id):
        LicenseGuard(self.settings).require("lab", tenant)
        change = self.store.one("SELECT * FROM changes WHERE tenant_id=? AND id=?", (tenant, change_id))
        if not change or change["state"] != "RESOLVIDO":
            raise ValueError("Release não elegível para rollback")
        env = self.store.environment(tenant, change["environment_id"])
        if env["kind"] != "fixture" or env["paused"]:
            raise ValueError("Rollback bloqueado")
        root, artifact = self.root(env), json.loads(change["artifact"])
        backup = (root / "artifacts" / (change_id + ".backup.py")).read_bytes()
        if hashlib.sha256(backup).hexdigest() != artifact["backup_sha256"]:
            raise ValueError("Backup adulterado")
        temp = root / "live/app.restore"
        temp.write_bytes(backup)
        temp.replace(root / "live/app.py")
        state = "REVERTIDO" if self._smoke(root / "live") else "FALHA_DE_IMPLANTACAO"
        self.store.execute("UPDATE changes SET state=? WHERE tenant_id=? AND id=?", (state, tenant, change_id))
        set_incident_state(self.store, tenant, change["incident_id"], state, "Rollback solicitado pelo operador")
        self.store.audit(tenant, "operator", "release.rollback", change_id, {"state": state})
        return state
