"""Teste de `Gremah` (GRid rEload MAker Hybrid) com cenario sintetico
(AGENTS.md: toda regra de entrada/saida em `strategy/` -> teste com
cenario sintetico). Cobre a troca de modo: ancora FIXA (abertura) antes
de `fixed_anchor_until`, ancora ROLANTE (preco atual) depois -- e que o
modo rolante nao depende de `open_price` ter sido visto."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from strategy.daytrade.base import Bar
from strategy.daytrade.lab.gremah import _CALIBRATION_BY_SYMBOL, Gremah, capital_minimo_brl


def _strat(**kwargs) -> Gremah:
    return Gremah(profit_pct=0.01, spacing_multiplier=2.0, stop_multiplier=20.0,
                  tick_size=0.01, fixed_anchor_until=time(14, 0), **kwargs)


def test_fase_fixa_ancora_na_abertura():
    strat = _strat()
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5.00, high=5.00, low=5.00, close=5.00, volume=0)

    actions = strat.on_bar(ts, bar, position=None, session_pnl_brl=0.0)

    assert len(actions) == 1
    assert actions[0].limit_price == pytest.approx(4.90)  # 5.00 - 2*5 ticks
    assert strat._state.open_price == pytest.approx(5.00)


def test_fase_rolante_nao_precisa_de_open_price():
    strat = _strat()
    strat.on_session_start(None)
    # comeca a observar direto as 15h -- depois do corte de 14:00, nunca
    # viu a abertura, `open_price` permanece None.
    ts = pd.Timestamp("2026-01-05 15:00", tz="UTC")
    bar = Bar(ts=ts, open=8.00, high=8.00, low=8.00, close=8.00, volume=0)

    actions = strat.on_bar(ts, bar, position=None, session_pnl_brl=0.0)

    assert len(actions) == 1
    assert strat._state.open_price is None  # nunca precisou saber
    assert actions[0].limit_price == pytest.approx(7.84)  # 8.00 - 2*8 ticks (ancora = preco atual)


def test_troca_de_fixo_para_rolante_no_mesmo_dia():
    strat = _strat()
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    strat.on_bar(ts0, Bar(ts=ts0, open=5.00, high=5.00, low=5.00, close=5.00, volume=0), None, 0.0)
    assert strat._state.pending_side == "long"

    # simula que aquele long fechou e o preco ja' deriva bastante (8.00),
    # agora depois do corte das 14:00 -- proxima recarga deve ancorar no
    # preco NOVO (rolante), nao mais em 5.00.
    strat._state.pending_side = None
    strat._state.long_fills = 1
    strat._state.last_closed_side = "long"
    ts1 = pd.Timestamp("2026-01-05 14:30", tz="UTC")
    actions = strat.on_bar(ts1, Bar(ts=ts1, open=8.00, high=8.00, low=8.00, close=8.00, volume=0), None, 0.0)

    assert len(actions) == 1
    assert actions[0].side == "short"
    assert actions[0].limit_price == pytest.approx(8.16)  # 8.00 + 2*8 ticks, nao 5.00 + spacing antigo


def test_ordem_fixa_nao_tocada_e_abandonada_ao_cruzar_para_a_fase_rolante():
    strat = _strat()
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    actions0 = strat.on_bar(ts0, Bar(ts=ts0, open=5.00, high=5.00, low=5.00, close=5.00, volume=0), None, 0.0)
    assert actions0[0].limit_price == pytest.approx(4.90)  # ordem fixa armada, nunca tocada
    assert strat._state.pending_side == "long"
    assert strat._state.pending_mode == "fixed"

    # preco deriva bem longe do nivel fixo (nunca tocou) e o relogio passa
    # do corte das 14:00 -- a ordem fixa parada em 4.90 deveria ser
    # abandonada e re-armada ancorada no preco atual (9.00), nao continuar
    # esperando ali indefinidamente.
    ts1 = pd.Timestamp("2026-01-05 14:30", tz="UTC")
    actions1 = strat.on_bar(ts1, Bar(ts=ts1, open=9.00, high=9.00, low=9.00, close=9.00, volume=0), None, 0.0)

    assert len(actions1) == 1
    assert actions1[0].side == "long"  # mesmo lado (nada foi preenchido/rotacionado)
    assert actions1[0].limit_price == pytest.approx(8.82)  # 9.00 - 2*9 ticks, nao mais 4.90
    assert strat._state.pending_mode == "rolling"


def test_ordem_rolante_tambem_e_reancorada_apos_esperar_demais():
    strat = _strat(rolling_reanchor_after_bars=3)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 15:00", tz="UTC")  # ja na fase rolante
    actions0 = strat.on_bar(ts0, Bar(ts=ts0, open=8.00, high=8.00, low=8.00, close=8.00, volume=0), None, 0.0)
    assert actions0[0].limit_price == pytest.approx(7.84)  # ancorou em 8.00
    assert strat._state.pending_bars_waited == 0

    # 3 barras passam sem tocar o nivel -- ordem ainda parada, so' contando.
    for _ in range(3):
        actions = strat.on_bar(ts0, Bar(ts=ts0, open=8.00, high=8.00, low=8.00, close=8.00, volume=0), None, 0.0)
        assert actions == []

    # preco deriva bem longe (12.00) e o robo re-ancora sozinho, sem
    # precisar de fill nem de troca de fase -- so' o tempo de espera.
    actions_reanchor = strat.on_bar(
        ts0, Bar(ts=ts0, open=12.00, high=12.00, low=12.00, close=12.00, volume=0), None, 0.0
    )
    assert len(actions_reanchor) == 1
    assert actions_reanchor[0].side == "long"
    assert actions_reanchor[0].limit_price == pytest.approx(11.76)  # 12.00 - 2*12 ticks, nao mais 7.84
    assert strat._state.pending_bars_waited == 0


# ---------- calibracao por simbolo (2026-08-21, IS apenas) ----------------

@pytest.mark.parametrize("symbol,profit_pct,stop_multiplier", [
    ("PMAM3", 0.0032, 10.0),
    ("CSAN3", 0.0021, 20.0),
    ("KLBN4", 0.0021, 5.0),
])
def test_calibracao_por_simbolo_e_usada_quando_nao_sobrescrita(symbol, profit_pct, stop_multiplier):
    strat = Gremah(symbol=symbol)

    assert strat.profit_pct == pytest.approx(profit_pct)
    assert strat.stop_multiplier == pytest.approx(stop_multiplier)
    # a tabela em si tem que bater com o que o teste espera -- se alguem
    # editar `_CALIBRATION_BY_SYMBOL` sem atualizar este teste, isto pega.
    assert _CALIBRATION_BY_SYMBOL[symbol].profit_pct == pytest.approx(profit_pct)
    assert _CALIBRATION_BY_SYMBOL[symbol].stop_multiplier == pytest.approx(stop_multiplier)


def test_profit_pct_explicito_vence_a_calibracao_da_tabela():
    strat = Gremah(symbol="PMAM3", profit_pct=0.0099)

    assert strat.profit_pct == pytest.approx(0.0099)
    # stop_multiplier nao foi passado -- continua vindo do lookup da tabela.
    assert strat.stop_multiplier == pytest.approx(10.0)


def test_stop_multiplier_explicito_vence_a_calibracao_da_tabela():
    strat = Gremah(symbol="CSAN3", stop_multiplier=99.0)

    assert strat.stop_multiplier == pytest.approx(99.0)
    # profit_pct nao foi passado -- continua vindo do lookup da tabela.
    assert strat.profit_pct == pytest.approx(0.0021)


def test_ambos_explicitos_ignora_a_tabela_mesmo_para_simbolo_desconhecido():
    strat = Gremah(symbol="ATIVO_INEXISTENTE", profit_pct=0.005, stop_multiplier=8.0)

    assert strat.profit_pct == pytest.approx(0.005)
    assert strat.stop_multiplier == pytest.approx(8.0)


def test_simbolo_desconhecido_sem_override_falha_alto():
    with pytest.raises(ValueError, match="ATIVO_INEXISTENTE"):
        Gremah(symbol="ATIVO_INEXISTENTE")


def test_simbolo_desconhecido_com_apenas_um_override_ainda_falha():
    # so' profit_pct foi passado -- stop_multiplier ainda precisaria do
    # lookup, que nao existe para este simbolo: tem que falhar, nao usar
    # nenhum stop_multiplier "default" implicito.
    with pytest.raises(ValueError, match="ATIVO_INEXISTENTE"):
        Gremah(symbol="ATIVO_INEXISTENTE", profit_pct=0.005)


# ---------- capital minimo (lote padrao, sem fracionario) -----------------

def test_capital_minimo_brl_arredonda_pra_cima_ao_proximo_multiplo_de_50():
    """A folga NAO e' um valor somado a parte -- e' a distancia ate o
    proximo multiplo de R$50 acima do custo do lote (pedido explicito do
    usuario 2026-08-21). PMAM3 (R$0,14): lote de R$14 -> R$50."""
    assert capital_minimo_brl(0.14) == pytest.approx(50.0)  # lote 14.00 -> 50
    assert capital_minimo_brl(3.64) == pytest.approx(400.0)  # lote 364.00 -> 400
    assert capital_minimo_brl(3.66) == pytest.approx(400.0)  # lote 366.00 -> 400


def test_capital_minimo_brl_lote_exato_multiplo_de_50_nao_sobe_pro_proximo():
    assert capital_minimo_brl(0.50) == pytest.approx(50.0)  # lote 50.00 -> 50 (ja e multiplo)
