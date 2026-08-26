"""Contrato compartilhado da familia de day trade (`strategy/daytrade/base.py`).

Cobre `capital_minimo_brl`, que saiu de `lab/gremah.py` em 2026-08-22: a regra
"2x o custo de 1 lote" nao e' de UM robo, vale para qualquer robo intradiario
que opere lote padrao sem fracionario -- e `live/intraday_runtime.py` precisa
consultar a MESMA funcao que a ficha exibe e que dimensionou o capital de todo
backtest da tabela de calibracao (AGENTS.md #6: `live/` aplica regra
declarada, nunca inventa a propria).
"""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.daytrade.base import (
    CAPITAL_MINIMO_EM_LOTES,
    LOTE_PADRAO_B3,
    Bar,
    JanelaVolatilidadeDiaria,
    RollingVolumeWindow,
    barra_diaria,
    capital_minimo_brl,
    geometria_e_degenerada,
)


def test_capital_minimo_e_o_dobro_do_custo_de_um_lote():
    """Regra do dono, 2026-08-22, com o exemplo que ele deu: PMAM3 a R$0,14
    -> lote de R$14,00 -> minimo R$28,00."""
    assert capital_minimo_brl(0.14) == pytest.approx(28.0)
    assert capital_minimo_brl(3.64) == pytest.approx(728.0)   # CSAN3
    assert capital_minimo_brl(151.95) == pytest.approx(30_390.0)  # CLSC4


def test_capital_minimo_acompanha_o_preco_sem_arredondar():
    """Substituiu (2026-08-22) a regra de arredondar pra cima ao proximo
    multiplo de R$50, que dava folga absurdamente desigual conforme o preco
    (PMAM3 R$14 -> R$50 era 3,6x o lote; CSAN3 R$364 -> R$400, so 1,1x).
    Agora a proporcao e' a MESMA em qualquer preco, e por isso um centavo a
    mais no preco move o minimo -- e' o comportamento pretendido, ja que o
    piso e' reavaliado a cada pregao."""
    assert capital_minimo_brl(1.00) == pytest.approx(200.0)
    assert capital_minimo_brl(1.01) == pytest.approx(202.0)
    for preco in (0.09, 0.5, 3.66, 5.08, 75.09):
        assert capital_minimo_brl(preco) % 50 != 0 or preco in (0.5,)


def test_capital_minimo_usa_o_lote_que_o_robo_de_fato_negocia():
    """`shares_per_lot` nao e' decoracao: quem chama ao vivo passa
    `config.default_quantity` (a quantidade que o robo realmente manda por
    ordem), para o piso cobrir o que sera' comprado -- nao um lote de
    referencia que nao corresponde a ordem."""
    assert capital_minimo_brl(2.00, shares_per_lot=100) == pytest.approx(400.0)
    assert capital_minimo_brl(2.00, shares_per_lot=200) == pytest.approx(800.0)
    assert capital_minimo_brl(2.00) == capital_minimo_brl(2.00, shares_per_lot=LOTE_PADRAO_B3)


def test_constantes_declaradas_batem_com_a_formula():
    """Se alguem mudar `CAPITAL_MINIMO_EM_LOTES` sem querer, isto pega -- a
    formula e as constantes nao podem divergir em silencio."""
    assert CAPITAL_MINIMO_EM_LOTES == pytest.approx(2.0)
    assert LOTE_PADRAO_B3 == 100
    assert capital_minimo_brl(7.0) == pytest.approx(7.0 * LOTE_PADRAO_B3 * CAPITAL_MINIMO_EM_LOTES)


# ---------- RollingVolumeWindow (2026-08-22, pedido do dono: media movel --
# substitui o teto de posicao antigo, congelado no primeiro minuto/janela
# inicial do pregao) --------------------------------------------------------

def _bar(ts: pd.Timestamp, volume: float) -> Bar:
    return Bar(ts=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=volume)


def test_media_por_minuto_sem_cauda_e_conservadora_ate_a_janela_encher():
    """Sem cauda do pregao anterior, minutos ainda nao vividos hoje contam
    como volume ZERO -- divide SEMPRE pela janela NOMINAL (30min por
    default), nunca so' pelo tempo decorrido. E' o lado seguro: superestimar
    o teto de posicao e' o erro caro (o book real nao absorve uma ordem
    grande demais), subestimar so' custa lote a menos."""
    janela = RollingVolumeWindow(janela_minutos=30.0)
    janela.iniciar_sessao()
    t0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    janela.registrar(t0, 3000.0)  # 1 unico evento, 0min decorridos

    assert janela.media_por_minuto(t0) == pytest.approx(3000.0 / 30.0)


