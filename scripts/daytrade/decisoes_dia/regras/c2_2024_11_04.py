"""Ciclo 2, dia 2024-11-04 (WIN, "bom", direcional de ALTA, ef 0,26; robo v2 = -R$53,04).

Gap de alta de +900 pts (0,55 ATRd) sobre 129.100, abre 130.000 e sobe quase sem recuo ate 132.170 (13:00): dia de tendencia
com VWAP sempre abaixo do preco. A v2 vendeu o gap as 09:30 (stop em 23 min, -R$19), calou as 3 entradas de compra do impulso
(10:15 +211, 10:30 +88, 11:30 +85: vetos de compra de "rompimento" valem tambem em dia de alta; e FAZER nos dois lados as 11:30)
e comprou o recuo das 13:15 ja no fim da perna (stop, -R$34).

Contem:
  FAZER / NAO_FAZER : 5 + 5 propostas (ajustes como novas funcoes; nada de r_*.py ou robo*.py e editado)
  AJUSTES / monta   : como cada proposta entra na v2 (substitui/adiciona) -> `robo_v2.monta_v2()` + `monta()`
  `python -m regras.c2_2024_11_04 dia`   resultado de cada proposta no dia (isolada e dentro do robo)
  `python -m regras.c2_2024_11_04 conj`  efeito de cada proposta nos 50 dias de dias_usados.json
Licao do ciclo 1 respeitada: todo veto novo descreve CONDICAO DE MERCADO (deslocamento, VWAP, minimas ascendentes, volume),
nunca o gatilho de uma FAZER.
"""
import sys
from pathlib import Path
import pandas as pd

AQUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AQUI))
from regras import r_2023_11_03 as r2311, r_2025_06_04 as r2506, r_2024_06_18 as r2406, r_2022_11_29 as r2211

MAXR = 590.0
H1 = pd.Timedelta(hours=1)

F_FALHA_MAX = "2024_06_18:falha_maxima"
F_GAP_SUST = "2022_11_29:gap_de_alta_sustentado"
F_GAP_FADE = "2024_06_18:gap_fade_fechamento"
F_RECUO = "2022_11_29:recuo_a_favor_tendencia"
V_N4_ALVO = "2023_11_03:Comprar rompimento com alvo menor que o stop"
V_N3_MANHA = "2025_06_04:N3 comprar rompimento da manha"


# ------------------------------------------------------------------ helpers (so passado)
def _hm(ctx):
    return ctx.t.hour * 60 + ctx.t.minute


def _vwap_serie(h):
    tp = (h.high + h.low + h.close) / 3
    return (tp * h.vol).cumsum() / h.vol.cumsum()


def _vwap(ctx):
    return float(_vwap_serie(ctx.hoje).iloc[-1])


def _desloc(ctx, k=0.5):
    """+1 se o dia ja subiu >= k ATRd desde a abertura E o preco esta acima da VWAP e a VWAP sobe; -1 espelho; 0 senao.
    Condicao de mercado (dia direcional), independente de qualquer gatilho."""
    h = ctx.hoje
    if len(h) < 2:
        return 0
    c, ab = float(h.close.iloc[-1]), float(h.open.iloc[0])
    v = _vwap_serie(h)
    sobe = v.iloc[-1] > v.iloc[max(0, len(v) - 3)]
    if c - ab >= k * ctx.atrd and c > v.iloc[-1] and sobe:
        return 1
    if ab - c >= k * ctx.atrd and c < v.iloc[-1] and not sobe:
        return -1
    return 0


def _ord(ctx, lado, stop, alvo, preco=None):
    p = float(ctx.hoje.close.iloc[-1]) if preco is None else float(preco)
    if lado == "compra":
        stop = max(stop, p - MAXR)
    else:
        stop = min(stop, p + MAXR)
    return dict(lado=lado, preco=p, stop=float(stop), alvo=(None if alvo is None else float(alvo)), contratos=1)


# =====================================================================================================
# 5 maneiras de deixar o dia positivo (P1..P5)
# =====================================================================================================

