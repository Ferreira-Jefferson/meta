"""Teste de `GremahTick` (AGENTS.md: toda regra de entrada/saida em
`strategy/` -> teste com cenario sintetico). Cobre os DOIS pontos que
mudaram de contagem-de-barras para tempo-de-parede frente a `Gremah` (M1):
reancoragem rolante por segundos decorridos, e o teto de posicao por volume
acumulado numa janela -- o resto (troca fixa/rolante, alternancia de lado)
e' identico a' `Gremah` e ja coberto por `test_gremah.py`."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from strategy.daytrade.base import Bar
from strategy.daytrade.lab.gremah_tick import (
    _CALIBRATION_BY_SYMBOL_TICK,
    _VOLATILITY_OVERRIDE_BY_SYMBOL_TICK,
    GremahTick,
)


def _strat(**kwargs) -> GremahTick:
    # `filtro_volume_toque_max`/`filtro_distancia_sma20_min_ticks` (2026-08-27):
    # DESLIGADOS por padrão aqui -- os testes deste arquivo cobrem outros
    # mecanismos (reancoragem por tempo, teto de lotes, divisão de entrada
    # etc.), com preço sintético constante que o filtro de distância
    # bloquearia sem relação nenhuma com o que cada teste verifica. Os
    # testes DEDICADOS aos dois filtros (mais abaixo) passam os valores
    # explicitamente, inclusive `None` para provar que restaura este mesmo
    # comportamento de sempre.
    kwargs.setdefault("filtro_volume_toque_max", None)
    kwargs.setdefault("filtro_distancia_sma20_min_ticks", None)
    return GremahTick(profit_pct=0.01, spacing_multiplier=2.0, stop_multiplier=20.0,
                       tick_size=0.01, fixed_anchor_until=time(14, 0), **kwargs)


def test_fase_fixa_ancora_na_abertura():
    strat = _strat()
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    bar = Bar(ts=ts, open=5.00, high=5.00, low=5.00, close=5.00, volume=0)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert len(actions) == 1
    assert actions[0].limit_price == pytest.approx(4.90)  # 5.00 - 2*5 ticks
    assert strat._state.open_price == pytest.approx(5.00)


def test_ordem_rolante_reancora_por_TEMPO_nao_por_contagem_de_ticks():
    # 3600 ticks chegando em 1 segundo cada NAO deveriam reancorar (so'
    # passaram 3600s de tempo simulado, exatamente o limiar de 1h) contra
    # 2 ticks separados por 2 HORAS reancorando de cara -- e' o tempo entre
    # `ts`, nao o numero de `on_bar` chamados, que decide.
    strat = _strat(rolling_reanchor_after_seconds=3600.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 15:00:00", tz="UTC")  # ja na fase rolante
    actions0 = strat.on_bar(ts0, Bar(ts=ts0, open=8.00, high=8.00, low=8.00, close=8.00, volume=0), None, 0.0)
    assert actions0[0].limit_price == pytest.approx(7.84)  # ancorou em 8.00
    assert strat._state.pending_since_ts == ts0

    # 100 ticks em rapida sucessao (1s de intervalo) -- muito tempo real
    # decorrido em CONTAGEM (seria mais que os 30 bars-equivalente da
    # Gremah original), mas so' 100 segundos de verdade: nao reancora.
    ts_rapido = ts0
    for _ in range(100):
        ts_rapido = ts_rapido + pd.Timedelta(seconds=1)
        actions = strat.on_bar(ts_rapido, Bar(ts=ts_rapido, open=8.00, high=8.00, low=8.00, close=8.00, volume=0), None, 0.0)
        assert actions == []
    assert strat._state.pending_mode == "rolling"
    assert strat._state.pending_since_ts == ts0  # ordem original, nao reancorou

    # agora um UNICO tick 2 horas depois do armamento -- tempo real passou
    # o limiar de 1h, reancora mesmo sem nenhum tick intermediario.
    ts_longe = ts0 + pd.Timedelta(hours=2)
    actions_reanchor = strat.on_bar(
        ts_longe, Bar(ts=ts_longe, open=12.00, high=12.00, low=12.00, close=12.00, volume=0), None, 0.0
    )
    assert len(actions_reanchor) == 1
    assert actions_reanchor[0].limit_price == pytest.approx(11.76)  # 12.00 - 2*12 ticks
    assert strat._state.pending_since_ts == ts_longe


def test_teto_de_lotes_reage_a_um_giro_recente_mais_fraco():
    """Substituiu (2026-08-22, pedido do dono) o teto congelado na janela
    inicial: agora e' uma media MOVEL (aqui explicita em 30min so' para a
    aritmetica do teste ficar redonda -- o default de verdade do robo e'
    1min, ver `REALOCACAO_JANELA_MINUTOS_PADRAO`), reavaliada a CADA
    entrada -- um pico isolado nao pode continuar inflando o teto depois
    de sair da janela."""
    strat = _strat(realocacao_teto_pct_volume_minuto=0.10, realocacao_limiar_caixa=0.0001,
                    realocacao_janela_minutos=30.0,
                    rolling_reanchor_after_seconds=1.0)  # limiar de caixa minusculo: nunca e' o gargalo
    strat.on_session_start(None)
    strat.on_capital_update(1_000_000.0)  # caixa gigante: so' o teto de volume deve limitar
    ts0 = pd.Timestamp("2026-01-05 15:00:00", tz="UTC")  # ja em fase rolante

    # 1 negocio de 93.000 acoes -- media por minuto (janela nominal de
    # 30min, sem cauda) = 93000/30 = 3100; teto 10% = 310 acoes = 3 lotes.
    actions0 = strat.on_bar(ts0, Bar(ts=ts0, open=5.00, high=5.00, low=5.00, close=5.00, volume=93_000), None, 0.0)
    assert len(actions0) == 1
    assert actions0[0].quantity == 300

    # 31 minutos depois -- o pico de 93.000 ja SAIU da janela de 30min, e o
    # giro recente foi so' 300 acoes. A ordem ficou velha (reancoragem em
    # 1s) e reancora aqui, RECONSULTANDO o teto -- que tem que refletir o
    # giro mais fraco, nao continuar travado nos 3 lotes iniciais.
    ts1 = ts0 + pd.Timedelta(minutes=31)
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

    Teto pelo NEGOCIO TIPICO (mediana), nao pela media/minuto, desde
    2026-08-24 (ver `GremahTick._lotes_por_realocacao`) -- com os 30 eventos
    da cauda mais o de hoje (31 >= `capacidade_min_eventos`), a mediana
    (10.000 acoes) e' o fluxo REAL observado, sem diluir pelo tamanho
    NOMINAL da janela como a media fazia."""
    strat = _strat(realocacao_teto_pct_volume_minuto=0.10, realocacao_limiar_caixa=0.0001,
                    realocacao_janela_minutos=30.0)
    ontem_fim = pd.Timestamp("2026-01-05 20:55:00", tz="UTC")
    cauda = [
        Bar(ts=ontem_fim - pd.Timedelta(minutes=m), open=5.0, high=5.0, low=5.0, close=5.0, volume=10_000.0)
        for m in range(29, -1, -1)
    ]  # 30 eventos x 10.000 acoes = 300.000 no total
    strat.seed_volume_window(cauda)
    strat.on_session_start(None)
    strat.on_capital_update(1_000_000.0)

    hoje_abertura = pd.Timestamp("2026-01-06 13:00:00", tz="UTC")
    actions = strat.on_bar(
        hoje_abertura, Bar(ts=hoje_abertura, open=5.00, high=5.00, low=5.00, close=5.00, volume=0.0),
        None, 0.0,
    )

    # mediana dos 31 eventos (30 da cauda a 10.000 + a barra de hoje a 0) =
    # 10.000 acoes; teto = 10.000 x capacidade_negocio_mult (4) = 40.000
    # acoes -- bem mais que o minimo de 1 lote que "sem cauda" produziria.
    assert len(actions) == 1
    assert actions[0].quantity == 40_000


