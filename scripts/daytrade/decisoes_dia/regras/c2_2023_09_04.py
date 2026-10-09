"""Ciclo 2, dia 2023-09-04 (WIN, "ruim", rotacao ef 0,016; v1 -R$126,25, v2 -R$126,25).

Pregao: abre 119.300, comprime 09:00-10:00 (faixa 119.045-119.515, ~470 pts), explode a partir das 10:15 (volume 2-3x) ate
120.135 (11:00) e devolve TUDO ate o fim: fecha 119.405 (~100 pts da abertura). Rali de ~1.090 pts seguido de queda lenta.
O robo (v2) fez 2 operacoes: F2 `vende falha da maxima matinal` as 10:00 no FUNDO da faixa (119.085, stop 119.515) e foi
stopado 19 min depois pela explosao (-R$88); e `recuo_a_favor_tendencia` as 11:30, no topo do rali (119.955), stop (-R$38,25).

Contem: FAZER (5) e NAO_FAZER (5), cada um com docstring; AJUSTES (como cada proposta entra no robo v2); `monta`, `avalia`.
`python -m regras.c2_2023_09_04` imprime o resultado no dia (isolada e dentro do robo v2) e o efeito nos 50 dias usados.
Nada de r_*.py, robo.py ou robo_v2.py e editado: as variantes montam as listas em memoria.
"""
import pandas as pd

H1 = pd.Timedelta(hours=1)
CAP = 590.0  # risco maximo por contrato (6% de R$2.000)


def _hm(ctx):
    return ctx.t.hour * 60 + ctx.t.minute


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _vwap(h):
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).sum() / h.vol.sum())


def _p1(h):
    return h[h.index < h.index[0] + H1]


def _ord(ctx, lado, k_stop, k_alvo, stop=None):
    p = float(ctx.hoje.close.iloc[-1])
    r = min(k_stop * ctx.atr15, CAP) if stop is None else min(abs(p - stop), CAP)
    if lado == "compra":
        return dict(lado=lado, preco=p, stop=p - r, alvo=p + k_alvo * ctx.atr15, contratos=1)
    return dict(lado=lado, preco=p, stop=p + r, alvo=p - k_alvo * ctx.atr15, contratos=1)



def gerir_adaptativo(ctx, pos):
    """GESTAO ADAPTATIVA (sem alvo fixo). Estado observado: excursao a favor desde a entrada em ATR15 (forca da perna) e ATR15
    atual (volatilidade). (1) excursao >= 1 ATR15: stop vai para o preco de entrada (zero a zero, sem pagar o custo de 10 pts);
    (2) trailing pela extrema favoravel desde a entrada: distancia 1,5 ATR15 enquanto a excursao < 3 ATR15 (deixa respirar) e
    1,0 ATR15 depois (perna forte e esticada: protege o lucro); o ATR e o da vela atual, entao encolhe com a volatilidade.
    O stop so anda a favor (o motor garante)."""
    h = ctx.hoje
    h = h[h.index >= pos["t_ent"].floor("15min")]
    if len(h) < 1:
        return None
    a = ctx.atr15
    if pos["lado"] == "venda":
        ext = float(h.low.min()); exc = (pos["preco"] - ext) / a
        d = 1.5 if exc < 3 else 1.0
        ns = ext + d * a
        if exc >= 1.0:
            ns = min(ns, pos["preco"] - 10)
            return ns
        return None
    ext = float(h.high.max()); exc = (ext - pos["preco"]) / a
    d = 1.5 if exc < 3 else 1.0
    ns = ext - d * a
    if exc >= 1.0:
        return max(ns, pos["preco"] + 10)
    return None


# =====================================================================================================
# 5 maneiras de deixar o dia positivo
# =====================================================================================================

