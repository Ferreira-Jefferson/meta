"""Teste da hipotese wdo_grid_reload_maker com cenario sintetico (AGENTS.md:
toda regra de entrada/saida em `strategy/` -> teste com cenario sintetico).

Cobre: primeira ordem (nivel/alvo/stop no tick certo), stop_ticks=None
desativando a protecao, recarga do mesmo nivel apos fechar por alvo
(alternando o lado), fechamento por stop tambem recarrega, teto de
`max_trades_per_side`, o `session_stop_brl` opcional (default
desligado -- ver a docstring do modulo para o porque de nao herdar o
default de acao), e a reancoragem/reprecificacao (2026-09-04, item 4.9 de
LICOES_DE_PRODUCAO.md) de uma EnterLimit PENDENTE quando o preco se afasta
sem tocar, no modo rolling (cancela e reabre no nivel novo, mesmo lado) e
a ausencia desse comportamento no modo fixed_session_open (fora de
escopo)."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from core.models import IntradayExitReason
from strategy.daytrade.base import Bar, EnterLimit, Exit, IntradayOpenPosition
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


def test_reancoragem_rolling_reprecifica_ordem_pendente_quando_preco_se_afasta():
    """Bug real corrigido em 2026-09-04 (LICOES_DE_PRODUCAO.md item 4.9):
    ate' entao, uma vez armada, a EnterLimit pendente ficava ESTACIONADA
    pelo resto do pregao se o preco se afastasse sem voltar a tocar nela --
    `on_bar` devolvia cedo sempre que `pending_side is not None`. Medido em
    producao: o robo ficou "ativo" so' 0%-14,3% do pregao em varios dias.

    Cenario: ordem long arma a 4999,5 (ancora=5000,0). Preco sobe e fecha em
    5010,0 sem NUNCA tocar 4999,5 -- com o bug antigo o robo ficaria mudo
    pelo resto da sessao. Com o fix, `on_bar` reancora na barra em que o
    preco se afastou e devolve uma NOVA EnterLimit no nivel atualizado
    (mesmo lado). O motor entao cancela a ordem antiga e arma a nova
    (`LimitPlaced(replaced=...)` / `LimitCancelled(reason="superseded")`),
    que preenche quando o preco volta a tocar o nivel NOVO."""
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0),   # open=5000,0 -> EnterLimit long @ 4999,5
        (5000.0, 5010.0, 5000.0, 5010.0),   # preco sobe e fecha em 5010,0, NUNCA toca 4999,5
        (5010.0, 5010.0, 5010.0, 5010.0),   # confirma que a ordem antiga continua sem tocar
        (5010.0, 5010.0, 5009.4, 5009.5),   # toca o NIVEL NOVO (5009,5 = 5010,0 - 1 tick)
        (5009.5, 5009.5, 5009.5, 5009.5),   # barra extra -- a barra anterior NAO pode ser a
                                             # ultima da sessao, senao o flatten forcado (fim de
                                             # dado) roda ANTES da checagem de fill (passo (2)
                                             # precede o passo (3b) em `_on_closed_bar_core`)
    ]
    bars = _bars(rows)
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16)
    costs = IntradayCostModel(point_value_brl=10.0, tick_size=0.5, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    config = IntradayBacktestConfig(costs=costs, initial_capital=1_000_000.0,
                                     session_end_time=time(23, 59), target_fills_as_maker=True)

    result = run_intraday_backtest(bars, strat, config)

    # preencheu no nivel NOVO (5009,5), nao no nivel original (4999,5) --
    # prova que a ordem antiga foi cancelada e a nova, no preco atualizado,
    # e' quem de fato executou.
    assert len(result.trades) == 1
    assert result.trades[0].side == "long"
    assert result.trades[0].entry_price == pytest.approx(5009.5)
    # o LADO pendente nunca mudou por causa do reprecamento -- so' o preco.
    assert strat._state.pending_side is None  # preencheu, fill confirmado


def test_reancoragem_rolling_mantem_o_lado_pendente_ao_reprecar():
    """Chamada direta a `on_bar` (sem motor): confirma que reprecar uma
    ordem pendente NUNCA troca o lado -- so' o preco/nivel muda. Referencia:
    LICOES_DE_PRODUCAO.md item 4.9."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar0 = Bar(ts=ts0, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    primeira = strat.on_bar(ts0, bar0, positions=[], session_pnl_brl=0.0)
    assert primeira[0].side == "long"
    assert primeira[0].limit_price == pytest.approx(4999.5)
    assert strat._state.pending_side == "long"

    # preco se afasta e fecha bem acima, sem tocar a ordem pendente -- a
    # ordem NAO deve mais ficar parada no nivel velho.
    ts1 = ts0 + pd.Timedelta(minutes=1)
    bar1 = Bar(ts=ts1, open=5000.0, high=5010.0, low=5000.0, close=5010.0, volume=10)
    segunda = strat.on_bar(ts1, bar1, positions=[], session_pnl_brl=0.0)

    assert len(segunda) == 1
    assert isinstance(segunda[0], EnterLimit)
    assert segunda[0].side == "long"                       # MESMO lado, nunca muda so' por reprecar
    assert segunda[0].limit_price == pytest.approx(5009.5)  # nivel novo: 5010,0 - 1 tick
    assert strat._state.pending_side == "long"


def test_reancoragem_fixed_session_open_nao_reprecifica_ordem_pendente():
    """Escopo do fix (item 4.9) e' SO' o modo rolling -- `fixed_session_open`
    continua devolvendo `[]` (nao reprecifica, nao cancela) enquanto a
    ordem esta pendente, mesmo com o preco se afastando muito."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
                                reanchor_mode="fixed_session_open")
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar0 = Bar(ts=ts0, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    strat.on_bar(ts0, bar0, positions=[], session_pnl_brl=0.0)
    assert strat._state.pending_side == "long"

    ts1 = ts0 + pd.Timedelta(minutes=1)
    bar1 = Bar(ts=ts1, open=5000.0, high=5010.0, low=5000.0, close=5010.0, volume=10)
    segunda = strat.on_bar(ts1, bar1, positions=[], session_pnl_brl=0.0)

    assert segunda == []
    assert strat._state.pending_side == "long"
    assert strat._level_price("long") == pytest.approx(4999.5)  # nivel original, intocado


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
    # 900 / (150 x 2.0) = 3 contratos SEM reserva, mas `_quantidade_da_entrada`
    # usa `contracts_from_capital_com_reserva` desde 2026-08-28 (incidente
    # real, ver a docstring do modulo e `strategy.daytrade.base.RESERVA_
    # CAIXA_SEGURANCA`) -- buffer efetivo 2.0 x 1.25 = 2.5, entao
    # 900 / (150 x 2.5) = 2.4 -> 2 contratos.
    strat2.on_capital_update(900.0)
    ordem2 = _primeira_ordem(strat2)
    assert ordem2.quantity == 2


def test_on_capital_update_nunca_chamado_ainda_produz_pelo_menos_1_contrato():
    """`_cash_atual_brl` comeca em 0.0 -- mesmo assim, com
    `margin_per_contract_brl` setado, a quantidade nunca cai para 0 (mesmo
    espirito do piso de `Gremah._lotes_por_realocacao`)."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
                                margin_per_contract_brl=150.0, hard_cap_contratos=5)
    ordem = _primeira_ordem(strat)
    assert ordem.quantity == 1


