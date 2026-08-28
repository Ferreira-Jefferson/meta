"""Teste da estrategia `wdo_fillreal_grid` com cenario sintetico (AGENTS.md:
toda regra de entrada/saida em `strategy/` -> teste com cenario sintetico).

Cobre as duas taticas novas (recuo de nivel, fatiamento de ordem) e os
contadores de preenchimento que a Frente F3 usa para medir taxa de
preenchimento simulada -- em especial o caso em que um FECHAMENTO e um
PREENCHIMENTO NOVO acontecem na MESMA barra (alvo de 1 tick torna isso
comum), onde um delta agregado ingenuo subestimaria o preenchimento."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from core.models import IntradayExitReason
from strategy.daytrade.base import Bar
from strategy.daytrade.lab.wdo_fillreal_grid import WdoFillRealismGrid


def _bars(rows: list[tuple[float, float, float, float, float]]) -> pd.DataFrame:
    """`rows`: (open, high, low, close, volume) por barra."""
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


def test_primeira_ordem_sem_recuo_usa_o_nivel_ideal():
    strat = WdoFillRealismGrid(tick_size=0.5, level_spacing_ticks=2, profit_ticks=1, stop_ticks=16,
                                retreat_ticks=0, quantity=1)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert len(actions) == 1
    order = actions[0]
    assert order.side == "long"
    assert order.limit_price == pytest.approx(4999.0)   # 5000 - 2 ticks
    assert order.initial_target == pytest.approx(4999.5)  # entrada + 1 tick
    assert order.initial_stop == pytest.approx(4991.0)    # entrada - 16 ticks
    assert order.split_quantities is None
    assert order.exit_split_unit is None
    assert strat.contracts_requested == 1
    assert strat.orders_armed == 1


def test_recuo_desloca_entrada_e_recalcula_alvo_a_partir_do_preco_real():
    """`retreat_ticks=2`: a ordem fica 2 ticks PIOR que o nivel ideal (compra
    mais barato) -- o alvo T1 continua exatamente 1 tick a partir do preco de
    entrada REAL (nao do nivel ideal), entao a geometria T1/S16 nao muda de
    definicao."""
    strat = WdoFillRealismGrid(tick_size=0.5, level_spacing_ticks=2, profit_ticks=1, stop_ticks=16,
                                retreat_ticks=2, quantity=1)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    order = actions[0]
    assert order.limit_price == pytest.approx(4998.0)     # nivel ideal 4999,0 - 2 ticks de recuo
    assert order.initial_target == pytest.approx(4998.5)  # entrada real + 1 tick, nao 4999,5
    assert order.initial_stop == pytest.approx(4990.0)    # entrada real - 16 ticks


def test_venda_recua_para_o_lado_pior_tambem():
    strat = WdoFillRealismGrid(tick_size=0.5, level_spacing_ticks=2, profit_ticks=1, stop_ticks=16,
                                retreat_ticks=2, quantity=1)
    strat._state.open_price = 5000.0
    level = strat._level_price("short")
    entry = strat._entry_price(level, "short")
    assert level == pytest.approx(5001.0)
    assert entry == pytest.approx(5002.0)  # vende mais CARO que o nivel ideal = pior para quem entra
    assert strat._target_price(entry, "short") == pytest.approx(5001.5)
    assert strat._stop_price(entry, "short") == pytest.approx(5010.0)


def test_split_entry_conta_2_preenchimentos_simultaneos_na_mesma_barra():
    """Fatia quantity=3 em 3 filhos de 1 contrato. A 3a barra preenche 2
    filhos DE UMA VEZ (mesma chave: mesmo side/ts/preco/quantidade) sem
    fechar nada -- a contagem por CHAVE precisa registrar os 2, nao 1."""
    strat = WdoFillRealismGrid(tick_size=0.5, level_spacing_ticks=2, profit_ticks=1, stop_ticks=16,
                                retreat_ticks=0, quantity=3, split_entry=True, max_trades_per_side=5)
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0, 10),   # define open=5000, arma LONG (3 filhos de 1) em 4999,0
        (5000.0, 5000.0, 4999.0, 4999.0, 1),    # toca o nivel; volume=1 so' preenche o 1o filho
        (4999.0, 4999.0, 4999.0, 4999.0, 2),    # NAO toca o alvo (4999,5); preenche os 2 filhos restantes juntos
        (4999.5, 4999.5, 4999.5, 4999.5, 5),    # agora fecha os 3 por ALVO na mesma barra
        (5001.0, 5001.0, 5001.0, 5001.0, 5),    # barra de cauda (nao pode ser `is_last_bar` a que fecha, senao
                                                 # o motor forca flatten ANTES da estrategia decidir de novo)
    ]
    bars = _bars(rows)
    cfg = _config(limit_fill_capped_by_volume=True)

    result = run_intraday_backtest(bars, strat, cfg)

    assert strat.contracts_filled == 3       # os 3 filhos do ciclo LONG preencheram (em 2 barras distintas)
    assert strat.contracts_requested == 6    # 3 do ciclo LONG + 3 do ciclo SHORT recarregado na barra 4
    assert strat.fill_rate_pct == pytest.approx(50.0)  # so' o ciclo LONG ja fechou; o SHORT acabou de armar
    assert len(result.trades) == 3
    assert all(t.exit_reason == IntradayExitReason.TARGET for t in result.trades)
    assert all(t.side == "long" for t in result.trades)
    assert sum(t.quantity for t in result.trades) == 3
    # o ciclo fechou por completo (os 3 fecharam juntos) -> recarregou o
    # lado OPOSTO (short) na propria barra 4.
    assert strat._state.armed is True
    assert strat._state.armed_side == "short"
    assert strat._state.long_attempts == 1
    assert strat._state.short_attempts == 1


def test_split_entry_com_alvo_apertado_orfaniza_filhos_ainda_parados():
    """Achado da mecanica real do motor (ver docstring do modulo): quando o
    1o filho preenchido bate o alvo de 1 tick ANTES dos irmaos preencherem,
    o motor CANCELA os irmaos ainda parados (`reason='position_closed'`) em
    vez de deixa-los esperando -- o ciclo fecha com MENOS que `quantity`
    contratos, e a estrategia considera o ciclo ENCERRADO (recarrega),
    nunca preso esperando um preenchimento que o motor ja' desistiu de
    tentar."""
    strat = WdoFillRealismGrid(tick_size=0.5, level_spacing_ticks=2, profit_ticks=1, stop_ticks=16,
                                retreat_ticks=0, quantity=3, split_entry=True, max_trades_per_side=5)
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0, 10),  # arma LONG (3 filhos) em 4999,0
        (5000.0, 5000.0, 4999.0, 4999.0, 1),   # preenche so' o 1o filho (volume=1)
        (4999.0, 4999.5, 4999.0, 4999.5, 3),   # bate o alvo do 1o filho -> fecha, orfaniza os 2 filhos parados
        (5001.0, 5001.0, 5001.0, 5001.0, 5),   # barra de cauda (ver comentario equivalente no teste acima)
    ]
    bars = _bars(rows)
    cfg = _config(limit_fill_capped_by_volume=True)

    result = run_intraday_backtest(bars, strat, cfg)

    assert strat.contracts_requested == 6   # 3 pedidos no ciclo LONG + 3 no ciclo SHORT recarregado
    assert strat.contracts_filled == 1      # so' 1 dos 3 preencheu -- os outros 2 foram orfanizados, nao contam
    assert strat.fill_rate_pct == pytest.approx(100.0 / 6.0)
    assert len(result.trades) == 1
    assert result.trades[0].quantity == 1
    assert strat._state.armed_side == "short"  # recarregou apos o ciclo (parcial) se encerrar


def test_split_entry_desliga_com_quantity_1():
    strat = WdoFillRealismGrid(tick_size=0.5, quantity=1, split_entry=True, split_exit=True)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    order = actions[0]
    assert order.split_quantities is None       # nada para fatiar com 1 contrato so'
    assert order.exit_split_unit is None


def test_max_trades_per_side_limita_recargas():
    strat = WdoFillRealismGrid(max_trades_per_side=0)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    assert actions == []
    assert strat.orders_armed == 0
    assert strat.fill_rate_pct is None