# ---- P1 (FAZER nova, reversao a VWAP): vender o rali esticado ---------------------------------------
def p1_vende_rali_esticado_da_vwap(ctx):
    """FAZER nova (reversao a media). Vende quando o fechamento esta >= 1,5 ATR15 ACIMA do VWAP do dia, depois de a vela
    ter subido (close > open) e ainda assim ficar abaixo da maxima do dia + ja ter passado 1h de pregao. Stop inicial 1 ATR15 acima
    do fechamento, SEM alvo: gestao adaptativa (`gerir_adaptativo`: break-even com 1 ATR15 a favor, trailing 1,5 -> 1,0 ATR15). Janela 10:45-13:30.
    Neste dia: 11:00, fechamento 120.005 contra VWAP 119.480 (+1,9 ATR15) apos subir 1.000 pts em 45 min; o dia devolveu
    tudo. Condicao de mercado: esticada em dia sem ancoragem direcional (VWAP chato antes da explosao). Em dia de tendencia
    forte o preco FICA esticado (a venda perde): por isso so uma tentativa por dia e o alvo e curto. Natureza: reversao.
    Geral? parcialmente (reversao a VWAP e fundamento classico, mas nos dias 'bons' tende a perder)."""
    h = ctx.hoje
    if len(h) < 8 or not (10 * 60 + 45 <= _hm(ctx) <= 13 * 60 + 30):
        return None
    vw = _vwap(h)
    u = h.iloc[-1]
    if u.close >= vw + 1.5 * ctx.atr15 and u.close > u.open and u.high < h.high.max() + 1:
        p = float(u.close)
        r = min(1.0 * ctx.atr15, CAP)
        return dict(lado="venda", preco=p, stop=p + r, alvo=None, contratos=1)


# ---- P2 (AJUSTE de FAZER): rompe_faixa_1h com alvo de 1R ---------------------------------------------
def p2_rompe_faixa_1h_alvo_1r(ctx):
    """AJUSTE de `2024_06_18:rompe_faixa_1h` (alvo 1,5R -> 1R). O gatilho original (fechamento acima da maxima da 1a hora com
    corpo >= 0,4 ATR15, faixa da 1a hora < 0,6 ATR diario, stop no meio da faixa) comprou 119.700 as 10:30 e o rali foi 435 pts
    (120.135): nao chegou em 1,5R (630 pts), voltou e stopou (-R$83). Com alvo 1R (420 pts) bate 120.130+10. Logica: depois da
    explosao inicial o primeiro impulso raramente da 1,5R em dia de rotacao; sair no 1R paga o impulso. Natureza: ajuste de saida.
    Geral? nao: o 1R so ganha se o impulso passou de 420 pts (aqui por 5 pts) - tratar como AJUSTADA AO DIA ate o conjunto provar."""
    h = ctx.hoje
    t = ctx.t
    if not (10 * 60 + 15 <= _hm(ctx) <= 12 * 60) or len(h) < 5:
        return None
    pri = _p1(h)
    hi, lo = pri.high.max(), pri.low.min()
    if (hi - lo) > 0.6 * ctx.atrd:
        return None
    u = h.iloc[-1]
    if abs(u.close - u.open) < 0.4 * ctx.atr15 or len(h) < 5 or u.vol < 1.5 * h.vol.iloc[:-1].mean():
        return None
    mid = (hi + lo) / 2
    if u.close > hi and h.high.iloc[:-1].max() <= hi + 50 and abs(u.close - mid) <= CAP:
        return dict(lado="compra", preco=float(u.close), stop=mid, alvo=float(u.close + (u.close - mid)), contratos=1)
    if u.close < lo and h.low.iloc[:-1].min() >= lo - 50 and abs(u.close - mid) <= CAP:
        return dict(lado="venda", preco=float(u.close), stop=mid, alvo=float(u.close - (mid - u.close)), contratos=1)


# ---- P3 (FAZER nova, devolucao da perna): perdeu o ponto medio do dia depois da expansao -------------
def p3_vende_perde_ponto_medio_do_dia(ctx):
    """FAZER nova. Depois de uma perna grande (maxima - minima do dia >= 3,5 ATR15) e de a maxima ter ficado para tras
    (>= 8 velas sem maxima nova), o fechamento perde o ponto medio da faixa do dia (maxima+minima)/2 pela PRIMEIRA vez
    desde 11:00: vende, stop 1,8 ATR15 acima do fechamento, SEM alvo (`gerir_adaptativo`). Janela 12:30-15:00.
    Neste dia: perna 1.090 pts (4 ATR15), medio 119.590; as 13:30 a vela perde 119.535 (fecha abaixo) e o preco foi
    119.310 (14:30) e 119.130 (15:00). Condicao: perna esgotada, preco devolvendo metade. Natureza: devolucao / exaustao.
    Geral? provavelmente em dias de rotacao; em dia de tendencia a perna volta a andar e o stop de 1 ATR15 protege."""
    h = ctx.hoje
    if len(h) < 16 or not (12 * 60 + 30 <= _hm(ctx) <= 15 * 60):
        return None
    hi, lo = h.high.max(), h.low.min()
    if (hi - lo) < 3.5 * ctx.atr15:
        return None
    n_sem_max = len(h) - 1 - int(h.high.values.argmax())
    if n_sem_max < 8:
        return None
    mid = (hi + lo) / 2
    cl = h.close
    # primeira vez que perde o ponto medio: fechamento atual < mid e todos os anteriores (apos a maxima) >= mid
    imax = int(h.high.values.argmax())
    if cl.iloc[-1] < mid and (cl.iloc[imax:-1] >= mid).all():
        p = float(cl.iloc[-1])
        stop = p + 1.8 * ctx.atr15  # stop largo: o preco volta a testar o ponto medio antes de cair; gestao adaptativa protege
        if stop - p > CAP:
            stop = p + CAP
        return dict(lado="venda", preco=p, stop=stop, alvo=None, contratos=1)