# ---------- divisao de entrada em pedacos (2026-08-22) --------------------
# So' tem efeito de verdade com `IntradayBacktestConfig.
# limit_fill_capped_by_volume=True` (testado em `test_intraday_machine.py`);
# aqui so' a LOGICA de fatiamento, isolada do motor.

def test_dividir_entrada_ligado_por_default():
    # Padrao `True` desde 2026-08-23 (pedido do dono, depois de medir IS/OOS
    # -- ver a memoria `dividir_entrada_is_oos_2026_08_23` do projeto).
    assert GremahTick(symbol="PMAM3").dividir_entrada is True


def test_exit_ttl_bars_padrao_e_8():
    # Decidido 2026-08-23 apos varrer 1..10 em PMAM3 (IS+OOS) -- ver a
    # memoria `exit_ttl_bars_decisao_2026_08_23` do projeto.
    assert GremahTick(symbol="PMAM3").exit_ttl_bars == 8


def test_dividir_pecas_1_lote_ou_menos_nao_divide():
    strat = _strat(dividir_entrada=True)
    assert strat._dividir_pecas(0) is None
    assert strat._dividir_pecas(100) is None  # 1 lote sozinho -- nada a dividir


def test_dividir_pecas_1_lote_fixo_por_pedaco_abaixo_do_teto():
    strat = _strat(dividir_entrada=True, dividir_max_pecas=8)

    pecas = strat._dividir_pecas(500)  # 5 lotes, abaixo do teto de 8

    assert pecas == (100, 100, 100, 100, 100)


