"""Scheduler: mantém dados frescos e rerroda o ranking automático de robôs.

- Janela FULL = HISTORY_START → data mais recente comum a todos os dados.
- Janela 5Y   = (data mais recente) - 5 anos → data mais recente (móvel).
- Janela 1Y   = último ano-calendário COMPLETO (ex.: 2025-01-01 → 2025-12-31
  enquanto 2026 não fechar) — fixa, não é uma janela móvel de 365 dias; avança
  sozinha quando o ano vigente terminar.
- TODO robô descoberto em `strategy/` (ver `strategy.discovery`) é rerrodado
  nas três janelas com o capital/lote do critério oficial de ranking
  (R$ 1.000, lote fracionário) e persistido no diário com `run_kind` marcado
  ('champion_full' / 'champion_3y') — isso que o ranking em
  `journal.reader.top_strategies_by_final_capital()` lê para montar o pódio.
  Não há promoção manual: um robô novo em `strategy/` entra na disputa no
  próximo refresh sem editar nada aqui.
- Uma run de campeão é considerada atual só quando cobre o período E foi
  calculada sobre o MESMO dado (`data_fingerprint`). Comparar apenas
  `period_end` deixava métrica velha no pódio: o provedor revisa closes
  ajustados retroativamente (split/dividendo/correção), mudando a série
  histórica inteira sem mover a última data um único dia.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pandas as pd

from backtest.metrics import negative_years
from backtest.runner import run as run_backtest_dispatch
from core.config import BENCHMARK, DB_PATH, HISTORY_START, WATCHLIST, BacktestConfig
from journal.enrichment import enrich
from journal.writer import append_equity, create_run, finalize_run, insert_trade, journal
from market_data.download import download_all
from market_data.loader import load_one, load_universe, universe_fingerprint
from strategy.registry import list_strategies

# Critério oficial de ranking (ver memória `ranking-criterion`): capital
# inicial pequeno, lote fracionário — não os R$ 100k/lote 100 do canonical antigo.
CHAMPION_CAPITAL = 1_000.0
CHAMPION_LOT_SIZE = 1
CHAMPION_5Y_YEARS = 5


# ---------- data freshness -------------------------------------------------

def latest_common_date() -> pd.Timestamp:
    """Última data comum a todos os parquets necessários (watchlist + IBOV + macro)."""
    latest: pd.Timestamp | None = None
    for t in list(WATCHLIST) + [BENCHMARK]:
        try:
            idx_last = load_one(t).index[-1]
        except FileNotFoundError:
            continue
        if latest is None or idx_last < latest:
            latest = idx_last

    for macro in ("selic", "usd_brl"):
        p = Path("data/raw") / f"{macro}.parquet"
        if p.exists():
            m_last = pd.read_parquet(p).index[-1]
            if latest is None or m_last < latest:
                latest = m_last

    return latest or pd.Timestamp.today().normalize()


# ---------- backtest execution --------------------------------------------

def _run_champion(strategy_key: str, factory, start: str, end: str, run_kind: str,
                  fingerprint: str | None = None) -> int:
    """Roda um backtest oficial de ranking e persiste. Retorna run_id."""
    strategy = factory()
    # universe_tickers permite a um robô experimental (setor bancário, universo
    # largo, etc.) escolher seu próprio universo em vez do WATCHLIST canonical
    # — ver o comentário em `strategy/base.py`.
    universe = load_universe(tickers=strategy.universe_tickers) if strategy.universe_tickers else load_universe()
    config = BacktestConfig(initial_capital=CHAMPION_CAPITAL, lot_size=CHAMPION_LOT_SIZE)
    result = run_backtest_dispatch(universe, strategy, config, start=start, end=end)

    metrics = dict(result.metrics)
    metrics["neg_years"] = negative_years(result.equity_curve)

    with journal() as conn:
        run_id = create_run(
            conn,
            strategy_name=strategy_key,
            strategy_version=strategy.version,
            period_start=start,
            period_end=end,
            initial_capital=config.initial_capital,
            run_kind=run_kind,
            data_fingerprint=fingerprint,
        )
        for trade in result.trades:
            trade.tags = enrich(trade)
            insert_trade(conn, run_id, trade)
        bench = result.benchmark_curve.reindex(result.equity_curve.index).ffill()
        equity_points = [
            (d.strftime("%Y-%m-%d"), float(e), float(bench.get(d)) if d in bench.index else None)
            for d, e in result.equity_curve.items()
        ]
        append_equity(conn, run_id, equity_points)
        finalize_run(conn, run_id, metrics)
    return run_id


def _latest_champion_state(
    strategy_key: str, run_kind: str, db_path: Path | None = None
) -> tuple[str | None, str | None]:
    """(period_end, data_fingerprint) da run oficial mais recente desse robô/janela."""
    with sqlite3.connect(db_path or DB_PATH) as c:
        cols = {row[1] for row in c.execute("PRAGMA table_info(runs)")}
        field = "data_fingerprint" if "data_fingerprint" in cols else "NULL"
        row = c.execute(
            f"SELECT period_end, {field} FROM runs WHERE strategy_name = ? AND run_kind = ? "
            "ORDER BY id DESC LIMIT 1",
            (strategy_key, run_kind),
        ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def _champion_is_current(
    strategy_key: str, run_kind: str, end: str, fingerprint: str
) -> bool:
    """A run gravada cobre o período E foi calculada sobre ESTE dado?

    A checagem de fingerprint é o que impede métrica stale no pódio: o yfinance
    revisa closes ajustados retroativamente (split, dividendo, correção), então
    a série de 2010-2025 pode mudar sem a última data avançar um dia. Antes daqui
    o ranking só olhava `period_end` e nunca rerrodava nesse caso.
    """
    last_end, last_fp = _latest_champion_state(strategy_key, run_kind)
    if (last_end or "0000-00-00") < end:
        return False
    return last_fp == fingerprint


# ---------- orchestration -------------------------------------------------

def refresh_champion_rankings(force: bool = False) -> dict:
    """Rerroda todo robô descoberto nas janelas FULL, 5Y e 1Y se os dados avançaram.

    force=True: rerroda mesmo se já está no dia (útil pra testar). Retorna
    resumo com {refreshed, failed, full_window, five_y_window, one_y_window}.
    """
    target_end_ts = latest_common_date()
    target_end = target_end_ts.strftime("%Y-%m-%d")
    five_y_start = (target_end_ts - pd.DateOffset(years=CHAMPION_5Y_YEARS)).strftime("%Y-%m-%d")
    # Último ano-calendário COMPLETO: se a data mais recente é em 2026, o
    # último ano fechado é 2025 (2026-01-01 -> 2025-12-31 continua sendo o
    # mesmo par até 2026 terminar). Janela fixa, não móvel.
    last_complete_year = target_end_ts.year - 1
    one_y_start = f"{last_complete_year}-01-01"
    one_y_end = f"{last_complete_year}-12-31"
    windows = [
        ("champion_full", HISTORY_START, target_end),
        ("champion_5y", five_y_start, target_end),
        ("champion_1y", one_y_start, one_y_end),
    ]

    refreshed: list[dict] = []
    failed: list[dict] = []
    strategies = list_strategies()
    print(f"[champion-refresh] target_end={target_end}, 5y_start={five_y_start}, "
          f"1y={one_y_start}..{one_y_end}, {len(strategies)} robôs")
    for info in strategies:
        # Fingerprint por robô: um robô com `universe_tickers` próprio (ex.
        # especialista em bancos) tem que ser invalidado quando O SEU dado
        # avança, não quando o WATCHLIST canonical avança — e vice-versa.
        strategy_tickers = info.factory().universe_tickers
        fingerprint = universe_fingerprint(tickers=strategy_tickers or WATCHLIST)
        for run_kind, start, end in windows:
            if not force and _champion_is_current(info.key, run_kind, end, fingerprint):
                continue
            t0 = time.perf_counter()
            try:
                run_id = _run_champion(info.key, info.factory, start, end, run_kind, fingerprint)
                dt = time.perf_counter() - t0
                print(f"  [ok] {info.key:30s} {run_kind:14s} run_id={run_id} {dt:.1f}s")
                refreshed.append({"key": info.key, "run_kind": run_kind, "run_id": run_id, "seconds": round(dt, 1)})
            except Exception as e:
                dt = time.perf_counter() - t0
                print(f"  [FAIL] {info.key:30s} {run_kind:14s} {dt:.1f}s → {type(e).__name__}: {e}")
                failed.append({"key": info.key, "run_kind": run_kind, "error": str(e)})
    return {
        "refreshed": refreshed,
        "failed": failed,
        "full_window": (HISTORY_START, target_end),
        "five_y_window": (five_y_start, target_end),
        "one_y_window": (one_y_start, one_y_end),
    }


def refresh_market_data() -> dict:
    """Baixa OHLCV + macro. Chamada periodicamente. Retorna paths escritos."""
    written = download_all()
    return {"paths": {k: str(v) for k, v in written.items()}}


def refresh_all(force_champions: bool = False) -> dict:
    """Fluxo completo: market data → ranking automático de robôs."""
    data = refresh_market_data()
    champions = refresh_champion_rankings(force=force_champions)
    return {"data": data, "champions": champions}
