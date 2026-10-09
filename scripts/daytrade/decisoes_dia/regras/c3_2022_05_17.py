"""Ciclo 3 - dia 2022-05-17 (WIN M15, ROTACAO, ef 0,033). v1 -R$120; v2 = v3 = -R$193,00 (2 operacoes).

O DIA: gap de alta de +985 pts (0,36 ATRd) sobre o fecho de ontem (109.325 -> abre 110.310), maxima 110.790 as 09:30, queda lenta ate 109.225
(15:30), volta e fecha 109.990 (-320 da abertura). Amplitude 1.565 pts (0,57 ATRd).
A v3 fez 2 stops/saidas ruins: (1) COMPRA `Recuo a media 8 em tendencia de alta` as 11:00 (110.495, stop 109.905 = 590, alvo 111.342), stopada as 11:35
(a vela das 11:30 caiu a 109.690); (2) VENDA `F1 rompe minima da 1a hora` as 12:15 (109.635, stop 110.225, alvo 108.445), zerada no fim em 109.990
(-73). A venda (2) so existe porque o A2 (v2) soltou o veto de venda de rompimento (v1 = -120, v2/v3 = -193).

Regras puras (so passado do instante). Nada existente e editado. `python -m regras.c3_2022_05_17` imprime R$ isolada no dia e R$ do dia
com a proposta DENTRO do robo v3. Efeito nos 70 dias: `python -m regras.c3_grupo_2022_04_13 <ids>` / `avalia`.
"""
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ)); sys.path.insert(0, str(RAIZ / "ciclo3"))
from regras import c3_grupo_2022_04_13 as g
from regras import c3_2022_04_13 as ca
from regras import c1_2023_07_27 as c1a, c2_2025_04_07 as c25, r_2023_11_03 as r11, r_2025_06_04 as r25

DIA = "2022-05-17"
V_STOP_CURTO = "2023_08_21:vende_rompimento_stop_curto"


def gap_atrd(ctx): return ca.gap_atrd(ctx)


def _prim_hora_low(ctx):
    h = ctx.hoje; return float(h[h.index.hour < 10].low.min())


def _idade_rompimento_min1h(ctx):
    """Velas desde o 1o fechamento abaixo da minima da 1a hora (None se nao rompeu)."""
    h = ctx.hoje; lo = _prim_hora_low(ctx); dep = h[h.index.hour >= 10]
    idx = [i for i in range(len(dep)) if dep.close.iloc[i] < lo]
    return None if not idx else len(dep) - 1 - idx[0]


# ============================================================================= FAZER / ajustes
def f1_fade_gap_cedo_com_rejeicao(ctx):
    """FAZER (entrada cedo, CONTRA o gap): 09:45-10:15, gap >= 0,3 ATRd; a vela que fechou e contra o gap (baixa no gap de alta / alta no gap de
    baixa), o fecho ainda esta do lado do gap em relacao a abertura do dia e a >= 0,25 ATR15 da extrema da manha -> opera contra o gap.
    Stop alem da extrema da manha +10 (minimo 0,8 ATR15, teto 590), alvo 1,5R. Condicao: gap pequeno rejeitado nas primeiras velas.
    AJUSTADA AO DIA (a memoria do projeto ja tem 'fade do gap nao replica')."""
    h = ctx.hoje
    if not (9 * 60 + 45 <= g.hm(ctx) <= 10 * 60 + 15) or len(h) < 3: return None
    gp = gap_atrd(ctx); u = h.iloc[-1]; c = float(u.close); r_min = 0.8 * ctx.atr15
    if gp >= 0.3 and u.close < u.open and c >= float(h.open.iloc[0]) and float(h.high.max()) - c >= 0.25 * ctx.atr15:
        r = min(max(float(h.high.max()) + 10 - c, r_min), g.TETO); return dict(lado="venda", preco=c, stop=c + r, alvo=c - 1.5 * r, contratos=1)
    if gp <= -0.3 and u.close > u.open and c <= float(h.open.iloc[0]) and c - float(h.low.min()) >= 0.25 * ctx.atr15:
        r = min(max(c - float(h.low.min()) + 10, r_min), g.TETO); return dict(lado="compra", preco=c, stop=c - r, alvo=c + 1.5 * r, contratos=1)


def f2_fade_vwap_em_rotacao(ctx):
    """FAZER ja existente em c2_2025_04_07 (F3): fade do VWAP em rotacao (ef<=0,08, 12:00-16:00, alvo no VWAP). Natureza: reversao a valor."""
    return c25.f3_fade_vwap_em_rotacao(ctx)


