"""Teste sintetico de `WdoGeoGridReload` (Frente F4-wdo-geometria-sessao,
AGENTS.md: toda regra de entrada/saida em `strategy/` precisa de teste com
cenario sintetico). Cobre: (1) `n_levels=1` reproduz a mecanica do v1 de
acao (`GridReloadMaker`) com tick de pontos; (2) `n_levels>1` roda em
RODIZIO de distancia em vez de recarregar sempre a mesma; (3) alternancia de
lado ao fechar; (4) teto de reloads por lado; (5) stop agregado de sessao
fica DESLIGADO por padrao (diferenca deliberada frente ao v1)."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from core.models import IntradayExitReason
from strategy.daytrade.base import Bar, EnterLimit
from strategy.daytrade.lab.wdo_geo_grid_reload import WdoGeoGridReload


def _bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-05 13:00", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_primeira_ordem_com_um_nivel_reproduz_o_v1():
    strat = WdoGeoGridReload(level_spacing_ticks=16, profit_ticks=1, stop_ticks=16,
                              tick_size=0.5, n_levels=1)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert len(actions) == 1
    assert isinstance(actions[0], EnterLimit)
    assert actions[0].side == "long"
    assert actions[0].limit_price == pytest.approx(4992.0)   # 5000 - 16*0.5
    assert actions[0].initial_target == pytest.approx(4992.5)  # +1 tick
    assert actions[0].initial_stop == pytest.approx(4984.0)    # -16 ticks


def test_stop_ticks_none_desativa_o_stop_de_protecao():
    strat = WdoGeoGridReload(level_spacing_ticks=16, profit_ticks=1, stop_ticks=None, tick_size=0.5)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    assert actions[0].initial_stop is None


def test_rodizio_de_niveis_alterna_a_distancia_do_mesmo_lado():
    # 2 niveis no lado long: primeira armacao usa L0 (1x spacing), a
    # SEGUINTE vez que o long for armado (depois do short ter passado na
    # frente pela alternancia) usa L1 (2x spacing).
    strat = WdoGeoGridReload(level_spacing_ticks=10, profit_ticks=1, stop_ticks=50,
                              tick_size=0.5, n_levels=2)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar0 = Bar(ts=ts0, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    primeira = strat.on_bar(ts0, bar0, positions=[], session_pnl_brl=0.0)
    assert primeira[0].limit_price == pytest.approx(4995.0)  # L0: 5000 - 1*10*0.5

    # simula: o long acabou de fechar (open_side="long") -> a proxima
    # armacao alterna para "short" primeiro, consumindo o L0 do short; so'
    # depois disso o long volta a ser tentado e usa L1.
    strat._state.open_side = "long"
    strat._state.pending_side = None
    segunda = strat.on_bar(ts0, bar0, positions=[], session_pnl_brl=0.0)
    assert segunda[0].side == "short"
    assert segunda[0].limit_price == pytest.approx(5005.0)  # L0 do short

    strat._state.open_side = "short"
    strat._state.pending_side = None
    terceira = strat.on_bar(ts0, bar0, positions=[], session_pnl_brl=0.0)
    assert terceira[0].side == "long"
    assert terceira[0].limit_price == pytest.approx(4990.0)  # L1: 5000 - 2*10*0.5


def test_recarrega_apos_fechar_por_alvo_alternando_o_lado():
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0),  # define open, emite EnterLimit long @ 4992
        (5000.0, 5000.0, 5000.0, 5000.0),
        (4993.0, 4993.0, 4990.0, 4992.0),  # preenche long em 4992
        (4992.0, 4993.0, 4992.0, 4992.5),  # toca alvo 4992.5 -> fecha por TARGET
        (4992.5, 4992.5, 4992.5, 4992.5),  # sem posicao: recarrega SHORT (alternancia)
    ]
    bars = _bars(rows)
    strat = WdoGeoGridReload(level_spacing_ticks=16, profit_ticks=1, stop_ticks=16, tick_size=0.5)
    costs = IntradayCostModel(point_value_brl=10.0, tick_size=0.5, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    config = IntradayBacktestConfig(costs=costs, initial_capital=1_000.0,
                                     session_end_time=time(23, 59), target_fills_as_maker=True)

    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == IntradayExitReason.TARGET
    assert result.trades[0].side == "long"
    assert strat._state.pending_side == "short"
    assert strat._state.long_fills == 1
    assert strat._state.short_fills == 0


def test_max_trades_per_side_limita_recargas():
    strat = WdoGeoGridReload(level_spacing_ticks=16, profit_ticks=1, stop_ticks=16,
                              tick_size=0.5, max_trades_per_side=0)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    assert actions == []


def test_sem_stop_agregado_de_sessao_por_padrao():
    strat = WdoGeoGridReload(level_spacing_ticks=16, profit_ticks=1, stop_ticks=16, tick_size=0.5)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    # PnL de sessao bem negativo nao deve halt-ar nada (session_stop_brl=None default)
    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=-999_999.0)
    assert len(actions) == 1
    assert strat._state.session_halted is False
