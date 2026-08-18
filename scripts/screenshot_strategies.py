"""Screenshots do fluxo de simulação: /strategies + página do sim ao vivo."""
from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


OUT = Path(__file__).resolve().parents[1] / "screenshots"


async def run() -> None:
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # 1. Snapshot do formulário
        await page.goto("http://127.0.0.1:8765/strategies", wait_until="networkidle")
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(OUT / "strategies_form.png"), full_page=True)
        print("  -> strategies_form.png")

        # 2. Preencher e submeter
        await page.fill('input[name="start_date"]', "2018-01-01")
        # Ao submeter vamos para /strategies/sim/{id}
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/strategies/sim/**", timeout=15000)

        # 3. Screenshot durante execução (aguarda alguns eventos de progresso)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT / "strategy_sim_running.png"), full_page=True)
        print("  -> strategy_sim_running.png")

        # 4. Aguarda "done" — status muda; damos até 20s
        try:
            await page.wait_for_selector('#sim-status:has-text("done")', timeout=20000)
        except Exception:
            pass
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUT / "strategy_sim_done.png"), full_page=True)
        print("  -> strategy_sim_done.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
