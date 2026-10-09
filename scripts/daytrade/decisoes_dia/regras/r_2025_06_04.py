"""Pregao 2025-06-04 (WIN). Regras puras: so usam o passado do instante da decisao."""
import numpy as np
import pandas as pd

H = pd.Timedelta(hours=1)


def _h(ctx):
    return ctx.hoje


def _prim_hora(ctx):
    h = _h(ctx)
    p = h[h.index < h.index[0] + H]
    return p


def _ema(ctx, n=20):
    return ctx.m15.close.ewm(span=n, adjust=False).mean().iloc[-1]


def _ord(ctx, lado, stop_atr, alvo_atr, extra=0.0):
    p = float(_h(ctx).close.iloc[-1])
    a = ctx.atr15
    stop_atr = min(stop_atr, 590.0 / a)  # risco maximo 6% do caixa (600 pts)
    if lado == "venda":
        return dict(lado="venda", preco=p, stop=p + stop_atr * a, alvo=(p - alvo_atr * a) if alvo_atr else None, contratos=1)
    return dict(lado="compra", preco=p, stop=p - stop_atr * a, alvo=(p + alvo_atr * a) if alvo_atr else None, contratos=1)


# ---------------- FAZER ----------------
def f1_rompe_minima_1a_hora(ctx):
    """Venda no fechamento abaixo da minima da 1a hora (09:00-10:00), so depois das 10:00 e antes das 14:00.
    Condicao: dia que comeca em rotacao e rompe a faixa inicial para baixo com o preco abaixo da EMA20 M15.
    Provavelmente geral (rompimento da faixa da 1a hora). Stop 1,5 ATR15, alvo 3 ATR15."""
    h = _h(ctx)
    if len(h) < 5 or not (pd.Timestamp(h.index[0]).hour == 9): return None
    if not (10 <= ctx.t.hour < 14): return None
    p1 = _prim_hora(ctx)
    c = h.close.iloc[-1]
    if c < p1.low.min() and c < _ema(ctx):
        return _ord(ctx, "venda", 1.5, 3.0)


def f2_falha_maxima_1a_hora(ctx):
    """Venda quando a vela rompe a maxima da 1a hora mas FECHA de volta abaixo dela, com pavio superior grande.
    Condicao: rompimento falso da faixa inicial num dia de rotacao (sem continuidade, volume nao explode).
    Provavelmente geral (reversao em falha). Stop 1,5 ATR15, alvo 3 ATR15."""
    h = _h(ctx)
    if len(h) < 5 or not (10 <= ctx.t.hour < 14): return None
    p1 = _prim_hora(ctx)
    u = h.iloc[-1]
    topo = p1.high.max()
    corpo = max(u.open, u.close)
    if u.high > topo and u.close < topo and (u.high - corpo) > 0.5 * (u.high - u.low):
        return _ord(ctx, "venda", 1.5, 3.0)


def f3_recuo_na_media_tendencia_baixa(ctx):
    """Venda no recuo ate a EMA9 M15 quando o dia ja esta em baixa (abaixo da abertura e EMA20 caindo).
    Condicao: tendencia intradiaria de baixa instalada; recuo a favor, nao rompimento.
    Provavelmente geral (pullback a favor). Stop 1,5 ATR15, alvo 3 ATR15."""
    h = _h(ctx)
    if len(h) < 8 or not (11 <= ctx.t.hour < 15): return None
    e20 = ctx.m15.close.ewm(span=20, adjust=False).mean()
    e9 = ctx.m15.close.ewm(span=9, adjust=False).mean()
    u = h.iloc[-1]
    if (u.close < h.open.iloc[0] and e20.iloc[-1] < e20.iloc[-4] and u.high >= e9.iloc[-1] and u.close < e9.iloc[-1]
            and u.close < u.open):
        return _ord(ctx, "venda", 1.5, 3.0)


def f4_compra_exaustao_queda(ctx):
    """Compra apos a queda do dia ter percorrido ~1 ATR diario desde a maxima e volume secando
    (volume da vela < 60% da media do dia), com fechamento acima da vela anterior.
    Condicao: queda esgotada em fim de dia; alvo curto (devolucao parcial).
    Ajustada ao dia (a maior parte das quedas esgotadas continua). Stop 1,5 ATR15, alvo 1,5 ATR15."""
    h = _h(ctx)
    if len(h) < 10: return None
    queda = h.high.max() - h.low.min()
    u = h.iloc[-1]
    if (h.low.iloc[-1] == h.low.min() or h.low.iloc[-2] == h.low.min()) and queda > 0.8 * ctx.atrd \
            and u.vol < 0.6 * h.vol.mean() and u.close > h.close.iloc[-2] and ctx.t.hour >= 15:
        return _ord(ctx, "compra", 1.5, 1.5)


