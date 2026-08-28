"""Teste da hipotese wdo_grid_reload_maker com cenario sintetico (AGENTS.md:
toda regra de entrada/saida em `strategy/` -> teste com cenario sintetico).

Cobre: primeira ordem (nivel/alvo/stop no tick certo), stop_ticks=None
desativando a protecao, recarga do mesmo nivel apos fechar por alvo
(alternando o lado), fechamento por stop tambem recarrega, teto de
`max_trades_per_side`, e o `session_stop_brl` opcional (default
desligado -- ver a docstring do modulo para o porque de nao herdar o
default de acao)."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from core.models import IntradayExitReason
from strategy.daytrade.base import Bar, EnterLimit
from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker


def _bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-05 13:00", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_primeira_ordem_t1_s16_x1_no_tick_certo():
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert len(actions) == 1
    assert isinstance(actions[0], EnterLimit)
    assert actions[0].side == "long"
    assert actions[0].limit_price == pytest.approx(4999.5)   # 1 tick (x1) abaixo da abertura
    assert actions[0].initial_target == pytest.approx(5000.0)  # +1 tick (T1)
    assert actions[0].initial_stop == pytest.approx(4991.5)    # -16 ticks (S16)


def test_stop_ticks_none_desativa_o_stop_de_protecao():
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=None)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    assert actions[0].initial_stop is None


def test_session_stop_brl_default_desligado_nao_interrompe_sessao():
    """Diferente de `GridReloadMaker` (default 30.0, calibrado p/ acao), o
    default aqui e' `None` -- uma perda de sessao grande (em escala de
    futuro) NAO deve achatar o robo sem pedido explicito."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    # session_pnl_brl bem negativo (maior que qualquer stop_brl herdado de
    # acao) -- sem `session_stop_brl` explicito, a estrategia continua
    # operando normalmente.
    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=-500.0)
    assert len(actions) == 1
    assert isinstance(actions[0], EnterLimit)


def test_session_stop_brl_explicito_interrompe_a_sessao():
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
                                session_stop_brl=100.0)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=-150.0)
    assert actions == []
    assert strat._state.session_halted is True


