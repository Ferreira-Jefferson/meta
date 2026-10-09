"""Pregao 2023-08-21 (WIN): gap de alta de ~485 pts, devolvido em 45 min, depois tendencia de baixa o dia todo."""
import pandas as pd
from base import simula_dia, resumo

HH = pd.Timedelta(hours=1)


def _faixa_1h(ctx):
    h = ctx.hoje
    p = h[h.index < h.index[0] + HH]
    return float(p.high.max()), float(p.low.min()), len(p)


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


# ---------------- FAZER ----------------
def f1_rompe_minima_1h(ctx):
    """Venda no rompimento da minima da 1a hora (09:00-10:00) quando a 1a hora e estreita (< 0,5 ATR diario).
    Condicao: dia abre comprimido; fechamento M15 abaixo da minima da 1a hora com volume acima da media da 1a hora.
    Stop: maxima da 1a hora (limitado a 500 pts); alvo 1,5x o risco. Provavelmente geral (rompimento de faixa da 1a hora)."""
    h = ctx.hoje
    if len(h) < 5 or ctx.ops_hoje: return None
    hi, lo, n = _faixa_1h(ctx)
    if hi - lo > 0.5 * ctx.atrd: return None
    c = float(h.close.iloc[-1])
    if c < lo and h.vol.iloc[-1] > h.vol.iloc[:4].mean():
        stop = min(hi, c + 500)
        return dict(lado="venda", stop=stop, alvo=c - 1.5 * (stop - c), contratos=1)


def f2_gap_preenchido(ctx):
    """Gap de alta devolvido: vende quando o fechamento M15 cai abaixo do fechamento de ontem depois de abrir com gap
    de alta > 0,15 ATR diario. Condicao: gap que nao se sustenta, o preco devolve o salto. Stop 450 pts acima, alvo 900.
    Provavelmente geral (gap fill), mas gap pequeno e ruidoso."""
    h = ctx.hoje
    if ctx.ops_hoje: return None
    ont = float(ctx.diario.close.iloc[-1]); ab = float(h.open.iloc[0])
    if ab - ont < 0.15 * ctx.atrd: return None
    c = float(h.close.iloc[-1])
    if c < ont:
        return dict(lado="venda", stop=c + 450, alvo=c - 900, contratos=1)


def f3_minima_de_ontem(ctx):
    """Venda quando o fechamento M15 perde a minima de ontem (apos 10:30), com preco abaixo da abertura e da EMA21 M15.
    Condicao: nivel de ontem quebrado a favor do dia vendedor. Stop 590 pts, sem alvo (deixa correr ate o fim). Provavelmente geral (nivel de ontem + tendencia)."""
    h = ctx.hoje
    if ctx.ops_hoje or ctx.t.hour * 60 + ctx.t.minute < 10 * 60 + 30: return None
    mn = float(ctx.diario.low.iloc[-1]); c = float(h.close.iloc[-1])
    if c < mn and c < float(h.open.iloc[0]) and c < _ema(ctx.m15.close, 21).iloc[-1]:
        return dict(lado="venda", stop=c + 590, alvo=None, contratos=1)


def f3_gerir(ctx, pos):
    h = ctx.hoje
    if len(h) < 4: return None
    return float(h.high.iloc[-3:].max()) + 50


def f4_recuo_ate_ema(ctx):
    """Recuo a favor da tendencia: EMA21 M15 caindo (queda > 80 pts em 3 velas) e uma vela sobe ate tocar a EMA21
    e fecha abaixo dela (rejeicao), depois das 10:30. Condicao: tendencia de baixa estabelecida; em rotacao lateral
    vira armadilha. Stop 450 pts, alvo 700. Provavelmente geral (pullback na tendencia)."""
    h = ctx.hoje
    if ctx.ops_hoje or ctx.t.hour * 60 + ctx.t.minute < 10 * 60 + 30: return None
    e = _ema(ctx.m15.close, 21)
    if e.iloc[-1] < e.iloc[-4] - 80 and h.high.iloc[-1] >= e.iloc[-1] - 120 and h.close.iloc[-1] < e.iloc[-1]:
        c = float(h.close.iloc[-1])
        return dict(lado="venda", stop=c + 450, alvo=c - 700, contratos=1)


def f5_falha_de_alta(ctx):
    """Reversao em falha: a maxima da vela supera a das 2 anteriores mas ela fecha em baixa, com o dia ja
    200 pts abaixo da abertura (vies de baixa). A falha de alta e ponto de venda. Stop acima da maxima da vela,
    alvo 600, nao opera depois das 15h. AJUSTADA ao dia (so funciona porque o dia e tendencia de baixa)."""
    h = ctx.hoje
    if len(h) < 6 or ctx.ops_hoje or ctx.t.hour >= 15: return None
    u = h.iloc[-1]
    if u.high > h.high.iloc[-3:-1].max() and u.close < u.open and u.close < h.open.iloc[0] - 200:
        return dict(lado="venda", stop=float(u.high) + 50, alvo=float(u.close) - 600, contratos=1)


