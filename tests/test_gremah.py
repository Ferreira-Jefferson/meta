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
from strategy.daytrade.lab.gremah import (
    _CALIBRATION_BY_SYMBOL,
    _GEOMETRIA_TICKS_BY_SYMBOL,
    _VOLATILITY_OVERRIDE_BY_SYMBOL,
    Gremah,
)


def _strat(**kwargs) -> Gremah:
    # Filtro de qualidade de entrada (2026-08-27) e' PADRAO `True` desde
    # entao (ver `FILTRO_MINUTOS_DESDE_ABERTURA_MIN_PADRAO`) -- desligado
    # aqui por padrao porque quase todo teste deste arquivo testa OUTRA
    # mecanica (troca de fase, sizing, geometria) com barras sinteticas na
    # abertura (minutos_desde_abertura=0) ou volume alto de proposito, e o
    # filtro nao pode ser o motivo de nenhum deles falhar. Os testes
    # dedicados ao filtro (mais abaixo) ligam explicitamente via kwargs.
    kwargs.setdefault("filtro_minutos_desde_abertura_min", None)
    kwargs.setdefault("filtro_volume_toque_max", None)
    return Gremah(profit_pct=0.01, spacing_multiplier=2.0, stop_multiplier=20.0,
                  tick_size=0.01, fixed_anchor_until=time(14, 0), **kwargs)


def test_fase_fixa_ancora_na_abertura():
    strat = _strat()
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5.00, high=5.00, low=5.00, close=5.00, volume=0)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

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

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

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
    assert actions0[0].limit_price == pytest.approx(4.90)  # ordem fixa posicionada, nunca tocada
    assert strat._state.pending_side == "long"
    assert strat._state.pending_mode == "fixed"

    # preco deriva bem longe do nivel fixo (nunca tocou) e o relogio passa
    # do corte das 14:00 -- a ordem fixa parada em 4.90 deveria ser
    # abandonada e re-posicionada ancorada no preco atual (9.00), nao continuar
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


# ---------- alvo por volatilidade (2026-08-23, opt-in) --------------------

def _diaria(rng: float) -> Bar:
    ts = pd.Timestamp("2026-01-04 18:00", tz="UTC")
    return Bar(ts=ts, open=10.0, high=10.0 + rng, low=10.0, close=10.0, volume=0)


def test_alvo_por_volatilidade_exige_mult_explicito():
    with pytest.raises(ValueError):
        Gremah(symbol="PMAM3", alvo_por_volatilidade=True)


def test_ticks_from_pct_continua_a_arquitetura_default():
    """Nao mexeu no caminho antigo: desligado (default), o alvo continua
    saindo 100% de `_ticks_from_pct`."""
    strat = _strat()
    assert strat.alvo_por_volatilidade is False
    profit, spacing, stop = strat._session_ticks(5.00)
    assert profit == strat._ticks_from_pct(5.00, strat.profit_pct)
    assert spacing == strat._ticks_from_pct(5.00, strat.profit_pct * strat.spacing_multiplier)
    assert stop == strat._ticks_from_pct(5.00, strat.profit_pct * strat.stop_multiplier)


def test_alvo_por_volatilidade_sem_janela_cai_no_fallback_percentual():
    """Ligado, mas `seed_daily_volatility` nunca foi chamado (primeiro
    pregao do historico, ou feed falhou) -- tem que se comportar
    EXATAMENTE como desligado, nunca travar nem devolver ticks invalidos."""
    strat = _strat(alvo_por_volatilidade=True, alvo_vol_mult=0.5)
    profit, spacing, stop = strat._session_ticks(5.00)
    assert profit == strat._ticks_from_pct(5.00, strat.profit_pct)
    assert spacing == strat._ticks_from_pct(5.00, strat.profit_pct * strat.spacing_multiplier)
    assert stop == strat._ticks_from_pct(5.00, strat.profit_pct * strat.stop_multiplier)