def test_recarrega_apos_fechar_por_alvo_alternando_o_lado():
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0),   # define open=5000.0, emite EnterLimit long @ 4999.5
        (5000.0, 5000.0, 5000.0, 5000.0),
        (4999.7, 4999.7, 4999.4, 4999.5),   # preenche long em 4999.5
        (4999.5, 5000.1, 4999.5, 5000.0),   # toca alvo 5000.0 -> fecha por TARGET
        (5000.0, 5000.0, 5000.0, 5000.0),   # sem posicao: deve recarregar o lado SHORT agora (alternancia)
    ]
    bars = _bars(rows)
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16)
    costs = IntradayCostModel(point_value_brl=10.0, tick_size=0.5, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    config = IntradayBacktestConfig(costs=costs, initial_capital=1_000_000.0,
                                     session_end_time=time(23, 59), target_fills_as_maker=True)

    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == IntradayExitReason.TARGET
    assert result.trades[0].side == "long"
    assert strat._state.pending_side == "short"
    assert strat._state.long_fills == 1
    assert strat._state.short_fills == 0


def test_reancoragem_fixed_session_open_mantem_o_mesmo_nivel_apos_stop():
    """Modo `reanchor_mode="fixed_session_open"` (mesma mecanica do
    `GridReloadMaker` original de acao, NAO o default aqui -- ver a
    docstring do modulo): o nivel do lado que recarrega continua ancorado
    no OPEN original da sessao, nao no preco onde o stop fechou."""
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0),   # open=5000.0, EnterLimit long @ 4999.5
        (5000.0, 5000.0, 5000.0, 5000.0),
        (4999.7, 4999.7, 4999.4, 4999.5),   # preenche long em 4999.5
        (4999.5, 4999.5, 4991.0, 4991.5),   # cai 16 ticks -> fecha por STOP
        (4991.5, 4991.5, 4991.5, 4991.5),   # sem posicao: recarrega SHORT (alternancia), nivel a partir do open ORIGINAL
    ]
    bars = _bars(rows)
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
                                reanchor_mode="fixed_session_open")
    costs = IntradayCostModel(point_value_brl=10.0, tick_size=0.5, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    config = IntradayBacktestConfig(costs=costs, initial_capital=1_000_000.0,
                                     session_end_time=time(23, 59), target_fills_as_maker=True)

    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == IntradayExitReason.STOP
    assert result.trades[0].pnl_brl == pytest.approx(-16 * 0.5 * 10.0, rel=1e-6)
    assert strat._state.pending_side == "short"
    # o nivel do lado short continua ancorado no open ORIGINAL da sessao
    # (5000.0), nao no preco onde o stop fechou.
    assert strat._level_price("short") == pytest.approx(5000.5)


def test_reancoragem_rolling_last_price_segue_o_preco_apos_stop():
    """Default `reanchor_mode="rolling_last_price"`: apos o stop fechar em
    4991,5, o proximo rearme ancora no FECHAMENTO da barra em que arma (nao
    mais no open original de 5000,0) -- mesmo espirito do modo "rolling" de
    `Gremah`."""
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0),   # open=5000.0, EnterLimit long @ 4999.5
        (5000.0, 5000.0, 5000.0, 5000.0),
        (4999.7, 4999.7, 4999.4, 4999.5),   # preenche long em 4999.5
        (4999.5, 4999.5, 4991.0, 4991.5),   # cai 16 ticks -> fecha por STOP
        (4991.5, 4991.5, 4991.5, 4991.5),   # sem posicao: recarrega SHORT ancorado no close desta barra (4991,5)
    ]
    bars = _bars(rows)
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16)
    costs = IntradayCostModel(point_value_brl=10.0, tick_size=0.5, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    config = IntradayBacktestConfig(costs=costs, initial_capital=1_000_000.0,
                                     session_end_time=time(23, 59), target_fills_as_maker=True)

    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == IntradayExitReason.STOP
    assert strat._state.pending_side == "short"
    # ancora seguiu o preco ate 4991,5 -- nivel short = ancora + 1 tick
    assert strat._level_price("short") == pytest.approx(4992.0)


def test_preco_de_abertura_e_ajustado_a_grade_do_tick():
    """A serie continua reporta preco fora da grade real (ex.: 5769,053
    contra multiplos de 0,5 do WDOV26) -- o robo tem de ancorar no preco
    ARREDONDADO (`no_tick`), senao todo nivel derivado sai fora da grade."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5769.053, high=5769.053, low=5769.053, close=5769.053, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert strat._state.open_price == pytest.approx(5769.0)
    assert actions[0].limit_price == pytest.approx(5768.5)
    assert actions[0].initial_target == pytest.approx(5769.0)
    assert actions[0].initial_stop == pytest.approx(5760.5)


def test_max_trades_per_side_limita_recargas():
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
                                max_trades_per_side=0)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    assert actions == []  # os dois lados ja esgotaram o limite de 0


# ---------- realocacao dinamica por CAPITAL (2026-08-27, aditiva/opt-in) ----
# `margin_per_contract_brl=None` (default) tem que continuar byte-a-byte
# identico ao comportamento de antes: `quantity` viaja intacto (inclusive
# `None`) para `EnterLimit`, e o motor decide via `default_quantity`.

def _primeira_ordem(strat: WdoGridReloadMaker):
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)
    assert len(actions) == 1 and isinstance(actions[0], EnterLimit)
    return actions[0]


def test_sem_margin_per_contract_brl_quantity_viaja_intacto_como_antes():
    """Regressao: `quantity=None` (default do robo) continua virando
    `quantity=None` na `EnterLimit` -- e' o motor quem decide via
    `IntradayBacktestConfig.default_quantity`, exatamente como sempre foi.
    Chamar `on_capital_update` com qualquer caixa nao pode mudar isto."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16)
    strat.on_capital_update(1_000_000.0)
    ordem = _primeira_ordem(strat)
    assert ordem.quantity is None


def test_quantity_fixo_explicito_tambem_viaja_intacto_sem_margin_per_contract_brl():
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
                                quantity=3)
    strat.on_capital_update(1_000_000.0)   # sem efeito -- modo antigo ignora o caixa
    ordem = _primeira_ordem(strat)
    assert ordem.quantity == 3


def test_capital_baixo_encolhe_a_quantidade_ate_1_contrato():
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
                                margin_per_contract_brl=150.0, hard_cap_contratos=5)
    strat.on_capital_update(300.0)   # 300 / (150 x buffer 2.0) = 1 contrato
    ordem = _primeira_ordem(strat)
    assert ordem.quantity == 1


def test_capital_alto_nunca_ultrapassa_o_hard_cap():
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
                                margin_per_contract_brl=150.0, hard_cap_contratos=5)
    strat.on_capital_update(1_000_000.0)   # caixa sustentaria centenas de contratos
    ordem = _primeira_ordem(strat)
    assert ordem.quantity == 5

    # caixa intermediario: fica ABAIXO do hard cap, nunca acima.
    strat2 = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
                                 margin_per_contract_brl=150.0, hard_cap_contratos=5)
    strat2.on_capital_update(900.0)   # 900 / (150 x 2.0) = 3 contratos
    ordem2 = _primeira_ordem(strat2)
    assert ordem2.quantity == 3


def test_on_capital_update_nunca_chamado_ainda_produz_pelo_menos_1_contrato():
    """`_cash_atual_brl` comeca em 0.0 -- mesmo assim, com
    `margin_per_contract_brl` setado, a quantidade nunca cai para 0 (mesmo
    espirito do piso de `Gremah._lotes_por_realocacao`)."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
                                margin_per_contract_brl=150.0, hard_cap_contratos=5)
    ordem = _primeira_ordem(strat)
    assert ordem.quantity == 1