def f3_fade_borda_rotacao(ctx):
    """FAZER novo do grupo: toque da borda da faixa do dia em rotacao com rejeicao, alvo 1R. Ver g.f_fade_borda_rotacao."""
    return g.f_fade_borda_rotacao(ctx)


def f4_venda_rompimento_alvo_0_5r(ctx):
    """AJUSTE de saida de `F1 rompe minima da 1a hora (venda)`: em rotacao (ef<0,10 no momento do sinal) alvo 0,5R em vez de 3 ATR15. No dia a
    venda das 12:15 teria sido paga a 0,5R (a minima seguinte foi 0,7R abaixo). Natureza: ajuste de saida / gestao adaptativa."""
    s = r25.f1_rompe_minima_1a_hora(ctx)
    if s and g.ef_hoje(ctx) < 0.10:
        s = dict(s); p = float(s["preco"]); s["alvo"] = p - 0.5 * abs(float(s["stop"]) - p)
    return s


# ============================================================================= NAO_FAZER (armadilhas; R$ < 0 isolada no dia)
def n1_comprar_recuo_em_rotacao_comprimida(ctx):
    """NAO FAZER: depois das 10:30, com ef do dia < 0,08 e faixa do dia < 0,35 ATRd, comprar o recuo a media 8 'em tendencia de alta'. Armadilha:
    a 'tendencia' e so o gap de abertura; a faixa de 3 horas e menor que 1/3 do ATR diario e o preco volta ao centro, entao o stop de 590 e varrido
    pelo ruido da proxima vela. Condicao: ef<0,08 + amplitude < 0,35 ATRd. (No dia: ef 0,064, amplitude 0,31.)"""
    if g._cond_cont_rot(ctx, None, None, 0.08, 0.35):
        return r11.f2_recuo_ema(ctx)


def n2_vender_terco_inferior_em_rotacao(ctx):
    """NAO FAZER: em rotacao (ef<0,10, apos 10:30), vender a vela de baixa no terco inferior da faixa do dia. Armadilha: a faixa devolve da borda.
    (A venda das 12:15 foi a 6% da faixa do dia, ef 0,144 > 0,10: este veto NAO a pegaria; so vale no dia 2022-04-13.)"""
    return ca.n1_vender_terco_inferior_em_rotacao(ctx)


def n3_vender_rompimento_velho_sem_volume(ctx):
    """NAO FAZER: vender o fechamento abaixo da minima da 1a hora quando o rompimento ja tem >= 2 velas (o 1o fechamento abaixo da faixa foi as
    11:30; o sinal das 12:15 e o 3o) e a vela do sinal tem volume < media do dia. Armadilha: o rompimento e velho e sem volume; a
    continuacao ja foi paga e o que sobra e o retorno ao meio. Condicao: idade >= 2 velas + volume da vela < media do dia, apos 11:30."""
    h = ctx.hoje
    if g.hm(ctx) < 11 * 60 + 30 or len(h) < 6: return None
    i = _idade_rompimento_min1h(ctx)
    if i is not None and i >= 2 and h.vol.iloc[-1] < h.vol.mean():
        r = min(1.5 * ctx.atr15, g.TETO); return g.ordem(ctx, "venda", r, 3.0 * ctx.atr15)


def n_a2_condicional(ctx):
    """A2 CONDICIONAL (pedido do ciclo 3; substitui o veto `vende_rompimento_stop_curto` da v3). A2 solta o veto da v1 em TODA venda abaixo
    da minima da 1a hora exceto o rompimento raso. Aqui: o veto ORIGINAL da v1 volta quando o estado observavel e de rotacao sem forca:
    ef do dia ate agora < 0,15 E volume da vela < media do dia E apos 11:30. Fora disso vale o A2 (libera). Usa so estado do instante."""
    s = c1a.a2_veto_rompimento_raso(ctx)
    if s: return s
    h = ctx.hoje
    if len(h) < 5 or g.hm(ctx) < 11 * 60 + 30: return None
    c = float(h.close.iloc[-1])
    if c < _prim_hora_low(ctx) and g.ef_hoje(ctx) < 0.15 and h.vol.iloc[-1] < h.vol.mean():
        return dict(lado="venda", stop=c + 120, alvo=c - 240, contratos=1)


def n4_vender_rompimento_em_rotacao_pos_amplitude(ctx):
    """NAO FAZER: vender rompimento da 1a hora quando o dia ja devolveu >= 1 ATR15 da perna (ef<0,15) E a faixa total < 0,5 ATRd. Armadilha: faixa
    estreita, a 'perna' e ruido. (No dia: amplitude 0,45 ATRd as 12:15.)"""
    h = ctx.hoje
    if g.hm(ctx) >= 11 * 60 + 30 and g.ef_hoje(ctx) < 0.15 and g.amp_atrd(ctx) < 0.5 and h.close.iloc[-1] < _prim_hora_low(ctx):
        r = min(1.5 * ctx.atr15, g.TETO); return g.ordem(ctx, "venda", r, 3.0 * ctx.atr15)


