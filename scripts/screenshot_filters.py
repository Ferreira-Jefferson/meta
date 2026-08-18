"""Screenshots home + detalhe pós-filtros."""
from __future__ import annotations

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path(__file__).resolve().parents[1] / "screenshots"


async def shot(page, url, name, wait=1500):
    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(wait)
    await page.screenshot(path=str(OUT / name), full_page=True)
    print(name)


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1440, "height": 900})
        pg = await ctx.new_page()
        await shot(pg, "http://127.0.0.1:8765/", "home_filters.png")
        await shot(pg, "http://127.0.0.1:8765/strategies/baseline_ma_cross", "detail_filters.png", wait=1800)
        await b.close()


if __name__ == "__main__":
    asyncio.run(main())
