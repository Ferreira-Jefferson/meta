"""Teste da hipotese ORB com cenario sintetico (AGENTS.md: toda regra de
entrada/saida em `strategy/` -> teste com cenario sintetico)."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import FuturesCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from core.models import IntradayExitReason
from strategy.daytrade.base import Bar
from strategy.daytrade.opening_range_breakout import OpeningRangeBreakout


def _bar(o, h, l, c):
    return Bar(ts=pd.Timestamp("2026-01-05 09:00", tz="UTC"), open=o, high=h, low=l, close=c, volume=10)


def test_forma_range_e_nao_decide_nada_dentro_da_janela():
    strat = OpeningRangeBreakout(range_minutes=5)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 09:00", tz="UTC")

    actions = strat.on_bar(ts0, _bar(100, 105, 95, 100), position=None, session_pnl_brl=0.0)

    assert actions == []
    assert strat._state.range_high == 105
    assert strat._state.range_low == 95


def test_rompimento_de_alta_apos_o_range_entra_comprado_com_stop_e_alvo_corretos():
    strat = OpeningRangeBreakout(range_minutes=5, target_r_multiple=1.5)
    strat.on_session_start(None)
    base = pd.Timestamp("2026-01-05 09:00", tz="UTC")

    strat.on_bar(base, _bar(100, 105, 95, 100), position=None, session_pnl_brl=0.0)
    for i in range(1, 5):
        strat.on_bar(base + pd.Timedelta(minutes=i), _bar(100, 105, 95, 100), position=None, session_pnl_brl=0.0)

    # range = [95, 105] (tamanho 10); rompimento para cima
    actions = strat.on_bar(base + pd.Timedelta(minutes=5), _bar(105, 112, 104, 110), position=None, session_pnl_brl=0.0)

    assert len(actions) == 1
    enter = actions[0]
    assert enter.side == "long"
    assert enter.initial_stop == pytest.approx(95.0)
    assert enter.initial_target == pytest.approx(110.0 + 1.5 * 10.0)


def test_uma_entrada_por_sessao():
    strat = OpeningRangeBreakout(range_minutes=1, target_r_multiple=1.0)
    strat.on_session_start(None)
    base = pd.Timestamp("2026-01-05 09:00", tz="UTC")

    strat.on_bar(base, _bar(100, 105, 95, 100), position=None, session_pnl_brl=0.0)
    primeira = strat.on_bar(base + pd.Timedelta(minutes=1), _bar(105, 112, 104, 110), position=None, session_pnl_brl=0.0)
    segunda = strat.on_bar(base + pd.Timedelta(minutes=2), _bar(110, 115, 109, 112), position=None, session_pnl_brl=0.0)

    assert len(primeira) == 1
    assert segunda == []


def test_reseta_estado_entre_sessoes():
    strat = OpeningRangeBreakout(range_minutes=1)
    strat.on_session_start(None)
    base = pd.Timestamp("2026-01-05 09:00", tz="UTC")
    strat.on_bar(base, _bar(100, 105, 95, 100), position=None, session_pnl_brl=0.0)
    strat.on_bar(base + pd.Timedelta(minutes=1), _bar(105, 112, 104, 110), position=None, session_pnl_brl=0.0)

    strat.on_session_start(None)  # nova sessao

    assert strat._state.range_high is None
    assert strat._state.traded_today is False


def test_integracao_com_o_motor_entra_e_sai_pelo_target():
    rows = [
        (100, 105, 95, 100),   # formando range (5 min)
        (100, 105, 95, 100),
        (100, 105, 95, 100),
        (100, 105, 95, 100),
        (100, 105, 95, 100),
        (105, 112, 104, 110),  # rompe alta -> Enter no proximo open
        (111, 113, 110, 111),  # executa entrada no open=111
        (120, 135, 119, 130),  # toca target (110 + 1.5*10 = 125)
        (125, 126, 124, 125),
    ]
    idx = pd.date_range("2026-01-05 09:00", periods=len(rows), freq="1min", tz="UTC")
    bars = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    bars["tick_volume"] = 10

    strat = OpeningRangeBreakout(range_minutes=5, target_r_multiple=1.5)
    costs = FuturesCostModel(point_value_brl=0.2, tick_size=1.0, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    config = IntradayBacktestConfig(costs=costs, session_end_time=time(23, 59))

    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side == "long"
    assert trade.entry_price == pytest.approx(111.0)
    assert trade.exit_reason == IntradayExitReason.TARGET
    assert trade.exit_price == pytest.approx(125.0)