def test_alvo_por_volatilidade_variante_a_mantem_stop_multiplier_por_simbolo():
    """Variante A (dono, 2026-08-23): so' o ALVO vira volatilidade; o stop
    continua usando o `stop_multiplier` do SIMBOLO (aqui, 20x explicito)."""
    strat = _strat(alvo_por_volatilidade=True, alvo_vol_mult=0.5)  # stop_multiplier=20.0 (de _strat)
    strat.seed_daily_volatility([_diaria(10.0), _diaria(20.0), _diaria(30.0)])  # mediana = 20.0

    profit, spacing, stop = strat._session_ticks(999.0)  # preco IGNORADO quando ha' volatilidade
    assert profit == max(1, round(20.0 * 0.5 / strat.tick_size))
    assert spacing == max(1, round(20.0 * 0.5 * strat.spacing_multiplier / strat.tick_size))
    assert stop == max(1, round(20.0 * 0.5 * strat.stop_multiplier / strat.tick_size))


def test_alvo_por_volatilidade_variante_b_stop_global_ignora_stop_multiplier():
    """Variante B (dono, 2026-08-23): `stop_vol_mult` GLOBAL substitui o
    `stop_multiplier` por simbolo so' para o stop."""
    strat = _strat(alvo_por_volatilidade=True, alvo_vol_mult=0.5, stop_vol_mult=8.0)
    strat.seed_daily_volatility([_diaria(10.0), _diaria(20.0), _diaria(30.0)])

    _, _, stop = strat._session_ticks(999.0)
    assert stop == max(1, round(20.0 * 0.5 * 8.0 / strat.tick_size))
    assert stop != max(1, round(20.0 * 0.5 * strat.stop_multiplier / strat.tick_size))


def test_seed_daily_volatility_substitui_nao_acumula():
    """Mesmo padrao de `seed_volume_window`/`definir_cauda_anterior`:
    chamar de novo REPLACES, nao empilha em cima do que ja' tinha."""
    strat = _strat(alvo_por_volatilidade=True, alvo_vol_mult=1.0)
    strat.seed_daily_volatility([_diaria(100.0)])
    assert strat._janela_vol.range_mediano() == pytest.approx(100.0)

    strat.seed_daily_volatility([_diaria(5.0)])
    assert strat._janela_vol.range_mediano() == pytest.approx(5.0)


def test_seed_daily_volatility_usa_so_a_cauda_do_tamanho_da_janela():
    """`previous_daily_bars` pode vir maior que `vol_janela_dias` (o motor
    de backtest manda tudo que ja' viu) -- so' as ultimas contam."""
    strat = _strat(alvo_por_volatilidade=True, alvo_vol_mult=1.0, vol_janela_dias=2)
    strat.seed_daily_volatility([_diaria(1000.0), _diaria(2.0), _diaria(4.0)])
    assert strat._janela_vol.range_mediano() == pytest.approx(3.0)  # mediana de [2.0, 4.0]


# ---------- stop_frac_range (2026-08-23, isolando a variavel: so' o stop) --

def test_stop_frac_range_desligado_nao_muda_nada():
    strat = _strat()
    assert strat.stop_frac_range is None
    profit, spacing, stop = strat._session_ticks(5.00)
    assert stop == strat._ticks_from_pct(5.00, strat.profit_pct * strat.stop_multiplier)


def test_stop_frac_range_troca_so_o_stop_mantem_alvo_e_espacamento_percentuais():
    """Alvo e espacamento continuam saindo do percentual de sempre -- so' o
    stop muda pra fracao do range diario."""
    strat = _strat(stop_frac_range=0.5)
    strat.seed_daily_volatility([_diaria(10.0), _diaria(20.0), _diaria(30.0)])  # mediana = 20.0

    profit, spacing, stop = strat._session_ticks(5.00)
    assert profit == strat._ticks_from_pct(5.00, strat.profit_pct)
    assert spacing == strat._ticks_from_pct(5.00, strat.profit_pct * strat.spacing_multiplier)
    assert stop == max(1, round(20.0 * 0.5 / strat.tick_size))
    assert stop != strat._ticks_from_pct(5.00, strat.profit_pct * strat.stop_multiplier)


