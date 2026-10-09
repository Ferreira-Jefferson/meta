"""Pregão 2023-03-20 (WIN, M15): abertura sem gap (+60 pts), queda lenta de ~1.450 pts de máxima a mínima,
dia de 1.765 pts (~0,9 ATR diário), sob semana e mês de baixa. Regras só com passado."""
import base


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _hhmm(ctx):
    return ctx.t.hour * 60 + ctx.t.minute


def _faixa1h(ctx):
    h = ctx.hoje[ctx.hoje.index.hour < 10]
    return float(h.high.max()), float(h.low.min())


# ---------------- FAZER ----------------
def f_rompe_minima_1h(ctx):
    """Vende o rompimento da mínima da 1ª hora (09-10h) após as 10:15, com fechamento abaixo dela e dia abaixo da abertura.
    Condição: dia de rotação que escorrega para baixo; stop na máxima da 1ª hora (limitado a 590 pts), alvo 1,5x o risco.
    Geral: provavelmente geral (rompimento da faixa inicial a favor do viés do fechamento). Resultado no dia: ver saída."""
    if _hhmm(ctx) < 10 * 60 + 15 or _hhmm(ctx) > 14 * 60 or ctx.ops_hoje:
        return None
    hi, lo = _faixa1h(ctx)
    c = float(ctx.hoje.close.iloc[-1])
    if c < lo and c < float(ctx.hoje.open.iloc[0]):
        stop = min(hi, c + 590)
        return dict(lado="venda", stop=stop, alvo=c - 1.5 * (stop - c), preco=c)


def f_recuo_ema_tendencia(ctx):
    """Vende o recuo até a EMA21 M15 quando EMA9<EMA21<EMA50 e o dia está abaixo da abertura (recuo a favor da tendência).
    Condição: tendência de baixa já estabelecida em M15; máxima da vela toca a EMA21 e fecha abaixo. Stop 1,2 ATR15, alvo 2,5 ATR15.
    Geral: provavelmente geral. Resultado no dia: ver saída."""
    if _hhmm(ctx) < 10 * 60 + 30 or _hhmm(ctx) > 15 * 60:
        return None
    c = ctx.m15.close
    e9, e21, e50 = _ema(c, 9).iloc[-1], _ema(c, 21).iloc[-1], _ema(c, 50).iloc[-1]
    u = ctx.hoje.iloc[-1]
    if e9 < e21 < e50 and u.high >= e21 and u.close < e21 and u.close < ctx.hoje.open.iloc[0]:
        a = ctx.atr15
        return dict(lado="venda", stop=u.close + 1.2 * a, alvo=u.close - 2.5 * a, preco=float(u.close))


def f_falha_alta_inicial(ctx):
    """Reversão em falha: o preço chega à máxima da 1ª hora (ou a fura), não sustenta e uma vela fecha de volta abaixo dela
    com corpo de baixa. Vende. Condição: rompimento/teste sem continuidade (alta rejeitada).
    Stop na máxima do teste, alvo 1,5x o risco abaixo. Geral: provavelmente geral. Resultado no dia: ver saída."""
    if _hhmm(ctx) < 10 * 60 + 15 or _hhmm(ctx) > 13 * 60 or ctx.ops_hoje:
        return None
    hi, lo = _faixa1h(ctx)
    h = ctx.hoje[ctx.hoje.index.hour >= 10]
    u = h.iloc[-1]
    if h.high.max() >= hi - 70 and u.close < hi and u.close < u.open and h.high.max() < hi + 300:
        ps = float(h.high.max()) + 10
        if ps - u.close <= 600:
            return dict(lado="venda", stop=ps, alvo=float(u.close) - 1.5 * (ps - float(u.close)), preco=float(u.close))


def f_rompe_minima_ontem(ctx):
    """Vende o fechamento M15 abaixo da mínima de ontem (nível de ontem) quando o preço está abaixo da média de 5 dias.
    Condição: perda de suporte do dia anterior em mercado que já cai. Stop 1 ATR15 acima do nível, alvo 2,5 ATR15 abaixo.
    Geral: provavelmente geral. Resultado no dia: ver saída."""
    if ctx.ops_hoje or _hhmm(ctx) > 15 * 60 or len(ctx.hoje) < 2:
        return None
    ly = float(ctx.diario.low.iloc[-1])
    c = float(ctx.hoje.close.iloc[-1])
    if c < ly and ctx.hoje.close.iloc[-2] >= ly and c < ctx.diario.close.iloc[-5:].mean():
        a = ctx.atr15
        return dict(lado="venda", stop=ly + a, alvo=c - 2.5 * a, preco=c)


def f_reteste_minima_ontem(ctx):
    """Vende o reteste por baixo da mínima de ontem: o nível foi perdido hoje (já houve fechamento abaixo), o preço volta a tocá-lo
    por baixo (máxima >= nível - 50) e a vela fecha abaixo dele. Condição: suporte virou resistência em dia de baixa.
    Stop 1 ATR15 acima do nível, alvo 1,5x o risco. Geral: provavelmente geral, mas poucas ocorrências. Resultado no dia: ver saída."""
    if ctx.ops_hoje or _hhmm(ctx) < 11 * 60 or _hhmm(ctx) > 15 * 60:
        return None
    ly = float(ctx.diario.low.iloc[-1])
    h = ctx.hoje
    u = h.iloc[-1]
    if (h.close.iloc[:-1] < ly).any() and u.high >= ly - 50 and u.close < ly:
        stop = ly + ctx.atr15
        return dict(lado="venda", stop=stop, alvo=float(u.close) - 1.5 * (stop - float(u.close)), preco=float(u.close))