# ---- P4 (FAZER nova, rompimento de contracao da tarde) -----------------------------------------------
def p4_vende_rompe_contracao_da_tarde(ctx):
    """FAZER nova (rompimento de compressao, so a favor da deriva do dia). Apos 13:30, as 6 velas anteriores formam uma faixa
    estreita (maxima - minima <= 2,5 ATR15; aqui a faixa 12:45-14:15 tem 305 pts) e a ultima vela fecha ABAIXO da minima
    dessa faixa com volume >= 1,3x a media das 6 e o preco abaixo do VWAP: vende, stop 1,2 ATR15, alvo 1 ATR15. Neste dia: 14:30-14:45 a vela de 434k contra media ~230k fecha 119.310 abaixo de 119.530 -> -265 pts em 30 min.
    Condicao: dia ja abaixo do VWAP e contracao seguida de expansao com volume. Natureza: rompimento de compressao.
    Geral? provavelmente (compressao + volume e fundamento amplo), mas e a mesma familia do rompimento da 1a hora, so que na tarde."""
    h = ctx.hoje
    if len(h) < 10 or not (13 * 60 + 30 <= _hm(ctx) <= 16 * 60):
        return None
    ant = h.iloc[-7:-1]
    u = h.iloc[-1]
    hi, lo = ant.high.max(), ant.low.min()
    if (hi - lo) > 2.5 * ctx.atr15:
        return None
    if u.close < lo and u.vol >= 1.3 * ant.vol.mean() and u.close < _vwap(h):
        p = float(u.close)
        stop = p + 1.2 * ctx.atr15
        return dict(lado="venda", preco=p, stop=min(stop, p + CAP), alvo=p - 1.0 * ctx.atr15, contratos=1)


# ---- P5 (FAZER nova, reversao no fim do dia): comprar a esticada abaixo da VWAP ------------------------
def p5_compra_esticada_abaixo_vwap_tarde(ctx):
    """FAZER nova (espelho tardio de P1, mas com gatilho de exaustao proprio: vela que RETOMA). Depois de 14:30, o fechamento
    esta >= 1,5 ATR15 abaixo do VWAP do dia e a vela e de alta (close > open): compra, stop abaixo da minima da vela - 20 (cap 590), alvo = fechamento + 0,5 da distancia
    ate o VWAP. Neste dia: 15:30 (vela 15:15: 119.185-119.335, fecha 119.325) o preco estava 270 pts abaixo do VWAP
    (1,8 ATR15) e voltou +135 (119.460). Condicao: VWAP muito distante no fim do dia sem tendencia, preco puxado de volta.
    Natureza: reversao de fim de dia. Geral? fraca; no dia de tendencia que fecha no extremo o preco nao volta (perde o stop)."""
    h = ctx.hoje
    if len(h) < 20 or not (14 * 60 + 30 <= _hm(ctx) <= 16 * 60 + 15):
        return None
    vw = _vwap(h)
    u = h.iloc[-1]
    rng = max(u.high - u.low, 1.0)
    if u.close <= vw - 1.5 * ctx.atr15 and u.close > u.open:
        p = float(u.close)
        stop = max(p - CAP, float(u.low - 20))
        return dict(lado="compra", preco=p, stop=stop, alvo=p + 0.5 * (vw - p), contratos=1)


# =====================================================================================================
# 5 coisas a NAO fazer (cada uma = condicao de mercado, independente do gatilho)
# =====================================================================================================

