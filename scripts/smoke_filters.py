"""Smoke test end-to-end dos filtros da home usando Playwright.

Uso: rode o dashboard (dev.bat) e depois:
  .\.venv\Scripts\python.exe scripts\smoke_filters.py
"""
from __future__ import annotations

import sys
import time
from playwright.sync_api import sync_playwright


URL = "http://127.0.0.1:8000/"


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        console_msgs: list[str] = []
        page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: console_msgs.append(f"[pageerror] {e}"))

        requests: list[str] = []
        page.on("request", lambda r: requests.append(f"{r.method} {r.url}") if "/runs/list" in r.url else None)

        page.goto(URL, wait_until="networkidle")

        # 1. Contagem inicial de linhas no tbody
        rows_before = page.locator("#runs-tbody tr").count()
        print(f"[baseline] linhas iniciais no #runs-tbody = {rows_before}")

        # 2. Seleciona campeão no select
        select = page.locator("select[name='strategy']")
        options = select.locator("option").all_text_contents()
        print(f"[filter select] opções: {options}")

        target = "momentum_macro_gated"
        if target not in options:
            print(f"ERRO: opção '{target}' não está no select — abortando")
            print("Console:", console_msgs)
            browser.close()
            return 2

        select.select_option(value=target)

        # 3. Espera HTMX processar (debounce 100ms + rede)
        page.wait_for_timeout(800)

        rows_after = page.locator("#runs-tbody tr").count()
        print(f"[after change] linhas no #runs-tbody = {rows_after}")
        print(f"[after change] requests /runs/list: {requests}")

        # 4. Verifica que só robô campeão aparece
        strategy_cells = page.locator("#runs-tbody tr td:nth-child(2)").all_text_contents()
        strategies_in_table = set(s.split(" v")[0].strip() for s in strategy_cells)
        print(f"[after change] robôs presentes na tabela: {strategies_in_table}")

        ok_request = any("strategy=momentum_macro_gated" in r for r in requests)
        ok_rows = strategies_in_table == {target}

        print()
        print(f"REQ dispararam?  {ok_request}")
        print(f"TABELA filtrada? {ok_rows}")

        if console_msgs:
            print()
            print("=== console/errors ===")
            for m in console_msgs[:20]:
                print(m)

        browser.close()
        return 0 if (ok_request and ok_rows) else 1


if __name__ == "__main__":
    sys.exit(main())
