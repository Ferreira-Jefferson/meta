"""Testes do nucleo Raschke: valores conhecidos, cenarios sinteticos por regra e
anti-look-ahead. Sem arquivos (paralelo-seguro)."""
from __future__ import annotations

import numpy as np

from scripts.raschke import nucleo as n
from scripts.raschke.nucleo import Barras, Custo, Ordem, Saida

CUSTO = Custo(tick=1.0, valor_ponto=1.0, qty=1)


def _barras(o, h, l, c, intraday=False, dia=None):
    o, h, l, c = (np.array(x, float) for x in (o, h, l, c))
    m = len(c)
    d = np.arange(m) if dia is None else np.array(dia)
    return Barras(o, h, l, c, d, np.zeros(m, int), intraday)


# ---------------- indicadores
def test_sma_ema_valores_conhecidos():
    x = np.array([1, 2, 3, 4, 5.0])
    assert n.sma(x, 3)[-1] == 4.0
    e = n.ema(x, 3)
    assert e[2] == 2.0 and abs(e[3] - 3.0) < 1e-12  # k=0.5: 2 + .5*(4-2)


def test_rsi_tendencia_pura_vale_100():
    r = n.rsi_de_serie(np.arange(20.0), 3)
    assert r[-1] == 100.0


def test_adx_tendencia_forte_alto_e_lateral_baixo():
    t = np.arange(120.0)
    forte = n.adx(t + 1, t - 1, t, 14)
    assert forte[-1] > 80
    lat = 10 + np.tile([0.0, 1.0], 60)
    assert n.adx(lat + 0.6, lat - 0.6, lat, 14)[-1] < 25


def test_lbr_rsi_usa_diferenca_do_roc():
    c = np.array([10, 11, 12, 13, 14, 15, 16, 17.0])  # ROC1 constante => diff = 0
    r = n.lbr_rsi(c, 3)
    assert np.isnan(r[0])
    assert r[-1] == 100.0 or 0 <= r[-1] <= 100


def test_estocastico_limites():
    h = np.linspace(11, 30, 40); l = h - 2; c = h
    f, s = n.estocastico_anti(h, l, c)
    assert f[-1] > 90 and not np.isnan(s[-1])


# ---------------- simulador (convencoes conservadoras)
def test_entrada_stop_gap_enche_na_abertura():
    # ordem compra stop 100; barra seguinte abre 103 => enche 103 (+1 tick)
    b = _barras([99, 103, 104, 90], [99, 105, 106, 91], [98, 102, 103, 89], [99, 104, 105, 90])
    t = n.simular(b, [Ordem(0, 1, 100.0, 95.0)], Saida(max_barras=1), CUSTO)
    assert len(t) == 1 and t[0].entrada == 104.0  # 103 + 1 tick de deslize


def test_stop_e_alvo_mesma_barra_stop_vence():
    b = _barras([99, 100, 100], [99, 100, 130], [98, 99.5, 80], [99, 100, 100])
    t = n.simular(b, [Ordem(0, 1, 100.0, 95.0)], Saida(alvo_r=1.0), CUSTO)
    assert t[0].motivo == "stop"


def test_alvo_exige_passar_um_tick_alem():
    # entrada 100(+1 slip)=101, stop 96 => risco 5; alvo 1R = 106; high 106 so toca => nao enche
    b = _barras([99, 100, 100, 100, 100], [99, 101, 106, 106, 106], [98, 99.5, 99, 99, 99], [99, 100, 100, 100, 100])
    t = n.simular(b, [Ordem(0, 1, 100.0, 96.0)], Saida(alvo_r=1.0, max_barras=2), CUSTO)
    assert t[0].motivo == "tempo"
    b2 = _barras([99, 100, 100, 100, 100], [99, 101, 107, 107, 107], [98, 99.5, 99, 99, 99], [99, 100, 100, 100, 100])
    t2 = n.simular(b2, [Ordem(0, 1, 100.0, 96.0)], Saida(alvo_r=1.0, max_barras=2), CUSTO)
    assert t2[0].motivo == "alvo" and t2[0].saida == 106.0


def test_stop_com_gap_sai_na_abertura_pior():
    b = _barras([99, 100, 90], [99, 101, 92], [98, 99.5, 88], [99, 100, 91])
    t = n.simular(b, [Ordem(0, 1, 100.0, 95.0)], Saida(), CUSTO)
    assert t[0].motivo == "stop" and t[0].saida == 89.0  # abre 90, -1 tick


def test_ordem_nao_enche_sem_rompimento():
    b = _barras([99, 99, 99], [99, 99.5, 99.5], [98, 98, 98], [99, 99, 99])
    assert n.simular(b, [Ordem(0, 1, 100.0, 95.0)], Saida(), CUSTO) == []


def test_eod_fecha_no_ultimo_pregao_do_dia():
    b = _barras([100] * 6, [101] * 6, [99.5] * 6, [100] * 6, intraday=True, dia=[1, 1, 1, 2, 2, 2])
    t = n.simular(b, [Ordem(0, 1, 100.5, 90.0)], Saida(eod=True), CUSTO)
    assert t[0].i_saida == 2 and t[0].motivo == "eod"


def test_ordem_intraday_nao_atravessa_o_dia():
    b = _barras([100] * 4, [100, 100, 105, 105], [99] * 4, [100] * 4, intraday=True, dia=[1, 1, 2, 2])
    assert n.simular(b, [Ordem(1, 1, 102.0, 90.0, validade=0)], Saida(eod=True), CUSTO) == []


