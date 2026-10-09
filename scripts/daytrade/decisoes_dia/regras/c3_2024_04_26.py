"""Ciclo 3 - 2024-04-26 (ruim, ef 0,137; v3 -R$52: gap_fade venda 09:45 stopada -R$82 + rompimento 1a hora compra +R$30).

Dia: gap de alta de +855 pts (3,6 ATR15, 0,44 ATRd) sobre 125.895. A barra de abertura (09:00) cai de 126.750 a 126.360 e fecha 126.370;
a 09:15 faz minima 126.250; a 09:30 (vol 1,04M, 2x a media) sobe 490 pts e fecha 126.830 (acima da abertura, 88% do range). A partir dai
so sobe: 128.250 as 15:45. Maior movimento: compra apos o fechamento da barra de abertura (t 09:15, 126.370) ate 128.250 = +1.870 pts.

Cada F* abaixo e um jeito de pegar a perna (todas a favor do gap, sem saber de antemao que o dia e direcional); cada N* e uma armadilha.
`python -m regras.c3_2024_04_26` imprime o resultado isolado de cada regra no dia (base.simula_dia, max 3 ops).
"""
import pandas as pd

MAXR = 590.0
GAPFADE = "2024_06_18:gap_fade_fechamento"


def _hm(ctx): return ctx.t.hour * 60 + ctx.t.minute


def _gap(ctx): return float(ctx.hoje.open.iloc[0] - ctx.diario.close.iloc[-1])


def _vwap(ctx):
    h = ctx.hoje
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).sum() / h.vol.sum())


def _ord(ctx, lado, stop_atr=1.5, alvo_atr=3.0):
    p = float(ctx.hoje.close.iloc[-1]); a = ctx.atr15
    s = min(stop_atr * a, MAXR)
    if lado == "venda":
        return dict(lado="venda", preco=p, stop=p + s, alvo=p - alvo_atr * a, contratos=1)
    return dict(lado="compra", preco=p, stop=p - s, alvo=p + alvo_atr * a, contratos=1)


def _pos(u):
    r = float(u.high - u.low)
    return (float(u.close) - float(u.low)) / r if r > 0 else 0.5


def _entrada(lado, p, st, k):
    st = max(st, p - MAXR) if lado == "compra" else min(st, p + MAXR)
    r = abs(p - st)
    return dict(lado=lado, preco=p, stop=st, alvo=(p + k * r if lado == "compra" else p - k * r), contratos=1)


# =====================================================================================================
# 5 maneiras de deixar o dia positivo (FAZER)
# =====================================================================================================
def f1_retoma_a_abertura_a_favor_do_gap(ctx):
    """FAZER (continuacao, entrada cedo): gap >= 0,15 ATRd; a(s) vela(s) anterior(es) fecharam do lado de ca da abertura do dia (o gap
    'devolveu'); a vela atual FECHA de volta alem da abertura no sentido do gap, com fechamento nos 30% extremos do range e volume >= 1,3x
    a media das velas anteriores do dia. Entre 09:30 e 10:30. Entra a favor do gap no fechamento; stop na extremidade da devolucao
    (-20 pts, max 590); alvo 2R. Dia: 09:30 fecha 126.830 (> abertura 126.750, 88% do range, volume 2x). Natureza: armadilha de
    devolucao do gap desfeita (o fade falhou). Provavelmente geral na forma; limiares 1,3x e 30% vistos no dia."""
    h = ctx.hoje
    if len(h) < 2 or not (9 * 60 + 30 <= _hm(ctx) <= 10 * 60 + 30): return None
    g = _gap(ctx)
    if abs(g) < 0.15 * ctx.atrd: return None
    o = float(h.open.iloc[0]); u = h.iloc[-1]; ant = h.iloc[:-1]
    if u.vol < 1.3 * ant.vol.mean(): return None
    c = float(u.close)
    if g > 0 and ant.close.iloc[-1] <= o < c and _pos(u) >= 0.7:
        return _entrada("compra", c, float(ant.low.min()) - 20, 2.0)
    if g < 0 and ant.close.iloc[-1] >= o > c and _pos(u) <= 0.3:
        return _entrada("venda", c, float(ant.high.max()) + 20, 2.0)


