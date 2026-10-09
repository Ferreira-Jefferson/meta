"""Pregão 2022-11-29 (WIN): gap de alta pequeno, abertura lateral, alta firme 10h15->13h30 (~3.000 pts), depois deriva para baixo.

Todas as regras usam só o passado do instante da decisão (ctx). Tudo relativo: ATR, 1ª hora, abertura, fechamento de ontem, VWAP.
"""
MAXRISCO = 600.0  # pts (6% de R$2.000 com 1 contrato)


def _h(ctx):
    return ctx.t.hour * 60 + ctx.t.minute


def _vwap(ctx):
    h = ctx.hoje
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).sum() / h.vol.sum())


def _prim_hora(ctx):
    h = ctx.hoje.iloc[:4]
    return float(h.high.max()), float(h.low.min())


def _stop_c(preco, nivel):
    return max(nivel, preco - MAXRISCO)


def _stop_v(preco, nivel):
    return min(nivel, preco + MAXRISCO)


def _trail_atr(k):
    """Gerir: stop acompanha a mínima/máxima das últimas 3 velas M15 menos/mais k*ATR (só a favor)."""
    def g(ctx, pos):
        u = ctx.hoje.iloc[-3:]
        if pos["lado"] == "compra":
            return float(u.low.min() - k * ctx.atr15)
        return float(u.high.max() + k * ctx.atr15)
    return g


# ---------------- FAZER ----------------
def f1_rompe_1a_hora(ctx):
    """Rompimento da máxima da 1ª hora (09:00-10:00), após 10:00, com fechamento acima e volume da vela >= média do dia.
    Compra, stop na mínima da 1ª hora (limitado a 600 pts), sem alvo, trailing por mínima de 3 velas.
    Condição: dia que sai da lateral da abertura com participação. Natureza: seguir rompimento. Provavelmente geral
    (rompimento de faixa de abertura com volume é fundamento comum), mas só 1 entrada/dia."""
    if len(ctx.hoje) < 5 or ctx.ops_hoje: return None
    mx, mn = _prim_hora(ctx)
    u = ctx.hoje.iloc[-1]
    if u.close > mx and u.vol >= ctx.hoje.vol.mean() and _h(ctx) < 14 * 60:
        p = float(u.close) + 20  # limite agressiva acima do fechamento: enche na hora (custa 20 pts)
        return dict(lado="compra", preco=p, stop=_stop_c(p, mn), alvo=None, contratos=1)


def f2_recuo_tendencia(ctx):
    """Recuo a favor da tendência: preço acima da VWAP e >= 1,8 ATR15 acima da abertura do dia (tendência de alta
    estabelecida); compra quando uma vela recua (fecha abaixo da anterior) e a mínima toca a média das últimas 4 fechadas. Stop 0,5 ATR15
    abaixo da mínima do recuo; alvo 1,5x o risco. Condição: tendência direcional já estabelecida, antes das 14h.
    Natureza: pullback a favor. Provavelmente geral, mas depende de o dia ser direcional (~20% dos dias)."""
    h = ctx.hoje
    if len(h) < 8 or _h(ctx) > 14 * 60: return None
    u, a = h.iloc[-1], h.iloc[-2]
    ma = h.close.iloc[-4:].mean()
    if u.close > _vwap(ctx) and (u.close - h.open.iloc[0]) > 1.8 * ctx.atr15 and u.close < a.close and u.low <= ma:
        p = float(u.close)
        st = _stop_c(p, float(u.low - 0.5 * ctx.atr15))
        return dict(lado="compra", preco=p, stop=st, alvo=p + 1.5 * (p - st), contratos=1)


