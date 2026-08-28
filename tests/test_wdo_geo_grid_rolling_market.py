"""Teste sintetico de `WdoGeoGridRollingMarket` (Frente F4-wdo-geometria-sessao,
RODADA 2, AGENTS.md: toda regra de entrada/saida em `strategy/` precisa de
teste com cenario sintetico). Cobre a diferenca central frente ao irmao
maker (`WdoGeoGridRolling`): o armamento NAO dispara ordem nenhuma (so'
guarda o nivel internamente), a entrada `Enter` a mercado so' sai quando o
nivel E' TOCADO por uma barra fechada, e essa entrada executa na ABERTURA
da barra SEGUINTE (nunca na propria barra do toque -- mesma disciplina
anti-look-ahead do resto do motor). Tambem cobre reancoragem por
estagnacao (silenciosa, sem acao devolvida) e o ciclo completo via motor
(toque -> Enter -> fill no open seguinte -> alvo -> recarga alternando
lado)."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from core.models import IntradayExitReason
from strategy.daytrade.base import Bar, Enter
from strategy.daytrade.lab.wdo_geo_grid_rolling_market import WdoGeoGridRollingMarket


def _bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-05 13:00", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_armamento_nao_dispara_ordem_so_guarda_o_nivel():
    strat = WdoGeoGridRollingMarket(level_spacing_ticks=16, profit_ticks=1, stop_ticks=16, tick_size=0.5)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5001.0, low=4999.0, close=5000.5, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert actions == []  # diferenca central frente ao irmao maker: nao arma EnterLimit nenhuma
    assert strat._state.pending_side == "long"
    assert strat._state.pending_level_price == pytest.approx(4992.5)  # 5000.5 - 16*0.5 (ancora = CLOSE)
    assert strat._state.pending_target == pytest.approx(4993.0)
    assert strat._state.pending_stop == pytest.approx(4984.5)


def test_dispara_entrada_a_mercado_so_quando_o_nivel_e_tocado():
    strat = WdoGeoGridRollingMarket(level_spacing_ticks=16, profit_ticks=1, stop_ticks=16, tick_size=0.5)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")

    bar_armamento = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    strat.on_bar(ts, bar_armamento, positions=[], session_pnl_brl=0.0)  # level=4992

    bar_sem_toque = Bar(ts=ts, open=4995.0, high=4996.0, low=4993.5, close=4994.0, volume=10)
    sem_acao = strat.on_bar(ts, bar_sem_toque, positions=[], session_pnl_brl=0.0)
    assert sem_acao == []
    assert strat._state.pending_side == "long"  # nivel continua vivo, ainda nao tocou

    bar_toque = Bar(ts=ts, open=4993.0, high=4993.0, low=4990.0, close=4992.0, volume=10)
    disparo = strat.on_bar(ts, bar_toque, positions=[], session_pnl_brl=0.0)
    assert len(disparo) == 1
    assert isinstance(disparo[0], Enter)
    assert disparo[0].side == "long"
    assert disparo[0].initial_target == pytest.approx(4992.5)  # 4992 + 1*0.5
    assert disparo[0].initial_stop == pytest.approx(4984.0)    # 4992 - 16*0.5
    # o robo NAO limpa `pending_side` sozinho aqui -- so' o motor, confirmando
    # o fill na barra seguinte (ver `on_bar`, ramo `if positions:`).
    assert strat._state.pending_side == "long"


def test_reancora_apos_estagnacao_sem_devolver_acao():
    strat = WdoGeoGridRollingMarket(level_spacing_ticks=10, profit_ticks=1, stop_ticks=50,
                                     tick_size=0.5, rolling_reanchor_after_bars=2)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar1 = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    strat.on_bar(ts, bar1, positions=[], session_pnl_brl=0.0)
    assert strat._state.pending_level_price == pytest.approx(4995.0)
    assert strat._state.pending_bars_waited == 0

    bar2 = Bar(ts=ts, open=5010.0, high=5010.0, low=5010.0, close=5010.0, volume=10)
    assert strat.on_bar(ts, bar2, positions=[], session_pnl_brl=0.0) == []
    assert strat._state.pending_bars_waited == 1

    bar2b = Bar(ts=ts, open=5015.0, high=5015.0, low=5015.0, close=5015.0, volume=10)
    assert strat.on_bar(ts, bar2b, positions=[], session_pnl_brl=0.0) == []
    assert strat._state.pending_bars_waited == 2

    # estagnou (waited >= 2): reancora no preco ATUAL, SEM devolver acao
    # (diferenca frente ao irmao maker, que devolveria uma nova EnterLimit
    # para o motor vigiar -- aqui nao ha ordem nenhuma no motor ainda).
    bar3 = Bar(ts=ts, open=5020.0, high=5020.0, low=5020.0, close=5020.0, volume=10)
    reancorada = strat.on_bar(ts, bar3, positions=[], session_pnl_brl=0.0)
    assert reancorada == []
    assert strat._state.pending_side == "long"
    assert strat._state.pending_level_price == pytest.approx(5015.0)  # 5020 - 10*0.5
    assert strat._state.pending_bars_waited == 0


def test_ciclo_completo_via_motor_toque_fill_no_open_seguinte_alvo_recarga():
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0),  # arma long, nivel=4992 -- SEM ordem no motor
        (4995.0, 4995.0, 4990.0, 4992.0),  # toca o nivel -> decide Enter(long) aqui
        (4988.0, 4989.0, 4987.0, 4988.5),  # Enter executa no OPEN desta barra (4988) -- fill confirmado
        (4990.0, 4993.0, 4990.0, 4992.5),  # toca alvo (high >= 4992.5) -> fecha por TARGET
        (4992.5, 4992.5, 4992.5, 4992.5),  # sem posicao -> arma SHORT (alterna o lado)
    ]
    bars = _bars(rows)
    strat = WdoGeoGridRollingMarket(level_spacing_ticks=16, profit_ticks=1, stop_ticks=16, tick_size=0.5)
    costs = IntradayCostModel(point_value_brl=10.0, tick_size=0.5, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    config = IntradayBacktestConfig(costs=costs, initial_capital=1_000.0,
                                     session_end_time=time(23, 59), target_fills_as_maker=True)

    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side == "long"
    assert trade.exit_reason == IntradayExitReason.TARGET
    assert trade.entry_price == pytest.approx(4988.0)   # open da barra SEGUINTE ao toque, slippage=0
    assert trade.exit_price == pytest.approx(4992.5)    # alvo, ainda maker (target_fills_as_maker=True)
    assert strat._state.pending_side == "short"          # recarregou alternando o lado


def test_max_trades_per_side_limita_recargas():
    strat = WdoGeoGridRollingMarket(level_spacing_ticks=16, profit_ticks=1, stop_ticks=16,
                                     tick_size=0.5, max_trades_per_side=0)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    assert actions == []
    assert strat._state.pending_side is None


def test_sem_stop_agregado_de_sessao_por_padrao():
    strat = WdoGeoGridRollingMarket(level_spacing_ticks=16, profit_ticks=1, stop_ticks=16, tick_size=0.5)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=-999_999.0)
    assert actions == []  # armou (guardou o nivel), so' nao ha ordem pra cancelar
    assert strat._state.session_halted is False
    assert strat._state.pending_side == "long"