# ---- P1 (ajuste de 2 vetos): vetos de compra de "rompimento" so valem fora de dia direcional de alta ----
def p1_n4_so_sem_alta_direcional(ctx):
    """AJUSTE de `2023_11_03:Comprar rompimento com alvo menor que o stop`. O veto bloqueia TODA compra entre 10:00 e 11:00 sempre
    que fecha acima da maxima da 1a hora, sem olhar o payoff do candidato (ele nem ve o stop da FAZER). Aqui ele deixa de valer
    quando o dia ja esta DIRECIONAL de alta (>= 0,5 ATRd acima da abertura, preco acima da VWAP e VWAP subindo): ai o rompimento
    da 1a hora e a perna dominante, nao armadilha. Condicao de mercado, nao de gatilho. Geral (so ATR relativo e VWAP)."""
    if _desloc(ctx) == 1:
        return None
    return r2311.n4_comprar_com_alvo_curto(ctx)


def p1_n3_so_sem_alta_direcional(ctx):
    """AJUSTE de `2025_06_04:N3 comprar rompimento da manha` (mesma logica de P1: no dia direcional de alta o rompimento
    intradiario nao e o 'topo da manha'). Os dois vetos tem de ser estreitados juntos: cada um sozinho ainda cala a compra."""
    if _desloc(ctx) == 1:
        return None
    return r2506.n3_compra_rompimento_alta_manha(ctx)


# ---- P2 (ajuste de FAZER): falha da maxima so em dia que NAO e direcional de alta ----------------------
def p2_falha_maxima_sem_alta_direcional(ctx):
    """AJUSTE de `2024_06_18:falha_maxima` (venda a falha do topo). Mesmo gatilho; nova condicao: o dia nao pode estar direcional de
    alta (>= 0,5 ATRd acima da abertura, acima da VWAP, VWAP subindo). Vender o topo de um impulso so tem sentido se o impulso ja
    esta cansado/rotacionando; em dia de alta limpa a 'falha' e um recuo de 1 vela. Efeito aqui: as 11:30 a FAZER de venda
    deixa de existir, acaba o bloqueio 'FAZER nos dois lados' e entra a compra do recuo (+R$85). Geral."""
    if _desloc(ctx) == 1:
        return None
    return r2406.f_falha_maxima(ctx)


# ---- P3 (ajuste + FAZER nova): gap que SEGURA vira continuacao; so o gap que FALHA e fadeado -----------------------
def p3_gap_fade_so_se_o_gap_falha(ctx):
    """AJUSTE de `2024_06_18:gap_fade_fechamento`. A original vende o gap de alta (compra o de baixa) mesmo com o preco ainda do lado
    do gap em relacao a ABERTURA do dia. Nova condicao: so faz o fade depois que o gap mostrou falha, isto e, o fechamento ja esta
    abaixo da abertura do dia (gap de alta) / acima (gap de baixa). Neste dia o preco ficou acima da abertura o dia inteiro e o fade
    das 09:30 (stop de 85 pts, alvo a 1.570 pts) foi o unico prejuizo da manha. Geral (so abertura e fechamento)."""
    s = r2406.f_gap_fade_fechamento(ctx)
    if not s:
        return None
    ab, px = float(ctx.hoje.open.iloc[0]), float(ctx.hoje.close.iloc[-1])
    if (s["lado"] == "venda" and px < ab) or (s["lado"] == "compra" and px > ab):
        return s
    return None


def p3b_gap_que_segura_continua(ctx):
    """FAZER nova (par do ajuste acima). Gap >= 0,3 ATRd cujas velas, ate 10:00, fecharam todas alem da abertura (gap de alta: acima),
    sem nunca devolver mais de 25% do gap, com o preco do lado certo da VWAP. Compra (gap de alta) com limite no fechamento
    entre 09:45 e 10:00, stop abaixo da minima do dia - 20 (max 590), alvo 1,5R. Espelho para gap de baixa. Natureza: gap com
    sustentacao (o fade e a mesma leitura com o sinal invertido). Provavelmente geral na ideia; poucos dias tem gap >= 0,3 ATRd."""
    h = ctx.hoje
    if len(h) < 3 or not (9 * 60 + 45 <= _hm(ctx) <= 10 * 60):
        return None
    ont = float(ctx.diario.close.iloc[-1])
    ab = float(h.open.iloc[0])
    gap = ab - ont
    if abs(gap) < 0.3 * ctx.atrd:
        return None
    p = float(h.close.iloc[-1])
    v = _vwap(ctx)
    if gap > 0 and (h.close > ab).all() and h.low.min() >= ab - 0.25 * gap and p > v:
        st = float(h.low.min() - 20)
        return _ord(ctx, "compra", st, p + 1.5 * (p - max(st, p - MAXR)), preco=p)
    if gap < 0 and (h.close < ab).all() and h.high.max() <= ab - 0.25 * gap and p < v:
        st = float(h.high.max() + 20)
        return _ord(ctx, "venda", st, p - 1.5 * (min(st, p + MAXR) - p), preco=p)