def test_stop_frac_range_sem_janela_cai_no_fallback_percentual():
    strat = _strat(stop_frac_range=0.5)  # nunca chamou seed_daily_volatility
    profit, spacing, stop = strat._session_ticks(5.00)
    assert stop == strat._ticks_from_pct(5.00, strat.profit_pct * strat.stop_multiplier)


def test_stop_frac_range_combina_com_alvo_por_volatilidade():
    """`alvo_por_volatilidade` decide alvo/espacamento; `stop_frac_range`
    ainda pode sobrescrever o stop por cima, independente do caminho que
    escolheu os outros dois."""
    strat = _strat(alvo_por_volatilidade=True, alvo_vol_mult=1.0, stop_frac_range=0.5)
    strat.seed_daily_volatility([_diaria(10.0), _diaria(20.0), _diaria(30.0)])

    profit, spacing, stop = strat._session_ticks(999.0)
    assert profit == max(1, round(20.0 * 1.0 / strat.tick_size))  # via alvo_vol_mult
    assert stop == max(1, round(20.0 * 0.5 / strat.tick_size))    # via stop_frac_range


# ---------- override por simbolo: (k,s) confirmado no OOS (2026-08-23) ----

@pytest.mark.parametrize("symbol,k,s", [
    ("BMGB4", 0.05, 8.0),
    ("CSAN3", 0.05, 5.0),
    ("GRND3", 0.05, 10.0),
    ("KLBN4", 0.05, 10.0),
])
def test_override_de_volatilidade_liga_sozinho_para_simbolo_confirmado(symbol, k, s):
    """Simbolo com par (k,s) confirmado no OOS (`_VOLATILITY_OVERRIDE_BY_
    SYMBOL`) constroi ja' em modo volatilidade, sem precisar passar nada
    explicito -- e' o resultado direto de "usar o que e' melhor pra cada
    um" (pedido do dono 2026-08-23), o mesmo protocolo de aceitar/descartar
    que ja' construiu a tabela percentual."""
    strat = Gremah(symbol=symbol)

    assert strat.alvo_por_volatilidade is True
    assert strat.alvo_vol_mult == pytest.approx(k)
    assert strat.stop_vol_mult == pytest.approx(s)
    # a tabela em si tem que bater com o teste -- se alguem editar
    # `_VOLATILITY_OVERRIDE_BY_SYMBOL` sem atualizar este teste, isto pega.
    assert _VOLATILITY_OVERRIDE_BY_SYMBOL[symbol] == (k, s)


@pytest.mark.parametrize("symbol", ["PMAM3", "DASA3", "PCAR3", "KLBN3", "LPSB3"])
def test_simbolos_sem_confirmacao_oos_continuam_no_percentual(symbol):
    """Os 6 simbolos onde nada bateu o percentual no IS (CLSC4, DASA3) ou
    pioraram no OOS (KLBN3, LPSB3, PCAR3, PMAM3) NAO tem override --
    continuam exatamente no caminho de sempre."""
    strat = Gremah(symbol=symbol)

    assert symbol not in _VOLATILITY_OVERRIDE_BY_SYMBOL
    assert strat.alvo_por_volatilidade is False


def test_alvo_vol_mult_explicito_vence_o_override():
    """Passar `alvo_vol_mult=` na mao sempre vence o override automatico --
    mesmo espirito de `profit_pct=` vencer `_CALIBRATION_BY_SYMBOL`."""
    strat = Gremah(symbol="BMGB4", alvo_vol_mult=0.99)

    assert strat.alvo_vol_mult == pytest.approx(0.99)
    assert strat.alvo_vol_mult != _VOLATILITY_OVERRIDE_BY_SYMBOL["BMGB4"][0]


def test_stop_vol_mult_explicito_vence_o_s_do_override():
    strat = Gremah(symbol="BMGB4", stop_vol_mult=99.0)

    assert strat.alvo_vol_mult == pytest.approx(_VOLATILITY_OVERRIDE_BY_SYMBOL["BMGB4"][0])
    assert strat.stop_vol_mult == pytest.approx(99.0)


