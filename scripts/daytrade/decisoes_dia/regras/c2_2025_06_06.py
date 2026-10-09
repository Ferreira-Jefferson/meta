"""Ciclo 2 - dia 2025-06-06 (WIN, rotacao, ef 0,045). Robo v2 fechou -R$128,79 (v1 fechou +R$122):
  09:30 gap_fade venda +37 | 12:00 F1 rompe minima da 1a hora (venda) stop -113 | 15:30 A3 reteste da minima de ontem (venda) stop -53.
A v1 tambem ganhou +85 na F5 (compra suporte, 10:00) que a A1b da v2 bloqueou, e vetou a F1 das 12:00 (veto stop_curto) que a A2 liberou.

Contem:
  FAZER     : 5 propostas de ganho (3 regras novas, 2 ajustes: F5/A1b relaxada e A3 com trailing)
  NAO_FAZER : 5 vetos (todos de venda; descrevem estado do mercado, nao o gatilho)
  AJUSTES   : como cada proposta entra no robo v2 (monta()).
`python -m regras.c2_2025_06_06` imprime o resultado de cada regra no dia (isolada e dentro do robo v2) e o efeito
nos 50 dias de dias_usados.json (ciclos 0, 1 e 2). Nenhum r_*.py nem robo*.py e editado.
"""
import pandas as pd

H1 = pd.Timedelta(hours=1)
MAXR = 590.0  # risco maximo por contrato (6% de R$2.000)


def _hm(ctx):
    return ctx.t.hour * 60 + ctx.t.minute


def _p1(ctx):
    h = ctx.hoje
    return h[h.index < h.index[0] + H1]


def _vwap(ctx):
    h = ctx.hoje
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).sum() / h.vol.sum())


def _dvwap(ctx):
    """distancia do fechamento a VWAP do dia, em ATR15 (negativo = abaixo)."""
    return (float(ctx.hoje.close.iloc[-1]) - _vwap(ctx)) / ctx.atr15


def _ord(ctx, lado, stop, alvo_r=None, alvo=None):
    p = float(ctx.hoje.close.iloc[-1])
    if lado == "compra":
        st = max(float(stop), p - MAXR)
        al = alvo if alvo is not None else (p + alvo_r * (p - st) if alvo_r else None)
    else:
        st = min(float(stop), p + MAXR)
        al = alvo if alvo is not None else (p - alvo_r * (st - p) if alvo_r else None)
    return dict(lado=lado, preco=p, stop=st, alvo=al, contratos=1)


# =====================================================================================================
# 5 maneiras de deixar o dia positivo
# =====================================================================================================

# ---- P1 (ajuste de FAZER): F5 so e bloqueada por minima nova REAL, nao por minima nova de poucos pontos -------
def p1_f5_minima_nova_so_se_real(ctx):
    """AJUSTE da A1b (a1b_compra_suporte_que_segurou, que substituiu a F5 na v2). A A1b veta a compra se a minima da vela de
    entrada e QUALQUER minima nova do dia. Aqui a vela das 10:00 fez minima 136.780 contra 136.840 da anterior: 60 pts = 0,26 ATR15,
    e o fechamento (136.970) ficou 190 pts acima, vela de alta - o suporte da abertura segurou. A v1 comprou e ganhou +R$85
    (alvo na maxima do dia). Condicao nova: so bloqueia se a minima da vela ficou >= 0,5 ATR15 ABAIXO da minima anterior do dia
    (queda de verdade, faca caindo); toque raso de poucos pontos nao e minima nova. Resto igual a F5.
    Natureza: ajuste de condicao de FAZER (compra de suporte na rotacao). Ajustada ao dia: o 0,5 ATR15 foi escolhido sabendo do
    caso (A1b nasceu de uma minima nova de 40 pts, 0,13 ATR15; aqui sao 60 pts, 0,26 ATR15) - a fronteira fica entre os dois."""
    h = ctx.hoje
    if len(h) < 4 or not (10 <= ctx.t.hour < 11): return None
    hi, lo = h.high.max(), h.low.min()
    u = h.iloc[-1]
    if u.low < h.low.iloc[:-1].min() - 0.5 * ctx.atr15: return None
    if (hi - lo) < 0.6 * ctx.atrd and u.close <= lo + 0.55 * (hi - lo) and u.close > u.open:
        p = float(u.close)
        return dict(lado="compra", preco=p, stop=p - min(1.5 * ctx.atr15, MAXR), alvo=float(hi), contratos=1)


