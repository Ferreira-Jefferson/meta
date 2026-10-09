"""Ciclo 3 - proposta COMUM aos dois dias negativos 2024-04-26 e 2024-07-30 (v3: -R$52 e -R$70).

Causa comum: a `gap_fade_fechamento` (a unica FAZER que disparou nos dois dias) vende/compra contra um gap que AINDA ESTA ALARGANDO.
  04-26: gap de alta de +855 pts (3,6 ATR15). A venda de 09:45 (fecha 126.830) esta ACIMA da abertura (126.750): o preco se afasta do
         fechamento de ontem (125.895), nao volta para ele. Stop de 127.230 -> -R$82 (10:27).
  07-30: gap de baixa de -260 pts (2,1 ATR15). As 3 compras (09:15/09:30/09:45 fechando 127.415 / 127.255 / 127.195) estao todas ABAIXO
         da abertura (127.520): o preco se afasta do fechamento de ontem (127.780). 3 stops: -29, -19, -22.
Em ambos o alvo da regra (fechamento de ontem) fica a 3,6 e 2,1 ATR15 de distancia, e o preco anda para o lado oposto.

Propostas comuns (`AJUSTES` e consumido por ciclo3/c3_av2d.py):
  G1  NAO_FAZER   gap alargando: entre 09:15 e 10:00, com gap >= 0,15 ATRd, nao operar CONTRA o gap se o fechamento esta alem da abertura
                  (gap de alta e close > abertura -> veta venda; gap de baixa e close < abertura -> veta compra).
  G2  AJUSTE      a mesma condicao dentro da propria `gap_fade_fechamento` (so ela deixa de disparar; nao veta outras regras).
  G3  NAO_FAZER   reentrada: nao entrar no mesmo lado ate 90 min depois de um STOP nesse lado (qualquer regra).
  G3b AJUSTE      `gap_fade_fechamento` so 1 tentativa por dia (se ja operou gap_fade hoje, nao dispara).
  G4  FAZER       flip: o stop de uma gap_fade e a confirmacao de que o gap continua. Se o ultimo trade do dia foi gap_fade stopado
                  (ha <= 60 min) e o fechamento ja esta alem do preco do stop, entra no sentido oposto ao do fade (a favor do gap),
                  stop 1,5 ATR15 (max 590), alvo 2R.
  G5  NAO_FAZER   gap_fade com alvo longe: o fechamento de ontem (alvo do fade) fica a >= 2 ATR15 do preco -> veta o fade.
  E1  MOTOR       FAZER nos dois lados na mesma vela: em vez de nao entrar, entra o lado que concorda com o deslocamento do dia
                  (fechamento - abertura do dia, |.| >= 1 ATR15).
  CAP5 MOTOR      teto de operacoes 3 -> 5 (informativo: nao resolve; no 07-30 a F1 entra as 11:00 e perde -R$13).
"""
import pandas as pd

MAXR = 590.0
GAPFADE = "2024_06_18:gap_fade_fechamento"


def _hm(ctx): return ctx.t.hour * 60 + ctx.t.minute


def _gap(ctx): return float(ctx.hoje.open.iloc[0] - ctx.diario.close.iloc[-1])


def _vwap(ctx):
    h = ctx.hoje
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).sum() / h.vol.sum())


def _ord(ctx, lado, stop_atr=1.5, alvo_atr=3.0):
    p = float(ctx.hoje.close.iloc[-1]); a = ctx.atr15
    s = min(stop_atr * a, MAXR)
    if lado == "venda":
        return dict(lado="venda", preco=p, stop=p + s, alvo=p - alvo_atr * a, contratos=1)
    return dict(lado="compra", preco=p, stop=p - s, alvo=p + alvo_atr * a, contratos=1)


def _alargando(ctx):
    """Sinal do gap (+1/-1) se |gap| >= 0,15 ATRd esta alargando (fechamento alem da abertura, no sentido do gap); senao 0."""
    if not (9 * 60 + 15 <= _hm(ctx) <= 10 * 60): return 0
    g = _gap(ctx)
    if abs(g) < 0.15 * ctx.atrd: return 0
    c = float(ctx.hoje.close.iloc[-1]); o = float(ctx.hoje.open.iloc[0])
    if g > 0 and c > o: return 1
    if g < 0 and c < o: return -1
    return 0


def g1_nao_operar_contra_gap_alargando(ctx):
    """NAO FAZER (G1): gap alargando. Condicao de mercado: o dia abriu em gap e o fechamento da vela ja esta mais longe do fechamento de
    ontem do que a abertura; o fade aposta no retorno e o preco faz o contrario. Veta VENDA em gap de alta e COMPRA em gap de baixa,
    entre 09:15 e 10:00. Geral (so usa gap, abertura e ultimo fechamento); o corte 0,15 ATRd e o da propria gap_fade."""
    s = _alargando(ctx)
    if s == 1: return _ord(ctx, "venda")
    if s == -1: return _ord(ctx, "compra")