def f2_barra_de_expansao_cedo_a_favor_do_gap(ctx):
    """FAZER (momentum, entrada cedo): a barra A4 (faixa >= 1,6 ATR15, volume >= 1,5x a media do dia, fecha nos 25% extremos) mas a
    partir de 09:30 (a A4 do robo so vale a partir das 10:00, pelo `_hm >= 600` sobre o FIM da vela) e SO a favor do gap. Stop na outra
    ponta da barra (max 590), alvo 1,5R. Dia: 09:30 range 560 (2,2 ATR15), vol 2x, fecha a 88% -> compra 126.830. Geral na forma (a
    A4 original e geral); o recorte 'a favor do gap' foi escolhido vendo o dia."""
    h = ctx.hoje
    if len(h) < 2 or not (9 * 60 + 30 <= _hm(ctx) <= 10 * 60): return None
    g = _gap(ctx)
    if abs(g) < 0.15 * ctx.atrd: return None
    u = h.iloc[-1]; rng = float(u.high - u.low)
    if rng < 1.6 * ctx.atr15 or u.vol < 1.5 * h.vol.iloc[:-1].mean(): return None
    c = float(u.close)
    if g > 0 and c >= u.high - 0.25 * rng: return _entrada("compra", c, float(u.low), 1.5)
    if g < 0 and c <= u.low + 0.25 * rng: return _entrada("venda", c, float(u.high), 1.5)


def f3_minimas_ascendentes_a_favor_do_gap(ctx):
    """FAZER (continuacao por estrutura): gap >= 0,15 ATRd; as minimas das 3 ultimas velas sao crescentes (gap de alta; no gap de baixa,
    maximas decrescentes), o fechamento esta alem da abertura do dia e do lado certo da VWAP. Entre 09:45 e 11:00. Entra a favor no
    fechamento; stop abaixo da menor minima das 3 velas (-20, max 590); alvo 2R. Dia: t 10:00, minimas 126.250 < 126.335 < 126.600,
    fecha 126.990 (> abertura 126.750). Natureza: higher lows a favor do gap. Provavelmente geral."""
    h = ctx.hoje
    if len(h) < 4 or not (9 * 60 + 45 <= _hm(ctx) <= 11 * 60): return None
    g = _gap(ctx)
    if abs(g) < 0.15 * ctx.atrd: return None
    u3 = h.iloc[-3:]; c = float(h.close.iloc[-1]); o = float(h.open.iloc[0]); v = _vwap(ctx)
    if g > 0 and u3.low.is_monotonic_increasing and u3.low.nunique() == 3 and c > o and c > v:
        return _entrada("compra", c, float(u3.low.min()) - 20, 2.0)
    if g < 0 and u3.high.is_monotonic_decreasing and u3.high.nunique() == 3 and c < o and c < v:
        return _entrada("venda", c, float(u3.high.max()) + 20, 2.0)


def f4_retomada_apos_recuo_raso_da_perna(ctx):
    """FAZER (recuo a favor, cedo): a perna do dia (minima do dia ate a maxima das velas anteriores a atual, maxima DEPOIS da minima) tem
    >= 2 ATR15; o recuo a partir dessa maxima foi de 15% a 40% da perna; a vela atual FECHA acima dessa maxima e acima da abertura do
    dia. Entre 09:45 e 11:30. Stop abaixo da minima do recuo (-20, max 590), alvo 2R (espelho para venda). Dia: perna 126.250-127.025
    (3,3 ATR15), recuo ate 126.730 (38%), t 10:30 a vela das 10:15 fecha 127.160 > 127.025 -> compra 127.160. Parecida com o
    `recuo_tendencia` do robo, mas sem exigir deslocamento de 0,6 ATRd (so ocorre depois das 10:30). Provavelmente geral; os limiares 2
    ATR15 e 40% foram vistos no dia."""
    h = ctx.hoje
    if len(h) < 5 or not (9 * 60 + 45 <= _hm(ctx) <= 11 * 60 + 30): return None
    o = float(h.open.iloc[0]); c = float(h.close.iloc[-1]); p = h.iloc[:-1]
    il = int(p.low.values.argmin()); ih = il + int(p.high.values[il:].argmax())
    lo = float(p.low.iloc[il]); hi = float(p.high.iloc[ih])
    if ih > il and hi - lo >= 2 * ctx.atr15:
        rec_lo = float(p.low.iloc[ih:].min())
        if 0.15 <= (hi - rec_lo) / (hi - lo) <= 0.40 and c > hi and c > o:
            return _entrada("compra", c, rec_lo - 20, 2.0)
    ih = int(p.high.values.argmax()); il = ih + int(p.low.values[ih:].argmin())
    hi = float(p.high.iloc[ih]); lo = float(p.low.iloc[il])
    if il > ih and hi - lo >= 2 * ctx.atr15:
        rec_hi = float(p.high.iloc[il:].max())
        if 0.15 <= (rec_hi - lo) / (hi - lo) <= 0.40 and c < lo and c < o:
            return _entrada("venda", c, rec_hi + 20, 2.0)


