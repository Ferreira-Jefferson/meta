"""Tira screenshots das páginas do dashboard usando Playwright."""
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

        pages = [
            ("overview",     "http://127.0.0.1:8765/",           True),
            ("trades",       "http://127.0.0.1:8765/trades",     True),
            ("trades_top",   "http://127.0.0.1:8765/trades",     False),
            ("insights",     "http://127.0.0.1:8765/insights",   True),
            ("trade_detail", "http://127.0.0.1:8765/trades/1",   True),
        ]
        for name, url, full in pages:
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(1500)
            path = OUT / f"{name}.png"
            await page.screenshot(path=str(path), full_page=full)
            print(f"  -> {path}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