# ---------- trailing sobre o lucro (2026-09-04, aditivo/opt-in) -------------
# `trailing_ativo=False` (default) tem que continuar byte-a-byte identico ao
# alvo ESTATICO de sempre -- ver a docstring do parametro em `__init__`.


def test_trailing_desligado_preserva_alvo_estatico_de_sempre():
    """Regressao: `trailing_ativo=False` (default, explicito aqui) preserva o
    alvo ESTATICO byte a byte -- `initial_target` continua sendo
    `profit_ticks` ticks do nivel, exatamente como antes deste parametro
    existir (mesma asserção de `test_primeira_ordem_t1_s16_x1_no_tick_certo`,
    so' que com o `profit_ticks=2` de producao atual e o flag explicito)."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2, stop_ticks=16,
                                trailing_ativo=False)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert len(actions) == 1
    assert isinstance(actions[0], EnterLimit)
    assert actions[0].initial_target == pytest.approx(5000.5)   # +2 ticks (T2) do nivel 4999,5, estatico
    assert actions[0].initial_stop == pytest.approx(4991.5)     # -16 ticks (S16), intacto


def test_trailing_ativo_entrada_sai_sem_alvo_estatico_stop_intacto():
    """`trailing_ativo=True`: a `EnterLimit` da entrada NAO carrega mais
    `initial_target` nenhum (fica `None` -- e' este `on_bar`, e so' ele, quem
    decide quando o lucro fecha) -- o STOP nao muda em nada."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2, stop_ticks=16,
                                trailing_ativo=True, trailing_recuo_ticks=1)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert len(actions) == 1
    assert isinstance(actions[0], EnterLimit)
    assert actions[0].initial_target is None
    assert actions[0].initial_stop == pytest.approx(4991.5)   # -16 ticks (S16), intacto


def test_trailing_ativo_sem_recuo_ticks_levanta_erro():
    """`trailing_recuo_ticks` e' OBRIGATORIO junto de `trailing_ativo=True`
    -- sem N nenhuma regra existe pra decidir, e nao ha' default "vencedor"
    (decisao de producao em aberto)."""
    with pytest.raises(ValueError):
        WdoGridReloadMaker(tick_size=0.5, profit_ticks=2, stop_ticks=16, trailing_ativo=True)


def test_trailing_recuo_ticks_negativo_levanta_erro():
    with pytest.raises(ValueError):
        WdoGridReloadMaker(tick_size=0.5, profit_ticks=2, stop_ticks=16,
                            trailing_ativo=True, trailing_recuo_ticks=-1)


def _posicao_long(entry_ts, entry_price: float, current_stop: float) -> IntradayOpenPosition:
    return IntradayOpenPosition(
        side="long", entry_ts=entry_ts, entry_price=entry_price, quantity=1,
        current_stop=current_stop, current_target=None, bars_held=0,
    )


def test_trailing_nao_fecha_antes_do_piso_e_tolera_recuo_dentro_do_limite():
    """`profit_ticks=2` (piso), `trailing_recuo_ticks=2`: a posicao bate
    EXATAMENTE o piso (recuo=0 dali, nao fecha) e depois recua 1 tick do
    pico -- como 1 <= 2 (o limiar configurado), a posicao continua aberta.
    Chamada direta a `on_bar` (sem motor), mesmo padrao de
    `test_reancoragem_rolling_mantem_o_lado_pendente_ao_reprecar`."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2, stop_ticks=16,
                                trailing_ativo=True, trailing_recuo_ticks=2)
    strat.on_session_start(None)
    entry_ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    pos = _posicao_long(entry_ts, entry_price=4999.5, current_stop=4991.5)

    # bate EXATAMENTE o piso de 2 ticks (4999,5 + 1,0 = 5000,5)
    ts1 = entry_ts + pd.Timedelta(seconds=1)
    bar1 = Bar(ts=ts1, open=5000.5, high=5000.5, low=5000.5, close=5000.5, volume=10)
    assert strat.on_bar(ts1, bar1, positions=[pos], session_pnl_brl=0.0) == []

    # recua 1 tick do pico (5000,5 -> 5000,0) -- dentro da tolerancia de 2
    ts2 = ts1 + pd.Timedelta(seconds=1)
    bar2 = Bar(ts=ts2, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=10)
    assert strat.on_bar(ts2, bar2, positions=[pos], session_pnl_brl=0.0) == []


def test_trailing_fecha_quando_o_recuo_ultrapassa_o_limiar():
    """Mesmo cenario do teste anterior, mas o recuo AVANCA alem do limiar
    configurado (`trailing_recuo_ticks=2`, recuo chega a 3): fecha com
    `Exit(reason="trailing_lucro")`."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2, stop_ticks=16,
                                trailing_ativo=True, trailing_recuo_ticks=2)
    strat.on_session_start(None)
    entry_ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    pos = _posicao_long(entry_ts, entry_price=4999.5, current_stop=4991.5)

    ts1 = entry_ts + pd.Timedelta(seconds=1)
    bar1 = Bar(ts=ts1, open=5000.5, high=5000.5, low=5000.5, close=5000.5, volume=10)
    assert strat.on_bar(ts1, bar1, positions=[pos], session_pnl_brl=0.0) == []  # bate o piso

    # recua 3 ticks do pico (5000,5 -> 4999,0) -- alem do limiar de 2
    ts2 = ts1 + pd.Timedelta(seconds=1)
    bar2 = Bar(ts=ts2, open=4999.0, high=4999.0, low=4999.0, close=4999.0, volume=10)
    acoes = strat.on_bar(ts2, bar2, positions=[pos], session_pnl_brl=0.0)

    assert len(acoes) == 1
    assert isinstance(acoes[0], Exit)
    assert acoes[0].reason == "trailing_lucro"