# ---- P2 (regra nova): reteste da VWAP por baixo depois de queda esticada -------------------------------------
def p2_venda_reteste_vwap_abaixo(ctx):
    """FAZER nova. Em dia que ja esteve >= 1,5 ATR15 ABAIXO da VWAP nas 8 velas anteriores, a vela atual volta a tocar a VWAP
    (maxima >= VWAP - 0,3 ATR15), fecha ABAIXO dela e em queda (fecha < abre), entre 11:00 e 16:00. Venda limitada no fechamento,
    stop 0,5 ATR15 acima da VWAP, alvo 1,5R. Neste dia: 13:15 (fecha 136.820, VWAP 136.957, a vela tocou 136.995): venda -> alvo
    em 14:00 (+R$94). Condicao de mercado: a VWAP vira resistencia quando o dia fez a esticada para baixo e devolveu so ate ela
    (vendedores defendem a media ponderada). Natureza: reteste de VWAP (a favor da tendencia do dia, ao contrario da F1 que
    persegue a minima esticada). Provavelmente geral na ideia; perde se o preco recupera a VWAP com volume."""
    h = ctx.hoje
    if len(h) < 10 or not (11 * 60 <= _hm(ctx) <= 16 * 60): return None
    u = h.iloc[-1]
    v = _vwap(ctx)
    a = ctx.atr15
    tp = (h.high + h.low + h.close) / 3
    vwv = (tp * h.vol).cumsum() / h.vol.cumsum()
    dist = ((h.close - vwv) / a).iloc[-9:-1]
    if dist.min() <= -1.5 and u.high >= v - 0.3 * a and u.close < v and u.close < u.open:
        return _ord(ctx, "venda", v + 0.5 * a, alvo_r=1.5)


# ---- P3 (regra nova): engolfo de baixa no topo do dia depois de rompimento da 1a hora ---------------------
def p3_engolfo_no_topo_do_dia(ctx):
    """FAZER nova. A maxima do dia foi feita nas 2 velas anteriores E esta acima da maxima da 1a hora (rompimento que nao
    continuou), e a vela atual fecha ABAIXO da minima da anterior, em queda, entre 10:00 e 14:00. Venda no fechamento, stop 20 pts
    acima da maxima do dia, alvo 1,5R. Neste dia: a maxima 137.535 (10:45) rompeu a da 1a hora (137.405) e as 11:15 a vela fecha
    137.000 abaixo da minima da anterior (137.105) -> venda, alvo em 16:15 (+R$164,50). Condicao: rompimento sem continuacao
    seguido de vela de rejeicao (reversao em falha com confirmacao de fechamento). Natureza: reversao de topo.
    Ajustada ao dia no alvo: o 1,5R foi fixado depois de ver que o 2R so chegava no fim (+R$20)."""
    h = ctx.hoje
    if len(h) < 6 or not (10 * 60 <= _hm(ctx) <= 14 * 60): return None
    u = h.iloc[-1]
    mx = h.high.max()
    if h.high.iloc[-3:-1].max() >= mx and mx > _p1(ctx).high.max() and u.close < h.low.iloc[-2] and u.close < u.open:
        return _ord(ctx, "venda", float(mx) + 20, alvo_r=1.5)


