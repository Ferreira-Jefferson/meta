"""Ciclo 1 - dia 2023-12-18 (WIN M15, tipo ruim, ef 0,113): abertura 132.450, +75 pts sobre o fechamento de ontem,
deriva lenta para cima (132.450 -> 133.490, fecha 133.175). O robo vendeu a falha da maxima da 1a hora as 11:00
(132.805) e levou stop 94 min depois (133.094): -R$59,86.
Regras puras: so usam o passado do instante da decisao. Execucao e risco como em INSTRUCOES.md."""
import pandas as pd

H = pd.Timedelta(hours=1)
CAP = 590.0  # risco maximo 6% do caixa


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _vwap(h):
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).cumsum().iloc[-1] / h.vol.cumsum().iloc[-1])


def _prim_hora(h):
    return h[h.index < h.index[0] + H]


def _ord(ctx, lado, stop_atr, alvo_atr):
    p = float(ctx.hoje.close.iloc[-1]); a = ctx.atr15
    stop_atr = min(stop_atr, CAP / a)
    s = 1 if lado == "compra" else -1
    return dict(lado=lado, preco=p, stop=p - s * stop_atr * a, alvo=(p + s * alvo_atr * a) if alvo_atr else None, contratos=1)


def _f2_sinal(ctx):
    """Gatilho da F2 original (r_2025_06_04): vela rompe a maxima da 1a hora e fecha abaixo, pavio superior > 50%."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= ctx.t.hour < 14): return False
    topo = _prim_hora(h).high.max(); u = h.iloc[-1]
    return bool(u.high > topo and u.close < topo and (u.high - max(u.open, u.close)) > 0.5 * (u.high - u.low))


# =============== AJUSTES a regra existente (nova versao da funcao) ===============
def f2_alvo_1atr(ctx):
    """AJUSTE de 2025_06_04:F2 falha na maxima da 1a hora. Mesmo gatilho, alvo 1 ATR15 (em vez de 3), stop 1,5 ATR15.
    Logica: falha de rompimento em dia de rotacao devolve ~1 ATR, nao 3; alvo 3 ATR nunca e atingido em rotacao.
    Condicao: dia sem tendencia (rotacao). Natureza: ajuste de saida (alvo)."""
    if _f2_sinal(ctx):
        return _ord(ctx, "venda", 1.5, 1.0)


def f2_trailing(ctx):
    """AJUSTE de 2025_06_04:F2. Mesmo gatilho/stop/alvo, mais o `gerir` f2_gerir_trailing (stop segue o menor
    fechamento desde a entrada + 1 ATR15). Natureza: gestao de saida. Condicao: falha que da so um pedaco e volta."""
    if _f2_sinal(ctx):
        return _ord(ctx, "venda", 1.5, 3.0)


def f2_gerir_trailing(ctx, pos):
    h = ctx.hoje; h = h[h.index >= pos["t_ent"].floor("15min")]
    return float(h.close.min()) + 1.0 * ctx.atr15


# =============== FAZER novas ===============
def f_compra_rejeicao_de_minima(ctx):
    """Compra quando a vela faz (ate 0,3 ATR15 de) a minima das 3 velas anteriores, fecha no terco superior da sua faixa, em alta, acima da
    abertura do dia, com faixa > 0,8 ATR15. Condicao: queda recente rejeitada (martelo) em dia que negocia acima da abertura;
    entre 10:00 e 14:00. Natureza: reversao em rejeicao a favor da deriva. Provavelmente geral. Stop 1,5 ATR15, alvo 2 ATR15."""
    h = ctx.hoje
    if len(h) < 6 or not (10 <= ctx.t.hour < 14): return None
    u = h.iloc[-1]; rng = u.high - u.low
    if rng <= 0: return None
    if (u.low <= h.iloc[-4:-1].low.min() + 0.3 * ctx.atr15 and u.close >= u.low + 0.66 * rng and u.close > u.open
            and u.close > h.open.iloc[0] and rng > 0.8 * ctx.atr15):
        return _ord(ctx, "compra", 1.5, 2.0)


def f_compra_recuo_vwap(ctx):
    """Compra o recuo ate o VWAP do dia em dia que ja negocia acima da abertura: a minima da vela toca/cruza o VWAP e a vela
    fecha acima dele, em alta, com EMA20 M15 subindo. Condicao: tendencia de alta suave; VWAP age como suporte.
    Natureza: recuo a favor a um nivel de valor (VWAP). Entre 10:00 e 15:00. Stop 1,5 ATR15, alvo 2 ATR15. Geral."""
    h = ctx.hoje
    if len(h) < 8 or not (10 <= ctx.t.hour < 15): return None
    vw = _vwap(h); u = h.iloc[-1]; e = _ema(ctx.m15.close, 20)
    if u.low <= vw and u.close > vw and u.close > u.open and u.close > h.open.iloc[0] and e.iloc[-1] > e.iloc[-4]:
        return _ord(ctx, "compra", 1.5, 2.0)


def f_compra_rompe_maxima_manha_tarde(ctx):
    """Compra o fechamento M15 acima da maxima de 09:00-12:00 depois das 13:00, com fechamento acima do VWAP.
    Condicao: a faixa da manha (rotacao) e resolvida para cima pelo preco na tarde. Natureza: rompimento da faixa da manha.
    Stop 1,5 ATR15, alvo 2 ATR15. Provavelmente geral, poucas ocorrencias."""
    h = ctx.hoje
    if not (13 <= ctx.t.hour < 15) or len(h) < 12: return None
    man = h[h.index.hour < 12]; u = h.iloc[-1]
    if u.close > man.high.max() and h.close.iloc[-2] <= man.high.max() and u.close > _vwap(h):
        return _ord(ctx, "compra", 1.5, 2.0)


# =============== NAO FAZER (vetos) ===============
def n_vender_contra_alinhamento_de_alta(ctx):
    """NAO FAZER: vender com EMA9 > EMA20 > EMA50 em M15 e fechamento acima da EMA20, entre 10:00 e 15:00.
    Armadilha: venda de falha/exaustao contra medias alinhadas para cima (tendencia de alta suave, ate de baixa volatilidade);
    a falha nao se completa e o stop de 1,5 ATR15 e varrido pela deriva."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= ctx.t.hour < 15): return None
    c = ctx.m15.close; e9, e20, e50 = _ema(c, 9).iloc[-1], _ema(c, 20).iloc[-1], _ema(c, 50).iloc[-1]
    if e9 > e20 > e50 and c.iloc[-1] > e20:
        return _ord(ctx, "venda", 1.5, 3.0)


