"""Screenshot de uma sim específica (passa o ID)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path(__file__).resolve().parents[1] / "screenshots"


async def run(sim_id: str, tag: str) -> None:
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        await page.goto(f"http://127.0.0.1:8765/strategies/sim/{sim_id}", wait_until="networkidle")
        try:
            await page.wait_for_selector('#sim-status:has-text("done")', timeout=8000)
        except Exception:
            pass
        await page.wait_for_timeout(1500)
        path = OUT / f"sim_{tag}.png"
        await page.screenshot(path=str(path), full_page=True)
        print(f"  -> {path}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "run"))
