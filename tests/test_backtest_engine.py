"""Testes do engine event-driven: execução D+1, stops automáticos, sem look-ahead."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest.engine import run_backtest
from core.config import BENCHMARK, BacktestConfig
from core.models import ExitReason
from strategy.base import Action, Enter, Exit, OpenPosition, Strategy


class _StubStrategy(Strategy):
    name = "stub"
    version = "0.1"

    def __init__(self, entry_dates, exit_dates, tickers=("TEST.SA",)):
        self.entry_dates = set(pd.to_datetime(entry_dates))
        self.exit_dates = set(pd.to_datetime(exit_dates))
        self.tickers = tuple(tickers)

    def initialize(self, panels, ibov):
        pass

    def on_bar(
        self,
        date: pd.Timestamp,
        open_positions: dict[str, OpenPosition],
        cash_available: float,
    ) -> list[Action]:
        acts: list[Action] = []
        for t in self.tickers:
            if date in self.exit_dates and t in open_positions:
                acts.append(Exit(ticker=t, reason=ExitReason.CROSS_DOWN))
            if date in self.entry_dates and t not in open_positions:
                acts.append(Enter(ticker=t))
        return acts


def _fabricate_ohlcv(dates, prices):
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "adj_close": prices,
            "volume": [1_000_000] * len(prices),
        },
        index=dates,
    )


def test_entry_executes_next_day_at_open():
    dates = pd.date_range("2024-01-02", periods=10, freq="B")
    prices_up = list(np.linspace(10.0, 20.0, 10))
    ohlcv = _fabricate_ohlcv(dates, prices_up)
    ibov = _fabricate_ohlcv(dates, [100_000] * 10)

    strategy = _StubStrategy(entry_dates=[dates[2]], exit_dates=[dates[7]])
    config = BacktestConfig(
        initial_capital=100_000.0, max_concurrent_positions=1, lot_size=1, stop_loss_pct=0.0
    )
    universe = {"TEST.SA": ohlcv, BENCHMARK: ibov}

    result = run_backtest(universe, strategy, config, start="2024-01-02", end="2024-01-15")

    assert len(result.trades) == 1
    trade = result.trades[0]
    # Enter decidido no close de dates[2] → executa no open de dates[3]
    assert trade.entry_date == dates[3].date()
    # Exit decidido no close de dates[7] → executa no open de dates[8]
    assert trade.exit_date == dates[8].date()
    assert trade.pnl_pct > 0


def test_stop_loss_triggers_from_default_config():
    dates = pd.date_range("2024-01-02", periods=15, freq="B")
    # Preço estável e depois queda de 20% para disparar o stop de 15%
    prices = [50.0] * 3 + [50.0, 48.0, 46.0, 44.0, 40.0, 38.0] + [38.0] * 6
    ohlcv = _fabricate_ohlcv(dates, prices)
    ibov = _fabricate_ohlcv(dates, [100_000] * len(prices))

    strategy = _StubStrategy(entry_dates=[dates[2]], exit_dates=[])
    config = BacktestConfig(
        initial_capital=100_000.0, max_concurrent_positions=1, lot_size=1, stop_loss_pct=0.15
    )
    universe = {"TEST.SA": ohlcv, BENCHMARK: ibov}

    result = run_backtest(universe, strategy, config, start="2024-01-02", end="2024-02-01")

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == ExitReason.STOP


def test_no_lookahead_entry_signal_on_last_day_not_executed():
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    ohlcv = _fabricate_ohlcv(dates, [10.0] * 5)
    ibov = _fabricate_ohlcv(dates, [100_000] * 5)

    strategy = _StubStrategy(entry_dates=[dates[-1]], exit_dates=[])
    config = BacktestConfig(
        initial_capital=100_000.0, max_concurrent_positions=1, lot_size=1, stop_loss_pct=0.0
    )
    universe = {"TEST.SA": ohlcv, BENCHMARK: ibov}

    result = run_backtest(universe, strategy, config, start="2024-01-02", end="2024-01-10")

    # Signal no último dia → sem próximo bar para executar → nenhuma posição fechada
    # (o engine também não fecha posições que nem chegaram a ser abertas)
    assert result.trades == []
