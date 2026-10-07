import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import motor as m


def test_geometria_e_nulo():
    g, p = m.ganho_perda(60, 120)
    assert (g, p) == (58, 127)
    assert abs(m.nulo_p(60, 120) - 120 / 180) < 1e-12
    # custo empurra o breakeven acima do nulo
    assert m.breakeven_p(g, p) > m.nulo_p(60, 120)
    assert abs(m.esperanca(m.breakeven_p(g, p), g, p)) < 1e-9


def test_resumo_distribuicao():
    r = m.resumo_distribuicao(np.array([10.0, -20.0]), np.array([0.7, 0.3]))
    assert abs(r["esperanca"] - 1.0) < 1e-9
    assert abs(r["win"] - 0.7) < 1e-9 and abs(r["payoff"] - 0.5) < 1e-9
    assert abs(r["breakeven_emp"] - 20 / 30) < 1e-9


def test_ruina_formula_vs_mc():
    res = np.array([5.0, -5.0])
    pr = np.array([0.55, 0.45])
    f = m.ruina_formula(res, pr, caixa=150, piso=100)  # barreira 50 = 10 perdas
    exato = (0.45 / 0.55) ** 10  # gambler's ruin classica
    assert abs(f - exato) / exato < 0.05
    mc = m.ruina_mc(res, pr, 150, n_ops=4000, n_caminhos=4000)["p_ruina"]
    assert abs(mc - exato) < 0.03
    assert m.ruina_formula(np.array([5.0, -5.0]), np.array([0.5, 0.5]), 150, 100) == 1.0


def test_p_encolhido():
    assert abs(m.p_encolhido(0, 0, 0.667) - 0.667) < 1e-12
    assert m.p_encolhido(9, 10, 0.667, n0=100) < 0.7  # 90% em n=10 quase nao move
    assert m.p_encolhido(900, 1000, 0.667, n0=100) > 0.87
    assert m.p_limite_inferior(9, 10, 0.667) < m.p_encolhido(9, 10, 0.667)


def test_n_para_confirmar():
    # +4pp sobre 66,7% exige >150 operacoes para 1 lado a 5%
    assert m.n_para_confirmar(0.667, 0.04) > 150


def test_kelly_e_tamanho():
    g, p = m.ganho_perda(60, 120)
    pn = m.nulo_p(60, 120)
    assert m.tamanho(pn, g, p, 250) == 0  # sem vantagem apos custo
    assert m.tamanho(0.75, g, p, 250) == 1  # caixa minima: 1 contrato
    # teto de pior caso: perda de 1 contrato = R$25,40 nao cabe em 5% de R$250
    assert m.tamanho(0.75, g, p, 250, teto_pior_caso=0.05) == 0
    assert m.tamanho(0.82, g, p, 5000) >= 2
    # margem
    assert m.contratos_por_caixa(99) == 0 and m.contratos_por_caixa(250) == 1
    assert m.contratos_por_caixa(1000) == 4
    # Kelly cheio de binario: n* = C*(pw-ql)/(wl)
    n = m.kelly_contratos(0.75, g, p, 1000, fracao=1.0)
    w, l = g * 0.2, p * 0.2
    assert abs(n - 1000 * (0.75 * w - 0.25 * l) / (w * l)) < 1e-9


def test_vol_stop_alvo():
    s, a = m.stop_alvo_por_vol(1.5, 100)
    assert s == 150 and a == 75
    s2, _ = m.stop_alvo_por_vol(0.5, 100)
    assert s2 == 50
    # stop largo -> menos contratos
    assert m.tamanho_ajustado_vol(5000, 150) < m.tamanho_ajustado_vol(5000, 50) or m.contratos_por_caixa(5000) < 20


def test_indice_vol():
    mins = np.array([540, 541, 570, 571])
    amp = np.array([100.0, 100.0, 50.0, 50.0])
    dst = np.array([True] * 4)
    idx = m.indice_vol_horario(mins, amp, dst)
    assert abs(idx[(True, 540)] - 100 / 75) < 1e-9 and abs(idx[(True, 570)] - 50 / 75) < 1e-9


def test_dst_eua():
    assert not m.dst_eua(dt.date(2026, 2, 27))
    assert not m.dst_eua(dt.date(2026, 3, 7))  # 2o domingo de marco/2026 = dia 8
    assert m.dst_eua(dt.date(2026, 3, 9))
    assert m.dst_eua(dt.date(2026, 10, 30))
    assert not m.dst_eua(dt.date(2026, 11, 2))


def test_combina_sinais():
    b = 0.667
    um = m.combina_sinais(b, [0.70])
    assert abs(um - 0.70) < 1e-9
    ingenuo = m.combina_sinais(b, [0.70, 0.70], rho_medio=0.0)
    corr = m.combina_sinais(b, [0.70, 0.70], rho_medio=1.0)
    assert ingenuo > um > b
    assert abs(corr - um) < 1e-9  # correlacao 1 = mesmo sinal repetido
    enc = m.combina_sinais(b, [0.70], encolhe=[0.5])
    assert b < enc < 0.70


def test_parada_dia():
    pd_ = m.ParadaDia(perda_max_brl=50, n_max_ops=3, n_max_stops=2)
    assert pd_.pode_operar(0, 0, 0)
    assert not pd_.pode_operar(-50, 1, 1)
    assert not pd_.pode_operar(0, 3, 0)
    assert not pd_.pode_operar(0, 2, 2)


def test_constancia():
    r = np.array([10, -5, -5, -5, 20, 3.0])
    mes = np.array([1, 1, 1, 2, 2, 2])
    assert m.pior_sequencia(r) == (3, -15.0)
    assert m.pct_meses_positivos(r, mes) == 0.5  # mes 1 soma 0 (nao positivo), mes 2 soma 18
    assert m.pior_mes(r, mes) == 0.0
    c = m.metricas_constancia(r, mes, 100.0)
    assert abs(c["liquido"] - 18) < 1e-9 and c["pior_seq_ops"] == 3


def test_tamanho_vec_igual_escalar():
    rng = np.random.default_rng(0)
    for _ in range(300):
        p = rng.uniform(0.5, 0.95); a = float(rng.choice([50, 75, 100, 250])); s = float(rng.choice([75, 150, 250, 500]))
        c = float(rng.choice([99, 250, 400, 1000, 5000]))
        g, l = m.ganho_perda(a, s)
        assert m.tamanho(p, g, l, c) == int(m.tamanho_vec(p, g, l, c)), (p, a, s, c)
