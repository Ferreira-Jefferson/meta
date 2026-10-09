"""Ciclo 3 - dia 2022-08-18 (WIN M15, tipo ruim, ef 0,032). v1, v2 e v3 fecharam -R$142,57 (2 operacoes).

O DIA: abertura 115.785, alta de 660 pts em 3 velas (maxima 116.445 as 09:30), devolve tudo ate 115.560 (11:00), rotaciona
115.6-116.1k ate as 12:30 e cai a 115.295 (13:45, a minima), volta a 116.140 as 16:30. Amplitude 1.150 pts = 0,57 ATRd. Eficiencia 0,032.
O robo comprou o 'suporte' as 10:15 (116.075, stop 115.657, -R$85,57) e vendeu o pullback EMA20 as 11:30 (115.790, alvo 2,5R = 1.033 pts),
que ficou aberto ate o fim e fechou no 116.065 (-R$57,00): o dia so andou 495 pts a favor (minima 115.295) e devolveu.
Maior movimento: venda das 09:45 (fecho 116.075 -> minima 115.295 as 13:45).

`python -m regras.c3_2022_08_18` imprime o resultado isolado de cada regra no dia.
Regras puras: so usam o passado do instante da decisao.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

TETO = 590.0


def _hm(ctx): return ctx.t.hour * 60 + ctx.t.minute
def _ema(s, n): return s.ewm(span=n, adjust=False).mean()


def _vwap(h):
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).sum() / h.vol.sum())


def _efic(ctx):
    h = ctx.hoje
    s = float((h.high - h.low).sum())
    return abs(float(h.close.iloc[-1] - h.open.iloc[0])) / s if s > 0 else 0.0


def _ord(ctx, lado, stop_px, alvo_r):
    """limitada no fecho; risco limitado ao TETO; alvo = alvo_r x risco (None = sem alvo)."""
    p = float(ctx.hoje.close.iloc[-1]); sg = 1 if lado == "compra" else -1
    r = min(abs(p - stop_px), TETO)
    if r < 1: return None
    return dict(lado=lado, preco=p, stop=p - sg * r, alvo=(None if alvo_r is None else p + sg * alvo_r * r), contratos=1)


# ============================================================================= FAZER (5)
def f1_venda_falha_da_maxima_cedo(ctx):
    """REVERSAO em falha (geral). Entre 09:45 e 11:00: a maxima do dia foi feita ha >= 1 vela (nao e a vela atual), subiu >= 2 ATR15
    desde a abertura (esticada), a vela atual e de baixa e fecha abaixo da ABERTURA da vela anterior (devolveu o impulso). Venda, stop na
    maxima do dia + 0,2 ATR15 (teto 590), alvo 1,5R. Condicao: alta de abertura sem continuidade, dia de rotacao. 09:45 de 18/08:
    fecho 116.075 < abertura anterior 116.135, maxima 116.445 (+660 = 2,3 ATR15)."""
    h = ctx.hoje
    if not (9 * 60 + 45 <= _hm(ctx) <= 11 * 60) or len(h) < 3: return None
    hi = float(h.high.max())
    if float(h.high.iloc[-1]) >= hi: return None
    if hi - float(h.open.iloc[0]) < 2 * ctx.atr15: return None
    u, a = h.iloc[-1], h.iloc[-2]
    if u.close < u.open and u.close < a.open:
        return _ord(ctx, "venda", hi + 0.2 * ctx.atr15, 1.5)


def f2_venda_perde_abertura_sob_vwap(ctx):
    """CONTINUACAO cedo (geral). Entre 10:30 e 12:00: o fecho cai abaixo da ABERTURA do dia e abaixo da VWAP, a VWAP do dia nao esta
    subindo (VWAP atual <= VWAP de 4 velas atras) e a vela anterior ainda fechava acima da abertura (e a primeira perda). Venda, stop 1,3 ATR15
    (teto 590), alvo 1R. Condicao: perda da abertura apos tentativa de alta falhada = o lado vendedor assume. AJUSTADA AO DIA: com stop de
    1,0 ATR15 o mesmo sinal da -R$63 (frágil ao parametro). 11:00 de 18/08: fecho 115.765 < abertura 115.785, antes 116.035 acima."""
    h = ctx.hoje
    if not (10 * 60 + 30 <= _hm(ctx) <= 12 * 60) or len(h) < 6: return None
    o = float(h.open.iloc[0]); c = float(h.close.iloc[-1])
    if not (c < o and float(h.close.iloc[-2]) >= o): return None
    v, v4 = _vwap(h), _vwap(h.iloc[:-4])
    if c < v and v <= v4:
        return _ord(ctx, "venda", c + 1.3 * ctx.atr15, 1.0)


def f3_fade_extremo_da_faixa_em_rotacao(ctx):
    """REVERSAO a media em rotacao (geral). Entre 10:30 e 15:00, com a faixa do dia (max-min) <= 0,7 ATRd e eficiencia do dia ate agora < 0,15:
    fecho no 15% superior da faixa -> venda; no 15% inferior -> compra. Stop 0,5 ATR15 alem do extremo do dia (teto 590), alvo no meio da
    faixa. Condicao: dia de rotacao, sem energia diaria. 13:45 de 18/08: fecho 115.325 no fundo da faixa, volta a 115.7-116.1k."""
    h = ctx.hoje
    if not (10 * 60 + 30 <= _hm(ctx) <= 15 * 60) or len(h) < 6: return None
    hi, lo = float(h.high.max()), float(h.low.min()); rg = hi - lo
    if rg <= 0 or rg > 0.7 * ctx.atrd or _efic(ctx) >= 0.15: return None
    c = float(h.close.iloc[-1]); p = (c - lo) / rg
    lado = "venda" if p >= 0.85 else ("compra" if p <= 0.15 else None)
    if lado is None: return None
    s = _ord(ctx, lado, (hi + 0.5 * ctx.atr15) if lado == "venda" else (lo - 0.5 * ctx.atr15), None)
    if s: s["alvo"] = (hi + lo) / 2
    return s


def f4_compra_virada_da_tarde(ctx):
    """REVERSAO de fim de queda (geral). Entre 14:30 e 15:30: o dia fez a minima nas ultimas 8 velas e NAO a renovou nas ultimas 3, o fecho
    rompe a maxima das 3 velas anteriores e fica acima da EMA9 M15; a queda desde a abertura foi pequena (<= 1 ATRd). Compra, stop na
    minima das ultimas 4 velas (teto 590), alvo 1R. Condicao: esgotamento da perna vendedora em dia de rotacao. 15:00 de 18/08:
    fecho 115.710 > maxima 115.625 das 3 anteriores; minima do dia 115.295 (13:45)."""
    h = ctx.hoje
    if not (14 * 60 + 30 <= _hm(ctx) <= 15 * 60 + 30) or len(h) < 10: return None
    mn = float(h.low.min())
    if float(h.low.iloc[-3:].min()) <= mn: return None
    if float(h.low.iloc[-8:].min()) > mn: return None
    if float(h.open.iloc[0]) - mn > ctx.atrd: return None
    c = float(h.close.iloc[-1])
    if c > float(h.high.iloc[-4:-1].max()) and c > float(_ema(ctx.m15.close, 9).iloc[-1]):
        return _ord(ctx, "compra", float(h.low.iloc[-4:].min()), 1.0)


def f5_pullback_alvo_1r_em_rotacao(ctx):
    """AJUSTE de `2022_11_16:venda pullback EMA20 em baixa` (alvo; geral). Mesmo gatilho e stop (1,3 ATR15, teto 580), mas o alvo cai de 2,5R
    para 1R quando a faixa do dia ate agora <= 0,6 ATRd (o dia nao tem 1.000 pts para dar). Espelho do N3. 11:30 de 18/08: alvo 1R =
    115.377, tocado as 13:30 (+R$80,64) em vez de fechar no 116.065 (-R$57)."""
    h = ctx.hoje
    if not (10 * 60 + 30 <= _hm(ctx) <= 15 * 60) or len(h) < 6: return None
    e = _ema(ctx.m15.close, 20); u = h.iloc[-1]
    if u.close < e.iloc[-1] and u.high >= e.iloc[-1] - 0.3 * ctx.atr15 and e.iloc[-1] < e.iloc[-4] and float(h.high.max() - h.low.min()) / ctx.atrd <= 0.6:
        c = float(u.close); r = min(1.3 * ctx.atr15, 580.0)
        return dict(lado="venda", preco=c, stop=c + r, alvo=c - 1.0 * r, contratos=1)


# ============================================================================= NAO_FAZER (5)
def n1_comprar_continuacao_da_abertura(ctx):
    """ARMADILHA (geral). Ate 10:00, comprar quando o fecho esta 1,5 ATR15 acima da abertura, vela de alta, e a amplitude do dia ainda
    e <= 0,5 ATRd: perseguir a esticada da abertura sem energia diaria. Stop 1,2 ATR15, alvo 1,5R. Nao fazer: comprar a esticada da
    abertura quando o ATR diario nao foi consumido. 09:30 de 18/08: fecho 116.335 (+550 = 3,3 ATR15), as 09:45 o preco devolve."""
    h = ctx.hoje
    if _hm(ctx) > 10 * 60 or len(h) < 2: return None
    c = float(h.close.iloc[-1])
    if c - float(h.open.iloc[0]) >= 1.5 * ctx.atr15 and h.close.iloc[-1] > h.open.iloc[-1] and (float(h.high.max() - h.low.min()) / ctx.atrd) <= 0.5:
        return _ord(ctx, "compra", c - 1.2 * ctx.atr15, 1.5)


def n2_comprar_suporte_no_meio_da_faixa(ctx):
    """ARMADILHA (geral). Entre 10:00 e 11:00, comprar 'suporte' quando o fecho esta no meio da faixa do dia (30% a 70% de max-min) e a
    eficiencia do dia ate agora < 0,1: nao ha suporte no meio de uma rotacao. Stop 1,5 ATR15, alvo 1R. 10:15 de 18/08: compra do F5
    a 116.075 (51% da faixa), stopada -R$85,57."""
    h = ctx.hoje
    if not (10 * 60 <= _hm(ctx) <= 11 * 60) or len(h) < 4: return None
    hi, lo = float(h.high.max()), float(h.low.min())
    if hi - lo <= 0: return None
    pos = (float(h.close.iloc[-1]) - lo) / (hi - lo)
    if 0.3 <= pos <= 0.7 and _efic(ctx) < 0.1:
        c = float(h.close.iloc[-1]); return _ord(ctx, "compra", c - 1.5 * ctx.atr15, 1.0)


def n3_vender_pullback_com_alvo_distante(ctx):
    """ARMADILHA (geral, o alvo e o problema). Venda no recuo a EMA20 com alvo de 2,5R (~1.000 pts) quando a amplitude do dia ate agora
    e <= 0,5 ATRd: o dia nao tem 1.000 pts para dar. 11:30 de 18/08: alvo 114.757, minima do dia 115.295."""
    h = ctx.hoje
    if not (10 * 60 + 30 <= _hm(ctx) <= 15 * 60) or len(h) < 6: return None
    e = _ema(ctx.m15.close, 20); u = h.iloc[-1]
    if u.close < e.iloc[-1] and u.high >= e.iloc[-1] - 0.3 * ctx.atr15 and e.iloc[-1] < e.iloc[-4]:
        if float(h.high.max() - h.low.min()) / ctx.atrd <= 0.6:
            c = float(u.close); r = min(1.3 * ctx.atr15, 580.0)
            return dict(lado="venda", preco=c, stop=c + r, alvo=c - 2.5 * r, contratos=1)


def n4_vender_fundo_do_dia_tarde(ctx):
    """ARMADILHA (geral). A partir de 13:45, vender quando a vela renova a minima do dia e a amplitude do dia <= 0,6 ATRd (dia sem energia,
    fundo da rotacao). Stop 1 ATR15, alvo 1,5R. 13:45 de 18/08 e o fundo do dia (115.295); dai o preco sobe 845 pts."""
    h = ctx.hoje
    if _hm(ctx) < 13 * 60 + 45 or len(h) < 10: return None
    c = float(h.close.iloc[-1])
    if float(h.low.iloc[-1]) <= float(h.low.min()) and float(h.high.max() - h.low.min()) / ctx.atrd <= 0.6:
        return _ord(ctx, "venda", c + ctx.atr15, 1.5)


def n5_comprar_fundo_de_faixa_antes_das_13h(ctx):
    """ARMADILHA (geral). Antes das 13:00, comprar o 'fundo da faixa' (fecho no 15% inferior de max-min do dia, faixa <= 0,7 ATRd, eficiencia < 0,15)
    quando a faixa ainda esta se formando: o fundo de manha costuma ser rompido. Stop 0,5 ATR15 abaixo da minima, alvo no meio da faixa.
    12:15 de 18/08: compra a 115.690, stopada (-R$62). (Versao horaria do F3: so vale depois das 13:00)."""
    h = ctx.hoje
    if not (10 * 60 + 30 <= _hm(ctx) < 13 * 60) or len(h) < 6: return None
    hi, lo = float(h.high.max()), float(h.low.min()); rg = hi - lo
    if rg <= 0 or rg > 0.7 * ctx.atrd or _efic(ctx) >= 0.15: return None
    c = float(h.close.iloc[-1])
    if (c - lo) / rg <= 0.15:
        s = _ord(ctx, "compra", lo - 0.5 * ctx.atr15, None)
        if s: s["alvo"] = (hi + lo) / 2
        return s


FAZER = [("F1 venda falha da maxima cedo", f1_venda_falha_da_maxima_cedo, None),
         ("F2 venda perde abertura sob VWAP", f2_venda_perde_abertura_sob_vwap, None),
         ("F3 fade do extremo da faixa em rotacao", f3_fade_extremo_da_faixa_em_rotacao, None),
         ("F4 compra virada da tarde", f4_compra_virada_da_tarde, None),
         ("F5 pullback com alvo 1R em rotacao", f5_pullback_alvo_1r_em_rotacao, None)]
NAO_FAZER = [("N1 comprar continuacao da abertura", n1_comprar_continuacao_da_abertura, None),
             ("N2 comprar suporte no meio da faixa", n2_comprar_suporte_no_meio_da_faixa, None),
             ("N3 venda pullback alvo distante", n3_vender_pullback_com_alvo_distante, None),
             ("N4 vender fundo do dia", n4_vender_fundo_do_dia_tarde, None),
             ("N5 comprar fundo de faixa antes das 13h", n5_comprar_fundo_de_faixa_antes_das_13h, None)]

if __name__ == "__main__":
    import base
    for tit, lst in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, g in lst:
            res = base.resumo(base.simula_dia("2022-08-18", r, g))
            print(f"{tit:9s} {nome:42s} ops={res['ops']} R$={res['brl']:9.2f}")