def n1_vender_no_fundo_da_faixa_estreita(ctx):
    """NAO FAZER: vender com o fechamento no FUNDO de uma faixa estreita do comeco do dia (fechamento a <= 25% da faixa
    do dia acima da minima do dia, faixa do dia <= 3 ATR15, antes das 10:30). Armadilha: o preco esta onde o rompimento para
    baixo ja foi testado e comprimido; quem vende ai paga o stop longe (topo da faixa) e a primeira expansao de volume
    e para cima ou para baixo com 50% de chance - mas o payoff e ruim (stop de 430 pts, alvo curto). Neste dia: F2 vendeu
    119.085 (faixa 119.045-119.515, posicao 8%), stop de 430 pts, explosao para cima: -R$88. Independente do gatilho de venda."""
    h = ctx.hoje
    if len(h) < 4 or _hm(ctx) > 10 * 60 + 30:
        return None
    hi, lo = h.high.max(), h.low.min()
    if (hi - lo) <= 3.0 * ctx.atr15 and (h.close.iloc[-1] - lo) <= 0.25 * (hi - lo):
        return _ord(ctx, "venda", 1.5, 1.0)


def n2_comprar_o_topo_esticado_do_rali(ctx):
    """NAO FAZER: comprar com o fechamento >= 1,2 ATR15 ACIMA do VWAP depois de a ultima maxima do dia ja ter ficado para tras
    (>= 3 velas sem maxima nova) e o volume da vela < media das 4 anteriores. Armadilha: 'recuo a favor' comprado no topo
    de uma perna que ja perdeu forca (volume secando) - o risco ate o stop e a favor do vendedor. Neste dia: 11:30 compra a
    119.955 (VWAP 119.596, +1,4 ATR15; maxima 120.135 as 11:00, 3 velas antes, volume 257k vs 400k+): stop -R$38,25 e o dia
    inteiro devolveu 650 pts. Independente do gatilho de compra."""
    h = ctx.hoje
    if len(h) < 8 or _hm(ctx) < 10 * 60 + 30:
        return None
    imax = int(h.high.values.argmax())
    if len(h) - 1 - imax < 2:
        return None
    u = h.iloc[-1]
    if u.close >= _vwap(h) + 1.2 * ctx.atr15 and u.vol < h.vol.iloc[-5:-1].mean():
        return _ord(ctx, "compra", 1.0, 1.0)


def n3_comprar_na_tarde_abaixo_do_vwap_descendente(ctx):
    """NAO FAZER: comprar depois das 12:30 com o fechamento abaixo do VWAP E com o VWAP caindo (VWAP de 4 velas atras maior
    que o atual) E a EMA20 M15 caindo. Armadilha: compra de 'queda' contra a deriva tardia (preco e media apontam para baixo,
    sem ancoragem de compradores). Neste dia: 12:45-14:00 as compras (faixa_tarde / recuo) deram -R$27 a -R$67 cada.
    Independente do gatilho de compra."""
    h = ctx.hoje
    if len(h) < 12 or _hm(ctx) < 12 * 60 + 30:
        return None
    u = h.iloc[-1]
    v_ant = _vwap(h.iloc[:-4])
    e = _ema(ctx.m15.close, 20)
    if u.close < _vwap(h) and _vwap(h) < v_ant and e.iloc[-1] < e.iloc[-4]:
        return _ord(ctx, "compra", 1.0, 1.0)


def n4_vender_com_preco_ja_esticado_para_baixo(ctx):
    """NAO FAZER: vender com o fechamento >= 2 ATR15 ABAIXO do VWAP e a ultima vela fazendo minima nova das ultimas 8 velas
    (vender o fundo esticado). Armadilha: esticada e falta de papel vendedor novo; o payoff e de stop. Neste dia: 15:15
    `vende_minima_nova_tarde` -R$62 (VWAP 119.607, preco 119.190: -2,6 ATR15, minima nova de 2h).
    Independente do gatilho de venda."""
    h = ctx.hoje
    if len(h) < 12 or _hm(ctx) < 11 * 60:
        return None
    u = h.iloc[-1]
    if u.close <= _vwap(h) - 2.0 * ctx.atr15 and u.low <= h.low.iloc[-9:-1].min():
        return _ord(ctx, "venda", 1.0, 1.0)


def _serrilhado(ctx):
    h = ctx.hoje
    if len(h) < 14 or not (12 * 60 <= _hm(ctx) <= 15 * 60 + 30):
        return False
    e = _ema(ctx.m15.close, 20)
    c = h.close.iloc[-8:]
    ee = e.loc[c.index]
    lado = (c > ee).astype(int).diff().abs().sum()  # numero de cruzamentos da EMA20 nas 8 velas
    inclin = abs(e.iloc[-1] - e.iloc[-8]) / ctx.atr15
    return lado >= 2 and inclin < 0.35