def test_dividir_pecas_e_prefixo_estavel_independente_do_total():
    # pedido do dono 2026-08-24: os mesmos primeiros lotes de uma entrada
    # pequena tem que aparecer IDENTICOS numa entrada maior -- ordens de 1
    # lote fixo sao independentes entre si, entao o prefixo nao muda.
    strat = _strat(dividir_entrada=True, dividir_max_pecas=8)

    pecas_7 = strat._dividir_pecas(700)
    pecas_5 = strat._dividir_pecas(500)

    assert pecas_7[:5] == pecas_5 == (100, 100, 100, 100, 100)


def test_dividir_pecas_respeita_o_teto_de_pedacos_cauda_absorve_excedente():
    strat = _strat(dividir_entrada=True, dividir_max_pecas=3)

    pecas = strat._dividir_pecas(1000)  # 10 lotes, teto de 3 pedacos

    assert pecas is not None
    assert len(pecas) == 3
    assert sum(pecas) == 1000
    # primeiros 2 pedacos continuam de 1 lote (prefixo intacto); a cauda
    # absorve o resto (8 lotes), nao distribui igualmente entre os 3.
    assert pecas == (100, 100, 800)


def test_janela_do_teto_de_volume_e_1min_por_decisao_do_dono_2026_08_22():
    """Mesma decisao (e mesma ressalva de que 30min media MELHOR, IS+OOS,
    na medicao feita em M1) documentada em `test_gremah.py` -- o pedido
    original cobria os dois robos, entao o mesmo valor foi aplicado aqui."""
    assert GremahTick(symbol="PMAM3").realocacao_janela_minutos == pytest.approx(1.0)


# ---------- calibracao por simbolo (ponto de partida copiado do M1) -------

@pytest.mark.parametrize("symbol,profit_pct,stop_multiplier", [
    ("PMAM3", 0.0032, 20.0),
    ("CSAN3", 0.0015, 5.0),
    ("KLBN4", 0.0015, 5.0),
])
def test_calibracao_por_simbolo_e_usada_quando_nao_sobrescrita(symbol, profit_pct, stop_multiplier):
    strat = GremahTick(symbol=symbol)

    assert strat.profit_pct == pytest.approx(profit_pct)
    assert strat.stop_multiplier == pytest.approx(stop_multiplier)
    assert _CALIBRATION_BY_SYMBOL_TICK[symbol].profit_pct == pytest.approx(profit_pct)


def test_simbolo_desconhecido_sem_override_falha_alto():
    with pytest.raises(ValueError, match="ATIVO_INEXISTENTE"):
        GremahTick(symbol="ATIVO_INEXISTENTE")


