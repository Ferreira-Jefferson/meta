"""Pregão 2022-11-16 (WIN M15): dia de TENDÊNCIA de baixa (abertura 113.655, mínima 110.340, fecho ~110.680),
gap de -515 pts (-0,14 ATR diário) sobre o fecho de ontem, ATR diário ~3.587.
Cada regra usa só ctx (passado até a decisão)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import base


def _hr(ctx):
    return ctx.t.hour + ctx.t.minute / 60


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _stop_pts(ctx, k):
    return min(k * ctx.atr15, 580.0)


# ---------------- FAZER ----------------
def f_rompe_1a_hora(ctx):
    """Venda no rompimento da mínima da 1ª hora (9h-10h) após as 10h, stop 1 ATR M15 acima, alvo 3x o risco.
    Condição: dia de tendência, em que a faixa da abertura é rompida e o preço não volta. Provavelmente geral
    (rompimento da faixa inicial é padrão clássico), mas em dia de rotação vira falso rompimento."""
    h = ctx.hoje
    if len(h) < 5 or _hr(ctx) < 10:
        return None
    pri = h.iloc[:4]
    if h.close.iloc[-1] < pri.low.min() and h.close.iloc[-2] >= pri.low.min():
        c = h.close.iloc[-1]; r = _stop_pts(ctx, 1.0)
        return dict(lado="venda", stop=c + r, alvo=c - 3 * r, contratos=1)


def f_pullback_ema(ctx):
    """Venda no recuo ate a EMA20 M15 (maxima toca a EMA20 menos 0,3 ATR e o fecho fica abaixo) com a EMA20 caindo
    nas ultimas 3 velas, entre 10h30 e 15h. Alvo 2,5x o risco (stop 1,3 ATR M15, max 580 pts).
    Condicao: tendencia de baixa em curso (continuacao). Provavelmente geral (continuacao, licao do projeto)."""
    if _hr(ctx) < 10.5 or _hr(ctx) > 15:
        return None
    e = _ema(ctx.m15.close, 20); h = ctx.hoje.iloc[-1]
    if h.close < e.iloc[-1] and h.high >= e.iloc[-1] - 0.3 * ctx.atr15 and e.iloc[-1] < e.iloc[-4]:
        c = h.close; r = _stop_pts(ctx, 1.3)
        return dict(lado="venda", stop=c + r, alvo=c - 2.5 * r, contratos=1)


def f_gap_abre_baixo_perde(ctx):
    """Gap de baixa (abertura abaixo do fecho de ontem): venda quando o fecho M15 cai mais de 0,5 ATR M15 abaixo da
    abertura de hoje pela 1a vez, entre 10h e 14h. Alvo 2,5x o risco.
    Condicao: gap de baixa que nao e preenchido e o preco perde a abertura. Provavelmente geral (gap + abertura como nivel)."""
    h = ctx.hoje; pc = ctx.diario.close.iloc[-1]
    if _hr(ctx) < 10 or _hr(ctx) > 14 or len(h) < 4:
        return None
    lim = h.open.iloc[0] - 0.5 * ctx.atr15
    if h.open.iloc[0] < pc and h.close.iloc[-1] < lim and h.close.iloc[-2] >= lim:
        c = h.close.iloc[-1]; r = _stop_pts(ctx, 1.0)
        return dict(lado="venda", stop=c + r, alvo=c - 2.5 * r, contratos=1)


def f_nova_min_sob_abertura(ctx):
    """Venda quando a vela fecha em nova minima do dia, abaixo da abertura por mais de 1 ATR M15 e abaixo da VWAP
    aproximada de hoje, entre 10h e 15h. Alvo 2x o risco. Condicao: pressao vendedora sustentada (eficiencia
    direcional alta). Ajustada ao dia (a tendencia unica do dia faz ela funcionar)."""
    h = ctx.hoje
    if _hr(ctx) < 10 or _hr(ctx) > 15 or len(h) < 6:
        return None
    c = h.close.iloc[-1]
    vw = (h.close * h.vol).cumsum().iloc[-1] / h.vol.cumsum().iloc[-1]
    if c < h.low.iloc[:-1].min() and c < h.open.iloc[0] - ctx.atr15 and c < vw:
        r = _stop_pts(ctx, 1.0)
        return dict(lado="venda", stop=c + r, alvo=c - 2 * r, contratos=1)


def f_reversao_fundo_tarde(ctx):
    """Compra unica do dia apos as 15h30: a minima do dia foi feita nas ultimas 6 velas, o fecho esta acima do maior
    fecho das 3 ultimas velas e a mais de 0,6 ATR M15 da minima. Alvo 1,2x o risco. Condicao: queda longa esgotada no fim do dia.
    Ajustada ao dia (reversao contraria a licao de continuacao; so a 1a entrada do dia e valida)."""
    h = ctx.hoje
    if _hr(ctx) < 15.5 or len(h) < 8 or ctx.ops_hoje:
        return None
    c = h.close.iloc[-1]; mn = h.low.min()
    if h.low.iloc[-6:].min() <= mn and c > h.close.iloc[-3:].max() - 1 and c - mn > 0.6 * ctx.atr15:
        r = _stop_pts(ctx, 1.0)
        return dict(lado="compra", stop=c - r, alvo=c + 1.2 * r, contratos=1)


# ---------------- NAO FAZER ----------------
def n_compra_cada_queda(ctx):
    """Compra cada queda de 1 ATR M15 em 3 velas (fundo barato), alvo 1x o risco. Armadilha: dia de tendencia de baixa,
    em que a queda continua (RSI baixo continua caindo). Veto: nao comprar queda quando preco < abertura e EMA20 caindo."""
    h = ctx.hoje
    if len(h) < 4 or _hr(ctx) < 10:
        return None
    c = h.close.iloc[-1]
    if h.close.iloc[-4] - c > 1.0 * ctx.atr15:
        r = _stop_pts(ctx, 1.2)
        return dict(lado="compra", stop=c - r, alvo=c + r, contratos=1)


def n_compra_inversao_1_vela(ctx):
    """Compra a primeira vela de alta depois de uma de baixa (11h-16h), alvo 1,5x. Armadilha: em tendencia de baixa
    cada alta isolada e so recuo. Veto: nao comprar viradas de 1 vela com o dia abaixo da abertura e abaixo da VWAP."""
    h = ctx.hoje
    if _hr(ctx) < 10 or _hr(ctx) > 16 or len(h) < 6:
        return None
    c = h.close.iloc[-1]
    if c > h.close.iloc[-2] and h.close.iloc[-2] < h.close.iloc[-3]:
        r = _stop_pts(ctx, 1.0)
        return dict(lado="compra", stop=c - r, alvo=c + 1.5 * r, contratos=1)


def n_compra_desvio_vwap(ctx):
    """Compra quando o fecho esta mais de 1,5 ATR M15 abaixo da VWAP de hoje (reversao a media), alvo 1,5x.
    Armadilha: em dia de tendencia o preco fica esticado abaixo da VWAP por horas. Veto: nao comprar desvio da
    VWAP quando a eficiencia direcional do dia esta alta (>0,5)."""
    h = ctx.hoje
    if _hr(ctx) < 11 or len(h) < 6:
        return None
    vw = (h.close * h.vol).cumsum().iloc[-1] / h.vol.cumsum().iloc[-1]; c = h.close.iloc[-1]
    if c < vw - 1.5 * ctx.atr15:
        r = _stop_pts(ctx, 1.0)
        return dict(lado="compra", stop=c - r, alvo=c + 1.5 * r, contratos=1)


def n_compra_suporte_ontem(ctx):
    """Compra o teste da minima de ontem (suporte), alvo 1,5x. Armadilha: dia que abre abaixo e perde o nivel de ontem;
    o suporte vira resistencia. Veto: nao comprar suporte de ontem em dia de gap de baixa com preco abaixo da abertura."""
    h = ctx.hoje; mn = ctx.diario.low.iloc[-1]
    if _hr(ctx) < 10 or len(h) < 4:
        return None
    if h.low.iloc[-1] <= mn + 100 and h.close.iloc[-1] > mn:
        c = h.close.iloc[-1]; r = _stop_pts(ctx, 1.0)
        return dict(lado="compra", stop=c - r, alvo=c + 1.5 * r, contratos=1)


def n_compra_falha_fundo_cedo(ctx):
    """Compra apos falha de fundo (vela anterior fez minima do dia, atual fecha acima da maxima dela) a partir das 14h,
    alvo 1,5x. Armadilha: o fundo ainda nao esta feito, a venda continua por mais 2 horas. Veto: nao comprar falha de fundo
    quando a minima do dia vem sendo renovada na ultima hora e o dia andou mais de 1 ATR diario... (so apos exaustao)."""
    h = ctx.hoje
    if _hr(ctx) < 14 or len(h) < 8:
        return None
    a, b = h.iloc[-2], h.iloc[-1]
    if a.low <= h.low.iloc[:-1].min() and b.close > a.high:
        c = b.close; r = _stop_pts(ctx, 1.0)
        return dict(lado="compra", stop=c - r, alvo=c + 1.5 * r, contratos=1)


FAZER = [("venda rompe minima 1a hora", f_rompe_1a_hora, None),
         ("venda pullback EMA20 em baixa", f_pullback_ema, None),
         ("venda gap de baixa perde abertura", f_gap_abre_baixo_perde, None),
         ("venda nova minima sob abertura/VWAP", f_nova_min_sob_abertura, None),
         ("compra reversao fundo tarde", f_reversao_fundo_tarde, None)]
NAO_FAZER = [("compra cada queda de 1 ATR", n_compra_cada_queda, None),
             ("compra inversao de 1 vela", n_compra_inversao_1_vela, None),
             ("compra desvio de 1,5 ATR da VWAP", n_compra_desvio_vwap, None),
             ("compra suporte minima de ontem", n_compra_suporte_ontem, None),
             ("compra falha de fundo cedo (14h)", n_compra_falha_fundo_cedo, None)]

if __name__ == "__main__":
    for tag, L in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, g in L:
            s = base.resumo(base.simula_dia("2022-11-16", r, g))
            print(f"{tag:9s} {nome:40s} ops={s['ops']} R$={s['brl']:9.2f} pts={s['pts']}")