def f5_compra_suporte_manha(ctx):
    """Compra na rotacao da manha: fechamento na metade inferior da faixa do dia ate agora (faixa < 0,6 ATRd),
    entre 10:00 e 11:00, em vela de alta. Alvo na maxima do dia.
    Condicao: dia de rotacao com gap pequeno. Ajustada ao dia. Stop 1,5 ATR15."""
    h = _h(ctx)
    if len(h) < 4 or not (10 <= ctx.t.hour < 11): return None
    hi, lo = h.high.max(), h.low.min()
    u = h.iloc[-1]
    if (hi - lo) < 0.6 * ctx.atrd and u.close <= lo + 0.55 * (hi - lo) and u.close > u.open:
        p = float(u.close)
        return dict(lado="compra", preco=p, stop=p - min(1.5 * ctx.atr15, 590.0), alvo=hi, contratos=1)


# ---------------- NAO FAZER ----------------
def n1_compra_cada_queda_na_baixa(ctx):
    """Comprar toda vela de queda que fecha na minima das 6 ultimas, depois das 11:30.
    Armadilha: dia em tendencia de baixa intradiaria (abaixo da abertura e EMA20); minima nova continua. Geral."""
    h = _h(ctx)
    if len(h) < 8 or not (11 <= ctx.t.hour < 15): return None
    if h.close.iloc[-1] <= h.close.iloc[-6:].min() and h.close.iloc[-1] < h.open.iloc[0]:
        return _ord(ctx, "compra", 1.5, 1.5)


def n2_venda_minima_na_rotacao_manha(ctx):
    """Vender o fechamento na minima das 4 ultimas velas entre 10:00 e 11:30.
    Armadilha: rotacao da manha (faixa estreita, ATR15 baixo, volume alto de abertura); a faixa devolve. Geral."""
    h = _h(ctx)
    if len(h) < 5 or not (10 <= ctx.t.hour < 12): return None
    if h.close.iloc[-1] <= h.close.iloc[-4:].min():
        return _ord(ctx, "venda", 1.5, 1.5)


def n3_compra_rompimento_alta_manha(ctx):
    """Comprar a vela que fecha acima do maior fechamento das 4 anteriores (antes das 12:00) com preco acima da abertura.
    Armadilha: rompimento intradiario em dia de rotacao; o topo da manha foi o topo do dia. Ajustada ao dia."""
    h = _h(ctx)
    if len(h) < 4 or not (9 <= ctx.t.hour < 12): return None
    if h.close.iloc[-1] > h.close.iloc[-5:-1].max() and h.close.iloc[-1] > h.open.iloc[0]:
        return _ord(ctx, "compra", 1.5, 3.0)


def n4_venda_exaustao_tarde(ctx):
    """Vender nova minima do dia depois das 15:00.
    Armadilha: queda ja percorrida (>0,8 ATR diario) e volume secando: o mercado para de cair e devolve. Ajustada ao dia."""
    h = _h(ctx)
    if len(h) < 10 or not (15 <= ctx.t.hour < 18): return None
    if h.close.iloc[-1] <= h.close.min():
        return _ord(ctx, "venda", 1.5, 3.0)


def n5_venda_gap_fechado_sem_volume(ctx):
    """Vender vela de rejeicao (pavio superior > 50% da vela) que rompe a maxima da manha, antes das 11:00.
    Armadilha: em rotacao com gap de alta pequeno o pavio nao e reversao, a faixa ainda sobe ate o topo. Ajustada ao dia."""
    h = _h(ctx)
    if len(h) < 4 or not (9 <= ctx.t.hour < 11): return None
    u = h.iloc[-1]
    if u.high > h.high.iloc[:-1].max() and (u.high - max(u.open, u.close)) > 0.5 * (u.high - u.low):
        return _ord(ctx, "venda", 1.5, 3.0)


FAZER = [("F1 rompe minima da 1a hora (venda)", f1_rompe_minima_1a_hora, None),
         ("F2 falha na maxima da 1a hora (venda)", f2_falha_maxima_1a_hora, None),
         ("F3 recuo na media em tendencia de baixa", f3_recuo_na_media_tendencia_baixa, None),
         ("F4 compra exaustao da queda", f4_compra_exaustao_queda, None),
         ("F5 compra suporte na rotacao da manha", f5_compra_suporte_manha, None)]
NAO_FAZER = [("N1 comprar cada queda na baixa", n1_compra_cada_queda_na_baixa, None),
             ("N2 vender minima na rotacao da manha", n2_venda_minima_na_rotacao_manha, None),
             ("N3 comprar rompimento da manha", n3_compra_rompimento_alta_manha, None),
             ("N4 vender minima nova depois das 15h", n4_venda_exaustao_tarde, None),
             ("N5 vender pavio de rejeicao na manha", n5_venda_gap_fechado_sem_volume, None)]

if __name__ == "__main__":
    import base
    for grupo, lista in (("FAZER", FAZER), ("NAO FAZER", NAO_FAZER)):
        for nome, r, g in lista:
            res = base.resumo(base.simula_dia("2025-06-04", r, g, max_ops=3))
            print(f"{grupo:9s} {nome:42s} R$ {res['brl']:9.2f} ops {res['ops']} pts {res['pts']}", flush=True)