def test_trailing_recuo_zero_fecha_no_primeiro_tick_contra_via_motor():
    """`trailing_recuo_ticks=0` ("sem folga nenhuma"): NAO fecha no proprio
    tick que toca o piso (ali o recuo e' 0 -- aquele preco VIROU o pico),
    fecha no PRIMEIRO tick seguinte que nao fizer novo pico. Motor completo
    (`run_intraday_backtest`), nao chamada direta -- prova que a acao
    `Exit` enfileirada de fato executa (na ABERTURA da barra SEGUINTE,
    anti-look-ahead, mesmo mecanismo ja' usado por `defesa_recuo`), nao so'
    que `on_bar` a devolveria."""
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0),   # open=5000,0 -> EnterLimit long @ 4999,5, SEM alvo estatico
        (5000.0, 5000.0, 5000.0, 5000.0),   # ainda pendente (reancora no mesmo nivel, sem tocar)
        (4999.7, 4999.7, 4999.4, 4999.5),   # preenche long em 4999,5 -- pico=4999,7, so' 0,4 tick, piso nao batido
        (5000.5, 5000.5, 5000.5, 5000.5),   # bate EXATAMENTE o piso (2 ticks) -- pico=5000,5, recuo=0, nao fecha
        (5000.0, 5000.0, 5000.0, 5000.0),   # nao faz novo pico -- recuo=1 tick > 0 -- ENFILEIRA Exit
        (5000.0, 5000.0, 5000.0, 5000.0),   # Exit executa na ABERTURA desta barra (5000,0)
        (5000.0, 5000.0, 5000.0, 5000.0),   # barra extra -- esta NAO pode ser a ultima da sessao,
                                             # senao o flatten forcado roda ANTES do Exit enfileirado
                                             # (passo (2) precede o passo (3) em `_on_closed_bar_core`)
    ]
    bars = _bars(rows)
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2, stop_ticks=16,
                                trailing_ativo=True, trailing_recuo_ticks=0)
    costs = IntradayCostModel(point_value_brl=10.0, tick_size=0.5, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    config = IntradayBacktestConfig(costs=costs, initial_capital=1_000_000.0,
                                     session_end_time=time(23, 59), target_fills_as_maker=True)

    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == IntradayExitReason.SIGNAL   # motor mapeia todo Exit(reason=...) da estrategia p/ SIGNAL
    assert trade.side == "long"
    assert trade.entry_price == pytest.approx(4999.5)
    assert trade.exit_price == pytest.approx(5000.0)         # 1 tick capturado (deu de volta 1 do pico de 2)


def test_trailing_ativo_stop_continua_funcionando_igual():
    """`trailing_ativo=True`, mas o preco NUNCA bate o piso -- cai direto 16
    ticks. O STOP fecha exatamente como sempre (gerido pelo motor, nunca
    consultando `on_bar`/o trailing): mesmo cenario e mesmas asserções de
    `test_reancoragem_rolling_last_price_segue_o_preco_apos_stop`, so' com
    `trailing_ativo` ligado por cima para provar que nao interfere."""
    rows = [
        (5000.0, 5000.0, 5000.0, 5000.0),   # open=5000,0 -> EnterLimit long @ 4999,5, SEM alvo estatico
        (5000.0, 5000.0, 5000.0, 5000.0),
        (4999.7, 4999.7, 4999.4, 4999.5),   # preenche long em 4999,5 -- pico=4999,7, piso (2 ticks) nao batido
        (4999.5, 4999.5, 4991.0, 4991.5),   # cai 16 ticks -> fecha por STOP (o motor, sem consultar on_bar)
        (4991.5, 4991.5, 4991.5, 4991.5),   # sem posicao: recarrega SHORT (alternancia)
    ]
    bars = _bars(rows)
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2, stop_ticks=16,
                                trailing_ativo=True, trailing_recuo_ticks=1)
    costs = IntradayCostModel(point_value_brl=10.0, tick_size=0.5, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    config = IntradayBacktestConfig(costs=costs, initial_capital=1_000_000.0,
                                     session_end_time=time(23, 59), target_fills_as_maker=True)

    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == IntradayExitReason.STOP
    assert result.trades[0].pnl_brl == pytest.approx(-16 * 0.5 * 10.0, rel=1e-6)
    assert strat._state.pending_side == "short"
    assert strat._level_price("short") == pytest.approx(4992.0)


# ---------- gate de atividade pre-entrada (2026-09-07, aditivo/opt-in) ------
# `gate_atividade_ativo=False` (default) tem que continuar byte-a-byte
# identico ao comportamento de antes -- ver a docstring do parametro em
# `__init__` (correlacao volume/volatilidade x duracao do trade, achada por
# analise sobre `scripts/daytrade/wdof1_mfe_mae_semana_2026_09_04.py`).


def test_gate_desligado_ignora_volume_baixo():
    """Regressao: sem `gate_atividade_ativo` (default `False`), a estrategia
    arma normalmente mesmo com volume ZERO na barra -- o gate nao existe
    para esta chamada."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=0.0)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert len(actions) == 1
    assert isinstance(actions[0], EnterLimit)
    assert strat.gate_bloqueios == 0


def test_gate_ativo_bloqueia_armamento_com_volume_abaixo_do_limiar():
    """Volume da barra (5) fica ABAIXO do limiar (100) -- o robo NAO arma
    nada nesta chamada (devolve `[]`), `pending_side` continua `None`, e o
    bloqueio e' contado em `gate_bloqueios`."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
                                gate_atividade_ativo=True, gate_volume_min=100.0, gate_janela_segundos=15)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=5.0)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert actions == []
    assert strat._state.pending_side is None
    assert strat.gate_bloqueios == 1


