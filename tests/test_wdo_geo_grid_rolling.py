"""Teste sintetico de `WdoGeoGridRolling` (Frente F4-wdo-geometria-sessao,
AGENTS.md: toda regra de entrada/saida em `strategy/` precisa de teste com
cenario sintetico). Cobre: ancora = `bar.close` no armamento, reancoragem
por estagnacao (`rolling_reanchor_after_bars`), alternancia de lado,
rodizio de `n_levels`, teto de reloads por lado e stop agregado desligado
por padrao."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from core.models import IntradayExitReason
from strategy.daytrade.base import Bar, EnterLimit
from strategy.daytrade.lab.wdo_geo_grid_rolling import WdoGeoGridRolling


def _bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-05 13:00", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_primeira_ordem_ancora_no_close_da_barra():
    strat = WdoGeoGridRolling(level_spacing_ticks=16, profit_ticks=1, stop_ticks=16, tick_size=0.5)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5001.0, low=4999.0, close=5000.5, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert len(actions) == 1
    assert isinstance(actions[0], EnterLimit)
    assert actions[0].side == "long"
    assert actions[0].limit_price == pytest.approx(4992.5)   # 5000.5 - 16*0.5 (ancora = CLOSE, nao open)
    assert actions[0].initial_target == pytest.approx(4993.0)
    assert actions[0].initial_stop == pytest.approx(4984.5)


def test_reancora_apos_estagnacao_sem_perder_o_lado():
    strat = WdoGeoGridRolling(level_spacing_ticks=10, profit_ticks=1, stop_ticks=50,
                               tick_size=0.5, rolling_reanchor_after_bars=2)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar1 = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    primeira = strat.on_bar(ts, bar1, positions=[], session_pnl_brl=0.0)
    assert primeira[0].limit_price == pytest.approx(4995.0)
    assert strat._state.pending_bars_waited == 0

    # ainda nao estagnou nas 2 proximas chamadas (waited sobe 0 -> 1 -> 2,
    # so' fica >= rolling_reanchor_after_bars=2 na TERCEIRA chamada seguida)
    bar2 = Bar(ts=ts, open=5010.0, high=5010.0, low=5010.0, close=5010.0, volume=10)
    sem_acao = strat.on_bar(ts, bar2, positions=[], session_pnl_brl=0.0)
    assert sem_acao == []
    assert strat._state.pending_bars_waited == 1

    bar2b = Bar(ts=ts, open=5015.0, high=5015.0, low=5015.0, close=5015.0, volume=10)
    ainda_sem_acao = strat.on_bar(ts, bar2b, positions=[], session_pnl_brl=0.0)
    assert ainda_sem_acao == []
    assert strat._state.pending_bars_waited == 2

    # agora estagnou (waited >= 2): reancora no preco ATUAL, mesmo lado
    bar3 = Bar(ts=ts, open=5020.0, high=5020.0, low=5020.0, close=5020.0, volume=10)
    reancorada = strat.on_bar(ts, bar3, positions=[], session_pnl_brl=0.0)
    assert reancorada[0].side == "long"
    assert reancorada[0].limit_price == pytest.approx(5015.0)  # 5020 - 10*0.5


def test_rodizio_de_niveis_alterna_a_distancia_do_mesmo_lado():
    strat = WdoGeoGridRolling(level_spacing_ticks=10, profit_ticks=1, stop_ticks=50,
                               tick_size=0.5, n_levels=2)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    primeira = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    assert primeira[0].limit_price == pytest.approx(4995.0)  # L0

    strat._state.open_side = "long"
    strat._state.pending_side = None
    segunda = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    assert segunda[0].side == "short"
    assert segunda[0].limit_price == pytest.approx(5005.0)  # L0 do short

    strat._state.open_side = "short"
    strat._state.pending_side = None
    terceira = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    assert terceira[0].side == "long"
    assert terceira[0].limit_price == pytest.approx(4990.0)  # L1 do long


def test_recarrega_apos_fechar_por_alvo_alternando_o_lado():
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0),  # ancora=5000, EnterLimit long @ 4992
        (5000.0, 5000.0, 5000.0, 5000.0),
        (4993.0, 4993.0, 4990.0, 4992.0),  # preenche long em 4992
        (4992.0, 4993.0, 4992.0, 4992.5),  # toca alvo -> fecha por TARGET
        (4992.5, 4992.5, 4992.5, 4992.5),  # sem posicao: recarrega SHORT
    ]
    bars = _bars(rows)
    strat = WdoGeoGridRolling(level_spacing_ticks=16, profit_ticks=1, stop_ticks=16, tick_size=0.5)
    costs = IntradayCostModel(point_value_brl=10.0, tick_size=0.5, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    config = IntradayBacktestConfig(costs=costs, initial_capital=1_000.0,
                                     session_end_time=time(23, 59), target_fills_as_maker=True)

    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == IntradayExitReason.TARGET
    assert result.trades[0].side == "long"
    assert strat._state.pending_side == "short"


def test_max_trades_per_side_limita_recargas():
    strat = WdoGeoGridRolling(level_spacing_ticks=16, profit_ticks=1, stop_ticks=16,
                               tick_size=0.5, max_trades_per_side=0)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    assert actions == []


def test_sem_stop_agregado_de_sessao_por_padrao():
    strat = WdoGeoGridRolling(level_spacing_ticks=16, profit_ticks=1, stop_ticks=16, tick_size=0.5)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=-999_999.0)
    assert len(actions) == 1
    assert strat._state.session_halted is False