def test_media_por_minuto_com_janela_cheia_e_a_media_de_verdade():
    janela = RollingVolumeWindow(janela_minutos=30.0)
    janela.iniciar_sessao()
    t0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    for i in range(30):
        janela.registrar(t0 + pd.Timedelta(minutes=i), 100.0)

    ts_final = t0 + pd.Timedelta(minutes=29)
    assert janela.media_por_minuto(ts_final) == pytest.approx(100.0)


def test_evicta_eventos_mais_velhos_que_a_propria_janela():
    """Um pico isolado bem antigo nao pode continuar inflando a media
    depois de sair da janela -- so' os eventos DENTRO dela contam."""
    janela = RollingVolumeWindow(janela_minutos=10.0)
    janela.iniciar_sessao()
    t0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    janela.registrar(t0, 100_000.0)  # pico isolado
    for i in range(1, 11):
        janela.registrar(t0 + pd.Timedelta(minutes=i), 10.0)
    ts_final = t0 + pd.Timedelta(minutes=11)
    janela.registrar(ts_final, 10.0)  # 11min depois do pico -- ja saiu da janela de 10min

    assert janela.media_por_minuto(ts_final) == pytest.approx(10.0)


def test_cauda_do_pregao_anterior_completa_o_deficit_na_abertura():
    """Pedido literal do dono: 'na abertura ele considera tambem as ultimas
    barras do dia anterior' -- sem os 30min de hoje ainda vividos, a media
    usa o final REAL do pregao anterior em vez de assumir volume zero."""
    janela = RollingVolumeWindow(janela_minutos=30.0)
    ontem_fim = pd.Timestamp("2026-01-05 20:55:00", tz="UTC")
    cauda = [_bar(ontem_fim - pd.Timedelta(minutes=m), 100.0) for m in range(29, -1, -1)]
    janela.definir_cauda_anterior(cauda)  # 30 barras x 100 acoes = 3000 no total
    janela.iniciar_sessao()

    hoje_abertura = pd.Timestamp("2026-01-06 13:00:00", tz="UTC")
    janela.registrar(hoje_abertura, 500.0)

    # 0min decorridos hoje -- deficit inteiro (30min) vem da cauda.
    assert janela.media_por_minuto(hoje_abertura) == pytest.approx((3000.0 + 500.0) / 30.0)


def test_cauda_para_de_ser_usada_assim_que_hoje_acumula_a_janela_inteira():
    janela = RollingVolumeWindow(janela_minutos=5.0)
    ontem_fim = pd.Timestamp("2026-01-05 20:55:00", tz="UTC")
    janela.definir_cauda_anterior([_bar(ontem_fim, 999_999.0)])  # pico enorme
    janela.iniciar_sessao()

    hoje_abertura = pd.Timestamp("2026-01-06 13:00:00", tz="UTC")
    for i in range(6):
        janela.registrar(hoje_abertura + pd.Timedelta(minutes=i), 100.0)
    ts_final = hoje_abertura + pd.Timedelta(minutes=5)  # 5min decorridos == janela inteira

    # decorrido (5min) NAO e' menor que a janela (5min) -- cauda ignorada,
    # o pico de ontem nao pode mais aparecer na media.
    assert janela.media_por_minuto(ts_final) == pytest.approx(100.0)


def test_definir_cauda_pode_vir_antes_ou_depois_de_iniciar_sessao():
    """As duas ordens de chamada tem que produzir o MESMO resultado -- ao
    vivo a cauda e' buscada no INICIO de `_start_session`, antes do warm
    start decidir cold vs quente; no backtest e' antes de `begin_session`."""
    ontem_fim = pd.Timestamp("2026-01-05 20:55:00", tz="UTC")
    cauda = [_bar(ontem_fim, 1000.0)]
    hoje = pd.Timestamp("2026-01-06 13:00:00", tz="UTC")

    antes = RollingVolumeWindow(janela_minutos=30.0)
    antes.definir_cauda_anterior(cauda)
    antes.iniciar_sessao()

    depois = RollingVolumeWindow(janela_minutos=30.0)
    depois.iniciar_sessao()
    depois.definir_cauda_anterior(cauda)

    assert antes.media_por_minuto(hoje) == pytest.approx(depois.media_por_minuto(hoje))


def test_cauda_vazia_e_o_default_seguro():
    """`definir_cauda_anterior([])` (primeiro pregao do historico, ou feed
    sem dado do dia anterior) tem que se comportar EXATAMENTE como nunca
    ter sido chamado -- nunca um erro, nunca um valor inventado."""
    com_chamada_vazia = RollingVolumeWindow(janela_minutos=30.0)
    com_chamada_vazia.definir_cauda_anterior([])
    com_chamada_vazia.iniciar_sessao()

    sem_chamada = RollingVolumeWindow(janela_minutos=30.0)
    sem_chamada.iniciar_sessao()

    t0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    com_chamada_vazia.registrar(t0, 900.0)
    sem_chamada.registrar(t0, 900.0)

    assert com_chamada_vazia.media_por_minuto(t0) == pytest.approx(sem_chamada.media_por_minuto(t0))