# ---- P4 (regra nova): reversao de minima do dia com alvo na VWAP ----------------------------------------------
def p4_reversao_da_minima_do_dia_ate_vwap(ctx):
    """FAZER nova. A vela anterior fez a MINIMA DO DIA e a atual fecha acima da maxima dela, em alta, entre 10:30 e 15:00.
    Compra no fechamento, stop 20 pts abaixo da menor minima das duas, alvo na VWAP (so entra se o caminho ate a VWAP vale >= 0,8 do
    risco). Neste dia: 12:15 fecha 136.650 (minima do dia 136.330 na vela anterior, VWAP 136.982) -> alvo em 12:45 (+R$64,50).
    Condicao: dia de rotacao que devolve a esticada a VWAP; a VWAP e o imam do dia. Natureza: reversao a media ponderada.
    Provavelmente geral na ideia (alvo e uma referencia do proprio dia, nao um numero fixo)."""
    h = ctx.hoje
    if len(h) < 8 or not (10 * 60 + 30 <= _hm(ctx) <= 15 * 60): return None
    u, p = h.iloc[-1], h.iloc[-2]
    if p.low <= h.low.iloc[:-1].min() and u.close > p.high and u.close > u.open:
        v = _vwap(ctx)
        c = float(u.close)
        st = float(min(p.low, u.low)) - 20
        if c > st and v - c >= 0.8 * (c - st):
            return _ord(ctx, "compra", st, alvo=v)


# ---- P5 (ajuste de gestao): A3 com trailing curto ----------------------------------------------------------
def p5_a3_gerir_trailing_curto(ctx, pos):
    """AJUSTE de SAIDA da A3 (c1:A3 reteste_minima_de_ontem; a regra de entrada nao muda, so o `gerir`). O stop de venda segue o
    MENOR FECHAMENTO desde a entrada + 0,5 ATR15 (so desce). Neste dia: A3 vende 15:30 a 136.460, o preco faz minimo 136.150 e a
    vela das 16:30 devolve 200 pts; o trailing (136.215 + 0,5 ATR15 = ~136.340) sai em +R$21,86 em vez de -R$52,79 no stop de 16:45.
    Condicao: dia de rotacao em que a continuacao da queda pos-15h e curta (volume seco). Natureza: gestao de saida.
    Ajustada ao dia (o 0,5 ATR15 foi escolhido vendo o dia); em tendencia limpa o trailing curto corta o ganho."""
    h = ctx.hoje
    h = h[h.index >= pos["t_ent"].floor("15min")]
    if pos["lado"] == "venda": return float(h.close.min()) + 0.5 * ctx.atr15
    return float(h.close.max()) - 0.5 * ctx.atr15


# =====================================================================================================
# 5 coisas a NAO fazer (cada uma da R$ < 0 neste dia; docstring = condicao de mercado que vira veto)
# =====================================================================================================
def n1_vender_esticado_abaixo_da_vwap(ctx):
    """NAO fazer: vender quando o fechamento ja esta >= 1,25 ATR15 ABAIXO da VWAP do dia. Armadilha: a venda chega no fim do
    movimento esticado e o preco devolve a VWAP; vendedor tardio paga o rebote. Neste dia: 11:45 (-1,74 ATR) e 14:00 (-1,63):
    stops. As duas entradas perdedoras do robo v2 (F1 12:00 em -1,67 e A3 15:30 em -1,38) tinham esse estado. Descreve o preco
    em relacao a VWAP, nao o gatilho. Veto de venda."""
    if len(ctx.hoje) < 5: return None
    if _dvwap(ctx) <= -1.25:
        a = ctx.atr15
        p = float(ctx.hoje.close.iloc[-1])
        return _ord(ctx, "venda", p + 1.5 * a, alvo=p - 3 * a)


