"""Teste da estrategia `wdo_fillreal_grid_x1` (Frente F3-wdo-fill-realismo,
rodada 2). Cobre o que mudou frente a `wdo_fillreal_grid.py`/rodada 1
(geometria default x1 e `reanchor_mode`) e reconfirma o comportamento
herdado (recuo, fatiamento, contadores de preenchimento -- ver
`tests/test_wdo_fillreal_grid.py` para a cobertura original, nao
duplicada linha a linha aqui alem do minimo para nao depender do outro
arquivo)."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from core.models import IntradayExitReason
from strategy.daytrade.base import Bar
from strategy.daytrade.lab.wdo_fillreal_grid_x1 import WdoFillRealismGridX1


def _bars(rows: list[tuple[float, float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-05 13:00", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx)


def _config(limit_fill_capped_by_volume: bool = False) -> IntradayBacktestConfig:
    costs = IntradayCostModel(point_value_brl=10.0, tick_size=0.5, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    return IntradayBacktestConfig(
        costs=costs, initial_capital=100_000.0, session_end_time=time(23, 59),
        session_end_policy="fixed", target_fills_as_maker=True,
        limit_fill_capped_by_volume=limit_fill_capped_by_volume,
        max_open_contracts=10,
    )


def test_default_e_geometria_x1_com_ancora_rolling():
    """A correcao central desta rodada: default e' spacing=1 ("x1", nao 3
    como na rodada 1) e `reanchor_mode="rolling_last_price"`."""
    strat = WdoFillRealismGridX1()
    assert strat.level_spacing_ticks == 1
    assert strat.profit_ticks == 1
    assert strat.stop_ticks == 16
    assert strat.reanchor_mode == "rolling_last_price"


def test_primeira_ordem_usa_nivel_x1_a_partir_da_abertura():
    strat = WdoFillRealismGridX1(tick_size=0.5, retreat_ticks=0, quantity=1)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert len(actions) == 1
    order = actions[0]
    assert order.side == "long"
    assert order.limit_price == pytest.approx(4999.5)   # abertura - 1 tick (x1)
    assert order.initial_target == pytest.approx(5000.0)  # entrada + 1 tick
    assert order.initial_stop == pytest.approx(4991.5)    # entrada - 16 ticks
    assert strat.contracts_requested == 1


def test_no_tick_alinha_abertura_fora_da_grade():
    """A serie continua reporta preco fora da grade real (ver docstring do
    modulo) -- `WdoFillRealismGridX1` (diferente de `WdoFillRealismGrid`,
    rodada 1) alinha via `no_tick` antes de derivar niveis."""
    strat = WdoFillRealismGridX1(tick_size=0.5, retreat_ticks=0, quantity=1)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.17, high=5000.17, low=5000.17, close=5000.17, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    order = actions[0]
    # 5000.17 -> no_tick -> 5000.0; nivel = 5000.0 - 0.5 = 4999.5, na grade.
    assert order.limit_price == pytest.approx(4999.5)
    assert (order.limit_price / 0.5) == pytest.approx(round(order.limit_price / 0.5))


def test_reanchor_rolling_segue_o_fechamento_ao_armar_nova_ordem():
    """Depois que o 1o ciclo fecha, a proxima ordem (modo rolling) ancora no
    FECHAMENTO da barra em que ela e' armada -- nao mais na abertura da
    sessao. Entrada e fechamento por alvo precisam de barras SEPARADAS (o
    motor so' checa stop/alvo de uma posicao a partir da barra SEGUINTE ao
    preenchimento -- ver `IntradaySessionMachine.on_closed_bar`, passo 1 vs
    3b), entao o cenario usa 4 barras: arma, preenche, fecha (+ reancora), e
    uma barra de cauda para a decisao de reancorar nao cair na ULTIMA barra
    da sessao (que forca flatten ANTES da estrategia decidir de novo)."""
    strat = WdoFillRealismGridX1(tick_size=0.5, retreat_ticks=0, quantity=1,
                                  reanchor_mode="rolling_last_price", max_trades_per_side=5)
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0, 10),      # define open=5000,0, arma LONG em 4999,5
        (4999.5, 4999.5, 4999.5, 4999.5, 5),       # toca a entrada (low<=4999,5); ainda nao toca o alvo (5000,0)
        (4999.5, 5000.0, 4998.7, 4998.7, 5),       # alvo tocado (high=5000,0) -> fecha; fechamento=4998,7
        (5001.0, 5001.0, 5001.0, 5001.0, 5),       # barra de cauda, nao decide nada novo aqui
    ]
    bars = _bars(rows)
    cfg = _config(limit_fill_capped_by_volume=True)

    result = run_intraday_backtest(bars, strat, cfg)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == IntradayExitReason.TARGET
    # proxima ordem (SHORT, recarregado na barra 3) ancora no FECHAMENTO da
    # barra 3 (4998,7 -> no_tick -> 4998,5), nao mais na abertura (5000,0).
    assert strat._state.anchor_price == pytest.approx(4998.5)
    assert strat._state.armed_side == "short"


def test_reanchor_fixed_session_open_nunca_muda():
    strat = WdoFillRealismGridX1(tick_size=0.5, retreat_ticks=0, quantity=1,
                                  reanchor_mode="fixed_session_open", max_trades_per_side=5)
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0, 10),
        (4999.5, 4999.5, 4999.5, 4999.5, 5),
        (4999.5, 5000.0, 4998.7, 4998.7, 5),
        (5001.0, 5001.0, 5001.0, 5001.0, 5),
    ]
    bars = _bars(rows)
    cfg = _config(limit_fill_capped_by_volume=True)

    run_intraday_backtest(bars, strat, cfg)

    assert strat._state.anchor_price == pytest.approx(5000.0)  # continua a abertura, nao o fechamento
    assert strat._state.armed_side == "short"


def test_recuo_desloca_entrada_e_recalcula_alvo_a_partir_do_preco_real():
    strat = WdoFillRealismGridX1(tick_size=0.5, level_spacing_ticks=2, profit_ticks=1, stop_ticks=16,
                                  retreat_ticks=2, quantity=1)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    order = actions[0]
    assert order.limit_price == pytest.approx(4998.0)     # nivel ideal 4999,0 - 2 ticks de recuo
    assert order.initial_target == pytest.approx(4998.5)  # entrada real + 1 tick
    assert order.initial_stop == pytest.approx(4990.0)    # entrada real - 16 ticks


def test_split_entry_conta_2_preenchimentos_simultaneos_na_mesma_barra():
    strat = WdoFillRealismGridX1(tick_size=0.5, level_spacing_ticks=2, profit_ticks=1, stop_ticks=16,
                                  retreat_ticks=0, quantity=3, split_entry=True, max_trades_per_side=5)
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0, 10),
        (5000.0, 5000.0, 4999.0, 4999.0, 1),
        (4999.0, 4999.0, 4999.0, 4999.0, 2),
        (4999.5, 4999.5, 4999.5, 4999.5, 5),
        (5001.0, 5001.0, 5001.0, 5001.0, 5),
    ]
    bars = _bars(rows)
    cfg = _config(limit_fill_capped_by_volume=True)

    result = run_intraday_backtest(bars, strat, cfg)

    assert strat.contracts_filled == 3
    assert strat.contracts_requested == 6
    assert strat.fill_rate_pct == pytest.approx(50.0)
    assert len(result.trades) == 3
    assert all(t.exit_reason == IntradayExitReason.TARGET for t in result.trades)
    assert sum(t.quantity for t in result.trades) == 3


def test_split_entry_com_alvo_apertado_orfaniza_filhos_ainda_parados():
    strat = WdoFillRealismGridX1(tick_size=0.5, level_spacing_ticks=2, profit_ticks=1, stop_ticks=16,
                                  retreat_ticks=0, quantity=3, split_entry=True, max_trades_per_side=5)
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0, 10),
        (5000.0, 5000.0, 4999.0, 4999.0, 1),
        (4999.0, 4999.5, 4999.0, 4999.5, 3),
        (5001.0, 5001.0, 5001.0, 5001.0, 5),
    ]
    bars = _bars(rows)
    cfg = _config(limit_fill_capped_by_volume=True)

    result = run_intraday_backtest(bars, strat, cfg)

    assert strat.contracts_requested == 6
    assert strat.contracts_filled == 1
    assert len(result.trades) == 1
    assert result.trades[0].quantity == 1


def test_split_entry_desliga_com_quantity_1():
    strat = WdoFillRealismGridX1(tick_size=0.5, quantity=1, split_entry=True, split_exit=True)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    order = actions[0]
    assert order.split_quantities is None
    assert order.exit_split_unit is None


def test_max_trades_per_side_limita_recargas():
    strat = WdoFillRealismGridX1(max_trades_per_side=0)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    assert actions == []
    assert strat.orders_armed == 0
    assert strat.fill_rate_pct is None


def test_session_stop_brl_none_por_default_nao_interrompe():
    """Diferente da rodada 1 (`WdoFillRealismGrid`, default 500.0), esta
    versao nao tem teto agregado de sessao por default -- mesmo motivo
    documentado em `wdo_grid_reload_maker.py` (o candidato nao menciona teto
    de sessao)."""
    strat = WdoFillRealismGridX1(max_trades_per_side=1)
    assert strat.session_stop_brl is None
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=-999_999.0)
    assert len(actions) == 1  # nao interrompe mesmo com PnL de sessao muito negativo
