# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## AGENTS.md is the source of truth

Repo-wide rules for all IAs live in `AGENTS.md` (layer boundaries, `journal` schema policy, anti-look-ahead, frontend aesthetic, parallel-test contract, standard backtest table). Read it first — this file only adds Claude-specific operational context on top.

`LICOES_DE_PRODUCAO.md` is the second thing to read before touching execution, sizing, or measurement method. It is the register of errors that already cost real money — the 2026-08-28 incident that zeroed the account, plus the accumulated record — each with the invariant that survived it. Written to be portable across language/platform, so it says *what must be true*, not *which API to call.

## Two products in one repo

The codebase is a **B3 trading robot** with two independent execution paths that share the same `strategy/` and `journal/`:

- **Swing / daily** — `strategy/*.py` (subclass of `strategy.base.Strategy`), decides once per session, runs on B3 stocks via `backtest/engine.py` or `live/runtime.py`.
- **Day trade / intraday** — `strategy/daytrade/lab/*.py` (subclass of `strategy.daytrade.base.IntradayStrategy`), decides bar-by-bar (M1 or tick), never carries overnight, runs on futures/stocks via `backtest/intraday/engine.py` or `live/intraday_runtime.py`.

They are deliberately kept apart: `IntradayStrategy` does not inherit from `Strategy`, so `strategy.discovery.discover_strategies()` never picks up a day trade robot for the daily podium (different instrument, capital, risk — incomparable). Each has its **own registry**:
- Daily: **auto-discovery** (`strategy/discovery.py`) — every concrete `Strategy` in `strategy/` is a candidate; the podium is computed from the journal by `scheduler.refresh_champion_rankings()`.
- Day trade: **explicit list** in `strategy/daytrade/registry.py` — order in that dict IS the podium.

The same live process (`scripts/run_live.py --slot swing|daytrade`) dispatches to the right runtime.

## Layer boundaries (from AGENTS.md — non-negotiable)

```
orchestration:  scheduler.py, live/, dashboard/       → may import anything
feature:        market_data, strategy, backtest,      → may import ONLY core/
                journal, market_data_intraday
core:           core/                                 → imports nothing from project
```

- Features do **not** import each other. If feature A needs data from feature B, it goes through a `core/` dataclass or through the SQLite journal.
- **Signal logic in `strategy/` must be pure** (OHLCV in → decisions out, no I/O, no DB). Reason: it will be ported to MQL5.
- **`live/` decides nothing.** The robot that trades real money is literally the same `Strategy` / `IntradayStrategy` instance the backtest runs. If `live/` adds a filter, rounding, or "safety" stop of its own, the backtest stops describing production and the validation history becomes fiction.
- **No look-ahead.** Decision at `close[D]` executes at `open[D+1]` (daily) or `open[bar t+1]` (intraday). This is enforced by the engine, not the strategy.

## Journal is the most valuable asset

When you add a new feature to the entry/exit snapshot, you MUST update **all four** places in sync — `tests/test_live_journal_rationale.py` fails if they diverge:
1. `signal_snapshots` table (backtest — `journal/schema.sql` via migration)
2. `live_signal_snapshots` table (real ops — same migration)
3. `core.models.MarketSnapshot`
4. `journal.live_store._SNAPSHOT_COLUMNS`

There are **two SQLite files on purpose** — `db/journal.sqlite` (backtest) and `db/live.sqlite` (live ops, tables prefixed `live_`) — so a long backtest thread in `dashboard/app.py` doesn't compete for the same file lock as a real-order write.

## Commands