# ---- P4 (ajuste estrutural dos vetos): em dia direcional, o veto do lado da tendencia nao vale -----------------------
def _sem_veto_a_favor_do_dia(r):
    def w(ctx):
        s = r(ctx)
        if s and s.get("lado") in ("compra", "venda"):
            d = _desloc(ctx)
            if (s["lado"] == "compra" and d == 1) or (s["lado"] == "venda" and d == -1):
                return None
        return s
    return w


# ---- P5 (ajuste de 2 vetos): mesmo que P1 mas a condicao e o GAP do dia, nao o deslocamento -------------------------
def _gap_alinhado_alta(ctx):
    """Dia que abriu com gap de alta >= 0,3 ATRd e continua com o fechamento acima da abertura (gap segurando)."""
    h = ctx.hoje
    gap = float(h.open.iloc[0]) - float(ctx.diario.close.iloc[-1])
    return gap >= 0.3 * ctx.atrd and float(h.close.iloc[-1]) > float(h.open.iloc[0])


def p5_n4_so_sem_gap_de_alta_seguro(ctx):
    """AJUSTE de `2023_11_03:Comprar rompimento com alvo menor que o stop`: nao vale quando o dia abriu com gap de alta >= 0,3 ATRd e o
    preco segue acima da abertura (rompimento a favor do gap). Condicao de mercado conhecida desde a 1a vela. Geral."""
    if _gap_alinhado_alta(ctx):
        return None
    return r2311.n4_comprar_com_alvo_curto(ctx)


def p5_n3_so_sem_gap_de_alta_seguro(ctx):
    """AJUSTE de `2025_06_04:N3 comprar rompimento da manha` (par do anterior)."""
    if _gap_alinhado_alta(ctx):
        return None
    return r2506.n3_compra_rompimento_alta_manha(ctx)


# ---- P6 (gestao ADAPTATIVA): P3b sem alvo fixo em dia direcional, stop acompanha a perna -------------------------------
def p3c_gap_que_segura_sem_alvo(ctx):
    """Mesma entrada de P3b, mas SEM alvo (o dia direcional de alta so se mede no fim) e com `gerir_adaptativo`. Natureza: gap com
    sustentacao + saida que depende do estado do dia. Geral na ideia; a gestao so atua depois de +1R."""
    s = p3b_gap_que_segura_continua(ctx)
    if s:
        s = dict(s); s["alvo"] = None
    return s


def gerir_adaptativo(ctx, pos):
    """Stop adaptativo: ate +1R nao mexe (deixa respirar, o stop inicial fica abaixo da minima do dia). Depois de +1R sobe o stop
    para a minima das ultimas k velas - 0,5 ATR15, onde k depende do estado: k=4 se o dia segue direcional (_desloc==pos) e a
    vela atual fechou perto da maxima (perna forte: folga larga), k=2 se o dia perdeu o deslocamento (aperta)."""
    h = ctx.hoje
    p = float(pos["preco"]); r = p - float(pos["stop"]) if pos["lado"] == "compra" else float(pos["stop"]) - p
    u = h.iloc[-1]
    c = float(u.close)
    ganho = (c - p) if pos["lado"] == "compra" else (p - c)
    if r <= 0 or ganho < r:
        return None
    k = 4 if _desloc(ctx) == (1 if pos["lado"] == "compra" else -1) else 2
    if pos["lado"] == "compra":
        return float(h.low.iloc[-k:].min() - 0.5 * ctx.atr15)
    return float(h.high.iloc[-k:].max() + 0.5 * ctx.atr15)


# =====================================================================================================
# 5 coisas a NAO fazer (V1..V5): cada uma e um veto = condicao de mercado; a funcao devolve a entrada "armadilha"
# =====================================================================================================