def n2_vender_apos_queda_de_3_atr_do_topo(ctx):
    """NAO fazer: vender quando o fechamento ja esta >= 3 ATR15 abaixo da maxima do dia. Armadilha: o movimento de baixa ja
    percorreu 3 velas-padrao; a continuacao exige mais do que o dia costuma dar em rotacao e o stop de 1,5 ATR15 e curto para o
    rebote. Neste dia: 11:45, 14:00, 17:30 (3 trades, -R$234). Veto de venda."""
    h = ctx.hoje
    if len(h) < 5: return None
    if (h.high.max() - h.close.iloc[-1]) >= 3 * ctx.atr15:
        a = ctx.atr15
        p = float(h.close.iloc[-1])
        return _ord(ctx, "venda", p + 1.5 * a, alvo=p - 3 * a)


def n3_vender_com_volume_seco_sob_a_vwap(ctx):
    """NAO fazer: vender quando o volume da vela e < 0,75x a media do dia e o preco esta >= 1 ATR15 abaixo da VWAP. Armadilha:
    queda sem participacao em dia de rotacao nao tem continuidade (os vendedores sumiram, o rebote nao encontra oferta). Neste dia:
    12:00 (vol 0,68x; F1 stop -R$113) e 15:30 (0,54x; A3 stop -R$53). Veto de venda."""
    h = ctx.hoje
    if len(h) < 8: return None
    u = h.iloc[-1]
    if u.vol < 0.75 * h.vol.mean() and _dvwap(ctx) <= -1.0:
        a = ctx.atr15
        p = float(u.close)
        return _ord(ctx, "venda", p + 1.5 * a, alvo=p - 3 * a)


def n4_vender_perto_da_minima_depois_das_15h(ctx):
    """NAO fazer: vender depois das 15:00 com o fechamento a menos de 1 ATR15 da minima do dia, quando o dia ja andou >= 0,5 ATR
    diario. Armadilha: o que sobra de queda e pouco (a minima esta ali) e o stop de 1,5 ATR15 e maior que o ganho possivel;
    sinais pos-15h ja pioram (licao do projeto). Neste dia: 15:00 stop -R$95. Veto de venda."""
    h = ctx.hoje
    if len(h) < 12 or _hm(ctx) < 15 * 60: return None
    if h.close.iloc[-1] - h.low.min() < 1.0 * ctx.atr15 and (h.high.max() - h.low.min()) >= 0.5 * ctx.atrd:
        a = ctx.atr15
        p = float(h.close.iloc[-1])
        return _ord(ctx, "venda", p + 1.5 * a, alvo=p - 1.5 * a)


def n5_vender_com_atr_expandido(ctx):
    """NAO fazer: vender vela de queda quando o ATR15 de agora e > 1,5x o ATR15 da 4a vela do dia. Armadilha: a volatilidade
    do dia dobrou (a queda das 11:30-11:45 abriu o ATR de ~210 para ~360): stops em ATR ficam largos, o risco por contrato sobe
    (R$110 contra R$60) e o rebote do dia de rotacao cabe dentro do stop. Neste dia: 11:45 stop -R$110 e 13:15 fim -R$16.
    Veto de venda."""
    import base
    h = ctx.hoje
    if len(h) < 8: return None
    a0 = float(base._atr(ctx.m15).loc[h.index[3]])
    if ctx.atr15 > 1.5 * a0 and h.close.iloc[-1] < h.close.iloc[-2]:
        a = ctx.atr15
        p = float(h.close.iloc[-1])
        return _ord(ctx, "venda", p + 1.5 * a, alvo=p - 3 * a)


# =====================================================================================================
# Acrescimo do dono: gestao ADAPTATIVA e veto N2 so dentro da faixa
# =====================================================================================================
def _ef_parcial(ctx):
    h = ctx.hoje
    rng = float((h.high - h.low).sum())
    return abs(float(h.close.iloc[-1] - h.open.iloc[0])) / rng if rng > 0 else 0.0