def f3_gap_sustentado(ctx):
    """Gap de alta (abertura > fechamento de ontem + 0,1 ATRd) que NÃO foi preenchido: depois de 10:45 o preço segue
    acima da abertura e a mínima do dia fica acima do fechamento de ontem; rompe a máxima das últimas 4 velas.
    Compra, stop na abertura do dia (limitado), alvo 1 ATRd. Condição: gap que se sustenta vira fluxo comprador.
    Natureza: gap. Ajustada ao dia (um só gap pequeno de alta; não testada em gap de baixa)."""
    h = ctx.hoje
    if len(h) < 8 or ctx.ops_hoje: return None
    gap = float(h.open.iloc[0] - ctx.diario.close.iloc[-1])
    if gap < 0.1 * ctx.atrd: return None
    u = h.iloc[-1]
    if _h(ctx) >= 10 * 60 + 45 and h.low.min() > ctx.diario.close.iloc[-1] and u.close > h.high.iloc[-5:-1].max() \
            and u.close > h.open.iloc[0]:
        p = float(u.close) + 20  # limite agressiva acima do fechamento
        return dict(lado="compra", preco=p, stop=_stop_c(p, float(h.open.iloc[0])), alvo=p + ctx.atrd, contratos=1)


def f4_falha_de_queda(ctx):
    """Reversão em falha: a vela perde a mínima da 1ª hora (varre stops) mas FECHA de volta acima dela, no terço superior da vela (rejeição). Compra, stop abaixo
    da mínima da varredura, alvo 2x o risco. Condição: rompimento de baixa sem continuação (armadilha de vendedores), antes
    das 12h. Natureza: reversão em falha (spring). Provavelmente geral."""
    h = ctx.hoje
    if len(h) < 5 or _h(ctx) > 12 * 60: return None
    mn = float(h.low.iloc[:4].min())
    u = h.iloc[-1]
    if u.low < mn and u.close > mn and (u.close - u.low) > 0.6 * (u.high - u.low):
        p = float(u.close)
        st = _stop_c(p, float(u.low - 20))
        return dict(lado="compra", preco=p, stop=st, alvo=p + 2 * (p - st), contratos=1)


def f5_quebra_fim_da_tarde(ctx):
    """Venda na quebra do fim da tarde: depois de 16:00, a vela fecha abaixo da mínima das 6 velas anteriores (1h30 de
    faixa) e abaixo da média das últimas 8 fechadas, com a máxima do dia > ATRd/3 acima. Venda (limite agressiva 20 pts
    abaixo do fechamento), stop na máxima das 3 últimas velas (limitado a 600), trailing.
    Condição: exaustão após alta forte; o preço devolve a perna. Natureza: exaustão / quebra de faixa.
    Ajustada ao dia (poucos dias dão a mesma sequência)."""
    h = ctx.hoje
    if _h(ctx) < 16 * 60 or ctx.ops_hoje or len(h) < 8: return None
    u = h.iloc[-1]
    if u.close < h.low.iloc[-7:-1].min() and u.close < h.close.iloc[-8:].mean() and (h.high.max() - u.close) > ctx.atrd / 3:
        p = float(u.close) - 20
        return dict(lado="venda", preco=p, stop=_stop_v(p, float(h.high.iloc[-3:].max())), alvo=None, contratos=1)


# ---------------- NAO FAZER ----------------
def n1_vende_quebra_cedo(ctx):
    """Vender o rompimento da mínima das velas anteriores nos primeiros 90 min (antes das 10:30). Stop na máxima do dia, alvo 1,5R.
    Armadilha: abertura em lateral estreita após gap a favor do contrário; a quebra de mínima é varredura e o preço sobe.
    Veto: não vender quebra de mínima na abertura se o dia abriu em gap de alta e a faixa é < ATRd/3."""
    h = ctx.hoje
    if len(h) < 3 or _h(ctx) > 10 * 60 + 30 or ctx.ops_hoje: return None
    u = h.iloc[-1]
    if u.close < h.low.iloc[:-1].min():
        p = float(u.close)
        st = _stop_v(p, float(h.high.max()))
        return dict(lado="venda", preco=p, stop=st, alvo=p - 1.5 * (st - p), contratos=1)


def n2_compra_maxima_nova_tarde(ctx):
    """Comprar a máxima nova do dia depois das 13:00. Stop 0,75 ATR15, sem alvo. Armadilha: topo da manhã após alta de ~1 ATRd
    em que o volume já cai; o rompimento tardio sem volume devolve tudo. Veto: não comprar máxima nova depois das 13h se o
    volume da vela é menor que a média do dia."""
    h = ctx.hoje
    if _h(ctx) < 13 * 60 or len(h) < 6: return None
    u = h.iloc[-1]
    if u.high >= h.high.max() and u.close > h.close.iloc[-2]:
        p = float(u.close)
        return dict(lado="compra", preco=p, stop=_stop_c(p, p - 0.75 * ctx.atr15), alvo=None, contratos=1)


