"""Ciclo 2 - dia 2023-10-17 (WIN M15, tipo ruim, ef 0,041). Abre em gap de baixa (-345 pts = 0,19 ATRd sobre 116.485),
cai ate 115.560 (10:30), faz um V ate 116.950 (12:45), devolve tudo ate 115.560 (15:30) e fica lateral ate 115.780.
O robo v2 fez 3 compras e 3 stops: -R$131,14 (gap_fade 09:30 -70, gap_fade 09:45 -22, recuo_a_favor 13:15 -39).
Regras puras: so usam o passado do instante da decisao. Execucao e risco como em INSTRUCOES.md."""
import pandas as pd

CAP = 590.0  # risco maximo 6% do caixa


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _vwap(h):
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).cumsum().iloc[-1] / h.vol.cumsum().iloc[-1])


def _prim_hora(h):
    return h[h.index < h.index[0] + pd.Timedelta(hours=1)]


def _hh(ctx):
    return ctx.t.hour + ctx.t.minute / 60


def _ord(ctx, lado, stop_atr, alvo_atr):
    p = float(ctx.hoje.close.iloc[-1]); a = ctx.atr15
    stop_atr = min(stop_atr, CAP / a)
    s = 1 if lado == "compra" else -1
    return dict(lado=lado, preco=p, stop=p - s * stop_atr * a, alvo=(p + s * alvo_atr * a) if alvo_atr else None, contratos=1)


# ============================ FAZER (5) ============================
def f1_compra_rompe_faixa_apos_queda_esticada(ctx):
    """FAZER (reversao confirmada de exaustao): entre 10:00 e 13:00, o preco ja caiu >= 2 ATR15 da abertura do dia
    ate a minima do dia e a vela fecha acima da maxima das 4 velas anteriores, e a vela anterior ainda nao tinha rompido (rompimento novo). Compra; stop 1,5 ATR15, alvo 1,5 ATR15.
    Condicao: queda esticada em 1-2 h seguida de saida da faixa para cima (capitulacao + confirmacao).
    Natureza: reversao de exaustao confirmada. Provavelmente geral (poucas ocorrencias)."""
    h = ctx.hoje
    if len(h) < 6 or not (10 <= _hh(ctx) < 13): return None
    if h.open.iloc[0] - h.low.min() < 2.0 * ctx.atr15: return None
    if h.close.iloc[-1] > h.high.iloc[-5:-1].max() and h.close.iloc[-2] <= h.high.iloc[-6:-2].max():
        return _ord(ctx, "compra", 1.5, 1.5)


def f2_compra_rompe_maxima_1a_hora_alvo_1atr(ctx):
    """FAZER (rompimento): entre 10:15 e 13:00 o fechamento passa acima da maxima da 1a hora (a anterior fechava abaixo/igual),
    sem exigir corpo. Stop 1,5 ATR15, alvo 1 ATR15 (em rotacao o rompimento rende ~1 ATR). Condicao: o dia devolveu a
    queda e retoma a faixa da 1a hora para cima. Natureza: rompimento da faixa da 1a hora, alvo curto. Provavelmente geral."""
    h = ctx.hoje
    if len(h) < 5 or not (10.25 <= _hh(ctx) < 13): return None
    topo = _prim_hora(h).high.max()
    if h.close.iloc[-1] > topo and h.close.iloc[-2] <= topo:
        return _ord(ctx, "compra", 1.5, 1.0)


def f3_vende_falha_maxima_do_dia_tarde(ctx):
    """FAZER (falha em extremo do dia): entre 13:00 e 15:00 a vela faz maxima NOVA do dia mas fecha abaixo da minima da
    vela anterior (engolfo de baixa no topo). Venda; stop 1,5 ATR15, alvo 1 ATR15. Condicao: rali de varias horas que
    perde forca e falha no topo. Natureza: reversao em falha. Provavelmente geral."""
    h = ctx.hoje
    if len(h) < 8 or not (13 <= _hh(ctx) < 15): return None
    u, a = h.iloc[-1], h.iloc[-2]
    if u.high > h.high.iloc[:-1].max() and u.close < a.low:
        return _ord(ctx, "venda", 1.5, 1.0)