def test_gate_ativo_permite_armamento_com_volume_acima_do_limiar():
    """Mesmo limiar do teste anterior, mas o volume da barra (200) fica
    ACIMA -- arma normalmente, sem bloqueio."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
                                gate_atividade_ativo=True, gate_volume_min=100.0, gate_janela_segundos=15)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=200.0)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert len(actions) == 1
    assert isinstance(actions[0], EnterLimit)
    assert actions[0].side == "long"
    assert strat._state.pending_side == "long"
    assert strat.gate_bloqueios == 0


def test_gate_acumula_volume_de_varios_ticks_dentro_da_janela():
    """Nenhum tick sozinho cruza o limiar (100), mas a SOMA de tres ticks
    dentro da janela de 15s cruza -- o robo so' arma no tick em que a soma
    ultrapassa, nao antes."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
                                gate_atividade_ativo=True, gate_volume_min=100.0, gate_janela_segundos=15)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    bar0 = Bar(ts=ts0, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=40.0)
    assert strat.on_bar(ts0, bar0, positions=[], session_pnl_brl=0.0) == []
    assert strat.gate_bloqueios == 1

    ts1 = ts0 + pd.Timedelta(seconds=2)
    bar1 = Bar(ts=ts1, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=40.0)
    assert strat.on_bar(ts1, bar1, positions=[], session_pnl_brl=0.0) == []  # soma=80, ainda <=100
    assert strat.gate_bloqueios == 2

    ts2 = ts1 + pd.Timedelta(seconds=2)
    bar2 = Bar(ts=ts2, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=40.0)
    acoes = strat.on_bar(ts2, bar2, positions=[], session_pnl_brl=0.0)  # soma=120, > 100 -- arma
    assert len(acoes) == 1
    assert isinstance(acoes[0], EnterLimit)
    assert strat.gate_bloqueios == 2  # nao incrementou de novo neste tick


def test_gate_nao_se_aplica_a_reancoragem_de_ordem_ja_pendente():
    """Escopo do gate (pedido do dono): so' o PRIMEIRO armamento de uma
    entrada passa pela checagem de volume -- a reancoragem/reprecamento de
    uma ordem JA' pendente (item 4.9) nunca e' bloqueada por volume baixo,
    mesmo com o gate ligado.

    `reancora_min_segundos=0.0` desliga o freio de reprecificacao (2026-09-07)
    de proposito: o cenario abaixo reprecifica 1 SEGUNDO depois de armar, e o
    default de 6s bloquearia a reancoragem por TEMPO -- o teste passaria a
    medir o freio, nao o gate. Ver a cobertura propria do freio no fim deste
    arquivo."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
                                gate_atividade_ativo=True, gate_volume_min=10.0, gate_janela_segundos=15,
                                reancora_min_segundos=0.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    bar0 = Bar(ts=ts0, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=50.0)
    primeira = strat.on_bar(ts0, bar0, positions=[], session_pnl_brl=0.0)
    assert len(primeira) == 1 and primeira[0].side == "long"
    assert strat._state.pending_side == "long"
    assert strat.gate_bloqueios == 0

    # preco se afasta sem tocar a ordem pendente -- reancora (item 4.9) com
    # volume ZERO nesta barra, bem abaixo do limiar (10.0).
    ts1 = ts0 + pd.Timedelta(seconds=1)
    bar1 = Bar(ts=ts1, open=5000.0, high=5010.0, low=5000.0, close=5010.0, volume=0.0)
    segunda = strat.on_bar(ts1, bar1, positions=[], session_pnl_brl=0.0)

    assert len(segunda) == 1
    assert isinstance(segunda[0], EnterLimit)
    assert segunda[0].side == "long"
    assert segunda[0].limit_price == pytest.approx(5009.5)
    assert strat.gate_bloqueios == 0  # reancoragem nunca conta como bloqueio


def test_gate_atividade_ativo_sem_volume_min_levanta_erro():
    """Mesmo padrao de `trailing_ativo`/`trailing_recuo_ticks`: nao ha'
    limiar 'vencedor' default -- exige `gate_volume_min` explicito."""
    with pytest.raises(ValueError):
        WdoGridReloadMaker(tick_size=0.5, profit_ticks=1, stop_ticks=16, gate_atividade_ativo=True)


def test_gate_volume_min_negativo_levanta_erro():
    with pytest.raises(ValueError):
        WdoGridReloadMaker(tick_size=0.5, profit_ticks=1, stop_ticks=16,
                            gate_atividade_ativo=True, gate_volume_min=-1.0)


def test_gate_janela_segundos_nao_positiva_levanta_erro():
    with pytest.raises(ValueError):
        WdoGridReloadMaker(tick_size=0.5, profit_ticks=1, stop_ticks=16,
                            gate_atividade_ativo=True, gate_volume_min=10.0, gate_janela_segundos=0)


# ---------------------------------------------------------------------------
# Freio de reprecificacao (2026-09-07) -- ver `reancora_min_segundos` /
# `reancora_min_ticks` em `WdoGridReloadMaker.__init__`.
#
# Contexto: o fix do item 4.9 (reancorar a ordem PENDENTE a cada barra) roda
# em `feed_kind="tick"`, onde "cada barra" e' CADA NEGOCIO -- medido no motor
# tick sobre 126 pregoes reais de WDO@, o robo SEM freio emitia dezenas de
# milhares de `LimitPlaced` por pregao, e ao vivo cada um vira
# cancelar+reenviar na corretora. O teto do proprio projeto
# (`live.intraday_runtime.COTA_ENVIOS_POR_MINUTO = 120` em janela rolante de
# 60s) recusa a ordem excedente, e o teto de patologia
# (`MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO = 600`) liga `disaster_halt` e para o
# robo pelo resto do pregao -- as dezenas de milhares de envios acima
# atravessam os dois. (Ate' 2026-09-08 havia um teto so', 30, que ja' parava
# o robo.) Estes testes cobrem o freio que impede isso.
# ---------------------------------------------------------------------------

def _tick(strat: WdoGridReloadMaker, ts, preco: float, volume: float = 10.0):
    """Um negocio (bar degenerado: open=high=low=close) entregue ao robo --
    mesma forma que `feed_kind="tick"` produz ao vivo e no motor tick."""
    bar = Bar(ts=ts, open=preco, high=preco, low=preco, close=preco, volume=volume)
    return strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)


def test_freio_de_reprecificacao_vem_ligado_por_padrao():
    """Diferente de `defesa_ativa`/`trailing_ativo`/`gate_atividade_ativo`
    (opt-in, default desligado), este freio nasce LIGADO: sem ele o
    comportamento default do robo estoura os tetos de envio do runtime ao
    vivo (`COTA_ENVIOS_POR_MINUTO`/`MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO`).

    O valor exato (10s) e' calibrado -- ver a tabela na docstring de
    `reancora_min_segundos`. Fixado aqui para uma mudanca de default nao
    passar despercebida: ela muda o pior minuto do robo em producao."""
    strat = WdoGridReloadMaker(tick_size=0.5, profit_ticks=2, stop_ticks=16)
    assert strat.reancora_min_segundos == 10.0
    # 2026-09-08: era 1 (histerese desligada). Ver `test_histerese_*` abaixo
    # e a tabela na docstring de `reancora_min_ticks` -- 1 virou baseline de
    # medicao, nao configuracao de operacao.
    assert strat.reancora_min_ticks == 2


def test_max_trades_per_side_continua_em_200():
    """Nao e' mais um teto folgado (2026-09-07): e' ele que limita quantos
    REARMES pos-fill o robo manda por minuto: o pior minuto medido no
    default do freio e' 26 em tempo de tick, 42 na medicao IS/OOS de
    2026-09-08. Subir este numero sem re-medir o pior minuto come a cota de
    vazao do runtime (`COTA_ENVIOS_POR_MINUTO = 120`) -- ver a docstring do
    parametro."""
    strat = WdoGridReloadMaker(tick_size=0.5, profit_ticks=2, stop_ticks=16)
    assert strat.max_trades_per_side == 200


def test_freio_bloqueia_reprecificacao_dentro_da_janela_de_espera():
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reancora_min_segundos=6.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    primeira = _tick(strat, ts0, 5000.0)
    assert len(primeira) == 1                                   # armou @ 4999,5
    assert primeira[0].limit_price == pytest.approx(4999.5)

    # o preco anda de verdade (ate' 5 ticks acima) mas ainda dentro da
    # espera -- o nivel novo seria outro, e mesmo assim NADA e' emitido.
    for seg in (1, 2, 3, 4, 5):
        acoes = _tick(strat, ts0 + pd.Timedelta(seconds=seg), 5000.0 + seg * 0.5)
        assert acoes == [], f"reprecificou em +{seg}s, antes dos 6s de espera"
    assert strat._state.pending_side == "long"                  # ordem antiga segue viva
    assert strat._state.pending_level == pytest.approx(4999.5)


def test_freio_libera_a_reprecificacao_depois_da_espera():
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reancora_min_segundos=6.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    _tick(strat, ts0, 5000.0)
    assert _tick(strat, ts0 + pd.Timedelta(seconds=3), 5005.0) == []   # freado

    acoes = _tick(strat, ts0 + pd.Timedelta(seconds=6), 5005.0)  # espera cumprida
    assert len(acoes) == 1
    assert isinstance(acoes[0], EnterLimit)
    assert acoes[0].side == "long"                               # lado nunca muda
    assert acoes[0].limit_price == pytest.approx(5004.5)         # 5005,0 - 1 tick
    assert strat._state.pending_level == pytest.approx(5004.5)


def test_freio_em_zero_restaura_o_comportamento_sem_freio():
    """`reancora_min_segundos=0.0` reprecifica a cada tick, como antes do
    freio existir -- e' o baseline de medicao, nunca configuracao de
    operacao."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reancora_min_segundos=0.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    _tick(strat, ts0, 5000.0)
    emitidas = [_tick(strat, ts0 + pd.Timedelta(seconds=s), 5000.0 + s) for s in (1, 2, 3)]
    assert all(len(a) == 1 for a in emitidas)
    assert [a[0].limit_price for a in emitidas] == pytest.approx([5000.5, 5001.5, 5002.5])