# ---------- barra_diaria / JanelaVolatilidadeDiaria (2026-08-23, alvo por
# volatilidade em vez de percentual do preco -- ver `strategy.daytrade.lab.
# gremah`/`gremah_tick`) -------------------------------------------------

def _bar_ohlc(hhmm: str, o, h, low, c) -> Bar:
    return Bar(ts=pd.Timestamp(f"2026-01-05 {hhmm}", tz="UTC"),
               open=float(o), high=float(h), low=float(low), close=float(c), volume=100.0)


def test_barra_diaria_agrega_ohlc_da_sessao_inteira():
    barras = [
        _bar_ohlc("13:00", 10.0, 10.5, 9.8, 10.2),
        _bar_ohlc("13:01", 10.2, 11.0, 10.1, 10.9),
        _bar_ohlc("13:02", 10.9, 10.9, 9.5, 9.6),
    ]
    diaria = barra_diaria(barras)
    assert diaria.open == pytest.approx(10.0)      # da PRIMEIRA barra
    assert diaria.high == pytest.approx(11.0)       # max de todas
    assert diaria.low == pytest.approx(9.5)         # min de todas
    assert diaria.close == pytest.approx(9.6)       # da ULTIMA barra
    assert diaria.volume == pytest.approx(300.0)    # soma
    assert diaria.ts == barras[-1].ts


def test_barra_diaria_vazia_e_none():
    assert barra_diaria([]) is None


def test_janela_volatilidade_vazia_devolve_none():
    janela = JanelaVolatilidadeDiaria(janela_dias=10)
    assert janela.range_mediano() is None


def test_janela_volatilidade_e_a_mediana_do_range_diario():
    janela = JanelaVolatilidadeDiaria(janela_dias=5)
    for rng in (3.0, 5.0, 100.0, 4.0, 6.0):  # mediana = 5.0, 100.0 e' outlier
        janela.registrar_dia(_bar_ohlc("18:00", 10.0, 10.0 + rng, 10.0, 10.0))
    assert janela.range_mediano() == pytest.approx(5.0)


def test_janela_volatilidade_descarta_alem_do_tamanho_declarado():
    """So' as ultimas `janela_dias` sessoes contam -- um pregao antigo demais
    nao pode continuar influenciando a mediana."""
    janela = JanelaVolatilidadeDiaria(janela_dias=3)
    janela.registrar_dia(_bar_ohlc("18:00", 10.0, 1_000.0, 10.0, 10.0))  # sai da janela
    for rng in (1.0, 2.0, 3.0):
        janela.registrar_dia(_bar_ohlc("18:00", 10.0, 10.0 + rng, 10.0, 10.0))
    assert janela.range_mediano() == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# `geometria_e_degenerada` -- a funcao pura por tras da guarda das duas
# estrategias da familia `gremah`. Testada aqui, isolada, porque e' o unico
# lugar em que a REGRA vive (as classes so' a chamam).
# ---------------------------------------------------------------------------


def test_geometria_degenerada_stop_colado_no_alvo():
    """O caso da PMAM3 a R$0,13: 1 tick de alvo contra 1 tick de stop."""
    assert geometria_e_degenerada(1, 1, 1.5) is True


def test_geometria_degenerada_pega_o_caso_intermediario():
    """O criterio e' RAZAO, nao igualdade: 3 contra 4 sao numeros diferentes e
    mesmo assim nada parecidos com o `stop_multiplier=20` que a calibracao
    pretendia."""
    assert geometria_e_degenerada(3, 4, 1.5) is True
    assert geometria_e_degenerada(3, 5, 1.5) is False


def test_geometria_sadia_nao_e_degenerada():
    assert geometria_e_degenerada(1, 20, 1.5) is False
    assert geometria_e_degenerada(2, 3, 1.5) is False


def test_sem_stop_nao_e_geometria_degenerada():
    """`None` e' "este desenho nao usa stop", outra coisa -- e nao cabe a esta
    funcao opinar sobre ele."""
    assert geometria_e_degenerada(1, None, 1.5) is False


def test_razao_minima_e_o_criterio_de_quem_chama():
    """1.0 aceita qualquer stop >= alvo; e' o ajuste que transforma a guarda de
    "quero assimetria" em "so' nao aceito stop MENOR que o alvo"."""
    assert geometria_e_degenerada(1, 1, 1.0) is False
    assert geometria_e_degenerada(2, 1, 1.0) is True