def _melhor_lucro_fechando(ctx, pos):
    """melhor fechamento a favor desde a entrada, em pts (>= 0)."""
    h = ctx.hoje
    h = h[h.index >= pos["t_ent"].floor("15min")]
    if pos["lado"] == "venda": return pos["preco"] - float(h.close.min())
    return float(h.close.max()) - pos["preco"]


def _trail(ctx, pos, dist):
    h = ctx.hoje
    h = h[h.index >= pos["t_ent"].floor("15min")]
    if pos["lado"] == "venda": return float(h.close.min()) + dist
    return float(h.close.max()) - dist


def g1_gerir_adaptativo_regime(ctx, pos):
    """GESTAO ADAPTATIVA (regime do dia). So age depois que o melhor fechamento andou >= 1 ATR15 a favor (a posicao provou algo).
    Depois: stop vai ao ponto de entrada e passa a seguir o melhor fechamento a uma distancia que depende do REGIME medido ate agora:
    eficiencia parcial do dia < 0,15 (rotacao) -> 0,5 ATR15 (aperta: a perna devolve); 0,15-0,30 -> 1,0 ATR15; >= 0,30
    (direcional) -> 1,5 ATR15 (afrouxa: deixa correr). Natureza: gestao de saida adaptativa. Nao usa o dia inteiro."""
    a = ctx.atr15
    if _melhor_lucro_fechando(ctx, pos) < 1.0 * a: return None
    ef = _ef_parcial(ctx)
    d = 0.5 * a if ef < 0.15 else (1.0 * a if ef < 0.30 else 1.5 * a)
    novo = _trail(ctx, pos, d)
    if pos["lado"] == "venda": return min(novo, pos["preco"])
    return max(novo, pos["preco"])


def g2_gerir_adaptativo_forca_da_perna(ctx, pos):
    """GESTAO ADAPTATIVA (forca da perna). Mesma ativacao da G1 (1 ATR15 a favor). A distancia do trailing depende da FORCA da perna:
    volume da vela atual < 0,75x a media do dia (perna secando) -> 0,5 ATR15; senao 1,25 ATR15. Natureza: gestao de saida adaptativa."""
    a = ctx.atr15
    if _melhor_lucro_fechando(ctx, pos) < 1.0 * a: return None
    h = ctx.hoje
    d = 0.5 * a if h.vol.iloc[-1] < 0.75 * h.vol.mean() else 1.25 * a
    novo = _trail(ctx, pos, d)
    if pos["lado"] == "venda": return min(novo, pos["preco"])
    return max(novo, pos["preco"])


def _sem_alvo_em_regime_direcional(regra):
    """envoltorio: em dia direcional (eficiencia parcial >= 0,30 com >= 8 velas) a entrada nao leva alvo (deixa correr com o trailing)."""
    def f(ctx):
        s = regra(ctx)
        if s and len(ctx.hoje) >= 8 and _ef_parcial(ctx) >= 0.30:
            s = dict(s); s["alvo"] = None
        return s
    f.__name__ = getattr(regra, "__name__", "r") + "_semalvo_direcional"
    return f


