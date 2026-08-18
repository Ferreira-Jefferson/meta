"""Gerenciador de simulações em execução.

Executa `run_backtest` em uma thread e publica eventos em uma fila que o
endpoint SSE do dashboard consome. Estado é mantido em memória — se o
processo cair, simulações em andamento são perdidas (aceitável para uso
local monousuário).
"""
from __future__ import annotations

import queue
import threading
import time
import traceback
import uuid
from typing import Iterable

import pandas as pd

from backtest.engine import run_backtest
from core.config import BENCHMARK, BacktestConfig
from journal.enrichment import enrich
from journal.writer import (
    append_equity,
    create_run,
    finalize_run,
    insert_trade,
    journal,
)
from market_data.loader import load_one
from strategy.registry import get_strategy


class Simulation:
    def __init__(self, sim_id: str, strategy_key: str, tickers: list[str], start: str, end: str, capital: float, lot_size: int = 100):
        self.id = sim_id
        self.strategy_key = strategy_key
        self.tickers = tickers
        self.start = start
        self.end = end
        self.capital = capital
        self.lot_size = lot_size
        self.status = "queued"
        self.run_id: int | None = None
        self.error: str | None = None
        self.events: queue.Queue = queue.Queue()
        self.thread: threading.Thread | None = None
        self.started_at = time.time()
        # Snapshots para replay quando cliente conecta tarde
        self.equity_history: list[dict] = []      # cada progress event
        self.log_history: list[dict] = []         # cada log
        self.done_payload: dict | None = None
        self.error_payload: dict | None = None
        # Live tracking de pico/vale (calculado on-the-fly)
        self.peak_equity: float = capital
        self.peak_date: str = start
        self.trough_equity: float = capital
        self.trough_date: str = start


_SIMULATIONS: dict[str, Simulation] = {}


def get(sim_id: str) -> Simulation | None:
    return _SIMULATIONS.get(sim_id)


def _emit(sim: Simulation, kind: str, payload: dict) -> None:
    if kind == "progress":
        sim.equity_history.append(payload)
        eq = payload.get("equity")
        date = payload.get("date")
        if eq is not None and date:
            if eq > sim.peak_equity:
                sim.peak_equity = eq
                sim.peak_date = date
            if eq < sim.trough_equity:
                sim.trough_equity = eq
                sim.trough_date = date
            payload["peak_equity"] = sim.peak_equity
            payload["peak_date"] = sim.peak_date
            payload["trough_equity"] = sim.trough_equity
            payload["trough_date"] = sim.trough_date
    elif kind == "log":
        sim.log_history.append(payload)
    elif kind == "done":
        payload["peak_equity"] = sim.peak_equity
        payload["peak_date"] = sim.peak_date
        payload["trough_equity"] = sim.trough_equity
        payload["trough_date"] = sim.trough_date
        sim.done_payload = payload
    elif kind == "error":
        sim.error_payload = payload
    sim.events.put((kind, payload))


def _run(sim: Simulation) -> None:
    try:
        sim.status = "loading"
        _emit(sim, "log", {"message": f"Carregando {len(sim.tickers)} ativos + IBOV..."})
        universe: dict[str, pd.DataFrame] = {}
        for t in sim.tickers:
            universe[t] = load_one(t)
        universe[BENCHMARK] = load_one(BENCHMARK)

        info = get_strategy(sim.strategy_key)
        strategy = info.factory()
        config = BacktestConfig(initial_capital=sim.capital, lot_size=sim.lot_size)

        sim.status = "running"
        _emit(sim, "log", {"message": f"Rodando {info.name} v{info.version} de {sim.start} a {sim.end}..."})

        def on_progress(p: dict) -> None:
            _emit(sim, "progress", p)

        result = run_backtest(
            universe, strategy, config,
            start=sim.start, end=sim.end,
            on_progress=on_progress,
        )

        _emit(sim, "log", {"message": f"Persistindo {len(result.trades)} trades no diário..."})
        with journal() as conn:
            run_id = create_run(
                conn,
                strategy_name=info.key,
                strategy_version=info.version,
                period_start=sim.start,
                period_end=sim.end,
                initial_capital=sim.capital,
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
            finalize_run(conn, run_id, result.metrics)

        sim.run_id = run_id
        sim.status = "done"
        final_equity = float(result.equity_curve.iloc[-1]) if len(result.equity_curve) else sim.capital
        _emit(sim, "done", {
            "run_id": run_id,
            "final_equity": final_equity,
            "initial_capital": sim.capital,
            "metrics": {
                "cagr": result.metrics["cagr"],
                "sharpe": result.metrics["sharpe"],
                "max_drawdown": result.metrics["max_drawdown"],
                "trades_count": result.metrics["trades_count"],
                "benchmark_cagr": result.metrics["benchmark_cagr"],
            },
        })
    except Exception as e:  # noqa: BLE001
        sim.status = "error"
        sim.error = f"{type(e).__name__}: {e}"
        traceback.print_exc()
        _emit(sim, "error", {"message": sim.error})


def start(
    strategy_key: str,
    tickers: Iterable[str],
    start_date: str,
    end_date: str,
    capital: float,
    lot_size: int = 100,
) -> Simulation:
    sim_id = uuid.uuid4().hex[:12]
    sim = Simulation(sim_id, strategy_key, list(tickers), start_date, end_date, capital, lot_size)
    _SIMULATIONS[sim_id] = sim
    sim.thread = threading.Thread(target=_run, args=(sim,), daemon=True)
    sim.thread.start()
    return sim