def test_ambos_explicitos_ignora_a_tabela_mesmo_para_simbolo_desconhecido():
    # capacidade_negocio_mult/capacidade_fracao tambem precisam de override
    # explicito aqui desde 2026-08-25 -- viraram lookup por simbolo igual
    # profit_pct/stop_multiplier (`_CAPACIDADE_BY_SYMBOL`), com a MESMA
    # guarda de "simbolo desconhecido falha alto" -- sem os dois, o
    # construtor falharia no lookup de capacidade mesmo com profit_pct/
    # stop_multiplier ja resolvidos.
    strat = Gremah(
        symbol="ATIVO_INEXISTENTE", profit_pct=0.005, stop_multiplier=8.0,
        capacidade_negocio_mult=1.0, capacidade_fracao=0.10,
    )

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
    verdade do robo e' 1min.

    Teto pela BARRA TIPICA (mediana), nao pela media/minuto, desde
    2026-08-24 (mesmo mecanismo portado da `GremahTick`, ver
    `Gremah._lotes_por_realocacao`) -- com as 30 barras da cauda mais a de
    hoje (31 >= `capacidade_min_eventos`), a mediana (10.000 acoes) e' o
    fluxo REAL observado, sem diluir pelo tamanho NOMINAL da janela como a
    media fazia."""
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

    # mediana das 31 barras (30 da cauda a 10.000 + a de hoje a 0) = 10.000
    # acoes; teto = 10.000 x capacidade_negocio_mult (1.0, default medido
    # 2026-08-24) = 10.000 acoes -- bem mais que o minimo de 1 lote que
    # "sem cauda" produziria.
    assert len(actions) == 1
    assert actions[0].quantity == 10_000


def test_janela_do_teto_de_volume_e_1min_por_decisao_do_dono_2026_08_22():
    """Nao e' o valor medido como mais consistente (30min tinha o menor
    MaxDD e o melhor Calmar, IS e OOS, dos tres tamanhos testados em
    PMAM3) -- e' a decisao EXPLICITA do dono apos ver essa medicao,
    marcada como provisoria ("por hora"). Este teste so existe para nao
    deixar essa decisao se perder numa refatoracao silenciosa."""
    assert Gremah(symbol="PMAM3").realocacao_janela_minutos == pytest.approx(1.0)


# ---------- divisao de entrada em pedacos (2026-08-23) ---------------------
# MESMA logica de `GremahTick._dividir_pecas` (ver `tests/test_gremah_tick.py`),
# aqui "evento" e' a barra M1 fechada em vez do negocio individual. So' tem
# efeito de verdade com `IntradayBacktestConfig.limit_fill_capped_by_volume=
# True` (testado em `test_intraday_machine.py`); aqui so' a LOGICA de
# fatiamento, isolada do motor.

def test_dividir_entrada_ligado_por_default():
    # Padrao `True` desde 2026-08-23 (pedido do dono, depois de medir IS/OOS
    # -- ver a memoria `dividir_entrada_is_oos_2026_08_23` do projeto).
    assert Gremah(symbol="PMAM3").dividir_entrada is True


def test_exit_ttl_bars_padrao_e_8():
    # Decidido 2026-08-23 apos varrer 1..10 em PMAM3 (IS+OOS) -- ver a
    # memoria `exit_ttl_bars_decisao_2026_08_23` do projeto.
    assert Gremah(symbol="PMAM3").exit_ttl_bars == 8


def test_dividir_pecas_sem_evento_na_janela_nao_divide():
    strat = _strat(dividir_entrada=True)
    ts = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    assert strat._dividir_pecas(500, ts) is None


def test_dividir_pecas_quando_barra_tipica_ja_cobre_o_total():
    strat = _strat(dividir_entrada=True, realocacao_janela_minutos=30.0)
    ts0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    strat._janela_volume.registrar(ts0, 10_000.0)  # 1 barra tipica de 10.000 acoes

    assert strat._dividir_pecas(500, ts0) is None  # 500 < 10.000 -- nada a dividir


def test_dividir_pecas_fatia_perto_da_barra_tipica_recente():
    strat = _strat(dividir_entrada=True, dividir_max_pecas=8, realocacao_janela_minutos=30.0)
    ts0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    for i in range(5):
        strat._janela_volume.registrar(ts0 + pd.Timedelta(minutes=i), 100.0)  # barras de 1 lote

    pecas = strat._dividir_pecas(500, ts0 + pd.Timedelta(minutes=5))

    assert pecas is not None
    assert sum(pecas) == 500
    assert all(p % 100 == 0 for p in pecas)


# ---------------------------------------------------------------------------
# GEOMETRIA EM TICKS (2026-08-26): alvo, espacamento e stop escolhidos de
# forma INDEPENDENTE. No caminho percentual os tres saem do mesmo `profit_pct`
# (`stop = profit_pct * stop_multiplier`), entao mexer num arrasta os outros.
# ---------------------------------------------------------------------------


def test_ticks_explicitos_default_none_nao_muda_nada():
    """Compatibilidade: os parametros novos existem, mas com o default `None`
    o resultado tem de ser IDENTICO ao caminho percentual de sempre. Se este
    teste quebrar, o robo em producao mudou de comportamento sem ninguem pedir."""
    strat = _strat()
    assert strat.profit_ticks is None
    assert strat.spacing_ticks is None
    assert strat.stop_ticks is None
    assert strat._session_ticks(5.00) == (
        strat._ticks_from_pct(5.00, strat.profit_pct),
        strat._ticks_from_pct(5.00, strat.profit_pct * strat.spacing_multiplier),
        strat._ticks_from_pct(5.00, strat.profit_pct * strat.stop_multiplier),
    )


def test_alvo_e_stop_em_ticks_sao_independentes():
    """O ponto inteiro da mudanca. No caminho percentual alvo e stop saem do
    MESMO `profit_pct` (`stop = profit_pct * stop_multiplier`), entao subir o
    alvo sobe o stop na mesma proporcao -- e a grade de calibracao nunca
    conseguiu perguntar "alvo maior com o stop onde esta". Em ticks, consegue."""
    apertado = _strat(profit_ticks=2, stop_ticks=8)
    largo = _strat(profit_ticks=4, stop_ticks=8)

    assert apertado._session_ticks(5.00)[0] == 2
    assert largo._session_ticks(5.00)[0] == 4
    # dobrar o alvo NAO mexeu no stop
    assert apertado._session_ticks(5.00)[2] == 8
    assert largo._session_ticks(5.00)[2] == 8


def test_ticks_explicitos_vencem_percentual_volatilidade_e_stop_frac_range():
    """Hierarquia declarada: o mais explicito vence. Aqui ligamos TODOS os
    outros caminhos ao mesmo tempo e os tres numeros ainda saem dos ticks."""
    strat = _strat(alvo_por_volatilidade=True, alvo_vol_mult=0.5,
                   stop_frac_range=0.9,
                   profit_ticks=3, spacing_ticks=7, stop_ticks=11)
    strat.seed_daily_volatility([_diaria(10.0), _diaria(20.0), _diaria(30.0)])

    assert strat._session_ticks(999.0) == (3, 7, 11)


def test_ticks_explicitos_nao_aceitam_zero_nem_negativo():
    """`_build_entry` multiplica ticks por `tick_size` sem checar sinal: um 0
    poria o alvo em cima do preco de entrada, e um negativo o jogaria para o
    lado errado -- os dois viram trade impossivel preenchido pelo backtest."""
    assert _strat(profit_ticks=0).profit_ticks == 1
    assert _strat(stop_ticks=-5).stop_ticks == 1
    assert _strat(spacing_ticks=0).spacing_ticks == 1


def test_geometria_em_ticks_por_simbolo_e_aplicada_sozinha():
    """PMAM3/M1 usa geometria em TICKS desde 2026-08-26 (IS + confirmacao OOS,
    ver o comentario de `_GEOMETRIA_TICKS_BY_SYMBOL`). Se alguem editar a
    tabela sem atualizar este teste, isto pega."""
    assert _GEOMETRIA_TICKS_BY_SYMBOL["PMAM3"] == (1, 1, 16)
    strat = Gremah(symbol="PMAM3")
    assert (strat.profit_ticks, strat.spacing_ticks, strat.stop_ticks) == (1, 1, 16)


def test_geometria_em_ticks_da_bmgb4_vence_o_override_de_volatilidade():
    """BMGB4 esta' nas DUAS tabelas (`_VOLATILITY_OVERRIDE_BY_SYMBOL` e
    `_GEOMETRIA_TICKS_BY_SYMBOL`, desde 2026-08-27, grade 22x22 com capital
    minimo real, IS+OOS) -- a de ticks tem que vencer, mesmo padrao ja
    documentado no comentario da CSAN3. Se alguem editar so' uma das duas
    tabelas, isto pega."""
    assert _GEOMETRIA_TICKS_BY_SYMBOL["BMGB4"] == (1, 1, 4)
    assert "BMGB4" in _VOLATILITY_OVERRIDE_BY_SYMBOL
    strat = Gremah(symbol="BMGB4")
    assert (strat.profit_ticks, strat.spacing_ticks, strat.stop_ticks) == (1, 1, 4)
    assert strat.alvo_por_volatilidade is True  # o campo liga sozinho...
    assert strat._session_ticks(5.13) == (1, 1, 4)  # ...mas os ticks decidem por ultimo


def test_geometria_em_ticks_nao_muda_com_o_preco():
    """O ponto de expressar a geometria em ticks: a PMAM3 caiu de R$4,53 para
    R$0,14 dentro da janela de backtest, e no caminho percentual o stop dela
    encolhia de 29 ticks para 1 junto. Em ticks, nao encolhe."""
    strat = Gremah(symbol="PMAM3")
    assert strat._session_ticks(0.14) == (1, 1, 16)
    assert strat._session_ticks(0.55) == (1, 1, 16)
    assert strat._session_ticks(4.53) == (1, 1, 16)


def test_geometria_em_ticks_nao_sobrescreve_escolha_explicita():
    """Mesmo espirito do override de volatilidade: a tabela nunca vence quem
    construiu o robo decidindo por conta propria."""
    strat = Gremah(symbol="PMAM3", stop_ticks=9)
    assert strat.stop_ticks == 9
    assert strat._session_ticks(0.55)[2] == 9


def test_simbolo_fora_da_tabela_de_ticks_segue_no_percentual():
    """A adocao foi de UM par (PMAM3/M1), nao da familia -- o experimento
    reprovou no OOS do motor tick, e os outros nove simbolos nem foram
    confirmados ainda."""
    strat = Gremah(symbol="DASA3")
    assert "DASA3" not in _GEOMETRIA_TICKS_BY_SYMBOL
    assert strat.profit_ticks is None
    assert strat._session_ticks(2.58) == (
        strat._ticks_from_pct(2.58, strat.profit_pct),
        strat._ticks_from_pct(2.58, strat.profit_pct * strat.spacing_multiplier),
        strat._ticks_from_pct(2.58, strat.profit_pct * strat.stop_multiplier),
    )


def test_pmam3_nao_entra_na_geometria_em_ticks_do_motor_tick():
    """Reprovado no OOS = descarte, sem segunda tentativa: o candidato da
    PMAM3 em tick (T1 E1 S2) venceu o IS por +9,4% e perdeu o OOS por -5,6%
    em 2026-08-26. A tabela do motor tick EXISTE (a BMGB4 passou na mesma
    rodada), entao o que este teste guarda e' a decisao sobre a PMAM3, nao a
    ausencia da tabela -- foi assim que ele foi escrito primeiro, com a
    premissa larga demais, e a BMGB4 o derrubou no mesmo dia."""
    from strategy.daytrade.lab.gremah_tick import _GEOMETRIA_TICKS_BY_SYMBOL_TICK
    assert "PMAM3" not in _GEOMETRIA_TICKS_BY_SYMBOL_TICK
    assert _GEOMETRIA_TICKS_BY_SYMBOL_TICK["BMGB4"] == (1, 1, 8)


# ---------------------------------------------------------------------------
# FILTRO DE QUALIDADE DE ENTRADA (2026-08-27) -- medido e confirmado OOS em
# `scripts/daytrade/gremah_signal_quality_2026_08_27.py` (PMAM3/M1, N=439
# trades OOS-only): minutos_desde_abertura>=216 e volume_toque<=3200 melhoram
# P&L medio/trade e reduzem MaxDD, mesma direcao no IS e no OOS. Pedido
# explicito do dono: virar comportamento PADRAO do robo (nao opt-in) -- ver
# `FILTRO_MINUTOS_DESDE_ABERTURA_MIN_PADRAO`/`FILTRO_VOLUME_TOQUE_MAX_PADRAO`.
# ---------------------------------------------------------------------------

def test_filtro_qualidade_entrada_ligado_por_padrao():
    """O ponto central do pedido: quem constrói `Gremah` sem tocar nestes
    dois parâmetros já opera FILTRADO -- os defaults JÁ SÃO os limiares
    confirmados, não `None`/desligado."""
    strat = Gremah(symbol="PMAM3")
    assert strat.filtro_minutos_desde_abertura_min == pytest.approx(216.0)
    assert strat.filtro_volume_toque_max == pytest.approx(3200.0)


def test_filtro_minutos_desde_abertura_bloqueia_entrada_cedo_demais():
    strat = _strat(filtro_minutos_desde_abertura_min=216.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")  # 1a barra -- minutos_desde_abertura = 0
    bar0 = Bar(ts=ts0, open=5.00, high=5.00, low=5.00, close=5.00, volume=0)

    actions0 = strat.on_bar(ts0, bar0, positions=[], session_pnl_brl=0.0)
    assert actions0 == []  # bloqueado: 0 < 216, mesmo efeito de nenhum sinal
    assert strat._state.pending_side is None  # nenhum estado de ordem mudou

    ts1 = ts0 + pd.Timedelta(minutes=216)  # exatamente no limiar
    bar1 = Bar(ts=ts1, open=5.00, high=5.00, low=5.00, close=5.00, volume=0)
    actions1 = strat.on_bar(ts1, bar1, positions=[], session_pnl_brl=0.0)
    assert len(actions1) == 1  # liberado: 216 >= 216 (limiar e' inclusivo)


def test_filtro_volume_toque_bloqueia_entrada_com_volume_alto():
    strat = _strat(filtro_volume_toque_max=3200.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")

    actions_bloqueado = strat.on_bar(
        ts0, Bar(ts=ts0, open=5.00, high=5.00, low=5.00, close=5.00, volume=5000),
        positions=[], session_pnl_brl=0.0,
    )
    assert actions_bloqueado == []  # bloqueado: 5000 > 3200
    assert strat._state.pending_side is None

    actions_liberado = strat.on_bar(
        ts0, Bar(ts=ts0, open=5.00, high=5.00, low=5.00, close=5.00, volume=1000),
        positions=[], session_pnl_brl=0.0,
    )
    assert len(actions_liberado) == 1  # liberado: 1000 <= 3200


def test_filtro_none_explicito_restaura_comportamento_antigo():
    """Rede de seguranca da regressao: `None` explicito nos dois desliga os
    filtros e devolve exatamente o comportamento de antes de 2026-08-27 --
    entrada imediata na 1a barra, mesmo com minutos=0 e volume altissimo."""
    strat = _strat(filtro_minutos_desde_abertura_min=None, filtro_volume_toque_max=None)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar0 = Bar(ts=ts0, open=5.00, high=5.00, low=5.00, close=5.00, volume=99_999)

    actions = strat.on_bar(ts0, bar0, positions=[], session_pnl_brl=0.0)
    assert len(actions) == 1
    assert actions[0].limit_price == pytest.approx(4.90)
