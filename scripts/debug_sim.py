"""Debug: verifica o DOM do chart e captura logs do console."""
from __future__ import annotations

import asyncio
import sys

from playwright.async_api import async_playwright


async def run(sim_id: str) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context()
        page = await ctx.new_page()
        page.on("console", lambda msg: print(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: print(f"[error] {err}"))
        await page.goto(f"http://127.0.0.1:8765/sim/{sim_id}", wait_until="networkidle")
        await page.wait_for_timeout(3000)

        result = await page.evaluate("""() => {
          const el = document.getElementById('chart-live');
          return {
            child_count: el ? el.children.length : -1,
            inner_length: el ? el.innerHTML.length : -1,
            has_svg: el ? !!el.querySelector('svg') : false,
            equity_len: window.equitySeries ? window.equitySeries.dates.length : 'undefined',
            plotly_loaded: !!window.Plotly,
          };
        }""")
        print("DOM/state:", result)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1]))
