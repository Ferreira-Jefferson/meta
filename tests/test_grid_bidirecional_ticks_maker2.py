"""Teste da hipotese grid_bidirecional_ticks_maker2 com cenario sintetico
(AGENTS.md: toda regra de entrada/saida em `strategy/` -> teste com
cenario sintetico). Cobre a diferenca frente ao v1: o alvo tambem vira
`initial_target` na `EnterLimit`, fechado pelo motor (sem gerenciamento
manual de Exit)."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from core.models import IntradayExitReason
from strategy.daytrade.base import Bar, EnterLimit
from strategy.daytrade.lab.grid_bidirecional_ticks_maker2 import GridBidirecionalTicksMaker2


def _bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-05 13:00", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_enterlimit_emitida_ja_carrega_initial_target():
    strat = GridBidirecionalTicksMaker2(legs_per_side=1, level_spacing_ticks=2, tick_size=0.01, profit_ticks=1)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=1.00, high=1.00, low=1.00, close=1.00, volume=10)

    actions = strat.on_bar(ts, bar, position=None, session_pnl_brl=0.0)

    assert len(actions) == 1
    assert isinstance(actions[0], EnterLimit)
    assert actions[0].limit_price == pytest.approx(0.98)
    assert actions[0].initial_target == pytest.approx(0.99)  # 0.98 + 1 tick


def test_integracao_entrada_e_alvo_ambos_sem_slippage_com_target_maker():
    rows = [
        (1.00, 1.00, 1.00, 1.00),   # define grid: long @ 0.98, target 0.99
        (1.00, 1.00, 1.00, 1.00),
        (0.99, 0.99, 0.97, 0.98),   # low=0.97 toca 0.98 -> preenche em 0.98 exato
        (0.98, 0.99, 0.98, 0.98),   # high=0.99 toca target -> fecha em 0.99 exato (maker)
        (0.99, 1.00, 0.98, 0.99),
    ]
    bars = _bars(rows)
    strat = GridBidirecionalTicksMaker2(legs_per_side=1, level_spacing_ticks=2, tick_size=0.01, profit_ticks=1)
    # slippage bem alto para provar que NEM entrada NEM alvo pagam nada.
    costs = IntradayCostModel(point_value_brl=1.0, tick_size=0.01, fee_round_trip_brl=0.0, slippage_ticks=5.0)
    config = IntradayBacktestConfig(costs=costs, session_end_time=time(23, 59), target_fills_as_maker=True)

    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(0.98)
    assert trade.exit_reason == IntradayExitReason.TARGET
    assert trade.exit_price == pytest.approx(0.99)
    assert trade.pnl_brl == pytest.approx(0.01 * trade.quantity)  # 1 tick liquido, sem custo nenhum