def v1_vender_em_dia_direcional_de_alta(ctx):
    """NAO FAZER: vender (qualquer 'falha', 'esticada' ou 'gap') com o dia direcional de alta (>= 0,4 ATRd acima da abertura, preco
    acima da VWAP e VWAP subindo). Armadilha: em dia de alta limpa a venda e contra a perna dominante; o stop curto (1 ATR15) e
    batido por um recuo de 2 velas. Veto: nao vender quando o deslocamento do dia e >= 0,4 ATRd a favor da compra e a VWAP sobe.
    Geral. Entrada-armadilha simulada: vende o fechamento de cada vela (10:00-15:00), stop 1 ATR15, alvo 1 ATR15."""
    h = ctx.hoje
    if len(h) < 2 or not (9 * 60 + 30 <= _hm(ctx) <= 15 * 60) or _desloc(ctx, 0.4) != 1:
        return None
    p = float(h.close.iloc[-1])
    return _ord(ctx, "venda", p + ctx.atr15, p - ctx.atr15, preco=p)


def v2_vender_gap_de_alta_nao_preenchido(ctx):
    """NAO FAZER: vender o gap de alta (>= 0,15 ATRd) ate 10:00 enquanto o gap NAO foi preenchido em pelo menos 25% e a vela fecha
    acima da abertura do dia. Armadilha: o veto original (`vender_gap_de_alta`, `len(h)==1`) so existe na 1a vela e a FAZER
    `gap_fade_fechamento` entra na seguinte (09:30). Aqui a condicao de mercado ('gap segurando') vale durante toda a janela da
    FAZER. Veto: gap de alta que segura acima de 75% do tamanho nao e fade. Geral (so gap relativo ao ATRd)."""
    h = ctx.hoje
    if len(h) < 2 or _hm(ctx) > 10 * 60 + 15:
        return None
    ont = float(ctx.diario.close.iloc[-1])
    ab = float(h.open.iloc[0])
    gap = ab - ont
    if gap < 0.15 * ctx.atrd:
        return None
    u = float(h.close.iloc[-1])
    if u > ont + 0.75 * gap and u > ab:
        return _ord(ctx, "venda", u + 100, ont, preco=u)


def v3_vender_com_minimas_ascendentes(ctx):
    """NAO FAZER: vender quando as minimas das ultimas 4 velas sobem em escada (cada minima > a anterior) e o fechamento esta acima da
    VWAP. Armadilha: escada de minimas = compradores defendendo cada recuo; a 'falha' do topo e so mais um degrau. Veto: nao vender
    com 4 minimas ascendentes sobre a VWAP. Geral (estrutura de preco, sem horario ou nivel). Entrada-armadilha: vende o fechamento,
    stop 1 ATR15, alvo 1 ATR15."""
    h = ctx.hoje
    if len(h) < 6 or not (10 * 60 <= _hm(ctx) <= 17 * 60):
        return None
    lo = h.low.iloc[-4:].values
    if all(lo[i] > lo[i - 1] for i in range(1, 4)) and h.close.iloc[-1] > _vwap(ctx):
        p = float(h.close.iloc[-1])
        return _ord(ctx, "venda", p + ctx.atr15, p - ctx.atr15, preco=p)


def v4_comprar_vela_vermelha_volume_seco_tarde(ctx):
    """NAO FAZER: comprar depois das 13:00 uma vela de baixa com volume < 70% da media do dia. Armadilha: recuo sem volume, depois da
    perna principal, nao e pullback com compradores (na vela das 13:00 deste dia o volume foi 62% da media e o robo comprou o fim
    da perna). Veto: nao comprar vela vermelha de volume seco na tarde. Provavelmente geral; mas dia lateral de tarde tem muito
    volume seco, entao pode cortar compra boa. Entrada-armadilha: compra o fechamento, stop 0,5 ATR15 abaixo da minima da vela, alvo 1,5R (a geometria da propria
    `recuo_a_favor_tendencia` que ela vetaria)."""
    h = ctx.hoje
    if len(h) < 8 or not (13 * 60 <= _hm(ctx) <= 17 * 60):
        return None
    u = h.iloc[-1]
    if u.close < u.open and u.vol < 0.7 * h.vol.iloc[:-1].mean():
        p = float(u.close)
        st = max(float(u.low - 0.5 * ctx.atr15), p - MAXR)
        return _ord(ctx, "compra", st, p + 1.5 * (p - st), preco=p)