def test_freio_nao_atrasa_o_primeiro_armamento_da_sessao():
    """O freio e' de SUBSTITUICAO, nao de armamento: a primeira ordem do
    pregao sai no primeiro tick, sem esperar nada."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reancora_min_segundos=30.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    acoes = _tick(strat, ts0, 5000.0)
    assert len(acoes) == 1
    assert acoes[0].limit_price == pytest.approx(4999.5)


def test_freio_nao_atrasa_o_rearme_depois_de_um_fill():
    """Rearmar apos a posicao fechar e' a mecanica central do robo (reload)
    -- o freio nao pode morde-la. Depois de um fill confirmado + fechamento,
    a proxima ordem sai no tick seguinte mesmo com a espera longe de
    cumprida."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reancora_min_segundos=30.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    _tick(strat, ts0, 5000.0)                                    # arma long @ 4999,5

    # tick com posicao ABERTA -> confirma o fill (pending_side vira open_side)
    pos = _posicao_long(ts0, 4999.5, 4991.5)
    ts1 = ts0 + pd.Timedelta(seconds=1)
    bar1 = Bar(ts=ts1, open=4999.5, high=4999.5, low=4999.5, close=4999.5, volume=10)
    assert strat.on_bar(ts1, bar1, positions=[pos], session_pnl_brl=0.0) == []
    assert strat._state.pending_level is None                    # rastro da ordem antiga limpo

    # posicao fechou -- 1s depois (muito antes dos 30s) o rearme tem de sair
    ts2 = ts0 + pd.Timedelta(seconds=2)
    acoes = _tick(strat, ts2, 5000.5)
    assert len(acoes) == 1
    assert acoes[0].side == "short"                              # alterna o lado que fechou