FAZER = [("rompe_minima_1h", f1_rompe_minima_1h, None), ("gap_preenchido", f2_gap_preenchido, None),
         ("minima_de_ontem", f3_minima_de_ontem, None), ("recuo_ate_ema21", f4_recuo_ate_ema, None),
         ("falha_de_alta", f5_falha_de_alta, None)]


# ---------------- NAO FAZER ----------------
def n1_compra_queda_1atr(ctx):
    """Comprar cada queda de 1 ATR M15 em relacao a maxima das ultimas 6 velas. Armadilha: dia de tendencia de baixa
    com continuacao (RSI baixo continua caindo); nao fazer quando o dia ja esta abaixo da abertura. Stop 450, alvo 450. Geral."""
    h = ctx.hoje
    if len(h) < 6 or ctx.t.hour >= 16: return None
    c = float(h.close.iloc[-1])
    if h.high.iloc[-6:].max() - c >= 1.0 * ctx.atr15:
        return dict(lado="compra", stop=c - 450, alvo=c + 450, contratos=1)


def n2_vende_rompimento_stop_curto(ctx):
    """Vender o rompimento da minima da 1a hora com stop de 120 pts e alvo de 240. Armadilha: o stop menor que o ruido normal
    (uma vela M15 tem ~300 pts) e varrido pelos repiques antes de a tendencia andar; nao fazer com stop menor que 1 ATR M15.
    Geral."""
    h = ctx.hoje
    if len(h) < 5: return None
    hi, lo, n = _faixa_1h(ctx)
    c = float(h.close.iloc[-1])
    if c < lo:
        return dict(lado="venda", stop=c + 120, alvo=c - 240, contratos=1)


def n3_compra_esticado_vs_ema21(ctx):
    """Comprar quando o fechamento esta mais de 1,5 ATR M15 abaixo da EMA21 (esticado), apostando na volta a media.
    Armadilha: tendencia forte nao volta; nao fazer contra a direcao do dia antes das 14h. Stop 500, alvo na EMA21."""
    h = ctx.hoje
    e = _ema(ctx.m15.close, 21).iloc[-1]; c = float(h.close.iloc[-1])
    if ctx.t.hour >= 14 or len(h) < 4: return None
    if e - c > 1.5 * ctx.atr15:
        return dict(lado="compra", stop=c - 500, alvo=e, contratos=1)


def n4_vende_minima_nova_tarde(ctx):
    """Vender a minima nova do dia depois das 15h. Armadilha: apos 15h a tendencia esgotou, o movimento fica lateral
    e o preco volta; nao fazer rompimento na ultima hora e meia, mesmo a favor do dia. Stop 300, alvo 600."""
    h = ctx.hoje
    if ctx.t.hour < 15 or len(h) < 6: return None
    if h.close.iloc[-1] < h.low.iloc[-9:-1].min():
        c = float(h.close.iloc[-1])
        return dict(lado="venda", stop=c + 300, alvo=c - 600, contratos=1)


def n5_compra_dois_verdes_gap_pequeno(ctx):
    """Comprar a retomada (vela de alta que fecha acima da maxima da vela anterior) em dia que abriu com gap de alta
    pequeno (<0,3 ATR diario) ja devolvido. Armadilha: repique curto dentro de tendencia de baixa; nao comprar repique
    abaixo da abertura do dia. Stop 450, alvo 900."""
    h = ctx.hoje
    if ctx.ops_hoje or len(h) < 4 or ctx.t.hour >= 15: return None
    ont = float(ctx.diario.close.iloc[-1]); ab = float(h.open.iloc[0])
    c = float(h.close.iloc[-1])
    if 0 < ab - ont < 0.3 * ctx.atrd and c < ab and h.close.iloc[-1] > h.open.iloc[-1] and c > h.high.iloc[-2]:
        return dict(lado="compra", stop=c - 450, alvo=c + 900, contratos=1)


NAO_FAZER = [("compra_queda_1atr", n1_compra_queda_1atr, None), ("vende_rompimento_stop_curto", n2_vende_rompimento_stop_curto, None),
             ("compra_esticado_vs_ema21", n3_compra_esticado_vs_ema21, None), ("vende_minima_nova_tarde", n4_vende_minima_nova_tarde, None),
             ("compra_repique_gap_pequeno", n5_compra_dois_verdes_gap_pequeno, None)]

if __name__ == "__main__":
    for tit, lst in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, g in lst:
            res = resumo(simula_dia("2023-08-21", r, g))
            print(f"{tit:9s} {nome:32s} ops={res['ops']} R$={res['brl']:9.2f}")
