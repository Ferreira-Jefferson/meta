"""Regras do pregão 2023-11-03 (WIN, M15). Dia de tendência de alta após gap de abertura (feriado em 02/11)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import base

MAXSTOP = 590.0  # pts: 6% de R$2.000 com 1 contrato = 600 pts


def _ref(ctx):
    return ctx.diario.iloc[-1]


def _gap(ctx):
    return (ctx.hoje.open.iloc[0] - _ref(ctx).close) / ctx.atrd


def _ent(ctx, lado, stop_dist, alvo_dist=None):
    p = float(ctx.hoje.close.iloc[-1])
    s = 1 if lado == "compra" else -1
    sd = min(stop_dist, MAXSTOP)
    return {"lado": lado, "preco": p, "stop": p - s * sd,
            "alvo": None if alvo_dist is None else p + s * alvo_dist, "contratos": 1}


# ---------------- FAZER ----------------
def f1_rompe_faixa_1h(ctx):
    """Rompimento da faixa da 1ª hora (9:00-10:00) a favor do gap. Compra quando, entre 10:00 e 14:00, o fechamento
    passa da máxima da 1ª hora (a vela anterior não tinha passado) e o dia abriu com gap de alta > 0,2 ATRd.
    Stop no meio da faixa (máx 590 pts), sem alvo (zera no fim).
    Condição: gap com continuação. Provavelmente geral (gap + faixa inicial)."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= ctx.t.hour < 14) or _gap(ctx) < 0.2:
        return None
    f = h.iloc[:4]
    top = f.high.max()
    if h.close.iloc[-1] > top and h.close.iloc[-2] <= top:
        return _ent(ctx, "compra", h.close.iloc[-1] - (top + f.low.min()) / 2)


def f2_recuo_ema(ctx):
    """Recuo a favor da tendência: acima da abertura do dia e da máxima de ontem, a vela toca a média de 8 M15 por baixo
    e fecha acima dela -> compra. Stop = amplitude até a mínima da vela + 1 ATR15; alvo 2,5 ATR15.
    Condição: tendência diária de alta de pé (fechamento > abertura do dia). Provavelmente geral."""
    h = ctx.hoje
    if len(h) < 6 or ctx.t.hour >= 15:
        return None
    ema = ctx.m15.close.ewm(span=8, adjust=False).mean().iloc[-1]
    u = h.iloc[-1]
    if u.close > h.open.iloc[0] and u.close > _ref(ctx).high and u.low <= ema < u.close:
        return _ent(ctx, "compra", u.close - u.low + ctx.atr15, 2.5 * ctx.atr15)


def f3_gap_acima_ontem(ctx):
    """Gap acima da máxima de ontem e aceitação: após a 1ª vela, se gap > 0,3 ATRd, abertura acima da máxima de ontem e a
    vela 1 fechou em alta, compra a continuação. Stop abaixo da mínima da 1ª vela, alvo 0,8 ATRd.
    Condição: gap de alta NÃO preenchido na 1ª vela. Ajustada ao dia (fundamento clássico, mas calibrada vendo o dia)."""
    h = ctx.hoje
    if len(h) != 1:
        return None
    u = h.iloc[0]
    if _gap(ctx) > 0.3 and u.open > _ref(ctx).high and u.close > u.open:
        return _ent(ctx, "compra", u.close - u.low + 50, ctx.atrd * 0.8)


def f4_maxima_do_dia_tarde(ctx):
    """Nova máxima do dia entre 14:00 e 15:00 com preço acima da média de 20 M15 e do dia subindo (fechamento > abertura +
    0,3 ATRd). Stop na mínima das 4 últimas velas; sem alvo, zera no fim (trailing curto testado e descartado: stopava no ruído).
    Condição: tendência persistente sem exaustão. Ajustada ao dia."""
    h = ctx.hoje
    if len(h) < 12 or not (14 <= ctx.t.hour < 15):
        return None
    u = h.iloc[-1]
    ma = ctx.m15.close.rolling(20).mean().iloc[-1]
    if u.high >= h.high.max() and u.close > ma and u.close - h.open.iloc[0] > 0.3 * ctx.atrd:
        e = _ent(ctx, "compra", u.close - h.low.iloc[-4:].min())
        return e


def f5_impulso_abertura(ctx):
    """Continuação do impulso: às 9:30, se as duas primeiras velas fecharam em alta e o fechamento está acima da máxima de
    ontem, compra. Stop 1,2 ATR15, alvo 2 ATR15. Condição: abertura direcional acima do nível de ontem. Ajustada ao dia."""
    h = ctx.hoje
    if len(h) != 2:
        return None
    if (h.close > h.open).all() and h.close.iloc[-1] > _ref(ctx).high:
        return _ent(ctx, "compra", 1.2 * ctx.atr15, 2 * ctx.atr15)