**Dev loop (auto-bootstraps venv, deps, DB, market data, then runs the dashboard on http://127.0.0.1:8000):**
```
.\dev.bat                    # dashboard survives; live robots survive too
.\dev.bat --kill-robots      # also kills run_live.py processes on Ctrl+C
```

**Tests (always parallel — see AGENTS.md § "A suíte roda em PARALELO"):**
```
.\.venv\Scripts\python.exe -m pytest                              # full suite (~35s)
.\.venv\Scripts\python.exe -m pytest tests/test_gremah.py         # one file
.\.venv\Scripts\python.exe -m pytest tests/test_gremah.py::test_x # one test
.\.venv\Scripts\python.exe -m pytest -n0                          # force serial (debugging only)
```
`pyproject.toml` fixes `-n auto --dist load`. New tests must use `tmp_path` (no shared file paths) and must not depend on execution order — otherwise you get flaky failures under xdist.

**Backtest one strategy:**
```
.\.venv\Scripts\python.exe scripts/run_backtest.py --strategy buy_the_dip_5pct --start 2010 --end 2024
```

**Live operation:**
```
.\.venv\Scripts\python.exe scripts/run_live.py --slot swing    init --capital 50000 --mode mt5 --strategy liqflop
.\.venv\Scripts\python.exe scripts/run_live.py --slot swing    loop --seconds 60
.\.venv\Scripts\python.exe scripts/run_live.py --slot daytrade --strategy gremah loop --seconds 5
```
Default `--execution-mode` is `shadow` (journals everything, sends no orders). See `DEPLOY.md` for the NSSM service + Windows-only rationale.

**Parameter sweeps / exploratory scripts** live in `scripts/daytrade/` and `scripts/`. Follow the parallelism pattern in `scripts/daytrade/sweep_gremah_tick.py`: `ProcessPoolExecutor` with `submit`/`as_completed` (never `pool.map`), one `redirect_stdout` per unit, `flush=True` on every print, and **stream each unit's result as it finishes** — never wait for the whole sweep to speak.

## Standard backtest table — do not invent columns

Every day trade script must print results through `backtest/intraday/report.py`: call `linha_de_resultado()` then `tabela()`. The 12 base columns (`variante`, `retorno`, `líquido R$`, `MaxDD %`, `MaxDD R$`, `lucro/DD`, `win%`, `trades`, `R$/dia`, `trd/dia`, `capital final`, `pregões`) are fixed and always in that order. Anything a specific run needs goes into the `extras` dict — **after** the base, never in place of it. Numbers use BR decimals (comma). Reasons for the two non-obvious choices (`lucro/DD` instead of annualized Calmar; nocional capital blanks capital-dependent columns) are documented in the module.

## Capital inicial: sempre o mínimo real do instrumento

Every backtest / sweep starts from the **real** minimum cash to operate the instrument, never a round test value like "R$50k so it doesn't zero." A generic capital silently changes how many lots fit and whether the capital gate lets a session trade at all, which flips which geometry "wins."

**Regra por instrumento (2 lotes / 2× buffer de margem — `CAPITAL_MINIMO_EM_LOTES = MARGIN_BUFFER_FUTUROS = 2.0`):**

| Instrumento | Fórmula | Onde |
|---|---|---|
| Ação B3 | `preço_atual × 100 × 2` (2 lotes padrão) | `strategy.daytrade.base.capital_minimo_brl(preco)` |
| Mini-índice (WIN) | `margem × 2` = **R$100 × 2 = R$200** | `contracts_from_capital(cash, margin=100)` |
| Mini-dólar (WDO) | `margem × 2` = **R$150 × 2 = R$300** | `contracts_from_capital(cash, margin=150)` |

**Sizing de ENTRADA REAL usa `contracts_from_capital_com_reserva`, não `contracts_from_capital`** (2026-08-28, depois do incidente que zerou a conta). Ela empilha `RESERVA_CAIXA_SEGURANCA = 1.25` por cima do buffer — 20% do caixa nunca entra na conta de quantos contratos cabem. Consequência prática, que muda os números da tabela acima na hora de operar de verdade: **WIN precisa de >R$250 e WDO de >R$375** para abrir 1 contrato. Com o mínimo "de tabela" (R$200/R$300) os robôs ficam INERTES — e isso é informação, não bug: na medição os dois já zeravam sozinhos, o mínimo documentado nunca foi suficiente. A reserva só tornou isso visível no backtest em vez de no extrato.

Use `config_for(..., preco_atual=preco_ref)` para ação e `contracts_from_capital(cash, margin_per_contract, buffer=2.0)` para futuro — nunca digitar o número na mão. `enforce_capital_minimo` fica no default do perfil (ligado para ação) pelo mesmo motivo: desligar mede geometria isolada do caixa, que é outra pergunta. A tabela de saída sempre mostra o capital usado (a coluna, ou implícito em `capital final − líquido R$`).

## Testes rodam em paralelo — sempre

`pyproject.toml` fixa `-n auto --dist load` (pytest-xdist). Suite inteira mede 92s serial → 35s paralela nesta máquina, e o ciclo "mede → decide → mede de novo" é o trabalho: suite lenta é o gargalo do projeto. **Todo teste novo obedece duas condições, senão o paralelismo quebra em falha intermitente:**

1. **Sem caminho de arquivo fixo compartilhado.** `tmp_path` sempre. Dois workers ao mesmo tempo pegariam o mesmo arquivo.
2. **Sem dependência de ordem entre testes.** `--dist load` distribui teste-a-teste; ordem de coleta ≠ ordem de execução.

Mesmo espírito para **sweeps de parâmetro**: `ProcessPoolExecutor` com `submit`/`as_completed` (nunca `pool.map`, que trava resultado pronto atrás de unidade lenta), `redirect_stdout` por unidade, `flush=True` em todo print, cada unidade imprime a linha DELA assim que termina — resumo ordenado vem depois. Ver `scripts/daytrade/sweep_gremah_tick.py` e `scripts/daytrade/sweep_copa.py`.

## Front-end: HTMX + Terminal Editorial

FastAPI + Jinja2 templates in `src/dashboard/templates/` (partials in `partials/`) + HTMX for partial swaps + Plotly.js. **No SPA framework.** All templates inherit from `base.html`. Colors from `static/css/tokens.css` — never hardcode. Fonts: JetBrains Mono (data/numbers), Instrument Serif (headlines). When creating/editing a template, invoke the `frontend-design` skill.

## Windows-specific gotchas

- Shell is PowerShell; use `.\.venv\Scripts\python.exe`, not `./venv/bin/python`.
- No TA-Lib (C dependency, painful on Windows) — indicators live in `core/indicators.py` as pure `(pd.Series, ...) -> pd.Series` functions.
- Live ops require Windows because `MetaTrader5` Python only talks to a locally-running MT5 terminal via Windows IPC — see `DEPLOY.md`.
- `dev.bat` explicitly cleans up port 8000 in a loop because uvicorn `--reload`'s master + spawned child both bind the socket.

## What NOT to do (from AGENTS.md)

- Add dependencies without justification (project weight matters).
- Use TA-Lib.
- Swap SQLite for another DB in this phase.
- Introduce React/Vue/any SPA framework — HTMX solves it.
- Put multiple strategies in one file — **one strategy per file** in `strategy/` (this is what makes auto-discovery work).
