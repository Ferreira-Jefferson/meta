"""Ciclo 3 - dia 2022-09-21 (WIN M15, tipo ruim, ef 0,057). v2 e v3 fecharam -R$89,75 (1 operacao); a v1 nao operou (R$0).

O DIA: abertura 113.600 (gap +295 sobre o fecho de ontem), cai em degraus ate 112.365 (12:00), faixa 112.4k-113.2k de 12:00 a 14:30 (~800 pts),
e as 15:00 vem o CHOQUE (barra de 885 pts, 1,2M de volume = o maior do dia, minima 112.035, abaixo da minima de ontem 112.165), devolve
ate 114.180 (15:45) e cai de novo ate 112.510. ATR15 ~300 de manha, 580 ao fim. Amplitude do dia 2.145 pts = 0,92 ATRd; eficiencia 0,057.
Unica operacao do v3: venda do pullback EMA20 as 13:15 (112.735, stop 448 pts), stopada 13:50 (-R$89,75): o fecho estava a 370 pts da
minima do dia, no meio de uma faixa de 2 h, com stop de ~1 ATR15 dentro do ruido da faixa. Na v1 o veto `vende_rompimento_stop_curto`
(original) bloqueava essa venda; o A2 da v2 o afrouxou e ela passou: efeito colateral do A2, a mesma familia dos 5 dias do ciclo 3.
Maior movimento: compra apos o choque das 15:00 (fecho 112.210 -> maxima 114.180 as 15:45 = +1.960 pts). Nenhuma FAZER de compra existia:
as FAZER do robo sao todas de continuacao de venda, e as de compra exigem queda >= 1,3 ATRd (a queda ate a minima foi 0,54 ATRd).

`python -m regras.c3_2022_09_21` imprime o resultado isolado de cada regra no dia.
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


def _vmed(ctx, n=20, pular=1):
    """mediana do volume das n velas M15 anteriores (pula as `pular` mais recentes)."""
    v = ctx.m15.vol.iloc[:-pular] if pular else ctx.m15.vol
    return float(v.iloc[-n:].median())


def _ord(ctx, lado, stop_px, alvo_r):
    p = float(ctx.hoje.close.iloc[-1]); sg = 1 if lado == "compra" else -1
    r = min(abs(p - stop_px), TETO)
    if r < 1: return None
    return dict(lado=lado, preco=p, stop=p - sg * r, alvo=(None if alvo_r is None else p + sg * alvo_r * r), contratos=1)


# ============================================================================= FAZER (5)
def f1_compra_exaustao_com_volume_na_minima(ctx):
    """REVERSAO por exaustao de volume (geral). A vela anterior tocou a minima do dia com volume >= 2,5x a mediana das 20 anteriores
    (liquidacao) e a vela atual fecha acima do fecho dela, de alta, sem perder a minima dela. Compra, stop 0,2 ATR15 abaixo da minima da
    vela de choque (teto 590), alvo 1,5R. Condicao: capitulacao com volume extremo. 15:15 de 21/09: vela das 15:00 minima 112.035, volume
    1,2M (mediana ~400k); 15:15 fecha 112.760. Nao exige queda de 1,3 ATRd (diferente do F2A do c2_2025_04_07)."""
    h = ctx.hoje
    if len(h) < 4 or _hm(ctx) > 16 * 60: return None
    a, u = h.iloc[-2], h.iloc[-1]
    if a.low <= h.low.min() and a.vol >= 2.5 * _vmed(ctx, 20, 2) and u.close > a.close and u.close > u.open and u.low >= a.low:
        return _ord(ctx, "compra", float(a.low) - 0.2 * ctx.atr15, 1.5)


def f2_compra_spring_na_minima_do_dia(ctx):
    """REVERSAO em rejeicao (geral). A partir de 11:30 e ate 15:00, a vela renova a minima do dia, fecha no terco superior da propria faixa e o
    dia ja caiu >= 0,4 ATRd da abertura. Compra, stop 0,2 ATR15 abaixo da minima da vela (teto 590), alvo 1,5R. Condicao: varredura de
    stops sem continuidade apos queda de verdade. 12:15 de 21/09: vela das 12:00 minima 112.365, fecho 112.605 (96% da faixa)."""
    h = ctx.hoje; u = h.iloc[-1]
    if not (11 * 60 + 30 <= _hm(ctx) <= 15 * 60) or len(h) < 8: return None
    if u.low <= h.low.min() and u.close >= u.low + 0.66 * (u.high - u.low) and (float(h.open.iloc[0]) - float(u.low)) >= 0.4 * ctx.atrd:
        return _ord(ctx, "compra", float(u.low) - 0.2 * ctx.atr15, 1.5)


def f3_compra_falha_da_minima_de_ontem(ctx):
    """NIVEL DE ONTEM (geral). Apos 10:00, a vela fura a minima de ontem por >= 0,1 ATR15 e FECHA acima dela. Compra, stop 0,2 ATR15 abaixo
    da minima da vela (teto 590), alvo 1,5R. Condicao: rompimento de suporte do dia anterior rejeitado. 15:15 de 21/09: vela das 15:00
    minima 112.035 < 112.165 (ontem), fecho 112.210."""
    h = ctx.hoje; u = h.iloc[-1]
    if _hm(ctx) < 10 * 60 + 15: return None
    ml = float(ctx.diario.low.iloc[-1])
    if u.low < ml - 0.1 * ctx.atr15 and u.close > ml:
        return _ord(ctx, "compra", float(u.low) - 0.2 * ctx.atr15, 1.5)


def f4_venda_devolve_metade_da_barra_de_choque(ctx):
    """CONTINUACAO apos choque (geral). Depois das 15:00: nas ultimas 8 velas houve uma barra de choque de ALTA (faixa >= 3x a mediana das
    faixas das 32 velas anteriores); o fecho atual cai abaixo do meio dela e o anterior ainda estava acima. Venda, stop 0,1 ATR15 acima da
    maxima da barra de choque (teto 590), alvo 1R. Condicao: o impulso do choque foi devolvido. 16:30 de 21/09: barra das 15:30 (112.610-114.055)
    perde o meio (113.332) em 16:15."""
    h = ctx.hoje
    if len(h) < 8 or _hm(ctx) < 15 * 60: return None
    rg = (h.high - h.low)
    ref = float((ctx.m15.high - ctx.m15.low).iloc[-40:-8].median())
    k = int(np.argmax(rg.values[-8:])); b = h.iloc[-8 + k]
    if rg.iloc[-8 + k] < 3 * ref: return None
    mid = (b.high + b.low) / 2
    if b.close > b.open and h.close.iloc[-1] < mid and h.close.iloc[-2] >= mid:
        return _ord(ctx, "venda", float(b.high) + 0.1 * ctx.atr15, 1.0)


def f5_venda_rompe_minima_da_manha_sob_vwap(ctx):
    """CONTINUACAO cedo (AJUSTADA AO DIA: com stop 1,3 ATR15 o mesmo sinal da -R$99 e com alvo 1,5R da -R$77). Entre 10:30 e 12:00 o fecho rompe
    a minima das 8 velas anteriores, fica no quarto inferior da propria vela e abaixo da VWAP. Venda, stop 1 ATR15 (teto 590), alvo 1R.
    11:00 de 21/09: fecho 112.820 < 112.960, VWAP ~113.250. Rompimento de minima de manha em dia de rotacao: o v3 esta vetado por N2/rotacao."""
    h = ctx.hoje; u = h.iloc[-1]
    if not (10 * 60 + 30 <= _hm(ctx) <= 12 * 60) or len(h) < 8: return None
    if u.close < float(h.low.iloc[-9:-1].min()) and u.close <= u.low + 0.35 * (u.high - u.low) and u.close < _vwap(h):
        return _ord(ctx, "venda", float(u.close) + 1.0 * ctx.atr15, 1.0)


# ============================================================================= NAO_FAZER (5)
def n1_vender_em_faixa_de_rotacao_apos_12h(ctx):
    """VETO de venda = A2 CONDICIONAL (geral). Apos 12:00, nao vender quando a eficiencia do dia ate agora < 0,12 e as 8 velas anteriores
    ficaram numa faixa <= 3 ATR15 (o dia andou de lado por 2 h): o stop de ~1 ATR15 fica dentro do ruido da faixa. Usa so estado
    observavel na hora (eficiencia e faixa de 2 h). 13:15 de 21/09: faixa 11:15-13:00 = 800 pts, eficiencia 0,10; a venda foi stopada
    (-R$89,75). E o veto original (rompimento de minima) restrito ao estado em que ele acerta."""
    h = ctx.hoje
    if _hm(ctx) < 12 * 60 or len(h) < 10: return None
    a = h.iloc[-9:-1]
    if _efic(ctx) < 0.12 and float(a.high.max() - a.low.min()) <= 3 * ctx.atr15:
        c = float(h.close.iloc[-1])
        return _ord(ctx, "venda", c + 1.3 * ctx.atr15, 2.5)


def n2_comprar_rompimento_de_faixa_comprimida_no_meio_da_tarde(ctx):
    """ARMADILHA (geral). Entre 12:00 e 14:30, comprar o rompimento da maxima de uma faixa de 2 h (<= 3 ATR15) com vela forte, sem
    volume extra: o rompimento do meio da tarde costuma ser falso. Stop no meio da faixa, alvo 1R. 13:45 de 21/09: fecho 113.095 > 113.060;
    devolve (-R$71)."""
    h = ctx.hoje; u = h.iloc[-1]
    if not (12 * 60 <= _hm(ctx) <= 14 * 60 + 30) or len(h) < 14: return None
    a = h.iloc[-9:-1]
    if a.high.max() - a.low.min() <= 3.0 * ctx.atr15 and u.close > a.high.max() and u.close >= u.low + 0.65 * (u.high - u.low):
        return _ord(ctx, "compra", float((a.high.max() + a.low.min()) / 2), 1.0)


def n3_vender_rompimento_de_minima_com_alvo_1_5r(ctx):
    """ARMADILHA (geral: o alvo). O mesmo sinal do F5 com alvo de 1,5R: em dia de faixa <= 1 ATRd o rompimento da minima da manha
    anda ~1R e devolve; alvo maior nao e atingido. Nao fazer: vender rompimento de minima de manha com alvo > 1R em rotacao.
    11:00 de 21/09: -R$76,64."""
    h = ctx.hoje; u = h.iloc[-1]
    if not (10 * 60 + 30 <= _hm(ctx) <= 12 * 60) or len(h) < 8 or float(h.high.max() - h.low.min()) > 1.0 * ctx.atrd: return None
    if u.close < float(h.low.iloc[-9:-1].min()) and u.close <= u.low + 0.35 * (u.high - u.low) and u.close < _vwap(h):
        return _ord(ctx, "venda", float(u.close) + 1.0 * ctx.atr15, 1.5)


def n4_comprar_perseguindo_a_barra_de_choque(ctx):
    """ARMADILHA (geral). Comprar o fecho de uma barra de choque de ALTA (faixa >= 3x a mediana, volume >= 2x a mediana) que ja devolveu
    pouco: o fecho no topo apos uma barra de 1.400 pts e perseguir. Stop 1 ATR15, alvo 1R. 15:45 de 21/09: barra das 15:30 fecha 113.900 e
    o preco volta a 113.270 em 15 min."""
    h = ctx.hoje; u = h.iloc[-1]
    if len(h) < 8 or _hm(ctx) < 15 * 60: return None
    ref = float((ctx.m15.high - ctx.m15.low).iloc[-41:-1].median())
    if (u.high - u.low) >= 3 * ref and u.vol >= 2 * _vmed(ctx, 20, 1) and u.close > u.open:
        c = float(u.close); return _ord(ctx, "compra", c - 1.0 * ctx.atr15, 1.0)


def n5_vender_minima_nova_com_volume_extremo(ctx):
    """ARMADILHA (geral). Vender o fecho de uma vela que renova a minima do dia com volume >= 2,5x a mediana das 20 anteriores (liquidacao
    ja consumada = exaustao, nao inicio). Stop 1 ATR15, alvo 1,5R. 15:15 de 21/09: vela das 15:00 (1,2M = 3x, minima 112.035) fecha 112.210
    e o preco sobe 1.970 pts."""
    h = ctx.hoje; u = h.iloc[-1]
    if len(h) < 6 or _hm(ctx) < 10 * 60: return None
    if u.low <= h.low.min() and u.vol >= 2.5 * _vmed(ctx, 20, 1):
        c = float(u.close); return _ord(ctx, "venda", c + 1.0 * ctx.atr15, 1.5)


FAZER = [("F1 compra exaustao com volume na minima", f1_compra_exaustao_com_volume_na_minima, None),
         ("F2 compra spring na minima do dia", f2_compra_spring_na_minima_do_dia, None),
         ("F3 compra falha da minima de ontem", f3_compra_falha_da_minima_de_ontem, None),
         ("F4 venda devolve metade da barra de choque", f4_venda_devolve_metade_da_barra_de_choque, None),
         ("F5 venda rompe minima da manha sob VWAP", f5_venda_rompe_minima_da_manha_sob_vwap, None)]
NAO_FAZER = [("N1 vender em faixa de rotacao apos 12h", n1_vender_em_faixa_de_rotacao_apos_12h, None),
             ("N2 comprar rompimento de faixa comprimida", n2_comprar_rompimento_de_faixa_comprimida_no_meio_da_tarde, None),
             ("N3 vender rompimento de minima com alvo 1,5R", n3_vender_rompimento_de_minima_com_alvo_1_5r, None),
             ("N4 comprar perseguindo barra de choque", n4_comprar_perseguindo_a_barra_de_choque, None),
             ("N5 vender minima nova com volume extremo", n5_vender_minima_nova_com_volume_extremo, None)]

if __name__ == "__main__":
    import base
    for tit, lst in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, g in lst:
            res = base.resumo(base.simula_dia("2022-09-21", r, g))
            print(f"{tit:9s} {nome:46s} ops={res['ops']} R$={res['brl']:9.2f}")