FAZER = [("F1 fade do gap cedo com rejeicao", f1_fade_gap_cedo_com_rejeicao, None),
         ("F2 fade do VWAP em rotacao", f2_fade_vwap_em_rotacao, None),
         ("F3 fade de borda da faixa em rotacao (nao dispara no dia: R$ 0)", f3_fade_borda_rotacao, None),
         ("F4 venda de rompimento da 1a hora, alvo 0,5R em rotacao (R$ < 0: nao serve)", f4_venda_rompimento_alvo_0_5r, None)]
# N2 (vender terco inferior) rende +75 isolada neste dia: NAO e armadilha aqui (so no 2022-04-13); fica fora da lista deste dia.
NAO_FAZER = [("N1 comprar recuo em rotacao comprimida", n1_comprar_recuo_em_rotacao_comprimida, None),
             ("N3 vender rompimento velho sem volume", n3_vender_rompimento_velho_sem_volume, None),
             ("N4 vender rompimento em faixa estreita", n4_vender_rompimento_em_rotacao_pos_amplitude, None)]


# ============================================================================= como cada proposta entra no v3 (Cfg)
def ap_a2_condicional(cfg):
    assert any(n == V_STOP_CURTO for n, _, _ in cfg.nf)
    cfg.nf = [(n, n_a2_condicional, gg) if n == V_STOP_CURTO else (n, r, gg) for n, r, gg in cfg.nf]


def _cancela_rompimento_velho(ctx, s, n):
    if s["lado"] != "venda" or g.hm(ctx) < 11 * 60 + 30 or len(ctx.hoje) < 6: return False
    i = _idade_rompimento_min1h(ctx)
    return i is not None and i >= 2 and ctx.hoje.vol.iloc[-1] < ctx.hoje.vol.mean()


def _cancela_venda_faixa_estreita(ctx, s, n):
    return (s["lado"] == "venda" and g.hm(ctx) >= 11 * 60 + 30 and g.ef_hoje(ctx) < 0.15 and g.amp_atrd(ctx) < 0.5
            and float(ctx.hoje.close.iloc[-1]) < _prim_hora_low(ctx))


CAND = {
    "b_F1_gap_cedo": g.ap_fz("c3b:F1 fade gap cedo", f1_fade_gap_cedo_com_rejeicao),
    "b_N3_romp_velho_sem_vol": g.ap_post(g.post_cancela(_cancela_rompimento_velho)),
    "b_N4_venda_faixa_estreita": g.ap_post(g.post_cancela(_cancela_venda_faixa_estreita)),
    "b_A2_condicional": ap_a2_condicional,
}
# F2 = a_F3_vwap_rotacao (c3_2022_04_13), F3 = G5_fade_borda_rot, F4 = G1c_alvo_0.5R_rot,
# N1 = G4v_cont_ef0.08_amp0.35, N2 = G3n_venda_ef0.1_f0.3
PROPOSTAS = {"F1": "b_F1_gap_cedo", "F2": "a_F3_vwap_rotacao", "F3": "G5_fade_borda_rot", "F4": "G1c_alvo_0.5R_rot",
             "N1": "G4v_cont_ef0.08_amp0.35", "N2": "G3n_venda_ef0.1_f0.3", "N3": "b_N3_romp_velho_sem_vol",
             "N4": "b_N4_venda_faixa_estreita", "A2c": "b_A2_condicional", "trava 0,5R rot": "G2b_trava_0.5R_rot"}


def dia_com(ids):
    import cfg3
    extra = dict(ca.CAND); extra.update(CAND)
    tr, _ = cfg3.roda(DIA, g.cfg_de(ids, extra))
    ok = [x for x in tr if x.t_ent is not None]
    return round(sum(x.brl for x in ok), 2), [(x.fonte[:30], x.lado, str(x.t_ent.time()), str(x.t_sai.time()), x.motivo, round(x.brl, 1)) for x in ok]


if __name__ == "__main__":
    import base
    for grupo, lista in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, _ in lista:
            res = base.resumo(base.simula_dia(DIA, r, None, max_ops=3))
            print(f"{grupo:9s} {nome:58s} isolada R$ {res['brl']:8.2f} ops {res['ops']}", flush=True)
    print("v3 puro:", dia_com(()))
    for k, i in PROPOSTAS.items():
        print(f"dentro do v3 + {k:16s} ({i}):", dia_com((i,)), flush=True)