# ---------------- NÃO FAZER ----------------
def n_compra_queda_1atr(ctx):
    """Compra a queda de 1 ATR15 desde a abertura (pegar faca). Armadilha: dia de baixa lenta e contínua
    (abaixo da abertura, EMAs descendo) - a queda continua. VETO: não comprar pullback com EMA9<EMA21<EMA50. Comportamento geral."""
    if ctx.ops_hoje or _hhmm(ctx) < 10 * 60:
        return None
    c = float(ctx.hoje.close.iloc[-1])
    if float(ctx.hoje.open.iloc[0]) - c >= ctx.atr15:
        return dict(lado="compra", stop=c - 2 * ctx.atr15, alvo=c + 1.5 * ctx.atr15, preco=c)


def n_compra_martelo(ctx):
    """Compra vela de reversão (martelo: pavio inferior > 2x o corpo, fecha em alta) depois das 10:30. Armadilha: em baixa lenta o pavio
    inferior é só absorção momentânea e a queda segue. VETO: não comprar vela isolada de reversão com EMA9<EMA21<EMA50 em M15."""
    if ctx.ops_hoje or _hhmm(ctx) < 10 * 60 + 30 or _hhmm(ctx) > 14 * 60:
        return None
    u = ctx.hoje.iloc[-1]
    corpo = abs(u.close - u.open)
    if u.close > u.open and (u.open - u.low) > 2 * max(corpo, 20):
        return dict(lado="compra", stop=float(u.low) - 150, alvo=float(u.close) + 450, preco=float(u.close))


def n_compra_minima_dia_falha(ctx):
    """Compra a defesa da mínima do dia (vela toca a mínima do dia e fecha acima do meio). Armadilha: em tendência de baixa
    a mínima nova é só mais uma etapa. VETO: não comprar suporte intradiário se o dia está abaixo da abertura e da mínima de ontem."""
    if ctx.ops_hoje or _hhmm(ctx) < 11 * 60:
        return None
    h = ctx.hoje
    u = h.iloc[-1]
    if u.low <= h.low.min() and u.close > (u.high + u.low) / 2:
        return dict(lado="compra", stop=u.low - 120, alvo=u.close + 400, preco=float(u.close))


def n_vende_minima_tarde(ctx):
    """Vende após 14:30 na mínima do dia esperando continuação. Armadilha: fim de tarde em dia que já andou - movimento esgotado,
    volume seca, preço fica de lado. VETO: não vender mínima nova depois das 14h quando o dia já percorreu mais de 0,8 ATR diário."""
    if ctx.ops_hoje or _hhmm(ctx) < 14 * 60 + 30 or _hhmm(ctx) > 16 * 60:
        return None
    h = ctx.hoje
    c = float(h.close.iloc[-1])
    if c <= h.close.min() + 1:
        return dict(lado="venda", stop=c + 300, alvo=c - 600, preco=c)


def n_compra_abertura(ctx):
    """Compra a 1ª vela M15 fechada em alta na abertura (segue o impulso inicial). Armadilha: abertura sem gap sobe um pouco e devolve;
    o impulso da 1ª vela não tem continuidade num dia de baixa. VETO: não comprar a 1ª vela do dia quando o dia anterior fechou na mínima e a tendência diária é de baixa."""
    if ctx.ops_hoje or _hhmm(ctx) > 9 * 60 + 15:
        return None
    u = ctx.hoje.iloc[-1]
    if u.close > u.open:
        c = float(u.close)
        return dict(lado="compra", stop=c - 150, alvo=c + 450, preco=c)


FAZER = [("Rompe mínima da 1ª hora (venda)", f_rompe_minima_1h, None),
         ("Recuo à EMA21 em baixa (venda)", f_recuo_ema_tendencia, None),
         ("Falha da alta inicial (venda)", f_falha_alta_inicial, None),
         ("Perde mínima de ontem (venda)", f_rompe_minima_ontem, None),
         ("Reteste da mínima de ontem (venda)", f_reteste_minima_ontem, None)]
NAO_FAZER = [("Comprar queda de 1 ATR", n_compra_queda_1atr, None),
             ("Comprar martelo (reversão)", n_compra_martelo, None),
             ("Comprar defesa da mínima do dia", n_compra_minima_dia_falha, None),
             ("Vender mínima nova após 14:30", n_vende_minima_tarde, None),
             ("Comprar a 1ª vela da abertura", n_compra_abertura, None)]

if __name__ == "__main__":
    for grupo, lista in (("FAZER", FAZER), ("NÃO FAZER", NAO_FAZER)):
        for nome, r, g in lista:
            res = base.resumo(base.simula_dia("2023-03-20", r, g))
            print(f"{grupo:9s} | {nome:38s} | R$ {res['brl']:8.2f} | ops {res['ops']}")
            for x in res["lista"]:
                print("     ", x)
