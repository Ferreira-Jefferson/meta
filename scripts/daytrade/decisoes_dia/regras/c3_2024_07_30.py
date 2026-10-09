"""Ciclo 3 - 2024-07-30 (ruim, ef 0,108; v3 -R$70: tres compras da gap_fade em 30 min, tres stops de -29/-19/-22).

Dia: gap de baixa de -260 pts (2,1 ATR15, 0,21 ATRd) sobre 127.780. Abre 127.520, a barra de abertura fecha 127.415 (abaixo da abertura) e o
dia cai em escada: 126.425 as 14:00 (maior movimento: venda apos a barra de abertura, t 09:15, 127.415 -> 126.435 = +980 pts).
Causa: a gap_fade comprou o gap tres vezes (t 09:15, 09:30, 09:45) abaixo da abertura, com o preco se afastando do alvo (fechamento de
ontem, 3 ATR15 acima). O teto de 3 ops/dia NAO foi o problema: com teto 5 (CAP5) a F1 `rompe minima da 1a hora (venda)` entra as 11:00 e
fecha -R$13 (dia -R$83). O que faltou foi a regra a favor do gap logo na abertura e uma regra para nao reentrar/virar apos o stop.
`python -m regras.c3_2024_07_30` imprime o resultado isolado de cada regra no dia.
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


def _entrada(lado, p, st, k):
    st = max(st, p - MAXR) if lado == "compra" else min(st, p + MAXR)
    r = abs(p - st)
    return dict(lado=lado, preco=p, stop=st, alvo=(p + k * r if lado == "compra" else p - k * r), contratos=1)


# =====================================================================================================
# 5 maneiras de deixar o dia positivo (FAZER)
# =====================================================================================================
def f1_quebra_da_barra_de_abertura_a_favor_do_gap(ctx):
    """FAZER (continuacao, entrada cedo): gap >= 0,15 ATRd e o gap CONTINUA nas primeiras barras. Dois gatilhos, no sentido do gap:
    (a) t 09:15: a barra de abertura fecha no terco extremo do proprio range e do lado do gap em relacao a abertura do dia (gap de
        baixa: fecha < abertura e a <= 35% do range); (b) ate 10:15, uma vela FECHA alem da extremidade da barra de abertura sem que
        nenhuma anterior tenha fechado la. Entra a favor no fechamento; stop na outra extremidade da barra de abertura (+-20, max 590);
        alvo 2R. Dia: t 09:15 a barra fecha 127.415 (abertura 127.520, 23% do range 127.340-127.665) -> venda 127.415, stop 127.685,
        alvo 126.875 (atingido as 10:30). Natureza: o gap nao encontrou contraparte; abertura vira resistencia. Provavelmente geral na
        forma; os 35% foram vistos no dia. Observacao: e o oposto exato da gap_fade e conflita com ela na mesma vela (por isso e
        prioritaria nas AJUSTES)."""
    h = ctx.hoje
    if not (9 * 60 + 15 <= _hm(ctx) <= 10 * 60 + 15): return None
    g = _gap(ctx)
    if abs(g) < 0.15 * ctx.atrd: return None
    b0 = h.iloc[0]; c = float(h.close.iloc[-1]); r = float(b0.high - b0.low)
    if len(h) == 1:
        if r <= 0: return None
        pos = (float(b0.close) - float(b0.low)) / r
        if g < 0 and b0.close < b0.open and pos <= 0.35: return _entrada("venda", c, float(b0.high) + 20, 2.0)
        if g > 0 and b0.close > b0.open and pos >= 0.65: return _entrada("compra", c, float(b0.low) - 20, 2.0)
        return None
    ant = h.close.iloc[:-1]
    if g < 0 and c < float(b0.low) and (ant >= float(b0.low)).all():
        return _entrada("venda", c, float(b0.high) + 20, 2.0)
    if g > 0 and c > float(b0.high) and (ant <= float(b0.high)).all():
        return _entrada("compra", c, float(b0.low) - 20, 2.0)


def f2_rompe_minima_de_4_velas_abaixo_da_vwap_e_abertura(ctx):
    """FAZER (continuacao por estrutura): a vela fecha abaixo da minima das 4 velas anteriores, abaixo da VWAP e abaixo da abertura do
    dia, entre 10:00 e 13:00 (espelho: acima da maxima, VWAP e abertura, para compra). Stop na maxima das 2 ultimas velas (+20, max 590);
    alvo 1,5R. Dia: t 10:30, a vela das 10:15 fecha 126.870 < minima das 4 anteriores (126.895), < VWAP, < abertura. Natureza: perna de
    queda com preco do lado vendedor de VWAP e abertura. Parece com a F1 `rompe minima da 1a hora` do robo mas sem depender da 1a hora
    nem do corpo; geral."""
    h = ctx.hoje
    if len(h) < 6 or not (10 * 60 <= _hm(ctx) <= 13 * 60): return None
    ant = h.iloc[-5:-1]; u2 = h.iloc[-2:]; c = float(h.close.iloc[-1]); o = float(h.open.iloc[0]); v = _vwap(ctx)
    if c < float(ant.low.min()) and c < v and c < o:
        return _entrada("venda", c, float(u2.high.max()) + 20, 1.5)
    if c > float(ant.high.max()) and c > v and c > o:
        return _entrada("compra", c, float(u2.low.min()) - 20, 1.5)


def f3_maximas_decrescentes_abaixo_da_vwap(ctx):
    """FAZER (continuacao, escada de baixa): as maximas das 3 ultimas velas sao decrescentes, o fechamento esta abaixo da VWAP e da
    abertura, e o fechamento da vela e menor que o da anterior. Entre 09:45 e 12:30. Stop na maxima da 3 velas (+20, max 590), alvo 2R
    (espelho para compra). Dia: t 10:00 (09:30 127.260 > 09:45 127.210 > 10:00? vela 09:45 high 127.210; 09:30 high 127.260; 09:15 high
    127.460) -> venda 127.000. Geral."""
    h = ctx.hoje
    if len(h) < 4 or not (9 * 60 + 45 <= _hm(ctx) <= 12 * 60 + 30): return None
    u3 = h.iloc[-3:]; c = float(h.close.iloc[-1]); o = float(h.open.iloc[0]); v = _vwap(ctx)
    if u3.high.is_monotonic_decreasing and u3.high.nunique() == 3 and c < v and c < o and c < float(h.close.iloc[-2]):
        return _entrada("venda", c, float(u3.high.max()) + 20, 2.0)
    if u3.low.is_monotonic_increasing and u3.low.nunique() == 3 and c > v and c > o and c > float(h.close.iloc[-2]):
        return _entrada("compra", c, float(u3.low.min()) - 20, 2.0)


def f4_perda_da_minima_de_ontem_a_favor_do_gap(ctx):
    """FAZER (nivel de ontem, continuacao): o dia abre DENTRO da faixa de ontem com gap >= 0,15 ATRd e, ate 11:00, uma vela FECHA alem
    da minima de ontem no sentido do gap de baixa (espelho: acima da maxima de ontem em gap de alta), sem ter fechado la antes. Entra a
    favor no fechamento; stop 0,5 ATR15 do lado de ca do nivel (max 590); alvo 2R. Dia: ontem min 127.120; t 10:00 a vela das 09:45
    fecha 127.000 < 127.120 -> venda 127.000, stop 127.181, alvo 126.638 (atingido 12:15). Natureza: nivel de ontem perdido a favor do
    gap (suporte vira resistencia). Provavelmente geral; 0,5 ATR15 de stop visto no dia."""
    h = ctx.hoje
    if len(h) < 2 or not (9 * 60 + 30 <= _hm(ctx) <= 11 * 60): return None
    g = _gap(ctx)
    if abs(g) < 0.15 * ctx.atrd: return None
    ont = ctx.diario.iloc[-1]; c = float(h.close.iloc[-1]); ant = h.close.iloc[:-1]
    if g < 0 and float(h.open.iloc[0]) > float(ont.low) and c < float(ont.low) and (ant >= float(ont.low)).all():
        return _entrada("venda", c, float(ont.low) + 0.5 * ctx.atr15, 2.0)
    if g > 0 and float(h.open.iloc[0]) < float(ont.high) and c > float(ont.high) and (ant <= float(ont.high)).all():
        return _entrada("compra", c, float(ont.high) - 0.5 * ctx.atr15, 2.0)


def f5_barra_de_baixa_quebra_minima_anterior_sob_vwap(ctx):
    """FAZER (continuacao micro, escada de baixa): vela de BAIXA que fecha abaixo da minima da vela anterior, com volume >= a media do
    dia, abaixo da VWAP e da abertura do dia, entre 10:00 e 15:00 (espelho para compra). Stop na maxima das 2 ultimas velas (+20, max
    590); alvo 1,5R. Dia: 10:15 (vol 778k, fecha 126.870 < 126.895), 12:00 (591k). Natureza: continuacao por quebra de minima com volume.
    Geral na forma; dispara muitas vezes (testar no conjunto)."""
    h = ctx.hoje
    if len(h) < 4 or not (10 * 60 <= _hm(ctx) <= 15 * 60): return None
    u, a = h.iloc[-1], h.iloc[-2]; c = float(u.close); o = float(h.open.iloc[0]); v = _vwap(ctx)
    if u.vol < h.vol.mean(): return None
    if u.close < u.open and c < float(a.low) and c < v and c < o:
        return _entrada("venda", c, float(h.high.iloc[-2:].max()) + 20, 1.5)
    if u.close > u.open and c > float(a.high) and c > v and c > o:
        return _entrada("compra", c, float(h.low.iloc[-2:].min()) - 20, 1.5)


FAZER = [
    ("F1 quebra da barra de abertura a favor do gap", f1_quebra_da_barra_de_abertura_a_favor_do_gap, None),
    ("F2 rompe minima de 4 velas sob VWAP e abertura", f2_rompe_minima_de_4_velas_abaixo_da_vwap_e_abertura, None),
    ("F3 maximas decrescentes sob a VWAP", f3_maximas_decrescentes_abaixo_da_vwap, None),
    ("F4 perda da minima de ontem a favor do gap", f4_perda_da_minima_de_ontem_a_favor_do_gap, None),
    ("F5 barra de baixa quebra minima anterior sob VWAP", f5_barra_de_baixa_quebra_minima_anterior_sob_vwap, None),
]


# =====================================================================================================
# 5 coisas a NAO fazer
# =====================================================================================================
def n1_comprar_gap_de_baixa_alem_da_abertura(ctx):
    """NAO FAZER comprar entre 09:15 e 10:00 com gap de baixa >= 0,15 ATRd e fechamento ABAIXO da abertura do dia (gap alargando).
    (G1 do grupo, so o lado de compra.) Dia: 09:15/09:30/09:45 fecham 127.415/127.255/127.195 < 127.520: tres compras, tres stops. Geral."""
    if not (9 * 60 + 15 <= _hm(ctx) <= 10 * 60): return None
    if _gap(ctx) <= -0.15 * ctx.atrd and float(ctx.hoje.close.iloc[-1]) < float(ctx.hoje.open.iloc[0]):
        return _ord(ctx, "compra")


def n2_reentrar_no_mesmo_lado_apos_stop(ctx):
    """NAO FAZER entrar no mesmo lado ate 90 min depois de um stop (G3 do grupo). Dia: as compras de 09:30 e 09:45 vieram 8 e 5 minutos
    depois do stop da anterior. Geral."""
    ops = ctx.ops_hoje
    if ops and ops[-1].motivo == "stop" and (ctx.t - ops[-1].t_sai) <= pd.Timedelta(minutes=90):
        return _ord(ctx, ops[-1].lado)


def n3_comprar_abaixo_de_vwap_e_abertura_com_maximas_decrescentes(ctx):
    """NAO FAZER comprar com o fechamento abaixo da VWAP e da abertura do dia e as maximas das 3 ultimas velas decrescentes, antes das
    15:00. Condicao: escada de baixa com preco do lado vendedor; comprar e pegar faca. Dia: de 09:45 ate ~12:30. Geral."""
    h = ctx.hoje
    if len(h) < 4 or not (9 * 60 + 45 <= _hm(ctx) <= 15 * 60): return None
    u3 = h.iloc[-3:]; c = float(h.close.iloc[-1])
    if u3.high.is_monotonic_decreasing and c < _vwap(ctx) and c < float(h.open.iloc[0]):
        return _ord(ctx, "compra")


def n4_gap_fade_com_alvo_a_2_atr15_ou_mais(ctx):
    """NAO FAZER fade de gap quando o fechamento de ontem (alvo do fade) esta a >= 2 ATR15 do preco (G5 do grupo). Dia: 127.780 contra
    127.415 = 365 pts = 3 ATR15 no primeiro sinal. Geral na forma."""
    if not (9 * 60 + 15 <= _hm(ctx) <= 10 * 60): return None
    g = _gap(ctx)
    if abs(g) < 0.15 * ctx.atrd: return None
    if abs(float(ctx.hoje.close.iloc[-1]) - float(ctx.diario.close.iloc[-1])) >= 2.0 * ctx.atr15:
        return _ord(ctx, "venda" if g > 0 else "compra")


def n5_comprar_apos_barra_vendedora_com_volume(ctx):
    """NAO FAZER comprar logo apos uma vela de BAIXA (fecha nos 25% inferiores) com volume >= 1,2x a media do dia, entre 09:45 e 14:00.
    Condicao: pressao vendedora com volume = continuacao, nao exaustao (o WIN M15 e mais continuacao que reversao). Dia: 10:15
    (vol 778k, fecha a 6%), 11:00 e 12:00. Geral na forma; 1,2x visto no dia."""
    h = ctx.hoje
    if len(h) < 4 or not (9 * 60 + 45 <= _hm(ctx) <= 14 * 60): return None
    u = h.iloc[-1]; r = float(u.high - u.low)
    if r > 0 and u.close < u.open and (u.close - u.low) / r <= 0.25 and u.vol >= 1.2 * h.vol.iloc[:-1].mean():
        return _ord(ctx, "compra")


NAO_FAZER = [
    ("N1 comprar gap de baixa alem da abertura", n1_comprar_gap_de_baixa_alem_da_abertura, None),
    ("N2 reentrar no mesmo lado apos stop", n2_reentrar_no_mesmo_lado_apos_stop, None),
    ("N3 comprar sob VWAP e abertura com maximas decrescentes", n3_comprar_abaixo_de_vwap_e_abertura_com_maximas_decrescentes, None),
    ("N4 gap_fade com alvo a >= 2 ATR15", n4_gap_fade_com_alvo_a_2_atr15_ou_mais, None),
    ("N5 comprar apos barra vendedora com volume", n5_comprar_apos_barra_vendedora_com_volume, None),
]

AJUSTES = {}
for _i, (_n, _r, _g) in enumerate(FAZER):
    AJUSTES[f"B_F{_i+1}"] = dict(add_prio=[(f"c3b:{_n}", _r, _g)])
    AJUSTES[f"B_F{_i+1}n"] = dict(add_fazer=[(f"c3b:{_n}", _r, _g)])
for _i, (_n, _r, _g) in enumerate(NAO_FAZER):
    AJUSTES[f"B_N{_i+1}"] = dict(add_veto=[(f"c3b:{_n}", _r, _g)])

DIA = "2024-07-30"

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import base
    for grupo, lista in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, g in lista:
            res = base.resumo(base.simula_dia(DIA, r, g, max_ops=3))
            print(f"{grupo:9s} {nome:56s} isolada R$ {res['brl']:8.2f} ops {res['ops']}", flush=True)
