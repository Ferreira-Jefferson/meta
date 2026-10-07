"""Testes do motor Larry Williams (scripts/larry_williams/).

Filosofia: cada teste e' um cenario construido a mao em que a resposta e' conhecida
(o que a corretora faria), nao um espelho do codigo. Cobrem:
  (a) cada setup + as convencoes de execucao (gap que fecha o range, outside day,
      empate stop x entrada = pior caso, ordem expira no fim do dia, bailout so' na
      ABERTURA seguinte);
  (b) anti-look-ahead: mutar/truncar o futuro nao muda nenhum sinal nem trade passado;
  (c) paridade de capital minimo com o repo;
  (d) so' tmp_path e sem dependencia de ordem (roda em paralelo, -n auto).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_LW = Path(__file__).resolve().parents[1] / "scripts" / "larry_williams"
if str(_LW) not in sys.path:
    sys.path.insert(0, str(_LW))

import lw_dados as D  # noqa: E402
import lw_setups as S  # noqa: E402
import lw_sim as M  # noqa: E402

NAN = float("nan")


# ---------------------------------------------------------------- helpers
def ativo_diario(o, h, l, c, classe="ACAO", lote=None):
    n = len(o)
    datas = np.datetime64("2024-01-02") + np.arange(n)
    return M.criar_ativo("T", classe, datas, o, h, l, c, lote=lote)


def ativo_m1(dias, classe="WIN"):
    """dias = lista de listas de barras (o,h,l,c); minutos consecutivos a partir de 09:00."""
    O, H, L, C, minuto, dia_id = [], [], [], [], [], []
    for d, barras in enumerate(dias):
        for k, (o, h, l, c) in enumerate(barras):
            O.append(o), H.append(h), L.append(l), C.append(c)
            minuto.append(540 + k), dia_id.append(d)
    datas = np.datetime64("2024-01-02") + np.arange(len(dias))
    return D._ativo_de_m1(classe, datas, O, H, L, C, np.array(minuto), np.array(dia_id), classe=classe)


def passeio(n=400, seed=1, base=100.0):
    rng = np.random.default_rng(seed)
    c = base + np.cumsum(rng.normal(0, 1.0, n))
    o = np.r_[base, c[:-1]] + rng.normal(0, 0.4, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.5, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.5, n))
    return o, h, l, c


def cfg(**kw):
    base = dict(lados="CV", stop_modo="frac", stop_frac=0.5, saida="FECHAMENTO")
    base.update(kw)
    return M.ConfigSim(**base)


def rodar(at, sin, **kw):
    return M.gerar_trades(at, sin, cfg(**kw))


# ================================================================ (a) SETUPS E EXECUCAO
def test_vb_niveis_sao_abertura_mais_k_vezes_range_de_ontem():
    o = np.array([100, 102.0, 106]); h = np.array([110, 108.0, 106.2])
    l = np.array([100, 103.0, 105.9]); c = np.array([105, 106.0, 106])
    sin = S.setup_vb(o, h, l, c, kc=0.5, kv=0.3)
    assert np.isnan(sin.nivel_c[0])
    assert sin.nivel_c[1] == pytest.approx(102 + 0.5 * 10)
    assert sin.nivel_v[1] == pytest.approx(102 - 0.3 * 10)
    assert sin.tipo_c == S.STOP and sin.tipo_v == S.STOP


def test_vb_compra_dispara_no_nivel_e_sai_no_fechamento():
    o = np.array([100, 102.0, 106]); h = np.array([110, 108.0, 106.2])
    l = np.array([100, 103.0, 105.9]); c = np.array([105, 106.0, 106])
    at = ativo_diario(o, h, l, c)
    tr = rodar(at, S.setup_vb(o, h, l, c, 0.5, 0.5))
    assert len(tr) == 1
    t = tr[0]
    assert (t.lado, t.dia_ent, t.px_ent, t.dia_sai, t.px_sai, t.motivo) == (1, 1, 107.0, 1, 106.0, "FECHAMENTO")
    assert t.slip_ent and t.slip_sai


def test_vb_venda_espelha_a_compra():
    # dia1: abre 102, sell stop em 97 (Kv=0.5, R1=10); minima 96 -> dispara; fecha 98
    o = np.array([100, 102.0, 98]); h = np.array([110, 102.5, 98.1])
    l = np.array([100, 96.0, 97.9]); c = np.array([105, 98.0, 98])
    at = ativo_diario(o, h, l, c)
    tr = rodar(at, S.setup_vb(o, h, l, c, 0.5, 0.5), stop_frac=1.0)
    assert len(tr) == 1
    t = tr[0]
    assert (t.lado, t.px_ent, t.px_sai, t.motivo) == (-1, 97.0, 98.0, "FECHAMENTO")
    p = M.pnl_dos_trades(at, tr, 0.0)
    assert p["pts"][0] == pytest.approx(97.0 - 98.0)   # venda perde quando o preco sobe


def test_empate_stop_x_entrada_na_mesma_barra_assume_pior_caso():
    # entrada em 107 e stop em 102 (0,5*R1=5) ambos dentro da barra do dia 1 (L=101 < 102)
    o = np.array([100, 102.0, 106]); h = np.array([110, 108.0, 106.2])
    l = np.array([100, 101.0, 105.9]); c = np.array([105, 106.0, 106])
    at = ativo_diario(o, h, l, c)
    tr = rodar(at, S.setup_vb(o, h, l, c, 0.5, 0.5))
    assert len(tr) == 1 and tr[0].motivo == "STOP" and tr[0].px_sai == 102.0 and tr[0].dia_sai == 1


def test_vb_dois_niveis_tocados_no_mesmo_candle_diario_vale_o_mais_proximo_da_abertura():
    # Kc=0.3 (buy 105), Kv=0.8 (sell 94): ambos tocados no candle diario -> compra (mais proxima)
    o = np.array([100, 102.0, 100]); h = np.array([110, 106.0, 100.1])
    l = np.array([100, 93.0, 99.9]); c = np.array([105, 99.0, 100])
    at = ativo_diario(o, h, l, c)
    tr = rodar(at, S.setup_vb(o, h, l, c, 0.3, 0.8), stop_modo="sem")
    assert len(tr) == 1 and tr[0].lado == 1 and tr[0].px_ent == pytest.approx(105.0)


def test_m1_resolve_qual_nivel_veio_primeiro_dentro_do_dia():
    # R1=100. dia1 abre 100050: buy 100100 / sell 100000 equidistantes. A venda toca primeiro (barra 1).
    dia0 = [(100000, 100100, 100000, 100050)] * 5
    dia1 = [(100050, 100060, 100040, 100050),
            (100050, 100040, 99990, 100000),      # toca sell stop 100000 (H nao passa do stop)
            (100000, 100110, 99995, 100100),      # toca buy 100100 depois (e estopa a venda em 100050)
            (100100, 100100, 100090, 100095)]
    dia1[1] = (100050, 100040, 99990, 100000)
    at = ativo_m1([dia0, dia1])
    sin = S.setup_vb(at.o, at.h, at.l, at.c, 0.5, 0.5)
    tr = M.gerar_trades(at, sin, cfg(saida="FECHAMENTO", stop_frac=0.5))
    assert len(tr) == 1
    t = tr[0]
    assert t.lado == -1 and t.px_ent == 100000 and t.px_sai == 100050 and t.motivo == "STOP"
    assert t.hora_ent == 541   # 09:01


def test_oops_gap_que_fecha_o_range_entra_em_L_de_ontem_e_sai_na_abertura_seguinte():
    o = np.array([100, 98.0, 100.9]); h = np.array([110, 101.0, 103.0])
    l = np.array([100, 97.0, 100.5]); c = np.array([105, 100.5, 102.5])
    sin = S.setup_oops(o, h, l, c)
    assert sin.nivel_c[1] == 100.0 and np.isnan(sin.nivel_v[1])    # abriu ABAIXO da minima de ontem
    at = ativo_diario(o, h, l, c)
    tr = rodar(at, sin, saida="ABERTURA_SEGUINTE")
    assert len(tr) == 1
    t = tr[0]
    assert (t.lado, t.px_ent, t.dia_sai, t.px_sai, t.motivo) == (1, 100.0, 2, 100.9, "ABERTURA_SEGUINTE")


def test_oops_ordem_expira_no_fim_do_dia_e_nao_vira_ordem_do_dia_seguinte():
    # dia1 abre em gap abaixo (98<100) mas nunca volta a 100 (max 99,5). Dia2 toca 100,5
    # mas o sinal de dia1 morreu com o pregao: nenhum trade.
    o = np.array([100, 98.0, 99.0]); h = np.array([110, 99.5, 100.5])
    l = np.array([100, 97.0, 98.0]); c = np.array([105, 99.0, 100.0])
    sin = S.setup_oops(o, h, l, c)
    assert sin.nivel_c[1] == 100.0 and np.isnan(sin.nivel_c[2])
    assert rodar(ativo_diario(o, h, l, c), sin, saida="ABERTURA_SEGUINTE") == []


def _smash_base():
    # dia0: min 100. dia1 (S): fecha 99 < 100 -> SMASH altista; dia2: buy stop em H(S)=103, stop em L(S)=98
    o = np.array([102, 101.0, 100.0, 104.0, 103.0, 105.0, 107.0])
    h = np.array([105, 103.0, 104.0, 106.0, 108.0, 109.0, 110.0])
    l = np.array([100, 98.0, 99.5, 103.0, 102.5, 104.0, 106.0])
    c = np.array([103, 99.0, 103.5, 105.0, 107.0, 108.0, 109.0])
    return o, h, l, c


def test_smash_niveis_e_stop_no_extremo_de_S():
    o, h, l, c = _smash_base()
    sin = S.setup_smash(o, h, l, c, n=1)
    assert sin.nivel_c[2] == 103.0 and sin.stop_abs_c[2] == 98.0
    assert np.isnan(sin.nivel_c[1]) and np.isnan(sin.nivel_v[2])


def test_smash_gap_acima_do_nivel_executa_na_abertura_pior_preco():
    o, h, l, c = _smash_base()
    o = o.copy(); o[2] = 104.0; h = h.copy(); h[2] = 105.0; l = l.copy(); l[2] = 103.5
    at = ativo_diario(o, h, l, c)
    tr = rodar(at, S.setup_smash(o, h, l, c), stop_modo="abs")
    assert tr[0].px_ent == 104.0     # buy stop 103 + gap: paga a abertura


def test_bailout_so_na_abertura_seguinte_e_so_se_lucrativa():
    # entra dia2 em 103 (stop 98). Dia2 fecha 103,5 (lucro) -> NAO sai no dia 2.
    # Dia3 abre 103 (nao e' >= entrada+tick) -> segura. Dia4 abre 104 -> BAILOUT em 104.
    o = np.array([102, 101.0, 100.0, 103.0, 104.0, 105.0])
    h = np.array([105, 103.0, 104.0, 105.0, 106.0, 106.0])
    l = np.array([100, 98.0, 99.5, 102.0, 103.5, 104.0])
    c = np.array([103, 99.0, 103.5, 104.0, 105.0, 105.5])
    at = ativo_diario(o, h, l, c)
    tr = rodar(at, S.setup_smash(o, h, l, c), stop_modo="abs", saida="BAILOUT")
    assert len(tr) == 1
    t = tr[0]
    assert t.dia_ent == 2 and t.px_ent == 103.0
    assert (t.dia_sai, t.px_sai, t.motivo) == (4, 104.0, "BAILOUT")


def test_bailout_espera_N_dias_antes_de_aceitar():
    o = np.array([102, 101.0, 100.0, 104.0, 105.0, 106.0])
    h = np.array([105, 103.0, 104.0, 106.0, 107.0, 107.0])
    l = np.array([100, 98.0, 99.5, 103.5, 104.5, 105.0])
    c = np.array([103, 99.0, 103.5, 105.0, 106.0, 106.5])
    at = ativo_diario(o, h, l, c)
    tr = rodar(at, S.setup_smash(o, h, l, c), stop_modo="abs", saida="BAILOUT", bailout_dias=1)
    assert tr[0].dia_sai == 4 and tr[0].px_sai == 105.0     # dia3 ainda "cedo" (espera 1 dia)


def test_stop_com_gap_de_abertura_executa_na_abertura_pior_que_o_stop():
    o = np.array([102, 101.0, 100.0, 96.0, 97.0])
    h = np.array([105, 103.0, 104.0, 97.0, 98.0])
    l = np.array([100, 98.0, 99.5, 95.0, 96.0])
    c = np.array([103, 99.0, 103.5, 96.5, 97.5])
    at = ativo_diario(o, h, l, c)
    tr = rodar(at, S.setup_smash(o, h, l, c), stop_modo="abs", saida="BAILOUT")
    assert (tr[0].dia_sai, tr[0].px_sai, tr[0].motivo) == (3, 96.0, "STOP_GAP")


def test_hsmash_exige_fechar_de_alta_na_zona_inferior_do_range():
    # S=dia1: c(99,5)>c0(99), range 100..110, 99,5 e' o fundo (<=25%), c<o.
    o = np.array([100, 108.0, 101.0]); h = np.array([102, 110.0, 105.0])
    l = np.array([98, 99.0, 100.0]); c = np.array([99, 100.0, 104.0])
    sin = S.setup_hsmash(o, h, l, c, zona=0.25, exige_close_contra_open=True)
    assert sin.nivel_c[2] == 110.0 and sin.stop_abs_c[2] == 99.0
    # com zona menor (5%) o fechamento (100 em 99..110 = 9%) nao qualifica
    assert np.isnan(S.setup_hsmash(o, h, l, c, zona=0.05).nivel_c[2])
    # se fechasse acima da abertura, a versao 'melhor' (c<o) rejeita
    o2 = o.copy(); o2[1] = 99.5
    assert np.isnan(S.setup_hsmash(o2, h, l, c, exige_close_contra_open=True).nivel_c[2])


def test_outside_day_sinal_altista_e_modos_de_entrada():
    o = np.array([9, 9.0, 7.0, 8.0]); h = np.array([10, 11.0, 8.0, 9.0])
    l = np.array([8, 7.0, 6.5, 7.5]); c = np.array([9, 7.5, 7.8, 8.5])
    # S=dia1: H 11>10, L 7<8, C 7,5<8 -> altista; dia2 abre 7 < C(S)=7,5 -> compra
    m = S.setup_outside(o, h, l, c, "A_MERCADO_NA_ABERTURA")
    assert m.nivel_c[2] == 7.0 and m.tipo_c == S.MERCADO
    li = S.setup_outside(o, h, l, c, "LIMITE_NO_FECHAMENTO_S")
    assert li.nivel_c[2] == 7.5 and li.tipo_c == S.LIMITE
    assert np.isnan(m.nivel_c[3])
    # abertura ACIMA do fechamento de S derruba o filtro
    o2 = o.copy(); o2[2] = 8.0
    assert np.isnan(S.setup_outside(o2, h, l, c).nivel_c[2])
    # lado venda desligado por padrao
    assert np.all(np.isnan(m.nivel_v))


def test_limite_so_preenche_se_o_preco_atravessa():
    o = np.array([9, 9.0, 7.0, 8.0]); h = np.array([10, 11.0, 8.0, 9.0])
    l = np.array([8, 7.0, 7.5, 7.5]); c = np.array([9, 7.5, 7.8, 8.5])
    li = S.setup_outside(o, h, l, c, "LIMITE_NO_FECHAMENTO_S")
    # abertura 7 <= 7,5: limite "marketable" preenche na abertura (como taker)
    tr = rodar(ativo_diario(o, h, l, c), li, stop_modo="sem")
    assert tr[0].px_ent == 7.0 and tr[0].slip_ent
    # agora o nivel (7,5) fica ABAIXO da abertura (8) e a minima so' TOCA 7,5: nao preenche
    o3 = o.copy(); o3[2] = 8.0; l3 = l.copy(); l3[2] = 7.5
    sin = S.setup_outside(o3, h, l3, c, "LIMITE_NO_FECHAMENTO_S")
    assert np.isnan(sin.nivel_c[2])   # filtro O<C(S) falha
    # construcao direta: limite de compra em 7,5 com abertura 8 e minima exatamente 7,5
    sin2 = S.Sinais("X", np.array([NAN, 7.5]), np.full(2, NAN), S.LIMITE, S.LIMITE, base_stop=np.array([NAN, 2.0]))
    at = ativo_diario(np.array([8, 8.0]), np.array([9, 8.5]), np.array([7, 7.5]), np.array([8, 8.0]))
    assert M.gerar_trades(at, sin2, cfg(stop_modo="sem")) == []          # tocar != preencher
    at2 = ativo_diario(np.array([8, 8.0]), np.array([9, 8.5]), np.array([7, 7.4]), np.array([8, 8.0]))
    assert M.gerar_trades(at2, sin2, cfg(stop_modo="sem"))[0].px_ent == 7.5


def test_gsv_valores_do_swing():
    o = np.array([10, 11, 12, 11.5, 12.5, 13, 12.0]); h = np.array([12, 13, 14, 13.5, 14.5, 15, 14.0])
    l = np.array([9, 10, 11, 10.5, 11.5, 12, 11.0]); c = np.array([11, 12, 13, 12.0, 13.5, 14, 12.5])
    v = S.valor_gsv(h, l, "C")
    # j=3: max(H0-L3, H2-L0) = max(12-10.5, 14-9) = 5
    assert v[3] == pytest.approx(5.0)
    vv = S.valor_gsv(h, l, "V")
    # j=3 (venda): max(H3-L0, H0-L2) = max(13.5-9, 12-11) = 4.5
    assert vv[3] == pytest.approx(4.5)
    sin = S.setup_gsv(o, h, l, c, n=1, kc=0.8, kv=1.2)
    # dia 4: S=3 fechou 12 > abriu 11,5 (dia de alta) -> so' venda; nivel = o - 1,2*GSV_v(3)
    assert np.isnan(sin.nivel_c[4]) and sin.nivel_v[4] == pytest.approx(12.5 - 1.2 * 4.5)


def test_percent_r_escala_0_100_com_100_sobrevendido():
    h = np.array([10, 11, 12, 13.0]); l = np.array([5, 6, 7, 8.0]); c = np.array([8, 9, 12, 8.0])
    r = S.percent_r(h, l, c, n=4)
    assert r[3] == pytest.approx(100.0 * (13 - 8) / (13 - 5))
    c2 = np.array([8, 9, 12, 5.0]); l2 = l.copy(); l2[3] = 5.0
    assert S.percent_r(h, l2, c2, n=4)[3] == pytest.approx(100.0)      # fechou na minima = sobrevendido


def test_wr_gatilho_toca_100_espera_e_volta_abaixo_de_95():
    r = np.array([50, 100, 99, 99, 99, 99, 90, 60.0])
    sc, sv = S.gatilhos_wr(r, espera=5, gatilho=95.0)
    # tocou 100 em t=1; passam 5 pregoes em t=6 e %R=90 <95 -> dispara em t=6, uma vez so'
    assert list(np.flatnonzero(sc)) == [6]
    sc2, _ = S.gatilhos_wr(r, espera=3, gatilho=95.0)
    assert list(np.flatnonzero(sc2)) == [6]   # %R=99 (>=95) segura o gatilho ate cair para 90


def test_wr_toque_com_tolerancia_dispara_onde_o_toque_literal_em_100_nao_ocorre():
    r = np.array([60, 97, 90, 90, 90, 90, 90, 60.0])       # nunca chega a 100
    assert S.gatilhos_wr(r, espera=5, gatilho=95.0)[0].sum() == 0
    sc, _ = S.gatilhos_wr(r, espera=5, gatilho=95.0, toque=95.0)
    assert list(np.flatnonzero(sc)) == [6]


def test_ultimate_oscillator_valor_conhecido():
    h = np.array([10, 12, 13.0]); l = np.array([8, 9, 11.0]); c = np.array([9, 11, 12.0])
    uo = S.ultimate_oscillator(h, l, c, periodos=(1, 1, 1))
    # t=1: BP = 11-min(9,9)=2 ; TR = max(12,9)-min(9,9)=3 -> UO=100*2/3
    assert uo[1] == pytest.approx(100 * 2 / 3)
    # t=2: BP = 12-min(11,11)=1 ; TR = 13-11 = 2 -> 50
    assert uo[2] == pytest.approx(50.0)


def test_pivo_de_3_barras_so_e_confirmado_na_barra_seguinte():
    l = np.array([5, 4, 3, 4, 5.0]); h = l + 2
    pa, pb = S.pivos_3_barras(h, l)
    assert pb[3] == 3.0 and np.isnan(pb[2])    # pivo em t=2, so' conhecido em t=3
    assert np.all(np.isnan(pa))


def test_tendencia_de_alta_apos_romper_o_ultimo_topo_e_sem_look_ahead():
    # zigzag ascendente: topos e fundos crescentes
    c = np.array([10, 12, 11, 13, 12, 15, 14, 17, 16, 19.0])
    h = c + 0.5; l = c - 0.5
    t = S.tendencia(h, l, c, "SWING")
    assert t[-1] == 1 and t[0] == 0
    # tendencia em D usa so' ate D-1: mudar o candle de D nao altera t[D]
    h2, l2, c2 = h.copy(), l.copy(), c.copy()
    h2[-1], l2[-1], c2[-1] = 100, -100, -50
    assert S.tendencia(h2, l2, c2, "SWING")[-1] == t[-1]
    # espelho: queda
    cb = 40 - c
    assert S.tendencia(cb + 0.5, cb - 0.5, cb, "SWING")[-1] == -1


def test_tendencia_inside_day_e_ignorado():
    c = np.array([10, 12, 11, 13, 12.5, 15, 14, 17, 16, 19.0])
    h = np.array([10.5, 12.5, 11.5, 13.5, 12.8, 15.5, 14.5, 17.5, 16.5, 19.5])
    l = np.array([9.5, 11.5, 10.5, 12.5, 12.2, 14.5, 13.5, 16.5, 15.5, 18.5])   # dia 4 e' inside (12.2..12.8 dentro de 12.5..13.5)
    assert S.tendencia(h, l, c, "SWING")[-1] == 1


def test_filtros_de_dia_mes_e_tendencia():
    o = np.arange(6) + 100.0
    sin = S.setup_vb(o, o + 2, o - 2, o, 0.5, 0.5)
    dow = np.array([0, 1, 2, 3, 4, 0]); mes = np.array([1, 1, 1, 2, 2, 2])
    tend = np.array([0, 1, 1, -1, -1, 1], dtype=np.int8)
    f = S.aplicar_filtros(sin, dow, mes, tend, dias_c=[1, 2], dias_v=[3], usar_tendencia=True)
    assert np.isnan(f.nivel_c[0]) and not np.isnan(f.nivel_c[2]) and np.isnan(f.nivel_c[4])
    assert not np.isnan(f.nivel_v[3]) and np.isnan(f.nivel_v[4])
    g = S.aplicar_filtros(sin, dow, mes, tend, meses_bloqueados=[1])
    assert np.isnan(g.nivel_c[2]) and not np.isnan(g.nivel_c[4])


def test_tdm_primeiro_pregao_do_mes_e_tdw():
    ano_mes = np.array([202401] * 3 + [202402] * 3)
    dom = S.dia_do_pregao_no_mes(ano_mes)
    assert list(dom) == [1, 2, 3, 1, 2, 3]
    o = np.arange(6) + 10.0
    sin = S.setup_tdm(o, o + 1, o - 1, o, dom, np.array([1, 1, 1, 2, 2, 2]), dias=(1,), meses_bloqueados=(2,))
    assert sin.nivel_c[0] == 10.0 and np.isnan(sin.nivel_c[3]) and np.isnan(sin.nivel_c[1])
    tdw = S.setup_tdw(o, o + 1, o - 1, o, np.array([0, 1, 2, 3, 4, 0]), dias_compra=(0,))
    assert list(np.flatnonzero(np.isfinite(tdw.nivel_c))) == [0, 5]
    # saida no fechamento do mesmo dia
    at = ativo_diario(o, o + 1, o - 1, o + 0.5)
    tr = M.gerar_trades(at, tdw, cfg(stop_modo="sem"))
    assert all(t.dia_ent == t.dia_sai and t.motivo == "FECHAMENTO" for t in tr)


def test_uo_gatilho_de_divergencia_altista():
    # dois fundos de preco (2o mais baixo) com UO mais alto no 2o; UO1 < 30; depois UO rompe o pico.
    l = np.array([10, 9, 8, 9, 10, 9.5, 7.5, 8, 9, 10, 11.0]); h = l + 1
    uo = np.array([50, 40, 20, 35, 45, 40, 25, 30, 40, 50, 60.0])   # fundo1 em t=2 (20) / fundo2 em t=6 (25)
    sc, sv = S.gatilhos_uo(h, l, uo, uo_compra_max=30, uo_venda_min=50, validade=10)
    # pivo2 (t=6) confirmado em t=7; pico entre os fundos = 45 -> UO > 45 em t=9 (50)
    assert list(np.flatnonzero(sc)) == [9]


def test_tres_barras_limite_na_sma3_minimas_alvo_na_sma3_maximas():
    dia0 = [(5000, 5004, 5000, 5002)] * 5     # R1 = 4
    dia1 = [(105, 110, 100, 105), (105, 111, 101, 105), (105, 112, 102, 105),   # SMA3 min=101, max=111
            (105, 106, 100.5, 105.5),      # barra 3: minima 100,5 < 101 -> preenche em 101
            (106, 112, 105, 111.5),        # barra 4: maxima 112 > alvo 111 -> ALVO
            (108, 108, 108, 108), (108, 108, 108, 108), (108, 108, 108, 108), (108, 108, 108, 108)]
    at = ativo_m1([dia0, dia1], classe="WDO")
    tend = np.array([0, 1], dtype=np.int8)
    tr = M.gerar_trades_tres_barras(at, tf=1, stop_frac=1.0, tend=tend)
    assert len(tr) == 1
    t = tr[0]
    assert (t.lado, t.px_ent, t.px_sai, t.motivo, t.slip_ent, t.slip_sai) == (1, 101.0, 111.0, "ALVO", False, False)
    # sem tendencia de alta, nao opera
    assert M.gerar_trades_tres_barras(at, tf=1, stop_frac=1.0, tend=np.zeros(2, dtype=np.int8)) == []


def test_reversao_vb_sai_no_nivel_oposto_e_inverte():
    # Dia1 compra em 105 (O100,K0,5,R1=10). Dia2 abre 106; sell stop do dia2 = 106-0,5*R1(dia1)
    o = np.array([100, 100.0, 106.0, 100.0]); h = np.array([110, 106.0, 107.0, 100.5])
    l = np.array([100, 99.0, 100.0, 99.0]); c = np.array([105, 106.0, 101.0, 100.0])
    sin = S.setup_vb(o, h, l, c, 0.5, 0.5)
    # dia1: buy 105 (R1=10); dia1 venda 95 nao tocada (l=99). dia2: R1=7 -> sell 106-3,5=102,5 ; tocado (l=100)
    tr = rodar(ativo_diario(o, h, l, c), sin, saida="REVERSAO", stop_modo="sem")
    assert tr[0].lado == 1 and tr[0].px_ent == 105.0
    assert tr[0].motivo == "REVERSAO" and tr[0].px_sai == pytest.approx(102.5) and tr[0].dia_sai == 2
    assert tr[1].lado == -1 and tr[1].dia_ent == 2 and tr[1].px_ent == pytest.approx(102.5)


def test_alvo_rr_e_stop_na_mesma_barra_vale_o_stop():
    o = np.array([102, 101.0, 100.0, 104.0])
    h = np.array([105, 103.0, 104.0, 120.0])
    l = np.array([100, 98.0, 99.5, 90.0])
    c = np.array([103, 99.0, 103.5, 110.0])
    at = ativo_diario(o, h, l, c)
    tr = rodar(at, S.setup_smash(o, h, l, c), stop_modo="abs", saida="RR", rr=1.0)
    # entrada dia2 em 103, stop 98, alvo 108; dia3 toca 120 e 90 na mesma barra -> STOP
    assert tr[0].motivo == "STOP" and tr[0].px_sai == 98.0


# ================================================================ custos / caixa / capital
def test_custos_vem_do_repo_futuro_um_tick_de_slippage():
    at = ativo_m1([[(100000, 100100, 100000, 100050)] * 3], classe="WIN")
    t = M.Trade(1, 0, 100000.0, 0, 100100.0, "FECHAMENTO", True, True, 540)
    p0 = M.pnl_dos_trades(at, [t], 0.0)
    p1 = M.pnl_dos_trades(at, [t], 1.0)
    assert p0["brl"][0] == pytest.approx(100 * 0.20 - 0.50)             # 100 pts * R$0,20 - R$0,50
    assert p1["brl"][0] == pytest.approx((100 - 10) * 0.20 - 0.50)      # 1 tick (5 pts) em CADA ponta


def test_custos_acao_usam_taxa_de_bolsa_do_repo():
    from backtest.intraday.costs import B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG
    at = ativo_diario(np.array([10.0, 10]), np.array([11.0, 11]), np.array([9.0, 9]), np.array([10.0, 10]))
    t = M.Trade(1, 0, 10.0, 0, 11.0, "FECHAMENTO", False, False, -1)
    p = M.pnl_dos_trades(at, [t], 0.0)
    assert p["brl"][0] == pytest.approx(100 * 1.0 - B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG * 100 * 21.0)


def test_paridade_de_capital_minimo_com_o_repo():
    from strategy.daytrade.base import contracts_from_capital_com_reserva, capital_minimo_brl
    win = ativo_m1([[(1, 1, 1, 1)]], classe="WIN")
    wdo = ativo_m1([[(1, 1, 1, 1)]], classe="WDO")
    assert M.capital_inicial(win, 0) == 250.0 and M.capital_inicial(wdo, 0) == 375.0
    # o capital minimo e' exatamente o que da' 1 contrato COM a reserva do motor; R$1 a menos da' 0
    for at in (win, wdo):
        cap = M.capital_inicial(at, 0)
        assert contracts_from_capital_com_reserva(cap, at.margem) == 1
        assert contracts_from_capital_com_reserva(cap - 1, at.margem) == 0
    acao = ativo_diario(np.array([37.0]), np.array([38.0]), np.array([36.0]), np.array([37.5]))
    assert M.capital_inicial(acao, 37.0) == capital_minimo_brl(37.0, shares_per_lot=100) == 7400.0
    etf = ativo_diario(np.array([37.0]), np.array([38.0]), np.array([36.0]), np.array([37.5]), classe="ETF_BTC")
    assert M.capital_inicial(etf, 37.0) == 74.0      # lote 1


def test_portao_de_caixa_futuro_so_a_margem_crua_barra_o_resto():
    win = ativo_m1([[(1, 1, 1, 1)]], classe="WIN")
    trades = [M.Trade(1, i, 100.0, i, 100.0, "X", False, False, -1) for i in range(3)]
    ok, final, pulados, minimo = M.aplica_caixa(win, trades, np.array([-200.0, 10.0, 10.0]),
                                                np.array([100.0] * 3), capital=250.0)
    # 250 >= 100: 1o entra (-> 50); 50 < margem 100: barrados. O R$250 de partida e' so' de PARTIDA.
    assert list(ok) == [True, False, False] and pulados == 2 and final == 50.0 and minimo == 50.0
    ok2, final2, p2, _ = M.aplica_caixa(win, trades, np.array([-100.0, 10.0, 10.0]),
                                        np.array([100.0] * 3), capital=250.0)
    assert list(ok2) == [True, True, True] and final2 == 170.0      # 150 >= margem crua: continua


def test_estatisticas_win_ao_lado_do_breakeven_empirico():
    at = ativo_m1([[(1, 1, 1, 1)]], classe="WIN")
    trades = [M.Trade(1, i, 100000.0, i, 100000.0 + d, "X", False, False, -1)
              for i, d in enumerate([100, 100, -50, -50, -50])]
    e = M.estatisticas(at, trades, 0.0, 250.0, pregoes=5, portao=False)
    ganho, perda = 100 * 0.2 - 0.5, 50 * 0.2 + 0.5
    assert e["n"] == 5 and e["win_pct"] == pytest.approx(40.0)
    assert e["be_emp_pct"] == pytest.approx(100 * perda / (ganho + perda))
    assert e["liquido"] == pytest.approx(2 * ganho - 3 * perda)
    # R$/op > 0 <=> win% > breakeven empirico (mesma afirmacao)
    assert (e["exp_brl"] > 0) == (e["win_pct"] > e["be_emp_pct"])


# ================================================================ (b) ANTI LOOK-AHEAD
def _todos_os_setups(o, h, l, c, at):
    cal = at.calendario()
    out = {
        "VB": S.setup_vb(o, h, l, c, 0.5, 0.7),
        "OOPS": S.setup_oops(o, h, l, c, 0.1),
        "SMASH": S.setup_smash(o, h, l, c, 3),
        "HSMASH": S.setup_hsmash(o, h, l, c),
        "OUTSIDE": S.setup_outside(o, h, l, c, lado_venda=True),
        "OUTSIDE_L": S.setup_outside(o, h, l, c, "LIMITE_NO_FECHAMENTO_S", lado_venda=True),
        "GSV": S.setup_gsv(o, h, l, c),
        "WR": S.setup_wr(o, h, l, c),
        "UO": S.setup_uo(o, h, l, c, uo_compra_max=45, uo_venda_min=45),
        "TDM": S.setup_tdm(o, h, l, c, cal["dom_pregao"], cal["mes"], (1, 2)),
        "TDW": S.setup_tdw(o, h, l, c, cal["dow"], (0, 2), (4,)),
    }
    return out


def _vetores(sin):
    v = [sin.nivel_c, sin.nivel_v, sin.base_stop]
    for x in (sin.stop_abs_c, sin.stop_abs_v, sin.saida_osc_c, sin.saida_osc_v):
        if x is not None:
            v.append(np.asarray(x, dtype=float))
    return v


@pytest.mark.parametrize("seed", [1, 2])
def test_anti_look_ahead_sinais_nao_mudam_se_o_futuro_for_mutado_ou_truncado(seed):
    o, h, l, c = passeio(300, seed)
    at = ativo_diario(o, h, l, c)
    cheio = _todos_os_setups(o, h, l, c, at)
    for corte in (60, 137, 250):
        # 1) apaga TUDO depois de `corte` (futuro) e MUTA h/l/c do proprio dia `corte`
        o2, h2, l2, c2 = (x[:corte + 1].copy() for x in (o, h, l, c))
        h2[corte], l2[corte], c2[corte] = h2[corte] + 50, l2[corte] - 50, c2[corte] + 33
        at2 = ativo_diario(o2, h2, l2, c2)
        parcial = _todos_os_setups(o2, h2, l2, c2, at2)
        for nome in cheio:
            for a, b in zip(_vetores(cheio[nome]), _vetores(parcial[nome])):
                np.testing.assert_array_equal(a[:corte + 1], b, err_msg=f"{nome} corte={corte}")
        # 2) tendencia conhecida em D nao usa D
        for modo in ("SWING", "SMA"):
            t_full = S.tendencia(h, l, c, modo, 20)
            t_par = S.tendencia(h2, l2, c2, modo, 20)
            np.testing.assert_array_equal(t_full[:corte + 1], t_par)


def test_anti_look_ahead_trades_passados_nao_mudam_com_o_futuro_truncado():
    o, h, l, c = passeio(400, 7)
    at = ativo_diario(o, h, l, c)
    for corte in (150, 300):
        o2, h2, l2, c2 = (x[:corte] for x in (o, h, l, c))
        at2 = ativo_diario(o2, h2, l2, c2)
        for nome, mk in {"VB": lambda a: S.setup_vb(a.o, a.h, a.l, a.c, 0.5, 0.5),
                         "SMASH": lambda a: S.setup_smash(a.o, a.h, a.l, a.c, 2),
                         "OOPS": lambda a: S.setup_oops(a.o, a.h, a.l, a.c)}.items():
            for saida in ("BAILOUT", "TEMPO", "REVERSAO", "RR"):
                kw = dict(saida=saida, stop_modo="abs" if nome == "SMASH" else "frac")
                full = [t for t in M.gerar_trades(at, mk(at), cfg(**kw)) if t.dia_sai < corte - 1]
                part = [t for t in M.gerar_trades(at2, mk(at2), cfg(**kw))
                        if t.motivo != "FIM_DADOS" and t.dia_sai < corte - 1]
                assert full == part, (nome, saida, corte)


def test_anti_look_ahead_m1_trades_do_inicio_nao_dependem_do_fim():
    rng = np.random.default_rng(3)
    dias = []
    p = 100000.0
    for _ in range(40):
        barras = []
        for _ in range(30):
            o = p; c = o + rng.normal(0, 30); h = max(o, c) + abs(rng.normal(0, 15)); l = min(o, c) - abs(rng.normal(0, 15))
            barras.append((o, h, l, c)); p = c
        dias.append(barras)
    at = ativo_m1(dias)
    sin = S.setup_vb(at.o, at.h, at.l, at.c, 0.5, 0.5)
    full = M.gerar_trades(at, sin, cfg(saida="BAILOUT"))
    at2 = ativo_m1(dias[:25])
    part = M.gerar_trades(at2, S.setup_vb(at2.o, at2.h, at2.l, at2.c, 0.5, 0.5), cfg(saida="BAILOUT"))
    assert [t for t in full if t.dia_sai < 23] == [t for t in part if t.motivo != "FIM_DADOS" and t.dia_sai < 23]


def test_um_trade_por_vez_e_sem_sobreposicao():
    o, h, l, c = passeio(500, 11)
    at = ativo_diario(o, h, l, c)
    tr = M.gerar_trades(at, S.setup_vb(o, h, l, c, 0.3, 0.3), cfg(saida="BAILOUT"))
    assert len(tr) > 20
    for a, b in zip(tr, tr[1:]):
        assert b.dia_ent >= a.dia_sai and (b.dia_ent > a.dia_sai or a.motivo in
                                           ("BAILOUT", "STOP_GAP", "ABERTURA_SEGUINTE", "REVERSAO", "OSC"))
    assert all(t.dia_sai >= t.dia_ent for t in tr)


# ================================================================ (d) exportacao e dados (tmp_path)
def test_exporta_csv_de_trades_no_formato_do_ea(tmp_path):
    o = np.array([100, 102.0, 106]); h = np.array([110, 108.0, 106.2])
    l = np.array([100, 103.0, 105.9]); c = np.array([105, 106.0, 106])
    at = ativo_diario(o, h, l, c)
    tr = rodar(at, S.setup_vb(o, h, l, c, 0.5, 0.5))
    destino = tmp_path / "ref.csv"
    M.exporta_trades_csv(at, tr, destino, slip_ticks=0.0)
    linhas = destino.read_text(encoding="utf-8").strip().splitlines()
    assert linhas[0] == "data;lado;entrada;saida;motivo;pnl_pts"
    campos = linhas[1].split(";")
    assert campos[0] == "2024-01-03" and campos[1] == "C" and campos[4] == "fechamento"
    assert float(campos[5]) == pytest.approx(-1.0)


def test_janelas_is_oos_por_tempo_sem_sobreposicao():
    datas = np.datetime64("2010-01-04") + np.arange(6000)
    n = len(datas)
    o = np.linspace(10, 20, n)
    at = M.criar_ativo("X", "ACAO", datas, o, o + 1, o - 1, o)
    w = D.janelas(at)
    assert w["IS"][1] == w["OOS"][0] and datas[w["IS"][1] - 1] <= np.datetime64("2020-12-31") < datas[w["OOS"][0]]