def v5_vender_maximas_ascendentes_renovadas(ctx):
    """NAO FAZER: vender quando o dia renovou a maxima em >= 3 das ultimas 6 velas e o fechamento esta no terco superior da faixa do
    dia. Armadilha: topo que se renova a cada poucas velas nao e topo; o 'pavio de rejeicao' ou 'falha' e vendido e a maxima nova vem
    em seguida. Veto: nao vender com maximas renovadas repetidas. Geral (estrutura de preco). Entrada-armadilha: vende o
    fechamento, stop 1 ATR15, alvo 1 ATR15."""
    h = ctx.hoje
    if len(h) < 8 or not (10 * 60 <= _hm(ctx) <= 17 * 60):
        return None
    hh = h.high.cummax()
    novas = int((h.high.iloc[-6:] >= hh.shift(1).iloc[-6:]).sum())
    fx = float(h.high.max() - h.low.min())
    if novas >= 3 and fx > 0 and (h.close.iloc[-1] - h.low.min()) / fx > 0.67:
        p = float(h.close.iloc[-1])
        return _ord(ctx, "venda", p + ctx.atr15, p - ctx.atr15, preco=p)


FAZER = [
    ("P1 vetos de compra de rompimento so fora de dia direcional de alta (N4+N3 estreitados)", p1_n4_so_sem_alta_direcional, None),
    ("P2 falha_maxima so fora de dia direcional de alta", p2_falha_maxima_sem_alta_direcional, None),
    ("P3 gap_fade so se o gap falha + gap que segura continua", p3_gap_fade_so_se_o_gap_falha, None),
    ("P4 em dia direcional nenhum veto do lado da tendencia vale (exemplo: N3 embrulhado)", _sem_veto_a_favor_do_dia(r2506.n3_compra_rompimento_alta_manha), None),
    ("P3b gap que segura continua (parte nova de P3)", p3b_gap_que_segura_continua, None),
    ("P5 vetos N4+N3 so fora de gap de alta que segura", p5_n4_so_sem_gap_de_alta_seguro, None),
]
NAO_FAZER = [
    ("V1 vender em dia direcional de alta", v1_vender_em_dia_direcional_de_alta, None),
    ("V2 vender gap de alta que segura (ate 10:15)", v2_vender_gap_de_alta_nao_preenchido, None),
    ("V3 vender com 4 minimas ascendentes sobre a VWAP", v3_vender_com_minimas_ascendentes, None),
    ("V4 comprar vela vermelha de volume seco na tarde", v4_comprar_vela_vermelha_volume_seco_tarde, None),
    ("V5 vender com maximas renovadas no terco superior", v5_vender_maximas_ascendentes_renovadas, None),
]

# como cada proposta entra na v2
AJUSTES = {
    "P1": dict(sub_veto={V_N4_ALVO: p1_n4_so_sem_alta_direcional, V_N3_MANHA: p1_n3_so_sem_alta_direcional}),
    "P2": dict(sub_fazer={F_FALHA_MAX: p2_falha_maxima_sem_alta_direcional}),
    "P3": dict(sub_fazer={F_GAP_FADE: p3_gap_fade_so_se_o_gap_falha}, add_fazer=[("c2:P3b gap_que_segura_continua", p3b_gap_que_segura_continua, None)]),
    "P6": dict(sub_fazer={F_GAP_FADE: p3_gap_fade_so_se_o_gap_falha}, add_fazer=[("c2:P6 gap_segura_adaptativo", p3c_gap_que_segura_sem_alvo, gerir_adaptativo)]),
    "P4": dict(wrap_veto=_sem_veto_a_favor_do_dia),
    "P5": dict(sub_veto={V_N4_ALVO: p5_n4_so_sem_gap_de_alta_seguro, V_N3_MANHA: p5_n3_so_sem_gap_de_alta_seguro}),
    "V1": dict(add_veto=[("c2:V1 vender_dia_alta", v1_vender_em_dia_direcional_de_alta, None)]),
    "V2": dict(add_veto=[("c2:V2 vender_gap_que_segura", v2_vender_gap_de_alta_nao_preenchido, None)]),
    "V3": dict(add_veto=[("c2:V3 vender_minimas_ascendentes", v3_vender_com_minimas_ascendentes, None)]),
    "V4": dict(add_veto=[("c2:V4 comprar_vermelha_sem_volume", v4_comprar_vela_vermelha_volume_seco_tarde, None)]),
    "V5": dict(add_veto=[("c2:V5 vender_maximas_renovadas", v5_vender_maximas_ascendentes_renovadas, None)]),
}