def n5_compra_no_serrilhado(ctx):
    """NAO FAZER (compra): entre 12:00 e 15:30, o preco cruzou a EMA20 M15 >= 2 vezes nas ultimas 8 velas e a inclinacao da EMA20
    em 8 velas e < 0,35 ATR15 (serrilhado colado na media). Armadilha: sem direcao, entrada em 'pullback' nao tem de onde
    voltar; o stop de 1 ATR fica dentro do ruido. Neste dia: 12:00-14:00 as velas ficaram coladas em EMA20/VWAP (119.600-119.700).
    (A versao para VENDA e n5v abaixo; as duas entram juntas como UMA proposta.) Independente do gatilho."""
    if _serrilhado(ctx):
        return _ord(ctx, "compra", 1.0, 1.0)


def n5v_venda_no_serrilhado(ctx):
    """Lado de venda de N5 (mesma condicao de mercado). Neste dia: `venda pullback EMA20` 13:45: -R$53,63."""
    if _serrilhado(ctx):
        return _ord(ctx, "venda", 1.0, 1.0)


def _vol_forte(ctx):
    h = ctx.hoje
    return len(h) >= 5 and h.vol.iloc[-1] >= 1.5 * h.vol.iloc[:-1].mean()


def v_alvo_curto_so_sem_volume(ctx):
    """AJUSTE de veto `2023_11_03:Comprar rompimento com alvo menor que o stop`: so veta se o rompimento NAO teve expansao de
    volume (vela < 1,5x a media das 8 anteriores). Rompimento com volume forte e participacao, nao armadilha."""
    from regras import r_2023_11_03 as r
    return None if _vol_forte(ctx) else r.n4_comprar_com_alvo_curto(ctx)


def v_n3_manha_so_sem_volume(ctx):
    """AJUSTE de veto `2025_06_04:N3 comprar rompimento da manha`: idem, so veta rompimento sem expansao de volume."""
    from regras import r_2025_06_04 as r
    return None if _vol_forte(ctx) else r.n3_compra_rompimento_alta_manha(ctx)


FAZER = [("P1 vende rali esticado da VWAP", p1_vende_rali_esticado_da_vwap, None),
         ("P2 rompe faixa 1h alvo 1R (ajuste)", p2_rompe_faixa_1h_alvo_1r, None),
         ("P3 vende perda do ponto medio do dia", p3_vende_perde_ponto_medio_do_dia, None),
         ("P4 vende rompimento de contracao da tarde", p4_vende_rompe_contracao_da_tarde, None),
         ("P5 compra esticada abaixo do VWAP na tarde", p5_compra_esticada_abaixo_vwap_tarde, None)]
NAO_FAZER = [("N1 vender no fundo da faixa estreita", n1_vender_no_fundo_da_faixa_estreita, None),
             ("N2 comprar o topo esticado do rali", n2_comprar_o_topo_esticado_do_rali, None),
             ("N3 comprar na tarde abaixo do VWAP descendente", n3_comprar_na_tarde_abaixo_do_vwap_descendente, None),
             ("N4 vender o fundo esticado", n4_vender_com_preco_ja_esticado_para_baixo, None),
             ("N5 operar no serrilhado (compra)", n5_compra_no_serrilhado, None)]