def test_freio_limita_substituicoes_por_minuto_por_construcao():
    """A garantia de que o deploy depende: com `reancora_min_segundos=S`, o
    robo nao emite mais que `60/S` substituicoes por minuto, faca o mercado o
    que fizer. Aqui 10 negocios por segundo durante 5 minutos, com o preco
    andando 1 tick a CADA negocio (pior caso: sem freio seriam 3.000 envios,
    ~600 por minuto -- 5x a cota de vazao `COTA_ENVIOS_POR_MINUTO=120` e no
    teto de patologia `MAX_TENTATIVAS_DE_ENVIO_POR_MINUTO=600`)."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reancora_min_segundos=6.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")

    emissoes = []
    for i in range(3000):                                        # 5 min a 10 ticks/s
        ts = ts0 + pd.Timedelta(milliseconds=100 * i)
        preco = 5000.0 + (i % 40) * 0.5                          # anda 1 tick por negocio
        if _tick(strat, ts, preco):
            emissoes.append(ts)

    assert len(emissoes) <= 5 * (60 / 6.0) + 1                   # <= 10/min + o armamento inicial
    pior = max(
        sum(1 for t in emissoes if 0 <= (t - inicio).total_seconds() <= 60)
        for inicio in emissoes
    )
    assert pior <= 60 / 6.0 + 1                                  # pior minuto: <= 11
    assert pior < 30                                             # ... com folga sobre o teto ao vivo


def test_reancora_min_ticks_exige_deriva_minima_antes_de_reprecar():
    """Segundo portao, independente do de tempo: com `reancora_min_ticks=4`
    (e o de tempo desligado), uma deriva de 2 ticks nao vale substituicao;
    a de 4 ticks vale."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reancora_min_segundos=0.0,
                               reancora_min_ticks=4)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    _tick(strat, ts0, 5000.0)                                    # ancora 5000,0 -> long @ 4999,5

    assert _tick(strat, ts0 + pd.Timedelta(seconds=1), 5001.0) == []   # deriva 2 ticks: nao
    acoes = _tick(strat, ts0 + pd.Timedelta(seconds=2), 5002.0)        # deriva 4 ticks: sim
    assert len(acoes) == 1
    assert acoes[0].limit_price == pytest.approx(5001.5)


def test_reancora_min_ticks_vale_para_os_dois_lados():
    """A deriva e' medida contra a ANCORA da ordem parada -- para o short o
    nivel fica ACIMA da ancora, entao o sinal do deslocamento inverte."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reancora_min_segundos=0.0,
                               reancora_min_ticks=4)
    strat.on_session_start(None)
    strat._state.last_closed_side = "long"                       # forca o proximo lado a ser short
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    primeira = _tick(strat, ts0, 5000.0)
    assert primeira[0].side == "short"
    assert primeira[0].limit_price == pytest.approx(5000.5)      # 1 tick ACIMA da ancora

    assert _tick(strat, ts0 + pd.Timedelta(seconds=1), 4999.0) == []   # deriva 2 ticks: nao
    acoes = _tick(strat, ts0 + pd.Timedelta(seconds=2), 4998.0)        # deriva 4 ticks: sim
    assert len(acoes) == 1
    assert acoes[0].side == "short"
    assert acoes[0].limit_price == pytest.approx(4998.5)


def test_freio_nao_afeta_o_modo_fixed_session_open():
    """`fixed_session_open` nunca reprecifica (escopo do item 4.9 e' so' o
    rolling) -- o freio nao muda nada la'."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reanchor_mode="fixed_session_open",
                               reancora_min_segundos=6.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    _tick(strat, ts0, 5000.0)
    assert _tick(strat, ts0 + pd.Timedelta(seconds=60), 5010.0) == []
    assert strat._level_price("long") == pytest.approx(4999.5)


def test_on_order_rejected_limpa_o_rastro_da_ordem_pendente():
    """Uma `EnterLimit` recusada nao deixa rastro de ordem parada -- ela
    nunca chegou a existir na corretora."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reancora_min_segundos=6.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    _tick(strat, ts0, 5000.0)
    strat.on_order_rejected(ts0)
    assert strat._state.pending_side is None
    assert strat._state.pending_level is None
    assert strat._state.pending_level_ts is None


def test_freio_segura_o_rearme_depois_de_uma_recusa():
    """Segundo lado do freio: uma recusa (teto de capital no motor, margem ao
    vivo) zera `pending_side`, e sem portao o robo cai no ramo de ARMAR e
    manda ordem NOVA no tick seguinte, com o mesmo caixa que acabou de ser
    recusado. Medido no motor tick (2026-03-04, capital real R$375): 2.874
    armamentos para 7 trades, 2.866 recusados por capital."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reancora_min_segundos=6.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    _tick(strat, ts0, 5000.0)
    strat.on_order_rejected(ts0)

    for seg in (1, 2, 3, 4, 5):
        assert _tick(strat, ts0 + pd.Timedelta(seconds=seg), 5000.0 + seg * 0.5) == [], \
            f"rearmou em +{seg}s, antes dos 6s de espera desde a recusa"

    acoes = _tick(strat, ts0 + pd.Timedelta(seconds=6), 5003.0)
    assert len(acoes) == 1
    assert isinstance(acoes[0], EnterLimit)


def test_recusa_em_laco_nao_ultrapassa_o_teto_de_envios_por_minuto():
    """O caso real: o caixa fica abaixo do piso para 1 contrato e TODA ordem
    e' recusada. Sem freio isso e' uma ordem nova por tick; com freio, no
    maximo `60/reancora_min_segundos` por minuto."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reancora_min_segundos=6.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")

    emissoes = []
    for i in range(3000):                                   # 5 min a 10 ticks/s
        ts = ts0 + pd.Timedelta(milliseconds=100 * i)
        if _tick(strat, ts, 5000.0 + (i % 40) * 0.5):
            emissoes.append(ts)
            strat.on_order_rejected(ts)                     # a corretora recusa TODAS

    pior = max(
        sum(1 for t in emissoes if 0 <= (t - inicio).total_seconds() <= 60)
        for inicio in emissoes
    )
    assert pior <= 60 / 6.0 + 1
    assert pior < 120                                # cota COTA_ENVIOS_POR_MINUTO


def test_fill_apaga_o_relogio_de_recusa():
    """Um FILL nao pode herdar a espera de uma recusa anterior -- senao o
    rearme pos-fechamento (a mecanica de reload) sairia atrasado."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reancora_min_segundos=30.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    _tick(strat, ts0, 5000.0)
    strat.on_order_rejected(ts0)
    assert strat._state.ultima_recusa_ts is not None

    # 31s depois o robo rearma, e desta vez PREENCHE
    ts1 = ts0 + pd.Timedelta(seconds=31)
    assert len(_tick(strat, ts1, 5000.0)) == 1
    pos = _posicao_long(ts1, 4999.5, 4991.5)
    ts2 = ts1 + pd.Timedelta(seconds=1)
    bar2 = Bar(ts=ts2, open=4999.5, high=4999.5, low=4999.5, close=4999.5, volume=10)
    strat.on_bar(ts2, bar2, positions=[pos], session_pnl_brl=0.0)
    assert strat._state.ultima_recusa_ts is None            # apagado pelo fill

    # posicao fechou -- rearme imediato, sem os 30s
    acoes = _tick(strat, ts2 + pd.Timedelta(seconds=1), 5000.5)
    assert len(acoes) == 1
    assert acoes[0].side == "short"