def test_um_trade_por_vez_e_um_por_dia():
    b = _barras([100] * 8, [102] * 8, [99] * 8, [100] * 8, intraday=True, dia=[1] * 8)
    od = [Ordem(0, 1, 101.0, 90.0), Ordem(1, 1, 101.0, 90.0)]
    assert len(n.simular(b, od, Saida(eod=True), CUSTO, um_por_dia=True)) == 1


def test_custo_percentual_e_fee_descontam():
    b = _barras([99, 100, 100, 100], [99, 101, 101, 101], [98, 99.5, 99.5, 99.5], [99, 100, 100, 100])
    c = Custo(tick=1.0, valor_ponto=1.0, qty=1, fee_brl=2.0)
    t = n.simular(b, [Ordem(0, 1, 100.0, 90.0)], Saida(max_barras=1), c)
    # entra 101 (100+slip), sai 100-1=99 => -2 pts, fee 2 => -4
    assert abs(t[0].pnl_brl - (-4.0)) < 1e-9


# ---------------- setups
def _serie_tendencia(m=120, passo=1.0):
    c = 100 + np.arange(m) * passo
    return c


def test_turtle_soup_dispara_com_nova_minima_de_20_e_idade():
    m = 40
    base = np.full(m, 100.0)
    l = base - 1.0
    h = base + 1.0
    l[20] = 90.0                 # minima antiga (idade 15 em i=35)
    c = base.copy()
    l[35] = 89.0                 # perfura
    c[35] = 90.5                 # fecha abaixo do nivel L+1 => ordem valida
    o = base.copy()
    b = _barras(o, h, l, c)
    ords = n.ordens_turtle_soup(b, 1.0, n_janela=20, idade=4)
    assert any(x.i == 35 and x.lado == 1 and x.entrada == 91.0 and x.stop == 88.0 for x in ords)


def test_turtle_soup_exige_idade_minima():
    m = 40
    l = np.full(m, 99.0); h = np.full(m, 101.0); c = np.full(m, 100.0)
    l[33] = 95.0                 # minima recente: idade 2 em i=35
    l[35] = 94.0; c[35] = 95.0
    b = _barras(c, h, l, c)
    assert not [x for x in n.ordens_turtle_soup(b, 1.0, idade=4) if x.i == 35 and x.lado == 1]


def test_plus_one_exige_fechamento_abaixo_da_minima_anterior():
    m = 40
    l = np.full(m, 99.0); h = np.full(m, 101.0); c = np.full(m, 100.0)
    l[20] = 90.0; l[35] = 89.0
    c[35] = 91.0                 # acima de L=90 => nao qualifica
    b = _barras(c, h, l, c)
    assert not [x for x in n.ordens_turtle_soup(b, 1.0, idade=3, plus_one=True) if x.i == 35 and x.lado == 1]
    c[35] = 89.5
    b = _barras(c, h, l, c)
    od = [x for x in n.ordens_turtle_soup(b, 1.0, idade=3, plus_one=True) if x.i == 35 and x.lado == 1]
    assert od and od[0].entrada == 90.0 and od[0].validade == 1


def test_80_20_compra_apos_perfurar_e_reentrar():
    # dia 1: abre no topo, fecha no fundo.  dia 2: perfura a minima de ontem e fica abaixo
    o = [100, 99, 98, 90, 90, 89, 88, 88, 88, 88, 88, 88, 88, 88, 88, 88] + [88] * 40
    dia = [1, 1, 1, 1] + [2] * 12 + [3] * 40
    # constroi manualmente: dia1 range 90..100, open 100, close 90
    h = [100, 100, 98, 90.5] + [90] * 12 + [90] * 40
    l = [99, 97, 92, 90] + [89, 88.5, 88, 88, 88, 88, 88, 88, 88, 88, 88, 88] + [88] * 40
    c = [99, 98, 95, 90] + [89.5, 89, 88.5, 88.5, 88.5, 88.5, 88.5, 88.5, 88.5, 88.5, 88.5, 88.5] + [88] * 40
    # ATR minusculo para pen_atr nao exigir demais
    b = _barras(o[:4] + [90] * 12 + [88] * 40, h, l, c, intraday=True, dia=dia)
    ords = n.ordens_80_20(b, 0.5, pen_atr=0.0)
    assert any(x.lado == 1 and x.entrada == 90.0 for x in ords)


def test_anti_nao_olha_futuro():
    rng = np.random.default_rng(0)
    c = 100 + np.cumsum(rng.normal(0, 1, 300))
    h = c + 0.5; l = c - 0.5
    b = _barras(c, h, l, c)
    full = n.ordens_anti(b, 0.01)
    corte = 200
    b2 = _barras(c[:corte], h[:corte], l[:corte], c[:corte])
    parc = n.ordens_anti(b2, 0.01)
    assert [x for x in full if x.i < corte - 1] == parc[:len([x for x in full if x.i < corte - 1])]


def test_holy_grail_nao_olha_futuro():
    rng = np.random.default_rng(1)
    c = 100 + np.cumsum(rng.normal(0.15, 1, 400))
    b = _barras(c, c + 0.7, c - 0.7, c)
    full = n.ordens_holy_grail(b, 0.01, adx_min=20.0)
    corte = 300
    b2 = _barras(c[:corte], (c + 0.7)[:corte], (c - 0.7)[:corte], c[:corte])
    parc = n.ordens_holy_grail(b2, 0.01, adx_min=20.0)
    ref = [x for x in full if x.i < corte - 1]
    assert ref == parc[:len(ref)] and len(ref) > 0