# ---------- override por simbolo: (k,s) confirmado no OOS (2026-08-23) ----

@pytest.mark.parametrize("symbol,k,s", [
    ("GRND3", 0.05, 8.0),
])
def test_override_de_volatilidade_liga_sozinho_para_simbolo_confirmado(symbol, k, s):
    """Mesmo mecanismo/motivo de `gremah.
    test_override_de_volatilidade_liga_sozinho_para_simbolo_confirmado` --
    GRND3 e' o primeiro simbolo confirmado em TICK com par de volatilidade
    em vez de percentual (2026-08-23)."""
    strat = GremahTick(symbol=symbol)

    assert strat.alvo_por_volatilidade is True
    assert strat.alvo_vol_mult == pytest.approx(k)
    assert strat.stop_vol_mult == pytest.approx(s)
    assert _VOLATILITY_OVERRIDE_BY_SYMBOL_TICK[symbol] == (k, s)


@pytest.mark.parametrize("symbol", ["PMAM3", "BMGB4", "KLBN3", "LPSB3", "DASA3", "KLBN4", "PCAR3", "CSAN3"])
def test_simbolos_sem_override_de_volatilidade_continuam_no_percentual(symbol):
    strat = GremahTick(symbol=symbol)

    assert symbol not in _VOLATILITY_OVERRIDE_BY_SYMBOL_TICK
    assert strat.alvo_por_volatilidade is False


def test_alvo_vol_mult_explicito_vence_o_override_tick():
    strat = GremahTick(symbol="GRND3", alvo_vol_mult=0.99)

    assert strat.alvo_vol_mult == pytest.approx(0.99)
    assert strat.alvo_vol_mult != _VOLATILITY_OVERRIDE_BY_SYMBOL_TICK["GRND3"][0]


def test_stop_vol_mult_explicito_vence_o_s_do_override_tick():
    strat = GremahTick(symbol="GRND3", stop_vol_mult=99.0)

    assert strat.alvo_vol_mult == pytest.approx(_VOLATILITY_OVERRIDE_BY_SYMBOL_TICK["GRND3"][0])
    assert strat.stop_vol_mult == pytest.approx(99.0)


# ---------- alvo por volatilidade (2026-08-23, opt-in) --------------------
# Mesmo mecanismo de `test_gremah.py` (mesma classe base) -- cobre so' que a
# `GremahTick` tem a MESMA API, nao repete a aritmetica ja' coberta la.

def _diaria(rng: float) -> Bar:
    ts = pd.Timestamp("2026-01-04 18:00:00", tz="UTC")
    return Bar(ts=ts, open=10.0, high=10.0 + rng, low=10.0, close=10.0, volume=0)


def test_alvo_por_volatilidade_exige_mult_explicito():
    with pytest.raises(ValueError):
        GremahTick(symbol="PMAM3", alvo_por_volatilidade=True)


def test_alvo_por_volatilidade_sem_janela_cai_no_fallback_percentual():
    strat = _strat(alvo_por_volatilidade=True, alvo_vol_mult=0.5)
    profit, spacing, stop = strat._session_ticks(5.00)
    assert profit == strat._ticks_from_pct(5.00, strat.profit_pct)
    assert spacing == strat._ticks_from_pct(5.00, strat.profit_pct * strat.spacing_multiplier)
    assert stop == strat._ticks_from_pct(5.00, strat.profit_pct * strat.stop_multiplier)


def test_alvo_por_volatilidade_usa_range_mediano_quando_disponivel():
    strat = _strat(alvo_por_volatilidade=True, alvo_vol_mult=0.5)
    strat.seed_daily_volatility([_diaria(10.0), _diaria(20.0), _diaria(30.0)])  # mediana = 20.0

    profit, _, _ = strat._session_ticks(999.0)  # preco IGNORADO quando ha' volatilidade
    assert profit == max(1, round(20.0 * 0.5 / strat.tick_size))