def f5_gap_nao_preenchido_em_1h_rompe_maxima(ctx):
    """FAZER (rompimento a favor do gap): em 1h (4 velas) o preco NAO voltou ao fechamento de ontem (gap de alta: minima do dia
    >= fechamento de ontem + 0,25 gap), e a vela fecha acima da maxima das 3 anteriores. Entre 10:00 e 11:30. Stop na minima das 3
    anteriores (-20, max 590), alvo 1,5R. Dia: 10:30 fecha 127.765 > 127.235 (ja com 1.020 pts de gap preservado). Natureza: gap que
    segura = demanda. Provavelmente geral; mas dispara tarde (10:30 -> so +30 pts de ganho no robo atual via C4)."""
    h = ctx.hoje
    if len(h) < 5 or not (10 * 60 <= _hm(ctx) <= 11 * 60 + 30): return None
    g = _gap(ctx)
    if abs(g) < 0.15 * ctx.atrd: return None
    pc = float(ctx.diario.close.iloc[-1]); c = float(h.close.iloc[-1]); ant = h.iloc[-4:-1]
    if g > 0 and float(h.low.min()) >= pc + 0.25 * g and c > float(ant.high.max()):
        return _entrada("compra", c, float(ant.low.min()) - 20, 1.5)
    if g < 0 and float(h.high.max()) <= pc + 0.25 * g and c < float(ant.low.min()):
        return _entrada("venda", c, float(ant.high.max()) + 20, 1.5)


FAZER = [
    ("F1 retoma a abertura a favor do gap", f1_retoma_a_abertura_a_favor_do_gap, None),
    ("F2 barra de expansao cedo a favor do gap", f2_barra_de_expansao_cedo_a_favor_do_gap, None),
    ("F3 minimas ascendentes a favor do gap", f3_minimas_ascendentes_a_favor_do_gap, None),
    ("F4 retomada apos recuo raso da perna", f4_retomada_apos_recuo_raso_da_perna, None),
    ("F5 gap nao preenchido em 1h rompe maxima", f5_gap_nao_preenchido_em_1h_rompe_maxima, None),
]


# =====================================================================================================
# 5 coisas a NAO fazer (cada uma = condicao de mercado que vira veto; sinaliza o lado a vetar)
# =====================================================================================================
def n1_vender_gap_de_alta_alem_da_abertura(ctx):
    """NAO FAZER vender entre 09:15 e 10:00 com gap de alta >= 0,15 ATRd e fechamento ACIMA da abertura do dia (o gap esta alargando).
    (G1 do grupo, aqui so o lado de venda.) Dia: 09:30 fecha 126.830 > 126.750: a venda perdeu -R$82. Geral."""
    if not (9 * 60 + 15 <= _hm(ctx) <= 10 * 60): return None
    if _gap(ctx) >= 0.15 * ctx.atrd and float(ctx.hoje.close.iloc[-1]) > float(ctx.hoje.open.iloc[0]):
        return _ord(ctx, "venda")


def n2_vender_apos_barra_de_volume_a_favor_do_gap(ctx):
    """NAO FAZER vender logo apos uma vela de ALTA com volume >= 1,5x a media do dia e fechamento nos 25% superiores, nas 2 primeiras
    horas, em gap de alta. Condicao: o volume pesado esta do lado comprador; vender o fechamento paga o pior preco. Dia: 09:30 vol 2x,
    fecha a 88%. Geral na forma; 1,5x visto nos dados."""
    h = ctx.hoje
    if len(h) < 2 or not (9 * 60 + 15 <= _hm(ctx) <= 11 * 60): return None
    u = h.iloc[-1]
    if _gap(ctx) > 0 and u.vol >= 1.5 * h.vol.iloc[:-1].mean() and _pos(u) >= 0.75 and u.close > u.open:
        return _ord(ctx, "venda")