def g2_gap_fade_sem_gap_alargando(orig):
    def f(ctx):
        if _alargando(ctx) != 0: return None
        return orig(ctx)
    return f


def g3_nao_reentrar_mesmo_lado_apos_stop(ctx):
    """NAO FAZER (G3): reentrada no mesmo lado logo depois de um stop. Condicao de mercado: o stop de ate 90 min atras prova que o lado
    estava errado naquele nivel; a regra que o gerou segue vendo o mesmo sinal na vela seguinte (07-30: 3 compras em 30 min).
    Geral (nao usa regra, preco nem data)."""
    ops = ctx.ops_hoje
    if not ops: return None
    u = ops[-1]
    if u.motivo == "stop" and (ctx.t - u.t_sai) <= pd.Timedelta(minutes=90):
        return _ord(ctx, u.lado)


def g3b_gap_fade_uma_tentativa(orig):
    def f(ctx):
        if any(GAPFADE in getattr(x, "fonte", "") for x in ctx.ops_hoje): return None
        return orig(ctx)
    return f


def g4_flip_apos_stop_do_gap_fade(ctx):
    """FAZER (G4, continuacao): a gap_fade foi stopada (ha <= 60 min) e o preco fecha alem do preco do stop. O mercado disse que o gap
    continua; entra a favor dele (lado oposto ao do fade). Stop 1,5 ATR15 (max 590), alvo 2R. Natureza: falha de fade = continuacao.
    Provavelmente geral na forma; n pequeno (so dispara apos stop de gap_fade)."""
    ops = ctx.ops_hoje
    if not ops: return None
    u = ops[-1]
    if GAPFADE not in getattr(u, "fonte", "") or u.motivo != "stop": return None
    if (ctx.t - u.t_sai) > pd.Timedelta(minutes=60): return None
    c = float(ctx.hoje.close.iloc[-1])
    if u.lado == "compra" and c < u.stop_ini:
        lado = "venda"
    elif u.lado == "venda" and c > u.stop_ini:
        lado = "compra"
    else:
        return None
    s = min(1.5 * ctx.atr15, MAXR)
    if lado == "venda": return dict(lado="venda", preco=c, stop=c + s, alvo=c - 2 * s, contratos=1)
    return dict(lado="compra", preco=c, stop=c - s, alvo=c + 2 * s, contratos=1)


def g5_gap_fade_com_alvo_longe(ctx):
    """NAO FAZER (G5): fade de gap com alvo longe. O alvo da gap_fade e o fechamento de ontem; quando ele fica a >= 2 ATR15 do preco, o
    trade precisa de 2+ barras cheias contra o fluxo da abertura. Veta o lado do fade (venda em gap de alta, compra em gap de baixa)
    entre 09:15 e 10:00. Geral na forma; o limiar 2 ATR15 foi visto nos dois dias."""
    if not (9 * 60 + 15 <= _hm(ctx) <= 10 * 60): return None
    g = _gap(ctx)
    if abs(g) < 0.15 * ctx.atrd: return None
    c = float(ctx.hoje.close.iloc[-1]); pc = float(ctx.diario.close.iloc[-1])
    if abs(c - pc) >= 2.0 * ctx.atr15:
        return _ord(ctx, "venda" if g > 0 else "compra")


FAZER = [("G4 flip apos stop do gap_fade", g4_flip_apos_stop_do_gap_fade, None)]
NAO_FAZER = [
    ("G1 nao operar contra gap alargando", g1_nao_operar_contra_gap_alargando, None),
    ("G3 nao reentrar no mesmo lado apos stop", g3_nao_reentrar_mesmo_lado_apos_stop, None),
    ("G5 nao fazer fade com alvo >= 2 ATR15", g5_gap_fade_com_alvo_longe, None),
]
# consumido por ciclo3/c3_av2d.py: add_fazer / add_prio / add_veto / sub_fazer={nome: fabrica(orig)} / motor
AJUSTES = {
    "G1": dict(add_veto=[("c3g:G1 gap alargando", g1_nao_operar_contra_gap_alargando, None)]),
    "G2": dict(sub_fazer={GAPFADE: g2_gap_fade_sem_gap_alargando}),
    "G3": dict(add_veto=[("c3g:G3 reentrada", g3_nao_reentrar_mesmo_lado_apos_stop, None)]),
    "G3b": dict(sub_fazer={GAPFADE: g3b_gap_fade_uma_tentativa}),
    "G4": dict(add_fazer=[("c3g:G4 flip", g4_flip_apos_stop_do_gap_fade, None)]),
    "G5": dict(add_veto=[("c3g:G5 alvo longe", g5_gap_fade_com_alvo_longe, None)]),
    "E1": dict(motor=dict(dois_lados="desloc")),
    "CAP5": dict(motor=dict(max_ops=5)),
}
