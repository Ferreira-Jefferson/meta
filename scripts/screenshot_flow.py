"""Captura screenshots da nova hierarquia: home → detalhe → resultado."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "screenshots"
OUT.mkdir(exist_ok=True)


async def shot(page, url: str, name: str, wait_ms: int = 1500) -> None:
    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(wait_ms)
    await page.screenshot(path=str(OUT / name), full_page=True)
    print(f"OK {name}")


async def main(sim_id: str, run_id: str) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        base = "http://127.0.0.1:8765"
        await shot(page, f"{base}/", "flow_1_home.png")
        await shot(page, f"{base}/strategies/baseline_ma_cross", "flow_2_detalhe.png")
        await shot(page, f"{base}/sim/{sim_id}", "flow_3_sim_result.png", wait_ms=4000)
        await shot(page, f"{base}/runs/{run_id}", "flow_4_run_detail.png", wait_ms=2500)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