# como cada proposta entra no robo v2 (listas em memoria). add_fazer = no FIM da lista de FAZER; add_veto = no fim dos vetos.
AJUSTES = {
    "P1": dict(add_fazer=[("c2:P1 vende rali esticado da VWAP", p1_vende_rali_esticado_da_vwap, gerir_adaptativo)]),
    "P2": dict(add_fazer_front=[("c2:P2 rompe faixa 1h com volume, alvo 1R", p2_rompe_faixa_1h_alvo_1r, None)],
               sub_veto={"2023_11_03:Comprar rompimento com alvo menor que o stop": (v_alvo_curto_so_sem_volume, None),
                         "2025_06_04:N3 comprar rompimento da manha": (v_n3_manha_so_sem_volume, None)}),
    "P3": dict(add_fazer=[("c2:P3 vende perda do ponto medio", p3_vende_perde_ponto_medio_do_dia, gerir_adaptativo)]),
    "P4": dict(add_fazer=[("c2:P4 vende rompe contracao tarde", p4_vende_rompe_contracao_da_tarde, None)]),
    "P5": dict(add_fazer=[("c2:P5 compra esticada abaixo VWAP", p5_compra_esticada_abaixo_vwap_tarde, None)]),
    "N1": dict(add_veto=[("c2:N1 vender fundo faixa estreita", n1_vender_no_fundo_da_faixa_estreita, None)]),
    "N2": dict(add_veto=[("c2:N2 comprar topo esticado", n2_comprar_o_topo_esticado_do_rali, None)]),
    "N3": dict(add_veto=[("c2:N3 comprar tarde VWAP desc", n3_comprar_na_tarde_abaixo_do_vwap_descendente, None)]),
    "N4": dict(add_veto=[("c2:N4 vender fundo esticado", n4_vender_com_preco_ja_esticado_para_baixo, None)]),
    "N5": dict(add_veto=[("c2:N5 serrilhado compra", n5_compra_no_serrilhado, None),
                         ("c2:N5v serrilhado venda", n5v_venda_no_serrilhado, None)]),
}


def monta(fz, nf, chaves):
    fz, nf = list(fz), list(nf)
    for k in chaves:
        a = AJUSTES[k]
        for orig, (fn, g) in a.get("sub_veto", {}).items():
            nf = [(n, fn, g) if n == orig else (n, r, gg) for n, r, gg in nf]
        fz = list(a.get("add_fazer_front", [])) + fz + list(a.get("add_fazer", []))
        nf = nf + list(a.get("add_veto", []))
    return fz, nf


# ---- avaliacao ---------------------------------------------------------------------------------------
DIA = "2023-09-04"


def _dias_usados():
    import json
    from pathlib import Path
    j = json.load(open(Path(__file__).resolve().parents[1] / "dias_usados.json"))
    return (list(j["ciclo0"]["dias"]) + [x["dia"] for x in j["ciclo1"]["dias"]]
            + [x["dia"] for x in j["ciclo2"]["dias"]])


def _um(args):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import robo, robo_v2
    from regras import c2_2023_09_04 as c2
    chaves, dia = args
    fz, nf = robo_v2.monta_v2()
    fz, nf = c2.monta(fz, nf, chaves)
    import os; tr, log, contra = robo_v2.roda_v2(dia, fz, nf, estrutural=bool(os.environ.get("C2_EST")))
    ok = [x for x in tr if x.t_ent]
    return chaves, dia, round(sum(x.brl for x in ok), 2), len(ok), [(x.fonte[:45], x.lado, str(x.t_ent.time()), x.motivo, round(x.brl, 1)) for x in ok]


def avalia(configs, dias=None, workers=10):
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


if __name__ == "__main__":
    import sys, json
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    for grupo, lista in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, g in lista:
            res = isolada(DIA, r, g)
            print(f"{grupo:9s} {nome:50s} isolada R$ {res['brl']:8.2f} ops {res['ops']}", flush=True)
            for x in res["lista"]:
                print("     ", x["lado"], x["sinal"], x["ent"], x["preco"], "stop", x["stop"], "alvo", x["alvo"], "->", x["sai"], x["preco_sai"], x["motivo"], x["brl"])
    base_c = [()] + [(k,) for k in AJUSTES]
    res = avalia(base_c)
    b = res[()]
    print("\nconfig | R$ no dia | R$ conjunto (50 dias) | dias que pioraram | dias que melhoraram")
    out = {}
    for c, r in res.items():
        tot = sum(v[0] for v in r.values())
        pi = [d for d in r if r[d][0] < b[d][0] - 0.005]
        me = [d for d in r if r[d][0] > b[d][0] + 0.005]
        out["+".join(c) or "BASE"] = dict(dia=r[DIA][0], conj=round(tot, 2), pioraram=pi, melhoraram=me,
                                           delta=round(tot - sum(v[0] for v in b.values()), 2),
                                           por_dia={d: v[0] for d, v in r.items()})
        print(f"{'+'.join(c) or 'BASE':6s} dia {r[DIA][0]:8.2f}  conj {tot:9.2f}  piorou {len(pi)}  melhorou {len(me)}", flush=True)
    json.dump(out, open(r"C:/Users/Jeffe/AppData/Local/Temp/claude/c--Users-Jeffe-Documents-study-meta/954f8ffb-cd41-4ca6-a2a4-a376310b6ecf/scratchpad/c2_numeros.json", "w"), indent=1)
