"""Ciclo 1 - dia 2025-01-20 (WIN, rotacao, ef 0,064). Robo fechou -R$54,09:
venda F2 falha da maxima +52; depois COMPRA recuo_a_favor_tendencia (12:30, -81, stop) e COMPRA Recuo a media 8 (14:45, -25, fim).
Cinco FAZER (F1..F5), cinco NAO_FAZER (N1..N5). Nenhum r_*.py foi editado.
Todas as regras usam so o passado de ctx (sem data, sem preco absoluto).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import base

MAXRISCO = 600.0


def _h(ctx):
    return ctx.t.hour * 60 + ctx.t.minute


def _vwap(ctx):
    h = ctx.hoje
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).sum() / h.vol.sum())


def _ent(ctx, lado, stop, alvo_r=None, preco=None):
    p = float(ctx.hoje.close.iloc[-1]) if preco is None else float(preco)
    if lado == "compra":
        st = max(float(stop), p - MAXRISCO)
        al = None if alvo_r is None else p + alvo_r * (p - st)
    else:
        st = min(float(stop), p + MAXRISCO)
        al = None if alvo_r is None else p - alvo_r * (st - p)
    return dict(lado=lado, preco=p, stop=st, alvo=al, contratos=1)


# ---------------- FAZER ----------------
def f1_spring_minima_1h_confirmado(ctx):
    """Spring da minima da 1a hora com FECHAMENTO anterior abaixo: a vela anterior (ou a de 2 atras) fechou abaixo da minima da 1a hora
    (09:00-10:00) e a vela atual volta a fechar ACIMA dela. Compra no fechamento, stop 20 pts abaixo da minima da varredura, alvo 2R.
    Condicao de mercado: rompimento de baixa que nao continua (vendedores armadilhados), 10:15-12:00.
    Natureza: reversao em falha com confirmacao de fechamento. Provavelmente geral."""
    h = ctx.hoje
    if len(h) < 6 or _h(ctx) > 12 * 60: return None
    mn = float(h.low.iloc[:4].min())
    if h.close.iloc[-1] > mn and (h.close.iloc[-2] < mn or h.close.iloc[-3] < mn):
        st = float(h.low.iloc[-3:].min()) - 20
        return _ent(ctx, "compra", st, 2.0)


def f2_rompe_maxima_de_ontem_vwap(ctx):
    """Rompimento da maxima de ontem: apos 10:00, fechamento acima da maxima do pregao anterior e acima da VWAP do dia (a vela anterior
    fechava abaixo). Compra, stop 0,6 ATR15 abaixo da maxima de ontem, alvo 1R. Condicao: nivel de ontem cede com preco acima da media
    ponderada. Natureza: nivel de ontem. Ajustada ao dia (alvo 1R escolhido vendo que o dia ficou lateral depois)."""
    h = ctx.hoje
    if len(h) < 5 or _h(ctx) > 14 * 60: return None
    ymax = float(ctx.diario.high.iloc[-1])
    if h.close.iloc[-1] > ymax and h.close.iloc[-2] <= ymax and h.close.iloc[-1] > _vwap(ctx):
        return _ent(ctx, "compra", ymax - 0.6 * ctx.atr15, 1.0)


def f3_venda_exaustao_topo_volume_seco(ctx):
    """Exaustao no topo: a maxima do dia foi feita nas ultimas 3 velas, o dia subiu >= 3 ATR15 desde a minima, e o volume da vela
    atual esta < 70% da media das 8 ultimas velas, fechando abaixo da anterior. Venda, stop 0,5 ATR15 acima da maxima do dia, alvo 1R.
    Condicao: alta esticada sem participacao vira devolucao (so ate 13h). Natureza: reversao por esgotamento de volume.
    Provavelmente geral, mas e contra a continuacao (licao do projeto) - por isso so com volume seco."""
    h = ctx.hoje
    if len(h) < 10 or _h(ctx) > 13 * 60: return None
    mx = float(h.high.max())
    if h.high.iloc[-3:].max() < mx: return None
    if mx - float(h.low.min()) < 3 * ctx.atr15: return None
    if h.vol.iloc[-1] < 0.7 * h.vol.iloc[-8:].mean() and h.close.iloc[-1] < h.close.iloc[-2]:
        return _ent(ctx, "venda", mx + 0.5 * ctx.atr15, 1.0)


def f4_retomada_vwap(ctx):
    """Retomada da VWAP: depois de >= 4 velas seguidas fechando abaixo da VWAP, a vela atual fecha acima da VWAP. Compra, stop na minima das ultimas 4 velas - 20 pts, alvo 1,5R. Condicao: rotacao que vira compradora apos a
    queda matinal, 10:30-13:00. Natureza: retomada de media ponderada. Provavelmente geral."""
    h = ctx.hoje
    if len(h) < 7 or not (10 * 60 + 30 <= _h(ctx) <= 13 * 60): return None
    tp = (h.high + h.low + h.close) / 3
    vw = (tp * h.vol).cumsum() / h.vol.cumsum()
    abaixo = (h.close.iloc[-5:-1] < vw.iloc[-5:-1]).all()
    if abaixo and h.close.iloc[-1] > vw.iloc[-1]:
        return _ent(ctx, "compra", float(h.low.iloc[-4:].min()) - 20, 1.5)


def f5_rompe_faixa_estreita_tarde(ctx):
    """Rompimento de faixa estreita no fim da tarde: depois das 16h, a vela fecha acima da maxima das 4 velas anteriores cuja amplitude
    somada e < 1,6 ATR15 (compressao), com volume > media das 8 ultimas. Compra, stop na minima da faixa, alvo 0,75R.
    Condicao: compressao de volatilidade resolvida para cima. Ajustada ao dia (depois das 15h os sinais pioram, licao do projeto)."""
    h = ctx.hoje
    if len(h) < 12 or _h(ctx) < 16 * 60: return None
    f = h.iloc[-5:-1]
    if (f.high.max() - f.low.min()) < 1.6 * ctx.atr15 and h.close.iloc[-1] > f.high.max() and h.vol.iloc[-1] > h.vol.iloc[-8:].mean():
        return _ent(ctx, "compra", float(f.low.min()), 0.75)


# ---------------- NAO_FAZER ----------------
def n1_comprar_recuo_volume_seco(ctx):
    """ARMADILHA: comprar recuo a favor da tendencia de alta com a vela de recuo em volume SECO (< 70% da media do dia), depois das 12h.
    Condicao: preco acima da VWAP e >= 1,8 ATR15 acima da abertura, vela fecha <= anterior. Nao faca quando o recuo vem sem
    participacao (o preco ja esticou e ninguem compra a queda). Perdeu 2 vezes neste dia (12:30 e 14:45)."""
    h = ctx.hoje
    if len(h) < 8: return None
    if h.close.iloc[-1] > _vwap(ctx) and h.close.iloc[-1] - h.open.iloc[0] > 1.8 * ctx.atr15 \
            and h.close.iloc[-1] <= h.close.iloc[-2] and h.vol.iloc[-1] < 0.7 * h.vol.mean() and _h(ctx) >= 12 * 60:
        return _ent(ctx, "compra", float(h.low.iloc[-1]) - 0.5 * ctx.atr15, 1.5)


def n2_comprar_topo_esticado(ctx):
    """ARMADILHA: comprar a maxima do dia depois de esticada >= 4 ATR15 desde a minima do dia (preco a menos de 0,3 ATR15 da maxima).
    Nao faca quando o dia ja andou 4 ATR15 de um lado: a compra paga o topo. Stop 1 ATR15, alvo 1,5R."""
    h = ctx.hoje
    if len(h) < 8: return None
    mx, mn = float(h.high.max()), float(h.low.min())
    c = float(h.close.iloc[-1])
    if mx - mn >= 4 * ctx.atr15 and mx - c < 0.3 * ctx.atr15:
        return _ent(ctx, "compra", c - ctx.atr15, 1.5)


def n3_vender_climax_de_queda(ctx):
    """ARMADILHA: vender o rompimento da minima da 1a hora numa vela de volume CLIMAX (> 1,2x a media das velas anteriores do dia):
    e capitulacao, nao inicio de tendencia. Nao faca quando o rompimento de baixa vem com pico de volume. Stop na maxima da vela de rompimento, alvo 1R."""
    h = ctx.hoje
    if len(h) < 5 or _h(ctx) > 12 * 60: return None
    mn = float(h.low.iloc[:4].min())
    u = h.iloc[-1]
    if u.close < mn and u.vol > 1.2 * h.vol.iloc[:-1].mean():
        return _ent(ctx, "venda", float(u.high), 1.0)


def n4_vender_perda_faixa_em_dia_de_alta(ctx):
    """ARMADILHA: vender a perda da minima das 4 velas anteriores no meio do dia (12:30-15:00) quando o preco esta acima da abertura
    em pelo menos 1 ATR15. Nao faca: em dia que sobe, a perda de faixa e pausa. Stop 0,8 ATR15 acima da vela, alvo 1R."""
    h = ctx.hoje
    if len(h) < 8 or not (12 * 60 + 30 <= _h(ctx) <= 15 * 60): return None
    f = h.iloc[-5:-1]
    c = float(h.close.iloc[-1])
    if c < float(f.low.min()) and c - h.open.iloc[0] > ctx.atr15:
        return _ent(ctx, "venda", float(h.high.iloc[-1]) + 0.8 * ctx.atr15, 1.0)


def n5_comprar_reacao_sem_volume_tarde(ctx):
    """ARMADILHA: comprar vela de alta de reacao em BAIXO volume (< 70% da media do dia) entre 14h e 15h, que fecha acima da maxima da
    vela anterior. Nao faca: reacao sem participacao no meio da tarde e so repique dentro da faixa.
    Stop na minima das 3 ultimas velas, alvo 1,5R. Foi a compra das 14:45 deste dia (fechou -R$25)."""
    h = ctx.hoje
    if len(h) < 12 or not (14 * 60 <= _h(ctx) <= 15 * 60): return None
    u = h.iloc[-1]
    if u.close > u.open and u.close > h.high.iloc[-2] and u.vol < 0.7 * h.vol.mean():
        return _ent(ctx, "compra", float(h.low.iloc[-3:].min()), 1.5)


FAZER = [("F1 spring minima 1a hora com fechamento abaixo antes", f1_spring_minima_1h_confirmado, None),
         ("F2 rompe maxima de ontem acima da VWAP", f2_rompe_maxima_de_ontem_vwap, None),
         ("F3 venda exaustao topo volume seco", f3_venda_exaustao_topo_volume_seco, None),
         ("F4 retomada da VWAP depois de 4 velas abaixo", f4_retomada_vwap, None),
         ("F5 rompe faixa estreita tarde", f5_rompe_faixa_estreita_tarde, None)]
NAO_FAZER = [("N1 nao comprar recuo com volume seco", n1_comprar_recuo_volume_seco, None),
             ("N2 nao comprar topo esticado", n2_comprar_topo_esticado, None),
             ("N3 nao vender climax de queda", n3_vender_climax_de_queda, None),
             ("N4 nao vender perda de faixa em dia de alta", n4_vender_perda_faixa_em_dia_de_alta, None),
             ("N5 nao comprar reacao sem volume na tarde", n5_comprar_reacao_sem_volume_tarde, None)]

if __name__ == "__main__":
    for tipo, lst in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for n, r, g in lst:
            s = base.resumo(base.simula_dia("2025-01-20", r, g))
            print(tipo, n, s["ops"], s["brl"], [(x["sinal"], x["lado"], x["motivo"], x["brl"]) for x in s["lista"]], flush=True)