def test_reancora_min_segundos_negativo_levanta_erro():
    with pytest.raises(ValueError):
        WdoGridReloadMaker(tick_size=0.5, profit_ticks=2, stop_ticks=16,
                           reancora_min_segundos=-1.0)


def test_reancora_min_ticks_abaixo_de_1_levanta_erro():
    with pytest.raises(ValueError):
        WdoGridReloadMaker(tick_size=0.5, profit_ticks=2, stop_ticks=16,
                           reancora_min_ticks=0)


# ---------------------------------------------------------------------------
# Histerese anti-pingue-pongue (2026-09-08) -- ver `reancora_min_ticks` em
# `WdoGridReloadMaker.__init__`.
#
# Achado do dono no 1o pregao com o item 4.9 ao vivo (slot
# `dt-wdo_grid_reload_maker-wdo@-live`, `live_events`): 125 linhas `LIMITE`
# para 22 rodadas, 103 delas `(substitui)`. Nenhuma era identica a'
# IMEDIATAMENTE anterior (a guarda de no-op do motor,
# `machine._reancoragem_no_mesmo_nivel`, nao tinha o que pegar) -- o
# desperdicio era VOLTAR a um nivel recem-abandonado: 65 das 103 moveram a
# ordem 1 tick, 49 devolveram a ordem a um nivel que a MESMA rodada ja' tinha
# ocupado. Cada volta e' um cancela+reenvia real que joga fora a fila
# acumulada, que num robo maker e' o produto.
#
# Os `bar.ts` espacados de 30s nos testes abaixo NAO sao licenca poetica:
# reproduzem a condicao real. A rodada #21 saiu inteira no MESMO segundo de
# parede (2026-09-08 15:00:44 UTC) porque a maquina reprocessava fila
# atrasada -- em tempo de TICK aquelas substituicoes estavam a minutos uma da
# outra, e o freio de `reancora_min_segundos=10.0` (que mede `bar.ts`, por
# ser regra de estrategia) achou que estava segurando. Ver a docstring de
# `live.intraday_runtime._check_cadencia_de_ordens`.
# ---------------------------------------------------------------------------

#: A rodada #21 do pregao de 2026-09-08, nivel por nivel, como o diario
#: registrou. `close` do tick -> nivel da ordem long (`close - 1 tick`):
#:   5105,5 -> @5105,0 | 5106,0 -> @5105,5 | 5105,5 -> @5105,0
#:   5106,0 -> @5105,5 | 5107,0 -> @5106,5  (este ultimo preencheu)
_RODADA_21 = [5105.5, 5106.0, 5105.5, 5106.0, 5107.0]


def _replay(strat: WdoGridReloadMaker, closes, passo_segundos: int = 30):
    """Roda `closes` como ticks espacados de `passo_segundos` (folgado sobre
    `reancora_min_segundos`, para o portao de TEMPO nunca ser quem decide) e
    devolve os precos-limite de cada `EnterLimit` emitida."""
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-09-08 15:00:44", tz="UTC")
    precos = []
    for i, preco in enumerate(closes):
        for acao in _tick(strat, ts0 + pd.Timedelta(seconds=passo_segundos * i), preco):
            precos.append(acao.limit_price)
    return precos


def test_histerese_nao_devolve_a_ordem_ao_nivel_recem_abandonado():
    """O pedido direto do dono, com a sequencia REAL da rodada #21:
    "substituiu 3 vezes para o mesmo preco, mesmo stop e mesmo alvo, isso e'
    uso de recurso desnecessario, neste caso nao deve substituir".

    5105,0 -> 5105,5 -> 5105,0 -> 5105,5 -> 5106,5 tem de produzir SO' a
    primeira ordem e a movida final para 5106,5. As tres do meio sao
    vai-e-vem entre duas pontas do book -- deriva de 1 tick nao e' preco
    andando.

    FALHA no codigo antigo (`reancora_min_ticks=1`): as 5 saem, que e'
    exatamente o que a corretora recebeu em 2026-09-08."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16)
    assert _replay(strat, _RODADA_21) == pytest.approx([5105.0, 5106.5])


def test_histerese_desligada_reproduz_o_desperdicio_de_2026_09_08():
    """`reancora_min_ticks=1` restaura o comportamento anterior byte a byte
    -- baseline de medicao, nunca configuracao de operacao. Fixa aqui o
    numero que o pregao real produziu (5 ordens para 1 entrada), para a
    diferenca contra o teste acima ser o valor da correcao, e nao uma
    afirmacao sobre um codigo que ninguem mais roda."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reancora_min_ticks=1)
    assert _replay(strat, _RODADA_21) == pytest.approx(
        [5105.0, 5105.5, 5105.0, 5105.5, 5106.5])


def test_histerese_barra_a_volta_larga_que_a_banda_sozinha_deixaria_passar():
    """A memoria do nivel ABANDONADO nao e' redundante com a banda: sem ela,
    a ordem sai de A, anda a banda inteira ate B e volta para A -- cada
    perna passa no portao de deriva e o par se repete indefinidamente.

    5099,5 -> 5101,0 (3 ticks, vale) -> 5099,5 de volta (3 ticks da parada,
    mas e' EXATAMENTE o nivel abandonado: recusa) -> 5102,5 (longe das
    duas: vale)."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16)
    # closes 5100,0 / 5101,5 / 5100,0 / 5103,0 -> niveis 5099,5 / 5101,0 / 5099,5 / 5102,5
    assert _replay(strat, [5100.0, 5101.5, 5100.0, 5103.0]) == pytest.approx(
        [5099.5, 5101.0, 5102.5])


def test_histerese_nao_prende_a_ordem_quando_o_preco_anda_de_verdade():
    """O contrapeso: a histerese nao pode virar a ordem estacionada que o
    item 4.9 corrigiu. Preco subindo 1 tick por tick (nunca volta) -- a
    ordem acompanha, so' que de 2 em 2 ticks em vez de 1 em 1."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16)
    closes = [5100.0 + 0.5 * i for i in range(9)]        # 5100,0 ... 5104,0
    assert _replay(strat, closes) == pytest.approx(
        [5099.5, 5100.5, 5101.5, 5102.5, 5103.5])


