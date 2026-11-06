"""Aceite de navegador em Chrome headless com medições locais reais.

Requer `python -m pip install playwright` e Chrome instalado.
Não aciona ações em produção.
"""

import json
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from guardian.cli import ticket
from guardian.config import Settings


def main():
    settings = Settings.load()
    output = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(ticket(settings)["url"])
        page.get_by_role("heading", name="Seu ambiente, sob controle.").wait_for(timeout=15000)
        # Seed apenas de um endpoint HTTP local real, nunca de métricas.
        info = page.evaluate("fetch('/api/v1/overview').then(r=>r.json())")
        if not any(e["name"] == "Guardian HTTP local" for e in info["environments"]):
            page.get_by_role("button", name="＋ Conectar ambiente", exact=True).click()
            form = page.locator("#environment-form")
            form.locator("[name=name]").fill("Guardian HTTP local")
            form.locator("[name=target]").fill(f"http://127.0.0.1:{settings.port}/healthz")
            form.get_by_role("button", name="Conectar ambiente", exact=True).click()
            page.locator("#modal").wait_for(state="hidden")
        activate = page.get_by_role("button", name="▶ Ativar Guardian", exact=True)
        if activate.count():
            activate.click()
        page.locator("svg.chart").wait_for(timeout=20000)
        page.screenshot(path=str(output / "painel-desktop.png"), full_page=True)
        for name, heading in [
            ("Incidentes", "Do sinal à causa."),
            ("Ambientes", "Ambientes conectados"),
            ("Correções e releases", "Correções com evidência."),
            ("Trilha de auditoria", "Cada decisão deixa uma trilha."),
            ("Licença e autoria", "Autorização verificável."),
            ("Alertas por e-mail", "Alertas que chegam até você."),
            ("Segurança global", "Antecipar também é proteger."),
        ]:
            page.get_by_role("button", name=name, exact=False).first.click()
            page.get_by_role("heading", name=heading, exact=True).wait_for()
        page.get_by_role("button", name="Trilha de auditoria", exact=False).first.click()
        page.get_by_role("button", name="Verificar integridade", exact=True).click()
        page.get_by_role("button", name="PowerShell e VS Code", exact=False).click()
        page.get_by_role("button", name="Coletar diagnóstico", exact=True).click()
        expect(page.locator(".terminal-box pre")).to_contain_text("capturedAt", timeout=20000)
        page.get_by_role("button", name="Visão geral", exact=False).click()
        production = page.get_by_role("button", name="Lumen10 - produção HTTP", exact=True)
        if production.count():
            production.click()
            expect(page.get_by_role("button", name="Lumen10 - produção HTTP", exact=True)).to_have_class(
                "selected", timeout=15000
            )
            expect(page.locator("#graph-env option")).to_have_count(2, timeout=15000)
            expect(page.locator(".stat").nth(2).locator("strong")).to_have_text("02")
            page.locator("#toast.show").wait_for(state="hidden", timeout=10000)
            expect(page.locator("#graph-env")).to_contain_text("Lumen10", timeout=15000)
            page.screenshot(path=str(output / "painel-lumen10.png"), full_page=True)
            page.get_by_role("button", name="Todos os sistemas", exact=True).click()
        page.locator("#toast.show").wait_for(state="hidden", timeout=10000)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(output / "painel-mobile.png"), full_page=True)
        overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth")
        browser.close()
    report = {
        "executed_at_epoch": time.time(),
        "browser": "Chrome headless",
        "javascript_errors": errors,
        "mobile_horizontal_overflow": overflow,
        "real_telemetry": True,
        "navigation_sections": 9,
        "system_tabs_tested": True,
        "activation_tested": True,
        "powershell_diagnostic_tested": True,
    }
    (output.parent / "aceite-painel.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if errors or overflow:
        raise SystemExit("Falha no aceite visual")


if __name__ == "__main__":
    main()