def f4_gap_fade_confirmado(ctx):
    """AJUSTE de 2024_06_18:gap_fade_fechamento (nova versao da funcao). Mesmo gap (>= 0,15 ATRd, dentro da faixa de ontem,
    alvo = fechamento de ontem, stop = extremo do dia -60 limitado a 590 pts), mas (a) a janela vai de 09:15 ate 12:00 e
    (b) so entra quando o fade ja comecou: a vela fecha do lado do fade da abertura do dia (acima dela no gap de baixa) e alem
    do extremo das 2 velas anteriores. Logica: o original compra a faca caindo 15 min depois da abertura (2 stops em 5 min neste
    dia); a confirmacao espera o preco recuperar a abertura. Natureza: ajuste de entrada (confirmacao). Provavelmente geral."""
    h = ctx.hoje
    if not (9.25 <= _hh(ctx) <= 12) or len(h) < 4: return None
    ont = ctx.diario.iloc[-1]; ab = h.open.iloc[0]; gap = ab - ont.close
    if abs(gap) < 0.15 * ctx.atrd or not (ont.low < ab < ont.high): return None
    px = float(h.close.iloc[-1])
    if gap < 0 and px < ont.close - 100 and px > ab and px > h.high.iloc[-3:-1].max():
        stop = max(h.low.min() - 60, px - 590)
        return dict(lado="compra", stop=stop, alvo=ont.close, preco=px, contratos=1)
    if gap > 0 and px > ont.close + 100 and px < ab and px < h.low.iloc[-3:-1].min():
        stop = min(h.high.max() + 60, px + 590)
        return dict(lado="venda", stop=stop, alvo=ont.close, preco=px, contratos=1)


def f5_vende_quebra_faixa_tarde(ctx):
    """FAZER (quebra de lateral): depois das 14:00 o fechamento fica abaixo da minima das 4 velas anteriores, com o preco
    abaixo da EMA9 M15 e o dia tendo estado acima da abertura em algum momento. Venda; stop 1,5 ATR15, alvo 1 ATR15.
    Condicao: lateralizacao do meio do dia resolvida para baixo. Natureza: rompimento de faixa da tarde. Geral."""
    h = ctx.hoje
    if len(h) < 8 or not (14 <= _hh(ctx) < 16): return None
    if h.close.iloc[-1] < h.low.iloc[-5:-1].min() and h.close.iloc[-1] < _ema(ctx.m15.close, 9).iloc[-1] and h.high.max() > h.open.iloc[0]:
        return _ord(ctx, "venda", 1.5, 1.0)


# ============================ NAO FAZER (5, vetos) ============================
def n1_comprar_logo_apos_vela_de_queda_forte(ctx):
    """NAO FAZER: comprar entre 09:15 e 10:30 na vela seguinte a uma queda forte (corpo >= 1,5 ATR15, fechamento no
    20% inferior da faixa, volume >= 1,3x a media das 10 velas anteriores). Armadilha: faca caindo; a queda de abertura
    continua. Condicao de mercado: pressao vendedora ativa nos primeiros 90 min."""
    h = ctx.hoje
    if len(h) < 2 or not (9.25 <= _hh(ctx) <= 10.5): return None
    u = h.iloc[-1]; rng = u.high - u.low
    vol_med = ctx.m15.vol.iloc[-11:-1].mean()
    if rng > 0 and u.open - u.close >= 1.5 * ctx.atr15 and u.close <= u.low + 0.2 * rng and u.vol >= 1.3 * vol_med:
        return _ord(ctx, "compra", 1.5, 1.0)


def n2_comprar_em_compressao_de_volume_tarde(ctx):
    """NAO FAZER: comprar entre 13:00 e 15:00 quando o volume das 3 ultimas velas e < 50% do volume medio do dia e a faixa
    media dessas velas < 0,7 ATR15. Armadilha: lateral sem fluxo; a compra nao tem combustivel e o stop e varrido pela
    devolucao. Condicao de mercado: mercado sem participacao, depois de um rali de manha."""
    h = ctx.hoje
    if len(h) < 12 or not (13 <= _hh(ctx) < 15): return None
    v3 = h.vol.iloc[-3:].mean(); r3 = (h.high - h.low).iloc[-3:].mean()
    if v3 < 0.5 * h.vol.mean() and r3 < 0.7 * ctx.atr15:
        return _ord(ctx, "compra", 1.5, 1.0)