def n3_vende_esticada(ctx):
    """Vender a esticada: preço > média de 8 velas + 1 ATR15 (contra a tendência). Stop 1 ATR15 acima, alvo na média.
    Armadilha: dia de continuação; a esticada vira tendência (no WIN M15 a continuação domina a reversão).
    Veto: não vender esticada quando a eficiência direcional intradiária do dia é alta (> 0,3)."""
    h = ctx.hoje
    if len(h) < 8 or _h(ctx) > 14 * 60: return None
    ma = h.close.iloc[-8:].mean()
    u = h.iloc[-1]
    if u.close > ma + 1.0 * ctx.atr15:
        p = float(u.close)
        return dict(lado="venda", preco=p, stop=p + ctx.atr15, alvo=float(ma), contratos=1)


def n4_compra_recuo_apos15h(ctx):
    """Comprar vela de alta acima da VWAP depois das 15:00, com o dia já em alta. Stop 0,75 ATR15, alvo 1,1 ATR15. Armadilha:
    depois das 15h os sinais pioram; a tendência da manhã se exaure e o fluxo vira venda.
    Veto: não comprar tendência depois das 15h se o preço já devolveu parte da perna do dia."""
    h = ctx.hoje
    if _h(ctx) < 15 * 60 or ctx.ops_hoje or len(h) < 8: return None
    u, a = h.iloc[-1], h.iloc[-2]
    if u.close > h.open.iloc[0] and u.close > a.close and u.close > _vwap(ctx):
        p = float(u.close)
        return dict(lado="compra", preco=p, stop=_stop_c(p, p - 0.75 * ctx.atr15), alvo=p + 1.1 * ctx.atr15, contratos=1)


def n5_vende_gap(ctx):
    """Vender o gap de alta esperando preencher o fechamento de ontem (entra após a 1ª vela). Stop 400 pts acima, alvo no
    fechamento de ontem. Armadilha: gap pequeno (< 0,25 ATRd) com fluxo comprador; preencher exige uma perna maior que a que
    o dia dá. Veto: não vender gap de alta se a 1ª vela fechou acima da abertura."""
    h = ctx.hoje
    if len(h) != 1 or ctx.ops_hoje: return None
    gap = float(h.open.iloc[0] - ctx.diario.close.iloc[-1])
    if gap > 0.1 * ctx.atrd:
        p = float(h.close.iloc[-1])
        return dict(lado="venda", preco=p, stop=p + 400, alvo=float(ctx.diario.close.iloc[-1]), contratos=1)


FAZER = [
    ("rompe_1a_hora_com_volume", f1_rompe_1a_hora, _trail_atr(0.5)),
    ("recuo_a_favor_tendencia", f2_recuo_tendencia, None),
    ("gap_de_alta_sustentado", f3_gap_sustentado, None),
    ("falha_de_queda_1a_hora", f4_falha_de_queda, None),
    ("quebra_fim_da_tarde_venda", f5_quebra_fim_da_tarde, _trail_atr(0.5)),
]
NAO_FAZER = [
    ("vender_quebra_minima_cedo", n1_vende_quebra_cedo, None),
    ("comprar_maxima_nova_tarde", n2_compra_maxima_nova_tarde, None),
    ("vender_esticada_contra", n3_vende_esticada, None),
    ("comprar_recuo_apos_15h", n4_compra_recuo_apos15h, None),
    ("vender_gap_de_alta", n5_vende_gap, None),
]

DIA = "2022-11-29"

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import base
    for grupo, lista in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, g in lista:
            res = base.resumo(base.simula_dia(DIA, r, g))
            print(f"{grupo:9s} {nome:30s} R$ {res['brl']:9.2f}  ops {res['ops']}  pts {res['pts']}")
            for x in res["lista"]:
                print("    ", x["lado"], x["sinal"], x["ent"], x["preco"], "stop", x["stop"], "->", x["sai"], x["preco_sai"], x["motivo"], x["brl"])