def p6_n2_so_dentro_da_faixa_da_1a_hora(ctx):
    """AJUSTE do veto `2025_06_04:N2 vender minima na rotacao da manha`. O original veta a venda de qualquer fechamento na minima das
    4 ultimas velas entre 10:00 e 12:00. Neste dia ele calou 3 vendas seguidas (11:15, 11:30, 11:45) durante a queda de 137.300 para
    136.330 (970 pts, R$194 por contrato) e so deixou entrar a F1 das 12:00, no FIM do movimento. Condicao nova: so veta enquanto o
    fechamento ainda esta DENTRO da faixa da 1a hora (>= minima da 1a hora): dentro da faixa a rotacao devolve; abaixo dela a faixa
    ja foi rompida e o veto descreve um mercado que nao existe mais. Geral na ideia (usa so a faixa da 1a hora)."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= ctx.t.hour < 12): return None
    if h.close.iloc[-1] >= _p1(ctx).low.min() and h.close.iloc[-1] <= h.close.iloc[-4:].min():
        a = ctx.atr15
        c = float(h.close.iloc[-1])
        return dict(lado="venda", preco=c, stop=c + 1.5 * a, alvo=c - 1.5 * a, contratos=1)


FAZER = [
    ("P1 ajuste F5: so bloqueia minima nova real (>=0,5 ATR)", p1_f5_minima_nova_so_se_real, None),
    ("P2 venda reteste da VWAP apos queda esticada", p2_venda_reteste_vwap_abaixo, None),
    ("P3 venda engolfo no topo do dia pos-rompimento", p3_engolfo_no_topo_do_dia, None),
    ("P4 compra reversao da minima do dia ate a VWAP", p4_reversao_da_minima_do_dia_ate_vwap, None),
    ("P5 ajuste A3: trailing curto", None, p5_a3_gerir_trailing_curto),  # so o gerir; a entrada e a da A3
]
NAO_FAZER = [
    ("N1 vender esticado >=1,25 ATR abaixo da VWAP", n1_vender_esticado_abaixo_da_vwap, None),
    ("N2 vender depois de queda >=3 ATR do topo", n2_vender_apos_queda_de_3_atr_do_topo, None),
    ("N3 vender com volume seco sob a VWAP", n3_vender_com_volume_seco_sob_a_vwap, None),
    ("N4 vender perto da minima depois das 15h", n4_vender_perto_da_minima_depois_das_15h, None),
    ("N5 vender com ATR15 expandido 1,5x", n5_vender_com_atr_expandido, None),
]

# ---- como cada proposta entra no robo v2 ----------------------------------------------------------------
F_F5 = "2025_06_04:F5 compra suporte na rotacao da manha"
A3 = "c1:A3 reteste_minima_de_ontem"
V_N2 = "2025_06_04:N2 vender minima na rotacao da manha"
AJUSTES = {
    "P1": dict(sub_fazer={F_F5: (p1_f5_minima_nova_so_se_real, None)}),
    "P2": dict(add_fazer=[("c2:P2 reteste_vwap", p2_venda_reteste_vwap_abaixo, None)]),
    "P3": dict(add_fazer=[("c2:P3 engolfo_topo", p3_engolfo_no_topo_do_dia, None)]),
    "P4": dict(add_fazer=[("c2:P4 reversao_minima_vwap", p4_reversao_da_minima_do_dia_ate_vwap, None)]),
    "P5": dict(sub_gerir={A3: p5_a3_gerir_trailing_curto}),
    "N1": dict(add_veto=[("c2:N1 esticado_vwap", n1_vender_esticado_abaixo_da_vwap, None)]),
    "N2": dict(add_veto=[("c2:N2 queda_3atr", n2_vender_apos_queda_de_3_atr_do_topo, None)]),
    "N3": dict(add_veto=[("c2:N3 vol_seco_sob_vwap", n3_vender_com_volume_seco_sob_a_vwap, None)]),
    "N4": dict(add_veto=[("c2:N4 perto_minima_pos15h", n4_vender_perto_da_minima_depois_das_15h, None)]),
    "N5": dict(add_veto=[("c2:N5 atr_expandido", n5_vender_com_atr_expandido, None)]),
    "P6": dict(sub_veto={V_N2: (p6_n2_so_dentro_da_faixa_da_1a_hora, None)}),
    "G1": dict(gerir_padrao=g1_gerir_adaptativo_regime),
    "G2": dict(gerir_padrao=g2_gerir_adaptativo_forca_da_perna),
    "G3": dict(gerir_padrao=g1_gerir_adaptativo_regime, sem_alvo_direcional=True),
}


def monta(fz, nf, chaves):
    """Aplica as propostas `chaves` as listas da v2 (robo_v2.monta_v2()) e devolve (fz, nf) novas."""
    fz, nf = list(fz), list(nf)
    for k in chaves:
        a = AJUSTES[k]
        for orig, (fn, g) in a.get("sub_fazer", {}).items():
            fz = [(n, fn, g) if n == orig else (n, r, gg) for n, r, gg in fz]
        for orig, g in a.get("sub_gerir", {}).items():
            fz = [(n, r, g) if n == orig else (n, r, gg) for n, r, gg in fz]
        for orig, (fn, g) in a.get("sub_veto", {}).items():
            nf = [(n, fn, g) if n == orig else (n, r, gg) for n, r, gg in nf]
        if "gerir_padrao" in a:  # gestao adaptativa universal: so nas entradas que nao tem gerir proprio
            gp = a["gerir_padrao"]
            fz = [(n, r, gg if gg is not None else gp) for n, r, gg in fz]
        if a.get("sem_alvo_direcional"):
            fz = [(n, _sem_alvo_em_regime_direcional(r), g) for n, r, g in fz]
        fz = fz + a.get("add_fazer", [])
        nf = nf + a.get("add_veto", [])
    return fz, nf


# ---- avaliacao ---------------------------------------------------------------------------------------
def _dias_usados():
    import json
    from pathlib import Path
    j = json.load(open(Path(__file__).resolve().parents[1] / "dias_usados.json"))
    return list(j["ciclo0"]["dias"]) + [x["dia"] for x in j["ciclo1"]["dias"]] + [x["dia"] for x in j["ciclo2"]["dias"]]


def _um(args):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import robo_v2
    from regras import c2_2025_06_06 as c2
    chaves, dia = args
    fz, nf = robo_v2.monta_v2()
    fz, nf = c2.monta(fz, nf, chaves)
    tr, log, contra = robo_v2.roda_v2(dia, fz, nf)
    ok = [x for x in tr if x.t_ent]
    return chaves, dia, round(sum(x.brl for x in ok), 2), len(ok), [(x.fonte[:45], x.lado, str(x.t_ent.time()), x.motivo, round(x.brl, 1)) for x in ok]


def avalia(configs, dias=None, workers=8):
    """configs: lista de tuplas de chaves de AJUSTES. Devolve {chaves: {dia: (brl, ops, trades)}} sobre os dias usados."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    dias = dias or _dias_usados()
    res = {tuple(c): {} for c in configs}
    with ProcessPoolExecutor(workers) as ex:
        fut = [ex.submit(_um, (tuple(c), d)) for c in configs for d in dias]
        for f in as_completed(fut):
            ch, d, brl, ops, tr = f.result()
            res[ch][d] = (brl, ops, tr)
    return res