# ---------------- NAO FAZER ----------------
def n1_vender_gap(ctx):
    """Fade do gap: vende na 1ª vela esperando o preenchimento do gap de alta (> 0,3 ATRd). Stop 1 ATR15 acima da máxima,
    alvo no fechamento de ontem. Armadilha: gap acima da máxima de ontem em dia de continuação não preenche.
    Veto: não vender gap quando a abertura está acima da máxima de ontem."""
    h = ctx.hoje
    if len(h) != 1 or _gap(ctx) < 0.3:
        return None
    return _ent(ctx, "venda", h.high.iloc[0] - h.close.iloc[0] + ctx.atr15, h.close.iloc[0] - _ref(ctx).close)


def n2_vender_maxima_nova(ctx):
    """Vender a máxima nova do dia (10:00-15:00) esperando reversão, stop 1 ATR15, alvo 1,5 ATR15. Armadilha: dia de
    tendência de alta com máximas sucessivas. Veto: não vender máxima nova com fechamento > abertura + 0,5 ATRd."""
    h = ctx.hoje
    if len(h) < 6 or ctx.t.hour < 10 or ctx.t.hour >= 15:
        return None
    if h.high.iloc[-1] >= h.high.max():
        return _ent(ctx, "venda", ctx.atr15, 1.5 * ctx.atr15)


def n3_vender_rompimento_baixo(ctx):
    """Vender o rompimento da mínima das 3 velas anteriores quando o preço está acima da média de 20 M15 (aposta em virada).
    Stop 1 ATR15, alvo 1,5 ATR15. Armadilha: queda curta dentro de tendência de alta é recuo, não virada.
    Veto: não vender mínima curta rompida com preço acima da média de 20."""
    h = ctx.hoje
    if len(h) < 6 or ctx.t.hour < 10 or ctx.t.hour >= 16:
        return None
    u = h.iloc[-1]
    if u.close < h.low.iloc[-4:-1].min() and u.close > ctx.m15.close.rolling(20).mean().iloc[-1]:
        return _ent(ctx, "venda", ctx.atr15, 1.5 * ctx.atr15)


def n4_comprar_com_alvo_curto(ctx):
    """Comprar o rompimento da máxima da 1ª hora (10:00-11:00) com alvo curto (0,6 ATR15) e stop largo (2 ATR15).
    Armadilha: payoff invertido; a tendência anda em degraus com recuos que batem o stop largo antes de pagar alvo curto,
    e o custo come o alvo. Veto: não comprar com alvo menor que o stop. Ajustada ao dia."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= ctx.t.hour < 11):
        return None
    if h.close.iloc[-1] > h.high.iloc[:4].max():
        return _ent(ctx, "compra", 2 * ctx.atr15, 0.6 * ctx.atr15)


def n5_vender_volume_seco(ctx):
    """Vender entre 14:00 e 17:00 quando a vela tem volume < 70% da média do dia e o preço está acima da abertura,
    esperando exaustão. Stop 1 ATR15, alvo 1,5 ATR15. Armadilha: volume baixo em tendência de alta é ausência de
    vendedores, não exaustão. Veto: volume baixo não é sinal de topo em dia direcional."""
    h = ctx.hoje
    if len(h) < 12 or not (14 <= ctx.t.hour < 17):
        return None
    if h.vol.iloc[-1] < 0.7 * h.vol.mean() and h.close.iloc[-1] > h.open.iloc[0]:
        return _ent(ctx, "venda", ctx.atr15, 1.5 * ctx.atr15)


FAZER = [("Rompimento da faixa da 1ª hora a favor do gap", f1_rompe_faixa_1h, None),
         ("Recuo à média 8 em tendência de alta", f2_recuo_ema, None),
         ("Gap acima da máxima de ontem, continuação", f3_gap_acima_ontem, None),
         ("Nova máxima da tarde", f4_maxima_do_dia_tarde, None),
         ("Impulso das 2 primeiras velas acima da máxima de ontem", f5_impulso_abertura, None)]
NAO_FAZER = [("Vender o gap de alta", n1_vender_gap, None),
             ("Vender a máxima nova do dia", n2_vender_maxima_nova, None),
             ("Vender rompimento de mínima curta acima da média", n3_vender_rompimento_baixo, None),
             ("Comprar rompimento com alvo menor que o stop", n4_comprar_com_alvo_curto, None),
             ("Vender volume seco no fim da tarde", n5_vender_volume_seco, None)]

if __name__ == "__main__":
    for tipo, lst in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, g in lst:
            res = base.resumo(base.simula_dia("2023-11-03", r, g))
            print(f"{tipo:10s} {nome:58s} R$ {res['brl']:9.2f} ops {res['ops']}")
            for x in res["lista"]:
                print("     ", x["lado"], x["ent"], x["sai"], x["motivo"], x["pts"], x["brl"])