def test_histerese_e_por_rodada_o_rearme_nao_herda_a_proibicao():
    """A memoria morre com a rodada. Se sobrevivesse ao fill, o robo ficaria
    proibido de reprecar para um nivel que a rodada ANTERIOR abandonou --
    e voltar ao mesmo nivel depois de fechar e' a mecanica de reload que da'
    nome ao robo."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-09-08 15:00:44", tz="UTC")

    assert _tick(strat, ts0, 5100.0)[0].limit_price == pytest.approx(5099.5)
    ts1 = ts0 + pd.Timedelta(seconds=30)
    assert _tick(strat, ts1, 5101.5)[0].limit_price == pytest.approx(5101.0)
    assert strat._state.nivel_abandonado == pytest.approx(5099.5)

    # a ordem em 5101,0 PREENCHE -- fim da rodada
    ts2 = ts1 + pd.Timedelta(seconds=30)
    pos = _posicao_long(ts2, 5101.0, 5093.0)
    bar2 = Bar(ts=ts2, open=5101.0, high=5101.0, low=5101.0, close=5101.0, volume=10)
    strat.on_bar(ts2, bar2, positions=[pos], session_pnl_brl=0.0)
    assert strat._state.nivel_abandonado is None

    # posicao fechou -- rodada NOVA (lado alterna para short, nivel = close + 1 tick)
    ts3 = ts2 + pd.Timedelta(seconds=30)
    nova = _tick(strat, ts3, 5101.0)
    assert nova[0].side == "short" and nova[0].limit_price == pytest.approx(5101.5)

    # reprecifica para 5099,5 -- o nivel que a rodada ANTERIOR abandonou.
    # 4 ticks da ordem parada: passa na banda, e nao pode ser barrado por
    # memoria velha.
    ts4 = ts3 + pd.Timedelta(seconds=30)
    volta = _tick(strat, ts4, 5099.0)
    assert len(volta) == 1
    assert volta[0].limit_price == pytest.approx(5099.5)


def test_histerese_nao_conta_reancoragem_no_mesmo_nivel_como_abandono():
    """Reancorar no MESMO nivel e' no-op no motor
    (`machine._reancoragem_no_mesmo_nivel`): a ordem nunca sai do book, a
    fila acumulada continua de pe' -- entao nao ha' nivel "abandonado" para
    lembrar. So' verificavel com a histerese desligada, que e' o unico modo
    em que uma reancoragem no mesmo nivel chega a ser emitida."""
    strat = WdoGridReloadMaker(tick_size=0.5, level_spacing_ticks=1, profit_ticks=2,
                               stop_ticks=16, reancora_min_ticks=1)
    assert _replay(strat, [5100.0, 5100.0]) == pytest.approx([5099.5, 5099.5])
    assert strat._state.nivel_abandonado is None


# ---------- os MARCOS de escala da config de PRODUCAO (2026-09-09) ---------
# Os testes de dimensionamento acima constroem o robo A MAO, so' com
# `margin_per_contract_brl` -- eles cobrem o teto por MARGEM e passariam
# verdes mesmo que o teto por RISCO sumisse da producao. O teto por risco
# nao mora no motor (`machine._cap_capital_atual` so' olha margem): ele
# existe SO' dentro de `_quantidade_da_entrada`, vindo de
# `registry._KWARGS_PADRAO`. Apagar a linha `risco_pct_por_trade=0.01` de
# la' devolveria a escala por margem -- 2 contratos com R$750 de caixa --
# sem nenhuma falha na suite. Estes dois testes fecham esse buraco: eles
# leem a config REAL de producao (`get_daytrade_robot`), nao uma montada
# no teste.


def _robo_de_producao():
    from strategy.daytrade.registry import get_daytrade_robot

    return get_daytrade_robot("wdo_grid_reload_maker")


def test_producao_declara_o_teto_por_RISCO_e_nao_so_o_de_margem():
    """O teto por risco e' o que impede a ruina por sequencia de stops
    (item 3.9 de LICOES_DE_PRODUCAO.md, incidente do `CopaWin`: caixa de
    R$3.000 a R$68,50 com margem/reserva funcionando exatamente como
    desenhadas). Margem protege a CORRETORA de chamada de margem, nao o
    dono. Se algum destes tres campos sumir do registry, o robo volta a
    escalar so' por margem."""
    strat = _robo_de_producao()
    assert strat.risco_pct_por_trade == 0.01
    assert strat.point_value_brl == 10.0
    assert strat.stop_ticks == 16      # o risco em R$ por contrato depende dele
    assert strat.margin_per_contract_brl == 150.0
    assert strat.hard_cap_contratos == 5


@pytest.mark.parametrize(
    "caixa_brl, contratos, porque",
    [
        (150.0,    1, "margem crua -- piso de SOBREVIVENCIA, 1 contrato"),
        (375.0,    1, "piso de PARTIDA do painel; risco ainda so' paga 1"),
        (750.0,    1, "MARGEM ja' pagaria 2 (750 / 375); o RISCO segura em 1"),
        (7_999.0,  1, "1% = R$79,99 < R$80 do stop de 1 contrato"),
        (15_999.0, 1, "1% = R$159,99 < R$160 do stop de 2 contratos"),
        (16_000.0, 2, "MARCO do 2o contrato: 1% = R$160 = 2 x R$80"),
        (24_000.0, 3, "MARCO do 3o"),
        (40_000.0, 5, "MARCO do 5o -- e' o hard cap regulatorio"),
        (1_000_000.0, 5, "hard cap de 5 continua valendo por cima de tudo"),
    ],
)
def test_marcos_de_escala_de_contrato_na_config_de_producao(caixa_brl, contratos, porque):
    """A tabela de marcos que o dono precisa conseguir prever de cabeca.

    Regra: um stop NUNCA pode consumir mais que 1% do caixa. O stop deste
    robo e' fixo -- `16 ticks x 0,5 x R$10 = R$80` por contrato -- entao
    cada contrato exige **R$8.000 de caixa**, e o teto vale
    `min(margem, risco)`. O caixa e' recalculado a cada entrada
    (`on_capital_update(initial_capital + realized_pnl)`), entao os mesmos
    marcos valem DESCENDO: caixa abaixo de R$16.000 volta a 1 contrato."""
    strat = _robo_de_producao()
    strat.on_capital_update(caixa_brl)
    assert strat._quantidade_da_entrada() == contratos, porque