def n_vender_em_semana_de_alta_acima_da_abertura(ctx):
    """NAO FAZER: vender com o fechamento de ontem acima da media dos 10 fechamentos diarios anteriores (contexto de alta
    de semanas) e o preco >= 1 ATR15 acima da abertura do dia. Armadilha: contrarian dentro de contexto semanal comprador,
    com o dia ja deslocado a favor da alta; as falhas de topo nao pegam. 10:00-15:00."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= ctx.t.hour < 15): return None
    if ctx.diario.close.iloc[-1] > ctx.diario.close.iloc[-10:].mean() and h.close.iloc[-1] >= h.open.iloc[0] + ctx.atr15:
        return _ord(ctx, "venda", 1.5, 3.0)


def n_vender_no_vwap_com_media_subindo(ctx):
    """NAO FAZER: vender com o fechamento a menos de 0,25 ATR15 do VWAP do dia (preco no 'valor justo') com EMA20 M15 subindo
    e o dia acima da abertura. Armadilha: no VWAP o preco nao esta esticado; a venda nao tem o que reverter. 10:00-15:00."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= ctx.t.hour < 15): return None
    e = _ema(ctx.m15.close, 20)
    if abs(h.close.iloc[-1] - _vwap(h)) < 0.25 * ctx.atr15 and e.iloc[-1] > e.iloc[-4] and h.close.iloc[-1] > h.open.iloc[0]:
        return _ord(ctx, "venda", 1.5, 3.0)


def n_vender_rompe_minima_hora_anterior(ctx):
    """NAO FAZER: vender o fechamento abaixo da minima das 4 velas anteriores entre 11:00 e 12:00, com o dia acima da abertura.
    Armadilha: falso rompimento para baixo da rotacao de fim de manha em dia que deriva para cima; o preco devolve."""
    h = ctx.hoje
    if len(h) < 6 or not (11 <= ctx.t.hour < 12): return None
    if h.close.iloc[-1] < h.low.iloc[-5:-1].min() and h.close.iloc[-1] > h.open.iloc[0]:
        return _ord(ctx, "venda", 1.5, 1.5)


def n_comprar_alta_esticada_tarde(ctx):
    """NAO FAZER: comprar o fechamento depois das 14:00 quando o preco ja subiu mais de 2 ATR15 nas ultimas 6 velas.
    Armadilha: compra esticada no fim da alta tardia; falta fôlego e o dia devolve ate o fechamento. Natureza: exaustao."""
    h = ctx.hoje
    if len(h) < 8 or not (14 <= ctx.t.hour < 16): return None
    if h.close.iloc[-1] - h.close.iloc[-7] > 2.0 * ctx.atr15:
        return _ord(ctx, "compra", 1.5, 1.5)


FAZER = [("F2 alvo 1 ATR (ajuste)", f2_alvo_1atr, None), ("F2 trailing (ajuste)", f2_trailing, f2_gerir_trailing),
         ("compra rejeicao de minima", f_compra_rejeicao_de_minima, None), ("compra recuo ao VWAP", f_compra_recuo_vwap, None),
         ("compra rompe maxima da manha na tarde", f_compra_rompe_maxima_manha_tarde, None)]
NAO_FAZER = [("vender contra medias alinhadas de alta", n_vender_contra_alinhamento_de_alta, None),
             ("vender em semana de alta acima da abertura", n_vender_em_semana_de_alta_acima_da_abertura, None),
             ("vender no VWAP com media subindo", n_vender_no_vwap_com_media_subindo, None),
             ("vender rompe minima da hora anterior", n_vender_rompe_minima_hora_anterior, None),
             ("comprar alta esticada na tarde", n_comprar_alta_esticada_tarde, None)]

if __name__ == "__main__":
    import base
    DIA = "2023-12-18"
    for tipo, lst in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for n, r, g in lst:
            res = base.resumo(base.simula_dia(DIA, r, g))
            print(tipo, n, "R$", res["brl"], "ops", res["ops"], [(x["sinal"], x["motivo"], x["brl"]) for x in res["lista"]])
