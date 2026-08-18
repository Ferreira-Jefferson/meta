from __future__ import annotations

import functools
from pathlib import Path

import pandas as pd
import pytest

import scheduler as scheduler_mod
from core.config import BENCHMARK, WATCHLIST
from journal.writer import init_db, journal as real_journal
from strategy.base import Strategy


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "journal.sqlite"
    schema_path = Path(__file__).resolve().parents[1] / "src" / "journal" / "schema.sql"
    init_db(db_path=db_path, schema_path=schema_path)
    monkeypatch.setattr(scheduler_mod, "journal", functools.partial(real_journal, db_path=db_path))
    return db_path


class _FakeStrategy(Strategy):
    """Robô mínimo só para exercitar a seleção de universo em `_run_champion`."""

    name = "fake_bank_strategy"
    version = "1.0"

    def __init__(self, universe_tickers=None):
        self.universe_tickers = universe_tickers

    def on_bar(self, date, open_positions, cash_available):
        return []


class _FakeResult:
    def __init__(self, equity):
        self.equity_curve = equity
        self.benchmark_curve = equity.copy()
        self.trades = []
        self.metrics = {
            "final_capital": float(equity.iloc[-1]),
            "cagr": 0.01, "sharpe": 0.1, "sortino": 0.1, "max_drawdown": -0.05,
            "calmar": 0.2, "win_rate": 0.5, "profit_factor": 1.0,
            "trades_count": 0, "benchmark_cagr": 0.02,
        }


def _fake_universe(tickers):
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    frame = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)
    universe = {t: frame for t in tickers}
    universe[BENCHMARK] = frame
    return universe


def test_run_champion_uses_watchlist_when_strategy_has_no_universe(monkeypatch, tmp_db):
    """Sem `universe_tickers`, `_run_champion` deve continuar usando o WATCHLIST canonical (comportamento antigo preservado)."""
    calls = []

    def fake_load_universe(tickers=WATCHLIST, include_benchmark=True, out_dir=None):
        calls.append(tuple(tickers))
        return _fake_universe(tickers)

    monkeypatch.setattr(scheduler_mod, "load_universe", fake_load_universe)
    monkeypatch.setattr(
        scheduler_mod, "run_backtest_dispatch",
        lambda universe, strategy, config, start, end: _FakeResult(pd.Series([1000.0, 1010.0], index=pd.date_range("2024-01-01", periods=2)))
    )

    scheduler_mod._run_champion(
        "fake_bank_strategy", lambda: _FakeStrategy(universe_tickers=None),
        "2024-01-01", "2024-01-03", "champion_full",
    )

    assert calls == [tuple(WATCHLIST)]


def test_run_champion_uses_strategy_universe_when_set(monkeypatch, tmp_db):
    """Com `universe_tickers` definido (ex. robô especialista em bancos), `_run_champion`
    deve carregar EXATAMENTE esse universo, não o WATCHLIST — ativa o contrato que
    `strategy/base.py` já documentava mas que nenhum código lia (era morto).
    """
    bank_universe = ("ITUB4.SA", "BBDC4.SA", "BBAS3.SA")
    calls = []

    def fake_load_universe(tickers=WATCHLIST, include_benchmark=True, out_dir=None):
        calls.append(tuple(tickers))
        return _fake_universe(tickers)

    monkeypatch.setattr(scheduler_mod, "load_universe", fake_load_universe)
    monkeypatch.setattr(
        scheduler_mod, "run_backtest_dispatch",
        lambda universe, strategy, config, start, end: _FakeResult(pd.Series([1000.0, 1010.0], index=pd.date_range("2024-01-01", periods=2)))
    )

    scheduler_mod._run_champion(
        "fake_bank_strategy", lambda: _FakeStrategy(universe_tickers=bank_universe),
        "2024-01-01", "2024-01-03", "champion_full",
    )

    assert calls == [bank_universe]
