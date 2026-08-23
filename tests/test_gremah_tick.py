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
from strategy.daytrade.lab.gremah_tick import _CALIBRATION_BY_SYMBOL_TICK, GremahTick


def _strat(**kwargs) -> GremahTick:
    return GremahTick(profit_pct=0.01, spacing_multiplier=2.0, stop_multiplier=20.0,
                       tick_size=0.01, fixed_anchor_until=time(14, 0), **kwargs)


def test_fase_fixa_ancora_na_abertura():
    strat = _strat()
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    bar = Bar(ts=ts, open=5.00, high=5.00, low=5.00, close=5.00, volume=0)

    actions = strat.on_bar(ts, bar, position=None, session_pnl_brl=0.0)

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
    verdade do robo e' 1min."""
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

    # media = 300.000 da cauda / 30 = 10.000 acoes/min; teto 10% = 1.000
    # acoes = 10 lotes -- nao o minimo de 1 lote que "sem cauda" produziria.
    assert len(actions) == 1
    assert actions[0].quantity == 1_000


# ---------- divisao de entrada em pedacos (2026-08-22, EXPLORATORIO) -------
# So' tem efeito de verdade com `IntradayBacktestConfig.
# limit_fill_capped_by_volume=True` (testado em `test_intraday_machine.py`);
# aqui so' a LOGICA de fatiamento, isolada do motor.

def test_dividir_entrada_desligado_por_default():
    assert GremahTick(symbol="PMAM3").dividir_entrada is False


def test_dividir_pecas_sem_evento_na_janela_nao_divide():
    strat = _strat(dividir_entrada=True)
    ts = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    assert strat._dividir_pecas(500, ts) is None


def test_dividir_pecas_quando_negocio_tipico_ja_cobre_o_total():
    strat = _strat(dividir_entrada=True)
    ts0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    strat._janela_volume.registrar(ts0, 10_000.0)  # 1 negocio tipico de 10.000 acoes

    assert strat._dividir_pecas(500, ts0) is None  # 500 < 10.000 -- nada a dividir


def test_dividir_pecas_fatia_perto_do_negocio_tipico_recente():
    strat = _strat(dividir_entrada=True, dividir_max_pecas=8)
    ts0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    for i in range(5):
        strat._janela_volume.registrar(ts0 + pd.Timedelta(seconds=i), 100.0)  # negocios de 1 lote

    pecas = strat._dividir_pecas(500, ts0 + pd.Timedelta(seconds=5))

    assert pecas is not None
    assert sum(pecas) == 500
    assert all(p % 100 == 0 for p in pecas)
    assert len(pecas) == 5  # 500/100 acoes = 5 pedacos de 1 lote, o tamanho tipico


def test_dividir_pecas_respeita_o_teto_de_pedacos():
    strat = _strat(dividir_entrada=True, dividir_max_pecas=3)
    ts0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    strat._janela_volume.registrar(ts0, 100.0)  # negocio tipico de 1 lote

    pecas = strat._dividir_pecas(1000, ts0)  # pediria 10 pedacos, teto corta em 3

    assert pecas is not None
    assert len(pecas) == 3
    assert sum(pecas) == 1000
    # distribuido o mais igual possivel (4/3/3 lotes), nao 10/0/0.
    assert sorted(pecas) == [300, 300, 400]


def test_janela_do_teto_de_volume_e_1min_por_decisao_do_dono_2026_08_22():
    """Mesma decisao (e mesma ressalva de que 30min media MELHOR, IS+OOS,
    na medicao feita em M1) documentada em `test_gremah.py` -- o pedido
    original cobria os dois robos, entao o mesmo valor foi aplicado aqui."""
    assert GremahTick(symbol="PMAM3").realocacao_janela_minutos == pytest.approx(1.0)


# ---------- calibracao por simbolo (ponto de partida copiado do M1) -------

@pytest.mark.parametrize("symbol,profit_pct,stop_multiplier", [
    ("PMAM3", 0.0032, 10.0),
    ("CSAN3", 0.0021, 20.0),
    ("KLBN4", 0.0021, 5.0),
])
def test_calibracao_por_simbolo_e_usada_quando_nao_sobrescrita(symbol, profit_pct, stop_multiplier):
    strat = GremahTick(symbol=symbol)

    assert strat.profit_pct == pytest.approx(profit_pct)
    assert strat.stop_multiplier == pytest.approx(stop_multiplier)
    assert _CALIBRATION_BY_SYMBOL_TICK[symbol].profit_pct == pytest.approx(profit_pct)


def test_simbolo_desconhecido_sem_override_falha_alto():
    with pytest.raises(ValueError, match="ATIVO_INEXISTENTE"):
        GremahTick(symbol="ATIVO_INEXISTENTE")
