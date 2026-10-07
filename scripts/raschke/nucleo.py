"""Nucleo puro das estrategias de Linda Raschke (Street Smarts, 1995).

Sem I/O. Cada setup e' uma funcao `ordens_*` que olha o FECHAMENTO da barra i
e devolve ordens-stop para as barras seguintes (sem look-ahead). O simulador
`simular` executa essas ordens barra a barra. Cada funcao tem espelho 1:1 no
EA `mt5/Raschke.mq5` (mesmos nomes de regra) -- mexeu aqui, mexa la.

Fonte das regras: texto integral do livro (caps. 3-10). Onde o livro e'
ambiguo, a escolha esta no docstring do setup e vira PARAMETRO da varredura.
Premissa declarada: os gatilhos do livro sao ordens-STOP (rompimento); isso e'
o proprio setup, nao da' para convertê-lo em limite sem mudar a estrategia.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


# --------------------------------------------------------------------------
# dados
# --------------------------------------------------------------------------
@dataclass
class Barras:
    """Serie OHLC. `dia` = id inteiro do pregao (igual p/ barras do mesmo dia);
    `intraday` liga o achatamento no fim do dia e a logica de 1a hora."""

    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    dia: np.ndarray
    minuto: np.ndarray  # minuto do dia (0..1439) do INICIO da barra
    intraday: bool = False
    barras_por_hora: int = 12

    def __len__(self) -> int:
        return len(self.c)


@dataclass(frozen=True)
class Ordem:
    i: int            # barra do sinal (fechamento de i)
    lado: int         # +1 compra, -1 venda
    entrada: float    # preco da ordem stop
    stop: float
    alvo: float | None = None   # alvo "de swing" (so' Holy Grail)
    validade: int = 1           # barras de vida (>=1); 0 = ate o fim do dia
    setup: str = ""


@dataclass(frozen=True)
class Saida:
    alvo_r: float | None = None     # alvo = fill +/- alvo_r * risco
    alvo_swing: bool = False        # usa Ordem.alvo (Holy Grail)
    trail_n: int = 0                # stop acompanha min/max das ultimas n barras
    max_barras: int = 0             # saida a mercado no fechamento da barra N (0=nunca)
    eod: bool = False               # intraday: fecha no ultimo pregao do dia
    pinball: bool = False           # carrega overnight se no lucro; sai abertura seguinte


@dataclass(frozen=True)
class Custo:
    tick: float
    valor_ponto: float       # R$ por ponto de preco, por unidade
    qty: float               # unidades por trade
    fee_brl: float = 0.0     # taxa fixa round-trip por trade
    pct_lado: float = 0.0    # custo percentual do nocional, por lado
    risco_min_ticks: float = 2.0


@dataclass
class Trade:
    i_sinal: int
    i_entrada: int
    i_saida: int
    lado: int
    entrada: float
    saida: float
    risco: float
    pnl_pts: float
    pnl_brl: float
    r: float
    motivo: str
    setup: str = ""


# --------------------------------------------------------------------------
# indicadores (puros)
# --------------------------------------------------------------------------
def sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    cs = np.cumsum(np.insert(x.astype(float), 0, 0.0))
    out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def ema(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    k = 2.0 / (n + 1.0)
    out[n - 1] = float(np.mean(x[:n]))
    for t in range(n, len(x)):
        out[t] = out[t - 1] + k * (x[t] - out[t - 1])
    return out


def wilder(x: np.ndarray, n: int) -> np.ndarray:
    """Media de Wilder: semente = SMA das n primeiras, depois (prev*(n-1)+x)/n."""
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    out[n - 1] = float(np.mean(x[:n]))
    for t in range(n, len(x)):
        out[t] = (out[t - 1] * (n - 1) + x[t]) / n
    return out


def atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    tr = np.empty(len(c))
    tr[0] = h[0] - l[0]
    pc = c[:-1]
    tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - pc), np.abs(l[1:] - pc)))
    return wilder(tr, n)


def adx(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    """ADX de Wilder (+DI, -DI -> DX -> media de Wilder do DX)."""
    m = len(c)
    out = np.full(m, np.nan)
    if m < 2 * n + 1:
        return out
    up = h[1:] - h[:-1]
    dn = l[:-1] - l[1:]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    # suavizacao por soma (Wilder): s = s - s/n + x
    s_tr = np.empty(m - 1)
    s_p = np.empty(m - 1)
    s_m = np.empty(m - 1)
    s_tr[n - 1], s_p[n - 1], s_m[n - 1] = tr[:n].sum(), pdm[:n].sum(), mdm[:n].sum()
    for t in range(n, m - 1):
        s_tr[t] = s_tr[t - 1] - s_tr[t - 1] / n + tr[t]
        s_p[t] = s_p[t - 1] - s_p[t - 1] / n + pdm[t]
        s_m[t] = s_m[t - 1] - s_m[t - 1] / n + mdm[t]
    dx = np.full(m - 1, np.nan)
    for t in range(n - 1, m - 1):
        if s_tr[t] > 0:
            pdi = 100.0 * s_p[t] / s_tr[t]
            mdi = 100.0 * s_m[t] / s_tr[t]
            den = pdi + mdi
            dx[t] = 100.0 * abs(pdi - mdi) / den if den > 0 else 0.0
        else:
            dx[t] = 0.0
    a = np.full(m - 1, np.nan)
    first = 2 * n - 2
    a[first] = float(np.mean(dx[n - 1:first + 1]))
    for t in range(first + 1, m - 1):
        a[t] = (a[t - 1] * (n - 1) + dx[t]) / n
    out[1:] = a
    return out


def rsi_de_serie(x: np.ndarray, n: int) -> np.ndarray:
    """RSI de Wilder aplicado a uma serie arbitraria (usa x[t]-x[t-1])."""
    out = np.full(len(x), np.nan)
    if len(x) < n + 1:
        return out
    d = np.diff(x)
    g = np.where(d > 0, d, 0.0)
    p = np.where(d < 0, -d, 0.0)
    ag = float(np.mean(g[:n]))
    ap = float(np.mean(p[:n]))
    out[n] = 100.0 if ap == 0 else 100.0 - 100.0 / (1.0 + ag / ap)
    for t in range(n, len(d)):
        ag = (ag * (n - 1) + g[t]) / n
        ap = (ap * (n - 1) + p[t]) / n
        out[t + 1] = 100.0 if ap == 0 else 100.0 - 100.0 / (1.0 + ag / ap)
    return out


def lbr_rsi(c: np.ndarray, n: int = 3) -> np.ndarray:
    """Momentum Pinball: RSI(n) do ROC(1)  (ROC1 = c[t]-c[t-1]; 'studies on studies')."""
    roc1 = np.concatenate([[np.nan], np.diff(c)])
    out = np.full(len(c), np.nan)
    sub = rsi_de_serie(roc1[1:], n)
    out[1:] = sub
    return out


def estocastico_anti(h: np.ndarray, l: np.ndarray, c: np.ndarray,
                     k_n: int = 7, suav: int = 4, d_n: int = 10) -> tuple[np.ndarray, np.ndarray]:
    """Anti (livro): %K de 7 com suavizacao 4 = linha rapida; %D = SMA10 da rapida."""
    m = len(c)
    raw = np.full(m, np.nan)
    for t in range(k_n - 1, m):
        hh = h[t - k_n + 1:t + 1].max()
        ll = l[t - k_n + 1:t + 1].min()
        raw[t] = 50.0 if hh == ll else 100.0 * (c[t] - ll) / (hh - ll)
    fast = sma(np.nan_to_num(raw, nan=50.0), suav)
    fast[:k_n + suav - 2] = np.nan
    slow = sma(np.nan_to_num(fast, nan=50.0), d_n)
    slow[:k_n + suav + d_n - 3] = np.nan
    return fast, slow


def osc_3_10(h: np.ndarray, l: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """3-10: rapida = SMA3 - SMA10 do preco medio; lenta = SMA16 da rapida."""
    m = (h + l) / 2.0
    fast = sma(m, 3) - sma(m, 10)
    slow = sma(np.nan_to_num(fast, nan=0.0), 16)
    slow[:10 + 16 - 2] = np.nan
    return fast, slow


# --------------------------------------------------------------------------
# agregados diarios (para 80-20 e Pinball em base intraday)
# --------------------------------------------------------------------------
def agregado_diario(b: Barras) -> dict[str, np.ndarray]:
    """Por BARRA: ohlc do pregao ANTERIOR e posicao dentro do pregao atual."""
    n = len(b)
    po = np.full(n, np.nan); ph = np.full(n, np.nan)
    pl = np.full(n, np.nan); pc = np.full(n, np.nan)
    idx_dia = np.zeros(n, dtype=int)
    ini = 0
    dias = []  # (ini, fim_exclusivo)
    for t in range(1, n + 1):
        if t == n or b.dia[t] != b.dia[ini]:
            dias.append((ini, t))
            ini = t
    d_o = np.array([b.o[a] for a, _ in dias]); d_h = np.array([b.h[a:z].max() for a, z in dias])
    d_l = np.array([b.l[a:z].min() for a, z in dias]); d_c = np.array([b.c[z - 1] for _, z in dias])
    rsi_d = lbr_rsi(d_c, 3)
    rng = d_h - d_l
    rng_med = sma(rng, 20)
    rsi_prev = np.full(n, np.nan); rng_ratio = np.full(n, np.nan)
    for k, (a, z) in enumerate(dias):
        idx_dia[a:z] = np.arange(z - a)
        if k >= 1:
            po[a:z], ph[a:z], pl[a:z], pc[a:z] = d_o[k - 1], d_h[k - 1], d_l[k - 1], d_c[k - 1]
            rsi_prev[a:z] = rsi_d[k - 1]
            if k >= 21 and rng_med[k - 1] > 0:
                rng_ratio[a:z] = rng[k - 1] / rng_med[k - 1]
    return dict(po=po, ph=ph, pl=pl, pc=pc, idx_dia=idx_dia, rsi_prev=rsi_prev, rng_ratio=rng_ratio)


# --------------------------------------------------------------------------
# setups -- cada um devolve lista[Ordem]
# --------------------------------------------------------------------------
def ordens_holy_grail(b: Barras, tick: float, adx_min: float = 30.0, modo: str = "toque",
                      olhar: int = 10, inclinacao: int = 5, swing_n: int = 3,
                      folga_ticks: float = 1.0) -> list[Ordem]:
    """Holy Grail (cap. 10). ADX(14)>adx_min; recuo ate a EMA20; buy stop acima da
    maxima da barra que tocou a EMA; stop na minima do recuo; alvo = swing high.
    Escolhas do livro-ambiguo: direcao = inclinacao da EMA20 em `inclinacao` barras;
    'toque' = ADX[i]>min na barra do toque; 'inicial' = ADX passou do min e estava
    subindo no pico dos ultimos `olhar` barras; 'primeiro toque' = barra anterior
    nao tocava a EMA. Reentrada e 'ADX precisa voltar a subir' nao implementados."""
    e20 = ema(b.c, 20)
    a = adx(b.h, b.l, b.c, 14)
    out: list[Ordem] = []
    start = max(60, olhar + 2, inclinacao + 1)
    for i in range(start, len(b) - 1):
        if np.isnan(a[i]) or np.isnan(e20[i]) or np.isnan(e20[i - 1]):
            continue
        if modo == "toque":
            ok = a[i] > adx_min
        else:
            seg = a[i - olhar:i + 1]
            k = int(np.nanargmax(seg))
            ok = bool(seg[k] > adx_min and (i - olhar + k) >= 1 and a[i - olhar + k] > a[i - olhar + k - 1])
        if not ok:
            continue
        subindo = e20[i] > e20[i - inclinacao]
        caindo = e20[i] < e20[i - inclinacao]
        if subindo and b.l[i] <= e20[i] and b.l[i - 1] > e20[i - 1]:
            stop = float(b.l[i - swing_n + 1:i + 1].min()) - tick
            alvo = float(b.h[i - 20:i + 1].max())
            out.append(Ordem(i, 1, float(b.h[i]) + folga_ticks * tick, stop, alvo, 1, "HG"))
        elif caindo and b.h[i] >= e20[i] and b.h[i - 1] < e20[i - 1]:
            stop = float(b.h[i - swing_n + 1:i + 1].max()) + tick
            alvo = float(b.l[i - 20:i + 1].min())
            out.append(Ordem(i, -1, float(b.l[i]) - folga_ticks * tick, stop, alvo, 1, "HG"))
    return out


def ordens_turtle_soup(b: Barras, tick: float, n_janela: int = 20, idade: int = 4,
                       folga_atr: float = 0.0, validade: int = 1, plus_one: bool = False) -> list[Ordem]:
    """Turtle Soup (cap. 4) / Plus One (cap. 5). Barra i faz nova minima de n_janela
    barras (L = minima das n anteriores, que ocorreu >= `idade` barras antes).
    TS: buy stop em L + folga (folga em fracao do ATR14; livro: 5-10 ticks);
        stop = minima de i - 1 tick. Entra nas `validade` barras seguintes (so' se o
        fechamento de i ainda esta abaixo do nivel -- senao a ordem ja teria enchido).
    Plus One: exige fechamento de i <= L; buy stop EXATO em L na barra seguinte
        (idade = 3 no livro); stop = minima de i - 1 tick. Venda: espelho."""
    at = atr(b.h, b.l, b.c, 14)
    out: list[Ordem] = []
    nome = "TS1" if plus_one else "TS"
    for i in range(max(n_janela + 1, 20), len(b) - 1):
        jan_l = b.l[i - n_janela:i]
        jan_h = b.h[i - n_janela:i]
        folga = 0.0 if plus_one else folga_atr * (at[i] if not np.isnan(at[i]) else 0.0)
        if b.l[i] < jan_l.min():
            L = float(jan_l.min())
            idade_L = n_janela - int(np.argmin(jan_l))  # barras entre a minima antiga e i
            if idade_L >= idade:
                nivel = L + max(folga, 0.0 if plus_one else tick)
                if (not plus_one and b.c[i] < nivel) or (plus_one and b.c[i] <= L):
                    out.append(Ordem(i, 1, nivel, float(b.l[i]) - tick, None, 1 if plus_one else validade, nome))
        if b.h[i] > jan_h.max():
            H = float(jan_h.max())
            idade_H = n_janela - int(np.argmax(jan_h))
            if idade_H >= idade:
                nivel = H - max(folga, 0.0 if plus_one else tick)
                if (not plus_one and b.c[i] > nivel) or (plus_one and b.c[i] >= H):
                    out.append(Ordem(i, -1, nivel, float(b.h[i]) + tick, None, 1 if plus_one else validade, nome))
    return out


def ordens_80_20(b: Barras, tick: float, pen_atr: float = 0.1, razao_range_min: float = 0.0,
                 corte: float = 0.2) -> list[Ordem]:
    """80-20 (cap. 6), so' em base intraday. Pregao anterior abriu nos 20% superiores
    do range e fechou nos 20% inferiores => hoje compra: o preco precisa perfurar a
    minima de ontem por `pen_atr` x ATR(14 barras; livro: 5-15 ticks) e a ordem buy
    stop NA minima de ontem vale ate o fim do pregao; stop = menor minima de hoje
    - 1 tick. Venda: espelho. `razao_range_min`: range de ontem / media 20 pregoes."""
    ag = agregado_diario(b)
    at = atr(b.h, b.l, b.c, 14)
    out: list[Ordem] = []
    n = len(b)
    min_hoje = np.inf
    max_hoje = -np.inf
    for i in range(n - 1):
        if ag["idx_dia"][i] == 0:
            min_hoje, max_hoje = np.inf, -np.inf
        min_hoje = min(min_hoje, b.l[i])
        max_hoje = max(max_hoje, b.h[i])
        po, ph, pl, pc = ag["po"][i], ag["ph"][i], ag["pl"][i], ag["pc"][i]
        if np.isnan(po) or ph <= pl or np.isnan(at[i]):
            continue
        if razao_range_min > 0 and not (ag["rng_ratio"][i] >= razao_range_min):
            continue
        r = ph - pl
        pen = pen_atr * at[i]
        if (po - pl) / r >= 1 - corte and (pc - pl) / r <= corte:      # compra
            if min_hoje <= pl - pen and b.c[i] < pl:
                out.append(Ordem(i, 1, float(pl), float(min_hoje) - tick, None, 0, "8020"))
        elif (po - pl) / r <= corte and (pc - pl) / r >= 1 - corte:    # venda
            if max_hoje >= ph + pen and b.c[i] > ph:
                out.append(Ordem(i, -1, float(ph), float(max_hoje) + tick, None, 0, "8020"))
    return out


def ordens_pinball(b: Barras, tick: float, rsi_lo: float = 30.0, rsi_hi: float = 70.0) -> list[Ordem]:
    """Momentum Pinball (cap. 7). LBR/RSI = RSI(3) do ROC(1) do FECHAMENTO diario.
    Dia 1: <30 (compra) / >70 (venda). Dia 2: buy stop acima da maxima da PRIMEIRA
    HORA, stop na minima da 1a hora (venda espelhada). Base diaria (sem 1a hora):
    variante 'PinballD' -- buy stop acima da maxima do dia 1, stop na minima do dia 1."""
    out: list[Ordem] = []
    if not b.intraday:
        r = lbr_rsi(b.c, 3)
        for i in range(5, len(b) - 1):
            if np.isnan(r[i]):
                continue
            if r[i] < rsi_lo:
                out.append(Ordem(i, 1, float(b.h[i]) + tick, float(b.l[i]) - tick, None, 1, "PinD"))
            elif r[i] > rsi_hi:
                out.append(Ordem(i, -1, float(b.l[i]) - tick, float(b.h[i]) + tick, None, 1, "PinD"))
        return out
    ag = agregado_diario(b)
    m = b.barras_por_hora
    for i in range(m - 1, len(b) - 1):
        if ag["idx_dia"][i] != m - 1 or np.isnan(ag["rsi_prev"][i]):
            continue
        h1 = float(b.h[i - m + 1:i + 1].max())
        l1 = float(b.l[i - m + 1:i + 1].min())
        rs = ag["rsi_prev"][i]
        if rs < rsi_lo:
            out.append(Ordem(i, 1, h1 + tick, l1 - tick, None, 0, "Pin"))
        elif rs > rsi_hi:
            out.append(Ordem(i, -1, l1 - tick, h1 + tick, None, 0, "Pin"))
    return out


def ordens_anti(b: Barras, tick: float, modo: str = "stoch", inclinacao: int = 3,
                recuo: int = 1) -> list[Ordem]:
    """Anti (cap. 9). Linha lenta com inclinacao definida; rapida recuou `recuo`
    barras e 'vira' (hook) a favor da lenta => buy stop 1 tick acima da maxima de i;
    stop = menor minima do recuo - 1 tick. modo 'stoch' = %K7/4,%D10 (livro);
    '310' = SMA3-SMA10 e SMA16 (descricao de fontes secundarias)."""
    if modo == "stoch":
        f, s = estocastico_anti(b.h, b.l, b.c)
    else:
        f, s = osc_3_10(b.h, b.l)
    out: list[Ordem] = []
    for i in range(max(40, inclinacao + recuo + 2), len(b) - 1):
        if np.isnan(s[i]) or np.isnan(s[i - inclinacao]) or np.isnan(f[i - recuo - 1]):
            continue
        sobe = s[i] > s[i - inclinacao]
        desce = s[i] < s[i - inclinacao]
        hook_up = f[i] > f[i - 1] and all(f[i - k] < f[i - k - 1] for k in range(1, recuo + 1))
        hook_dn = f[i] < f[i - 1] and all(f[i - k] > f[i - k - 1] for k in range(1, recuo + 1))
        if sobe and hook_up:
            st = float(b.l[i - recuo:i + 1].min()) - tick
            out.append(Ordem(i, 1, float(b.h[i]) + tick, st, None, 1, "ANTI"))
        elif desce and hook_dn:
            st = float(b.h[i - recuo:i + 1].max()) + tick
            out.append(Ordem(i, -1, float(b.l[i]) - tick, st, None, 1, "ANTI"))
    return out


# --------------------------------------------------------------------------
# simulador
# --------------------------------------------------------------------------
def _fim_do_dia(b: Barras, k: int) -> bool:
    return k == len(b) - 1 or b.dia[k + 1] != b.dia[k]


def simular(b: Barras, ordens: list[Ordem], saida: Saida, custo: Custo,
            um_por_dia: bool = False) -> list[Trade]:
    """Executa as ordens em sequencia, uma posicao por vez.

    Convencoes CONSERVADORAS (declaradas): compra stop enche em max(open, nivel)
    + 1 tick de deslize; stop sai em min(open, stop) - 1 tick (gap pega o pior);
    na mesma barra stop vence alvo; alvo (limite) so' enche se o preco passa 1 tick
    ALEM dele (tocar nao e' preencher), sem deslize; saida a mercado (tempo, fim
    do dia) paga 1 tick. Na barra de entrada o stop vale (pior caso)."""
    tick = custo.tick
    trades: list[Trade] = []
    livre_ate = -1
    ult_dia_trade = None
    n = len(b)
    for od in ordens:
        if od.i < livre_ate:
            continue
        if um_por_dia and ult_dia_trade == b.dia[od.i]:
            continue
        # ---- preenchimento
        ult = od.i + od.validade if od.validade > 0 else n - 1
        j_fill = -1
        for j in range(od.i + 1, min(ult, n - 1) + 1):
            if b.intraday and b.dia[j] != b.dia[od.i]:
                break
            if od.lado == 1 and b.h[j] >= od.entrada:
                j_fill = j; break
            if od.lado == -1 and b.l[j] <= od.entrada:
                j_fill = j; break
        if j_fill < 0:
            continue
        lado = od.lado
        px = max(b.o[j_fill], od.entrada) if lado == 1 else min(b.o[j_fill], od.entrada)
        fill = px + lado * tick
        risco = (fill - od.stop) * lado
        if risco < custo.risco_min_ticks * tick:
            continue
        stop = od.stop
        alvo = None
        if saida.alvo_r:
            alvo = fill + lado * saida.alvo_r * risco
        elif saida.alvo_swing and od.alvo is not None and (od.alvo - fill) * lado > 0.5 * risco:
            alvo = od.alvo
        # ---- gestao
        k = j_fill
        motivo = ""
        px_sai = None
        while True:
            # stop (vale tambem na barra de entrada)
            if (lado == 1 and b.l[k] <= stop) or (lado == -1 and b.h[k] >= stop):
                base = min(b.o[k], stop) if (lado == 1 and k > j_fill) else (
                    max(b.o[k], stop) if (lado == -1 and k > j_fill) else stop)
                px_sai = base - lado * tick
                motivo = "stop"
                break
            if alvo is not None and k > j_fill:
                if (lado == 1 and b.h[k] >= alvo + tick) or (lado == -1 and b.l[k] <= alvo - tick):
                    px_sai = alvo
                    motivo = "alvo"
                    break
            # fim de dados
            if k == n - 1:
                px_sai = b.c[k] - lado * tick
                motivo = "fim"
                break
            fim_dia = b.intraday and _fim_do_dia(b, k)
            if saida.max_barras and (k - j_fill) >= saida.max_barras:
                px_sai = b.c[k] - lado * tick
                motivo = "tempo"
                break
            if fim_dia and (saida.eod or saida.pinball):
                if saida.pinball and (b.c[k] - fill) * lado > 0 and b.dia[j_fill] == b.dia[k]:
                    # carrega: sai na abertura do proximo pregao (stop continua valendo no gap)
                    k += 1
                    if (lado == 1 and b.o[k] <= stop) or (lado == -1 and b.o[k] >= stop):
                        px_sai = b.o[k] - lado * tick
                        motivo = "stop_gap"
                    else:
                        px_sai = b.o[k] - lado * tick
                        motivo = "pinball_d3"
                    break
                px_sai = b.c[k] - lado * tick
                motivo = "eod"
                break
            # trailing (atualiza ao fechar a barra k, vale a partir de k+1)
            if saida.trail_n and k >= j_fill:
                a0 = max(j_fill, k - saida.trail_n + 1)
                if lado == 1:
                    stop = max(stop, float(b.l[a0:k + 1].min()) - tick)
                else:
                    stop = min(stop, float(b.h[a0:k + 1].max()) + tick)
            k += 1
        pts = (px_sai - fill) * lado
        pts_bruto_sem_slip = pts
        brl = pts * custo.valor_ponto * custo.qty
        brl -= custo.fee_brl
        brl -= custo.pct_lado * (fill + px_sai) * custo.valor_ponto * custo.qty
        # (o deslize ja esta embutido nos precos de entrada/saida)
        net_pts = brl / (custo.valor_ponto * custo.qty)
        trades.append(Trade(od.i, j_fill, k, lado, fill, px_sai, risco, pts_bruto_sem_slip, brl,
                            net_pts / risco, motivo, od.setup))
        livre_ate = k
        ult_dia_trade = b.dia[j_fill]
    return trades


# --------------------------------------------------------------------------
# metricas
# --------------------------------------------------------------------------
def metricas(trades: list[Trade]) -> dict[str, float]:
    if not trades:
        return dict(n=0, win=0.0, exp_r=0.0, pf=0.0, liq=0.0, maxdd=0.0, be_emp=0.0)
    pnl = np.array([t.pnl_brl for t in trades])
    r = np.array([t.r for t in trades])
    ganhos = pnl[pnl > 0]
    perdas = -pnl[pnl < 0]
    eq = np.cumsum(pnl)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], eq])) - np.concatenate([[0.0], eq])).max())
    win = float((pnl > 0).mean())
    be = (perdas.mean() / (ganhos.mean() + perdas.mean())) if len(ganhos) and len(perdas) else float("nan")
    return dict(n=len(trades), win=win, exp_r=float(r.mean()),
                pf=float(ganhos.sum() / perdas.sum()) if perdas.sum() > 0 else float("inf"),
                liq=float(pnl.sum()), maxdd=dd, be_emp=be)
