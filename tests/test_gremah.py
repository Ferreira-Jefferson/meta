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
from strategy.daytrade.lab.gremah import _CALIBRATION_BY_SYMBOL, Gremah


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


# ---------- teto de lotes por volume rolante (2026-08-22, pedido do dono) --

def test_teto_de_lotes_reage_a_um_giro_recente_mais_fraco():
    """Substituiu (2026-08-22) o teto congelado no PRIMEIRO minuto do
    pregao: agora e' uma media MOVEL (`realocacao_janela_minutos`, aqui
    explicito em 30min so' para a aritmetica do teste ficar redonda -- o
    default de verdade do robo e' 1min, ver `REALOCACAO_JANELA_MINUTOS_
    PADRAO`), reavaliada a CADA entrada -- um pico isolado nao pode
    continuar inflando o teto depois de sair da janela."""
    strat = _strat(realocacao_teto_pct_volume_minuto=0.10, realocacao_limiar_caixa=0.0001,
                    realocacao_janela_minutos=30.0,
                    rolling_reanchor_after_bars=1)  # limiar de caixa minusculo: nunca e' o gargalo
    strat.on_session_start(None)
    strat.on_capital_update(1_000_000.0)  # caixa gigante: so' o teto de volume deve limitar
    ts0 = pd.Timestamp("2026-01-05 15:00", tz="UTC")  # ja em fase rolante

    # 1 barra de 93.000 acoes -- media por minuto (janela nominal de 30min,
    # sem cauda) = 93000/30 = 3100; teto 10% = 310 acoes = 3 lotes.
    actions0 = strat.on_bar(ts0, Bar(ts=ts0, open=5.00, high=5.00, low=5.00, close=5.00, volume=93_000), None, 0.0)
    assert len(actions0) == 1
    assert actions0[0].quantity == 300

    ts_meio = ts0 + pd.Timedelta(minutes=1)
    actions_meio = strat.on_bar(
        ts_meio, Bar(ts=ts_meio, open=5.00, high=5.00, low=5.00, close=5.00, volume=50), None, 0.0)
    assert actions_meio == []  # ordem ainda parada, so' contando barras (rolling_reanchor_after_bars=1)

    # 32 minutos depois do pico -- ele (e a barra intermediaria) ja SAIRAM
    # da janela de 30min. A reancoragem (1 barra de espera) reconsulta o
    # teto, que tem que refletir o giro recente fraco, nao os 3 lotes
    # iniciais.
    ts1 = ts0 + pd.Timedelta(minutes=32)
    actions1 = strat.on_bar(ts1, Bar(ts=ts1, open=5.00, high=5.00, low=5.00, close=5.00, volume=300), None, 0.0)
    assert len(actions1) == 1
    assert actions1[0].quantity == 100  # 1 lote (minimo) -- media caiu para 300/30 = 10 acoes/min


def test_seed_volume_window_usa_a_cauda_do_pregao_anterior_na_abertura():
    """Pedido literal do dono: na abertura, sem 30min de hoje ainda vividos,
    o robo usa as ultimas barras do pregao ANTERIOR em vez de assumir volume
    zero -- `seed_volume_window` e' o canal por onde o CHAMADOR (`live/`/
    `backtest/`) entrega essa cauda (a estrategia nunca busca historico
    sozinha, AGENTS.md: `strategy/` so' importa `core`). Janela explicita em
    30min so' para a aritmetica do teste ficar redonda -- o default de
    verdade do robo e' 1min."""
    strat = _strat(realocacao_teto_pct_volume_minuto=0.10, realocacao_limiar_caixa=0.0001,
                    realocacao_janela_minutos=30.0)
    ontem_fim = pd.Timestamp("2026-01-05 20:55", tz="UTC")
    cauda = [
        Bar(ts=ontem_fim - pd.Timedelta(minutes=m), open=5.0, high=5.0, low=5.0, close=5.0, volume=10_000.0)
        for m in range(29, -1, -1)
    ]  # 30 barras x 10.000 acoes = 300.000 no total
    strat.seed_volume_window(cauda)
    strat.on_session_start(None)
    strat.on_capital_update(1_000_000.0)

    ts0 = pd.Timestamp("2026-01-06 13:00", tz="UTC")
    actions = strat.on_bar(ts0, Bar(ts=ts0, open=5.00, high=5.00, low=5.00, close=5.00, volume=0.0), None, 0.0)

    # media = 300.000 da cauda / 30 = 10.000 acoes/min; teto 10% = 1.000
    # acoes = 10 lotes -- nao o minimo de 1 lote que "sem cauda" produziria.
    assert len(actions) == 1
    assert actions[0].quantity == 1_000


def test_janela_do_teto_de_volume_e_1min_por_decisao_do_dono_2026_08_22():
    """Nao e' o valor medido como mais consistente (30min tinha o menor
    MaxDD e o melhor Calmar, IS e OOS, dos tres tamanhos testados em
    PMAM3) -- e' a decisao EXPLICITA do dono apos ver essa medicao,
    marcada como provisoria ("por hora"). Este teste so existe para nao
    deixar essa decisao se perder numa refatoracao silenciosa."""
    assert Gremah(symbol="PMAM3").realocacao_janela_minutos == pytest.approx(1.0)