def n3_vender_acima_da_vwap_com_minimas_ascendentes(ctx):
    """NAO FAZER vender com fechamento acima da VWAP do dia e as minimas das 3 ultimas velas crescentes, antes das 15:00. Condicao:
    estrutura de alta (higher lows) e preco acima do valor medio; vender e apostar contra os dois. Dia: t 10:00-11:00. Geral."""
    h = ctx.hoje
    if len(h) < 4 or not (9 * 60 + 45 <= _hm(ctx) <= 15 * 60): return None
    u3 = h.iloc[-3:]
    if u3.low.is_monotonic_increasing and float(h.close.iloc[-1]) > _vwap(ctx):
        return _ord(ctx, "venda")


def n4_fade_de_gap_grande(ctx):
    """NAO FAZER fade de gap >= 0,4 ATRd (gap grande para o ativo): o fechamento de ontem esta longe demais para ser alvo de 1 trade e
    gap grande costuma ser informacao nova (continua). Veta o lado do fade entre 09:15 e 10:00. Dia: 855 pts = 0,44 ATRd. Geral na
    forma; 0,4 ATRd visto no dia."""
    if not (9 * 60 + 15 <= _hm(ctx) <= 10 * 60): return None
    g = _gap(ctx)
    if abs(g) >= 0.4 * ctx.atrd: return _ord(ctx, "venda" if g > 0 else "compra")


def n5_vender_com_vwap_subindo_acima_da_abertura(ctx):
    """NAO FAZER vender antes das 11:30 quando o fechamento esta acima da abertura do dia E a VWAP sobe nas ultimas 3 velas
    (VWAP de agora > VWAP de 3 velas atras). Condicao: o dia ja compra a favor do tempo; vender e fade de tendencia nascente. Geral."""
    h = ctx.hoje
    if len(h) < 5 or not (9 * 60 + 30 <= _hm(ctx) <= 11 * 60 + 30): return None
    tp = (h.high + h.low + h.close) / 3
    vw = (tp * h.vol).cumsum() / h.vol.cumsum()
    if float(h.close.iloc[-1]) > float(h.open.iloc[0]) and vw.iloc[-1] > vw.iloc[-4]:
        return _ord(ctx, "venda")


NAO_FAZER = [
    ("N1 vender gap de alta alem da abertura", n1_vender_gap_de_alta_alem_da_abertura, None),
    ("N2 vender apos barra de volume a favor do gap", n2_vender_apos_barra_de_volume_a_favor_do_gap, None),
    ("N3 vender acima da VWAP com minimas ascendentes", n3_vender_acima_da_vwap_com_minimas_ascendentes, None),
    ("N4 fade de gap grande", n4_fade_de_gap_grande, None),
    ("N5 vender com VWAP subindo acima da abertura", n5_vender_com_vwap_subindo_acima_da_abertura, None),
]

AJUSTES = {}
for _i, (_n, _r, _g) in enumerate(FAZER):
    AJUSTES[f"A_F{_i+1}"] = dict(add_prio=[(f"c3a:{_n}", _r, _g)])       # prioritaria: ignora vetos e o conflito de 2 lados
    AJUSTES[f"A_F{_i+1}n"] = dict(add_fazer=[(f"c3a:{_n}", _r, _g)])     # normal: no fim da lista, sujeita a vetos e a 2 lados
for _i, (_n, _r, _g) in enumerate(NAO_FAZER):
    AJUSTES[f"A_N{_i+1}"] = dict(add_veto=[(f"c3a:{_n}", _r, _g)])

DIA = "2024-04-26"

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import base
    for grupo, lista in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, g in lista:
            res = base.resumo(base.simula_dia(DIA, r, g, max_ops=3))
            print(f"{grupo:9s} {nome:52s} isolada R$ {res['brl']:8.2f} ops {res['ops']}", flush=True)