def isolada(dia, regra, gerir=None):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import base
    return base.resumo(base.simula_dia(dia, regra, gerir, max_ops=3))


DIA = "2025-06-06"

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    for grupo, lista in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, g in lista:
            if r is None: continue  # P5 e so gestao (medida dentro do robo)
            res = isolada(DIA, r, g)
            print(f"{grupo:9s} {nome:56s} isolada R$ {res['brl']:8.2f} ops {res['ops']}", flush=True)
    import os
    todas = [(k,) for k in AJUSTES] + [("P6", "P3"), ("P5", "N4", "N5")]
    configs = [()] + (todas if os.environ.get("C2_TODAS") else [c for c in todas if c[0] in ("P6", "G1", "G2", "G3") or len(c) > 1])
    res = avalia(configs)
    b = res[()]
    print("\nconfig | R$ no dia (robo v2) | R$ 50 dias | dias que pioraram | dias que melhoraram")
    for c, r in res.items():
        tot = sum(v[0] for v in r.values())
        pi = [d for d in r if r[d][0] < b[d][0] - 0.005]
        me = [d for d in r if r[d][0] > b[d][0] + 0.005]
        print(f"{'+'.join(c) or 'BASE':6s} dia {r[DIA][0]:8.2f}  50d {tot:9.2f}  piorou {len(pi)} {pi}  melhorou {len(me)}", flush=True)
