"""Teste da hipotese grid_reload_maker com cenario sintetico (AGENTS.md:
toda regra de entrada/saida em `strategy/` -> teste com cenario
sintetico). Cobre as duas ideias novas frente ao v2: recarga do mesmo
nivel apos fechar, e stop largo de protecao por posicao."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from core.models import IntradayExitReason
from strategy.daytrade.base import Bar, EnterLimit
from strategy.daytrade.lab.grid_reload_maker import GridReloadMaker


def _bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-05 13:00", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_primeira_ordem_carrega_target_e_stop_largo():
    strat = GridReloadMaker(level_spacing_ticks=3, profit_ticks=1, stop_ticks=20, tick_size=0.01)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=1.00, high=1.00, low=1.00, close=1.00, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert len(actions) == 1
    assert isinstance(actions[0], EnterLimit)
    assert actions[0].side == "long"
    assert actions[0].limit_price == pytest.approx(0.97)
    assert actions[0].initial_target == pytest.approx(0.98)
    assert actions[0].initial_stop == pytest.approx(0.77)  # 0.97 - 20 ticks


def test_stop_ticks_none_desativa_o_stop_de_protecao():
    strat = GridReloadMaker(level_spacing_ticks=3, profit_ticks=1, stop_ticks=None, tick_size=0.01)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=1.00, high=1.00, low=1.00, close=1.00, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    assert actions[0].initial_stop is None


def test_recarrega_apos_fechar_por_alvo_alternando_o_lado():
    rows = [
        (1.00, 1.00, 1.00, 1.00),   # define open=1.00, emite EnterLimit long @ 0.97
        (1.00, 1.00, 1.00, 1.00),
        (0.98, 0.98, 0.96, 0.97),   # preenche long em 0.97
        (0.97, 0.99, 0.97, 0.98),   # toca alvo 0.98 -> fecha por TARGET
        (0.98, 0.98, 0.98, 0.98),   # sem posicao: deve recarregar o lado SHORT agora (alternancia)
    ]
    bars = _bars(rows)
    strat = GridReloadMaker(level_spacing_ticks=3, profit_ticks=1, stop_ticks=20, tick_size=0.01)
    costs = IntradayCostModel(point_value_brl=1.0, tick_size=0.01, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    config = IntradayBacktestConfig(costs=costs, initial_capital=1_000.0,
                                     session_end_time=time(23, 59), target_fills_as_maker=True)

    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == IntradayExitReason.TARGET
    assert result.trades[0].side == "long"
    # depois de fechar, o proximo lado armado deve ser "short" (alternancia)
    assert strat._state.pending_side == "short"
    assert strat._state.long_fills == 1
    assert strat._state.short_fills == 0


def test_max_trades_per_side_limita_recargas():
    strat = GridReloadMaker(level_spacing_ticks=3, profit_ticks=1, stop_ticks=20, tick_size=0.01, max_trades_per_side=0)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=1.00, high=1.00, low=1.00, close=1.00, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    assert actions == []  # os dois lados ja esgotaram o limite de 0