def test_stop_vol_mult_global_vence_stop_multiplier_por_simbolo():
    strat = _strat(alvo_por_volatilidade=True, alvo_vol_mult=0.5, stop_vol_mult=8.0)
    strat.seed_daily_volatility([_diaria(10.0), _diaria(20.0), _diaria(30.0)])

    _, _, stop = strat._session_ticks(999.0)
    assert stop == max(1, round(20.0 * 0.5 * 8.0 / strat.tick_size))


def test_stop_frac_range_troca_so_o_stop():
    strat = _strat(stop_frac_range=0.5)
    strat.seed_daily_volatility([_diaria(10.0), _diaria(20.0), _diaria(30.0)])

    profit, spacing, stop = strat._session_ticks(5.00)
    assert profit == strat._ticks_from_pct(5.00, strat.profit_pct)
    assert stop == max(1, round(20.0 * 0.5 / strat.tick_size))


def test_stop_frac_range_sem_janela_cai_no_fallback_percentual():
    strat = _strat(stop_frac_range=0.5)
    profit, spacing, stop = strat._session_ticks(5.00)
    assert stop == strat._ticks_from_pct(5.00, strat.profit_pct * strat.stop_multiplier)


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


# ---------------------------------------------------------------------------
# Filtros de qualidade de ENTRADA (2026-08-27) -- `volume_toque` e
# `distancia_sma20_ticks`, confirmados no OOS (`scripts/daytrade/
# signal_quality_gremahtick_2026_08_27.py` +
# `signal_quality_gremahtick_oos_2026_08_27.py`, PMAM3 motor tick). Pedido
# do dono: aplicar JA' em producao, limiares confirmados como DEFAULT (nao
# opt-in desligado) -- ver `FILTRO_VOLUME_TOQUE_MAX_PADRAO`/`FILTRO_
# DISTANCIA_SMA20_MIN_TICKS_PADRAO` no modulo.
# ---------------------------------------------------------------------------

def test_filtros_qualidade_sinal_ligados_por_padrao():
    """(a) Construcao DEFAULT (sem passar nada) tem os dois filtros ATIVOS
    nos limiares confirmados -- nao "desligado por padrao"."""
    strat = GremahTick(symbol="PMAM3")

    assert strat.filtro_volume_toque_max == pytest.approx(400.0)
    assert strat.filtro_distancia_sma20_min_ticks == pytest.approx(0.70)