def monta(fz, nf, chaves):
    fz, nf = list(fz), list(nf)
    for k in chaves:
        a = AJUSTES[k]
        for orig, fn in a.get("sub_fazer", {}).items():
            assert any(n == orig for n, _, _ in fz), orig
            fz = [(n, fn, g) if n == orig else (n, r, g) for n, r, g in fz]
        for orig, fn in a.get("sub_veto", {}).items():
            assert any(n == orig for n, _, _ in nf), orig
            nf = [(n, fn, g) if n == orig else (n, r, g) for n, r, g in nf]
        if "wrap_veto" in a:
            nf = [(n, a["wrap_veto"](r), g) for n, r, g in nf]
        fz += a.get("add_fazer", [])
        nf += a.get("add_veto", [])
    return fz, nf


# ---- avaliacao ---------------------------------------------------------------------------------------
def _dias_usados():
    import json
    j = json.load(open(AQUI / "dias_usados.json"))
    return (list(j["ciclo0"]["dias"]) + [x["dia"] for x in j["ciclo1"]["dias"]] + [x["dia"] for x in j["ciclo2"]["dias"]])


def _um(args):
    sys.path.insert(0, str(AQUI))
    import robo, robo_v2
    from regras import c2_2024_11_04 as c2
    chaves, dia = args
    fz, nf = robo_v2.monta_v2()
    fz, nf = c2.monta(fz, nf, chaves)
    tr, log, contra = robo_v2.roda_v2(dia, fz, nf)
    ok = [x for x in tr if x.t_ent]
    return chaves, dia, round(sum(x.brl for x in ok), 2), len(ok), [(x.fonte[:40], x.lado, str(x.t_ent.time()), x.motivo, round(x.brl, 1)) for x in ok]


def avalia(configs, dias, workers=11):
    from concurrent.futures import ProcessPoolExecutor, as_completed
    res = {tuple(c): {} for c in configs}
    with ProcessPoolExecutor(workers) as ex:
        fut = [ex.submit(_um, (tuple(c), d)) for c in configs for d in dias]
        for f in as_completed(fut):
            ch, d, brl, ops, tr = f.result()
            res[ch][d] = (brl, ops, tr)
    return res


def isolada(dia, regra, gerir=None):
    import base
    return base.resumo(base.simula_dia(dia, regra, gerir, max_ops=3))


DIA = "2024-11-04"

if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "dia"
    if modo == "dia":
        for grupo, lista in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
            for nome, r, g in lista:
                res = isolada(DIA, r, g)
                print(f"{grupo:9s} {nome[:62]:62s} isolada R$ {res['brl']:8.2f} ops {res['ops']}", flush=True)
        cfgs = [()] + [(k,) for k in AJUSTES]
        res = avalia(cfgs, [DIA])
        for c in cfgs:
            b = res[c][DIA]
            print(f"{'+'.join(c) or 'BASE':8s} robo R$ {b[0]:8.2f} ops {b[1]}", [(t[0][:30], t[1], t[2], t[3], t[4]) for t in b[2]], flush=True)
    else:
        import json
        dias = _dias_usados()
        cfgs = [()] + [(k,) for k in AJUSTES]
        res = avalia(cfgs, dias)
        b = res[()]
        base_tot = sum(v[0] for v in b.values())
        print(f"BASE v2: R$ {base_tot:.2f} em {len(dias)} dias")
        for c in cfgs[1:]:
            r = res[c]
            tot = sum(v[0] for v in r.values())
            pi = sorted((round(r[d][0] - b[d][0], 2), d) for d in r if r[d][0] < b[d][0] - 0.005)
            me = sorted((round(r[d][0] - b[d][0], 2), d) for d in r if r[d][0] > b[d][0] + 0.005)
            print(f"{'+'.join(c):6s} dia {r[DIA][0]:8.2f}  conj {tot:9.2f} (delta {tot - base_tot:+9.2f})  piorou {len(pi)} {pi}  melhorou {len(me)} {me}", flush=True)
        json.dump({"+".join(c): {d: v for d, v in r.items()} for c, r in res.items()}, open(sys.argv[2] if len(sys.argv) > 2 else "NUL", "w"), default=str)