def n3_vender_no_fundo_apos_queda_esticada(ctx):
    """NAO FAZER: vender entre 10:00 e 11:15 com o preco >= 2 ATR15 abaixo da abertura do dia e a menos de 0,5 ATR15 da
    minima do dia. Armadilha: venda de esgotamento; sem espaco para continuar, rebote. Condicao: queda ja esticada."""
    h = ctx.hoje
    if len(h) < 4 or not (10 <= _hh(ctx) <= 11.25): return None
    p = h.close.iloc[-1]
    if h.open.iloc[0] - p >= 2.0 * ctx.atr15 and p - h.low.min() <= 0.5 * ctx.atr15:
        return _ord(ctx, "venda", 1.5, 1.0)


def n4_comprar_esticado_acima_do_vwap_depois_do_meio_dia(ctx):
    """NAO FAZER: comprar depois das 12:00 com o fechamento >= 2,5 ATR15 acima do VWAP do dia (esticado) e o volume das 3 ultimas velas < 70% da media do dia (esticado sem fluxo).
    Armadilha: compra de topo de V; o preco volta ao valor justo. Condicao: afastamento do VWAP."""
    h = ctx.hoje
    if len(h) < 12 or not (12 <= _hh(ctx) < 16): return None
    if h.close.iloc[-1] - _vwap(h) >= 2.5 * ctx.atr15 and h.vol.iloc[-3:].mean() < 0.7 * h.vol.mean():
        return _ord(ctx, "compra", 1.5, 1.0)


def n5_comprar_apos_perder_ema9_com_dia_devolvendo(ctx):
    """NAO FAZER: comprar entre 13:30 e 16:00 quando o fechamento esta abaixo da EMA9 M15 e a vela fecha abaixo da anterior,
    com a maxima do dia a >= 2 ATR15 do preco (rali devolvendo). Armadilha: comprar o recuo quando o recuo e o inicio da
    reversao do dia. Condicao: devolucao do rali do meio do dia."""
    h = ctx.hoje
    if len(h) < 10 or not (13.5 <= _hh(ctx) < 16): return None
    c = ctx.m15.close
    if c.iloc[-1] < _ema(c, 9).iloc[-1] and c.iloc[-1] < c.iloc[-2] and h.high.max() - c.iloc[-1] >= 2.0 * ctx.atr15:
        return _ord(ctx, "compra", 1.5, 1.0)


FAZER = [("c2a F1 compra rompe faixa apos queda esticada", f1_compra_rompe_faixa_apos_queda_esticada, None),
         ("c2a F2 compra rompe maxima 1a hora alvo 1 ATR", f2_compra_rompe_maxima_1a_hora_alvo_1atr, None),
         ("c2a F3 vende falha da maxima do dia na tarde", f3_vende_falha_maxima_do_dia_tarde, None),
         ("c2a F4 gap_fade confirmado (ajuste)", f4_gap_fade_confirmado, None),
         ("c2a F5 vende quebra de faixa da tarde", f5_vende_quebra_faixa_tarde, None)]
NAO_FAZER = [("c2a N1 comprar apos vela de queda forte", n1_comprar_logo_apos_vela_de_queda_forte, None),
             ("c2a N2 comprar em compressao de volume na tarde", n2_comprar_em_compressao_de_volume_tarde, None),
             ("c2a N3 vender no fundo apos queda esticada", n3_vender_no_fundo_apos_queda_esticada, None),
             ("c2a N4 comprar esticado acima do VWAP", n4_comprar_esticado_acima_do_vwap_depois_do_meio_dia, None),
             ("c2a N5 comprar com rali devolvendo", n5_comprar_apos_perder_ema9_com_dia_devolvendo, None)]

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import base
    DIA = "2023-10-17"
    for tipo, lst in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for n, r, g in lst:
            res = base.resumo(base.simula_dia(DIA, r, g))
            print(tipo, n, "R$", res["brl"], "ops", res["ops"], [(x["sinal"], x["motivo"], x["brl"]) for x in res["lista"]])