def test_filtro_distancia_sma20_bloqueia_reancoragem_contra_a_media():
    """`filtro_distancia_sma20_min_ticks`: so' usa dado ANTERIOR ao toque,
    entao barra a TENTATIVA de armar a ordem (nunca precisa desfazer nada).
    10 ticks parados em 8.00 constroem a media; um pulo de ancora pra 20.00
    (reancoragem rolante, ordem ficou velha) fica longe DEMAIS da media na
    direcao ERRADA -- bloqueado, igual a nao ter havido sinal nenhum."""
    strat = _strat(filtro_distancia_sma20_min_ticks=0.70, rolling_reanchor_after_seconds=5.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 15:00:00", tz="UTC")
    actions0 = strat.on_bar(ts0, Bar(ts=ts0, open=8.00, high=8.00, low=8.00, close=8.00, volume=0), None, 0.0)
    assert len(actions0) == 1  # 1o tick da sessao: janela vazia, filtro nao bloqueia
    assert strat._state.pending_side == "long"

    ts = ts0
    for _ in range(9):  # completa 10 fechamentos anteriores (minimo da janela)
        ts = ts + pd.Timedelta(seconds=0.1)
        actions = strat.on_bar(ts, Bar(ts=ts, open=8.00, high=8.00, low=8.00, close=8.00, volume=0), None, 0.0)
        assert actions == []  # ordem ainda pendente, nao reancora (< 5s)

    # 1h depois, preco salta pra 20.00 -- ordem fica velha (tenta reancorar),
    # mas a media (10 x 8.00) fica MUITO abaixo do novo nivel: bloqueado.
    ts_longe = ts0 + pd.Timedelta(hours=1)
    actions_bloqueadas = strat.on_bar(
        ts_longe, Bar(ts=ts_longe, open=20.00, high=20.00, low=20.00, close=20.00, volume=0), None, 0.0,
    )
    assert actions_bloqueadas == []
    assert strat._state.pending_side == "long"  # continua a ordem ANTIGA
    assert strat._state.pending_since_ts == ts0  # nao reancorou de verdade


def test_filtro_distancia_sma20_none_desativa_e_reancora_normal():
    """(b) `filtro_distancia_sma20_min_ticks=None` restaura o comportamento
    de sempre -- MESMO cenario do teste acima (pulo de preco contra a
    media), mas agora reancora sem checar distancia nenhuma."""
    strat = _strat(filtro_distancia_sma20_min_ticks=None, rolling_reanchor_after_seconds=5.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 15:00:00", tz="UTC")
    strat.on_bar(ts0, Bar(ts=ts0, open=8.00, high=8.00, low=8.00, close=8.00, volume=0), None, 0.0)
    ts = ts0
    for _ in range(9):
        ts = ts + pd.Timedelta(seconds=0.1)
        strat.on_bar(ts, Bar(ts=ts, open=8.00, high=8.00, low=8.00, close=8.00, volume=0), None, 0.0)

    ts_longe = ts0 + pd.Timedelta(hours=1)
    actions = strat.on_bar(
        ts_longe, Bar(ts=ts_longe, open=20.00, high=20.00, low=20.00, close=20.00, volume=0), None, 0.0,
    )
    assert len(actions) == 1  # sem o filtro, reancora normalmente
    assert strat._state.pending_since_ts == ts_longe


def test_filtro_volume_toque_desfaz_fill_de_volume_alto():
    """`filtro_volume_toque_max`: so' e' conhecido DEPOIS que o negocio de
    toque ja aconteceu (o motor ja abriu a posicao ANTES de chamar `on_bar`,
    ver `IntradaySessionMachine.on_closed_bar`), entao a unica coisa
    possivel e' desfazer -- `Exit` imediato quando o volume do toque
    (`bar.volume` NESTA MESMA barra) excede o limiar."""
    strat = _strat(filtro_volume_toque_max=50.0)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 15:00:00", tz="UTC")
    actions0 = strat.on_bar(ts0, Bar(ts=ts0, open=8.00, high=8.00, low=8.00, close=8.00, volume=0), None, 0.0)
    assert len(actions0) == 1
    assert strat._state.pending_side == "long"

    # o motor "preencheu": proxima chamada chega com posicao ja aberta e o
    # volume do PROPRIO negocio de toque acima do limiar (50).
    ts1 = ts0 + pd.Timedelta(seconds=1)
    actions1 = strat.on_bar(
        ts1, Bar(ts=ts1, open=7.84, high=7.84, low=7.84, close=7.84, volume=100.0),
        [object()], 0.0,
    )

    assert len(actions1) == 1
    assert actions1[0].reason == "filtro_volume_toque"
    assert strat._state.pending_side is None
    assert strat._state.open_side == "long"  # a posicao foi contabilizada como aberta de verdade
    assert strat._state.long_fills == 1


def test_filtro_volume_toque_none_desativa_e_aceita_qualquer_fill():
    """(b) `filtro_volume_toque_max=None` restaura o comportamento de sempre
    -- MESMO fill de volume gigante do teste acima, mas agora aceito sem
    `Exit` nenhum."""
    strat = _strat(filtro_volume_toque_max=None)
    strat.on_session_start(None)
    ts0 = pd.Timestamp("2026-01-05 15:00:00", tz="UTC")
    strat.on_bar(ts0, Bar(ts=ts0, open=8.00, high=8.00, low=8.00, close=8.00, volume=0), None, 0.0)

    ts1 = ts0 + pd.Timedelta(seconds=1)
    actions1 = strat.on_bar(
        ts1, Bar(ts=ts1, open=7.84, high=7.84, low=7.84, close=7.84, volume=999_999.0),
        [object()], 0.0,
    )

    assert actions1 == []  # aceito normalmente, sem Exit forcado
    assert strat._state.pending_side is None
    assert strat._state.open_side == "long"
    assert strat._state.long_fills == 1
