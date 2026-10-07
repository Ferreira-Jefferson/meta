"""Setups de Larry Williams -- funcoes PURAS (arrays numpy in, sinais/niveis out).

Contrato: scripts/larry_williams/ESPECIFICACAO.md. Cada interpretacao que a
especificacao deixa em aberto esta registrada em DECISOES.md (uma linha cada).

Convencoes (valem para TODAS as funcoes deste modulo):
  * Todos os arrays tem o comprimento `n` (um elemento por pregao) e o indice
    `i` e' o dia D. `o,h,l,c` sao abertura, maxima, minima e fechamento do dia.
  * O sinal/nivel em `i` usa SOMENTE `h,l,c` ate `i-1` e `o[i]` (a abertura de
    D). Nunca `h[i]`, `l[i]`, `c[i]`: isso e' look-ahead (testado em
    tests/test_larry_williams.py, que muta o futuro e exige sinal identico).
  * "S" = dia do setup = D-1. R1 = H(D-1) - L(D-1).
  * `NaN` num nivel = nenhuma ordem naquele dia/lado.
  * Sem I/O, sem pandas, sem estado global: portavel para MQL5.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

# Tipos de ordem de entrada (valem por Sinais, um para o lado comprado, um para o vendido).
STOP = 0       # buy/sell stop: dispara quando o preco ROMPE o nivel (vira mercado)
LIMITE = 1     # buy/sell limit: so' preenche se o preco ATRAVESSA o nivel
MERCADO = 2    # a mercado na abertura de D

NOMES_TIPO = {STOP: "STOP", LIMITE: "LIMITE", MERCADO: "MERCADO"}

NAN = float("nan")


# ----------------------------------------------------------------------------
# Resultado de um setup
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Sinais:
    """Ordens que um setup quer ter vivas em cada dia D (valem so' no dia D)."""

    nome: str
    nivel_c: np.ndarray            # nivel da ordem de COMPRA em D (NaN = sem ordem)
    nivel_v: np.ndarray            # nivel da ordem de VENDA em D
    tipo_c: int
    tipo_v: int
    base_stop: np.ndarray          # R1 (ou outra base) para `StopFrac * base`
    stop_abs_c: np.ndarray | None = None   # stop em preco absoluto (ex.: L(S)), NaN = usar fracao
    stop_abs_v: np.ndarray | None = None
    saida_osc_c: np.ndarray | None = None  # True em D => sair da compra na ABERTURA de D
    saida_osc_v: np.ndarray | None = None


# ----------------------------------------------------------------------------
# Utilidades de serie
# ----------------------------------------------------------------------------
def desloca(x: np.ndarray, k: int = 1) -> np.ndarray:
    """x[i-k] em i (NaN nos k primeiros). k=1 => 'ontem'."""
    saida = np.full(x.shape, np.nan, dtype=float)
    if k <= 0:
        return x.astype(float)
    if len(x) > k:
        saida[k:] = x[:-k]
    return saida


def _janela(x: np.ndarray, n: int, fn) -> np.ndarray:
    """fn aplicada a janela de n elementos TERMINANDO em i (inclusive); NaN antes."""
    saida = np.full(x.shape, np.nan, dtype=float)
    if len(x) >= n:
        saida[n - 1:] = fn(sliding_window_view(x.astype(float), n), axis=1)
    return saida


def minimo_janela(x: np.ndarray, n: int) -> np.ndarray:
    return _janela(x, n, np.min)


def maximo_janela(x: np.ndarray, n: int) -> np.ndarray:
    return _janela(x, n, np.max)


def media_janela(x: np.ndarray, n: int) -> np.ndarray:
    return _janela(x, n, np.mean)


def range_ontem(h: np.ndarray, l: np.ndarray) -> np.ndarray:
    """R1 = H(D-1) - L(D-1)."""
    return desloca(h - l, 1)


def _vazio(n: int) -> np.ndarray:
    return np.full(n, np.nan, dtype=float)


# ----------------------------------------------------------------------------
# Calendario (usado por TDM/TDW e pelos filtros) -- recebe codigos inteiros
# ----------------------------------------------------------------------------
def dia_do_pregao_no_mes(ano_mes: np.ndarray) -> np.ndarray:
    """1,2,3... contado a partir do primeiro pregao do mes (`ano_mes` = ano*100+mes)."""
    saida = np.zeros(len(ano_mes), dtype=np.int64)
    contador = 0
    for i, am in enumerate(ano_mes):
        contador = contador + 1 if i > 0 and am == ano_mes[i - 1] else 1
        saida[i] = contador
    return saida


# ----------------------------------------------------------------------------
# Indicadores: %R, Ultimate Oscillator, pivos de 3 barras
# ----------------------------------------------------------------------------
def percent_r(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 10) -> np.ndarray:
    """%R na escala de Larry (0-100; 100 = sobrevendido): 100*(HH-C)/(HH-LL)."""
    hh = maximo_janela(h, n)
    ll = minimo_janela(l, n)
    faixa = hh - ll
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 100.0 * (hh - c) / faixa
    r[faixa <= 0] = np.nan
    return r


def ultimate_oscillator(h: np.ndarray, l: np.ndarray, c: np.ndarray,
                        periodos: tuple[int, int, int] = (7, 14, 28)) -> np.ndarray:
    """UO = 100*(4*A7 + 2*A14 + A28)/7, A_p = soma(BP)/soma(TR) em p barras."""
    n = len(c)
    cp = desloca(c, 1)
    bp = c - np.minimum(l, cp)
    tr = np.maximum(h, cp) - np.minimum(l, cp)
    medias = []
    for p in periodos:
        sbp = _janela(bp, p, np.sum)
        str_ = _janela(tr, p, np.sum)
        with np.errstate(divide="ignore", invalid="ignore"):
            a = sbp / str_
        a[str_ <= 0] = np.nan
        medias.append(a)
    a7, a14, a28 = medias
    return 100.0 * (4.0 * a7 + 2.0 * a14 + a28) / 7.0


def pivos_3_barras(h: np.ndarray, l: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pivos de 3 barras CONFIRMADOS so' ao fechar a barra seguinte (sem look-ahead).

    Retorna (pivo_alta, pivo_baixa) alinhados ao dia da CONFIRMACAO t: em t vem o
    preco do pivo que estava em t-1 (NaN se nao houve). Pivo de baixa em j:
    L[j] < L[j-1] e L[j] < L[j+1]; de alta: H[j] > H[j-1] e H[j] > H[j+1]."""
    n = len(h)
    pa = np.full(n, np.nan)
    pb = np.full(n, np.nan)
    for t in range(2, n):
        j = t - 1
        if h[j] > h[j - 1] and h[j] > h[t]:
            pa[t] = h[j]
        if l[j] < l[j - 1] and l[j] < l[t]:
            pb[t] = l[j]
    return pa, pb


# ----------------------------------------------------------------------------
# TENDENCIA (filtro compartilhado)
# ----------------------------------------------------------------------------
def tendencia_swing_no_fechamento(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Tendencia por swing, avaliada NO FECHAMENTO de cada barra t (+1 alta, -1 baixa, 0 indef.).

    Short-term low = minima com minimas MAIORES dos dois lados (3 barras); short-term
    high espelhado; inside days ignorados; pivo confirmado so' quando a barra seguinte
    (nao-inside) se completa. ALTA = o fechamento rompeu o ultimo short-term high mais
    recentemente do que rompeu para baixo o ultimo short-term low."""
    n = len(c)
    saida = np.zeros(n, dtype=np.int8)
    ultimo_alto = np.nan
    ultimo_baixo = np.nan
    t_rompe_cima = -1
    t_rompe_baixo = -1
    # sequencia de barras nao-inside (indices)
    seq: list[int] = []
    for t in range(n):
        if t > 0 and h[t] <= h[t - 1] and l[t] >= l[t - 1]:
            pass  # inside day: nao entra na sequencia de pivos
        else:
            seq.append(t)
            if len(seq) >= 3:
                b0, b1, b2 = seq[-3], seq[-2], seq[-1]
                if h[b1] > h[b0] and h[b1] > h[b2]:
                    ultimo_alto = h[b1]
                if l[b1] < l[b0] and l[b1] < l[b2]:
                    ultimo_baixo = l[b1]
        if not np.isnan(ultimo_alto) and c[t] > ultimo_alto:
            t_rompe_cima = t
        if not np.isnan(ultimo_baixo) and c[t] < ultimo_baixo:
            t_rompe_baixo = t
        if t_rompe_cima < 0 and t_rompe_baixo < 0:
            saida[t] = 0
        elif t_rompe_cima > t_rompe_baixo:
            saida[t] = 1
        elif t_rompe_baixo > t_rompe_cima:
            saida[t] = -1
        else:
            saida[t] = 0
    return saida


def tendencia(h: np.ndarray, l: np.ndarray, c: np.ndarray, modo: str = "SWING",
              n: int = 50) -> np.ndarray:
    """Tendencia CONHECIDA NA ABERTURA de D (usa so' ate D-1): +1 alta, -1 baixa, 0 indef.

    modo: 'NENHUM' (sempre 0) | 'SWING' | 'SMA' (C > SMA(n); usa `n`)."""
    tam = len(c)
    if modo == "NENHUM":
        return np.zeros(tam, dtype=np.int8)
    if modo == "SWING":
        fech = tendencia_swing_no_fechamento(h, l, c)
    elif modo == "SMA":
        sma = media_janela(c, n)
        fech = np.where(np.isnan(sma), 0, np.where(c > sma, 1, -1)).astype(np.int8)
    else:
        raise ValueError(f"modo de tendencia desconhecido: {modo}")
    saida = np.zeros(tam, dtype=np.int8)
    saida[1:] = fech[:-1]
    return saida


# ----------------------------------------------------------------------------
# Filtros (dia da semana, mes, tendencia)
# ----------------------------------------------------------------------------
def mascara_dias(dow: np.ndarray, dias_permitidos) -> np.ndarray:
    """True nos dias da semana (0=seg ... 4=sex) permitidos; `None` = todos."""
    if dias_permitidos is None:
        return np.ones(len(dow), dtype=bool)
    return np.isin(dow, list(dias_permitidos))


def mascara_meses(mes: np.ndarray, meses_bloqueados) -> np.ndarray:
    if not meses_bloqueados:
        return np.ones(len(mes), dtype=bool)
    return ~np.isin(mes, list(meses_bloqueados))


def aplicar_filtros(sin: Sinais, dow: np.ndarray, mes: np.ndarray, tend: np.ndarray,
                    dias_c=None, dias_v=None, meses_bloqueados=None,
                    usar_tendencia: bool = False) -> Sinais:
    """Devolve novo Sinais com NaN onde o filtro proibe. Tendencia: compra so' se +1,
    venda so' se -1 (0 = indefinida bloqueia ambos)."""
    ok_c = mascara_dias(dow, dias_c) & mascara_meses(mes, meses_bloqueados)
    ok_v = mascara_dias(dow, dias_v) & mascara_meses(mes, meses_bloqueados)
    if usar_tendencia:
        ok_c = ok_c & (tend > 0)
        ok_v = ok_v & (tend < 0)
    return replace(
        sin,
        nivel_c=np.where(ok_c, sin.nivel_c, np.nan),
        nivel_v=np.where(ok_v, sin.nivel_v, np.nan),
    )


# ----------------------------------------------------------------------------
# VB -- Volatility Breakout [LIVRO cap.4]
# ----------------------------------------------------------------------------
def setup_vb(o, h, l, c, kc: float = 0.5, kv: float = 0.5) -> Sinais:
    """Compra: buy stop em O + Kc*R1. Venda: sell stop em O - Kv*R1."""
    r1 = range_ontem(h, l)
    return Sinais("VB", o + kc * r1, o - kv * r1, STOP, STOP, base_stop=r1)


# ----------------------------------------------------------------------------
# OOPS [LIVRO cap.7]
# ----------------------------------------------------------------------------
def setup_oops(o, h, l, c, gap_min: float = 0.0) -> Sinais:
    """Compra: O(D) < L(D-1) (abre ABAIXO da minima de ontem); buy stop em L(D-1).
    Venda: O(D) > H(D-1); sell stop em H(D-1). gap_min em fracao de R1."""
    r1 = range_ontem(h, l)
    l1, h1 = desloca(l), desloca(h)
    cond_c = (o < l1) & ((l1 - o) >= gap_min * r1)
    cond_v = (o > h1) & ((o - h1) >= gap_min * r1)
    return Sinais("OOPS", np.where(cond_c, l1, np.nan), np.where(cond_v, h1, np.nan),
                  STOP, STOP, base_stop=r1)


# ----------------------------------------------------------------------------
# SMASH / HSMASH [LIVRO cap.5; stop = SEC]
# ----------------------------------------------------------------------------
def _eh_outside(h, l) -> np.ndarray:
    return (h > desloca(h)) & (l < desloca(l))


def setup_smash(o, h, l, c, n: int = 1, excluir_outside: bool = False) -> Sinais:
    """Compra: C(S) < min(L(S-1..S-n)); buy stop em H(S) em D; stop = L(S).
    Venda: C(S) > max(H(S-1..S-n)); sell stop em L(S); stop = H(S)."""
    r1 = range_ontem(h, l)
    min_l = minimo_janela(l, n)   # em k: min l[k-n+1..k]
    max_h = maximo_janela(h, n)
    cs = desloca(c, 1)
    cond_c = cs < desloca(min_l, 2)   # min(l[S-1..S-n]) = min_l[S-1] = min_l[i-2]
    cond_v = cs > desloca(max_h, 2)
    if excluir_outside:
        fora = desloca(_eh_outside(h, l).astype(float), 1) > 0
        cond_c &= ~fora
        cond_v &= ~fora
    hs, ls = desloca(h), desloca(l)
    return Sinais("SMASH", np.where(cond_c, hs, np.nan), np.where(cond_v, ls, np.nan),
                  STOP, STOP, base_stop=r1,
                  stop_abs_c=np.where(cond_c, ls, np.nan), stop_abs_v=np.where(cond_v, hs, np.nan))


def setup_hsmash(o, h, l, c, zona: float = 0.25, exige_close_contra_open: bool = False) -> Sinais:
    """Hidden Smash. Compra: C(S)>C(S-1), C(S) nos `zona` inferiores do range de S
    (+ opcional C(S)<O(S)); buy stop em H(S). Venda espelhada; sell stop em L(S)."""
    r1 = range_ontem(h, l)
    faixa = h - l
    with np.errstate(divide="ignore", invalid="ignore"):
        pos_baixo = (c - l) / faixa
        pos_alto = (h - c) / faixa
    cp = desloca(c, 1)
    cond_c_s = (c > cp) & (pos_baixo <= zona) & (faixa > 0)
    cond_v_s = (c < cp) & (pos_alto <= zona) & (faixa > 0)
    if exige_close_contra_open:
        cond_c_s &= c < o
        cond_v_s &= c > o
    cond_c = desloca(cond_c_s.astype(float), 1) > 0
    cond_v = desloca(cond_v_s.astype(float), 1) > 0
    hs, ls = desloca(h), desloca(l)
    return Sinais("HSMASH", np.where(cond_c, hs, np.nan), np.where(cond_v, ls, np.nan),
                  STOP, STOP, base_stop=r1,
                  stop_abs_c=np.where(cond_c, ls, np.nan), stop_abs_v=np.where(cond_v, hs, np.nan))


# ----------------------------------------------------------------------------
# OUTSIDE [LIVRO cap.5]
# ----------------------------------------------------------------------------
def setup_outside(o, h, l, c, modo: str = "A_MERCADO_NA_ABERTURA", lado_venda: bool = False) -> Sinais:
    """Outside day com fechamento fora. Altista em S: H(S)>H(S-1), L(S)<L(S-1), C(S)<L(S-1);
    filtro O(D)<C(S). Entrada: a mercado na abertura de D ('A_MERCADO_NA_ABERTURA') ou
    limite em C(S) ('LIMITE_NO_FECHAMENTO_S'). Venda (opcional): C(S)>H(S-1), O(D)>C(S)."""
    r1 = range_ontem(h, l)
    fora = _eh_outside(h, l)
    sinal_c = desloca((fora & (c < desloca(l))).astype(float), 1) > 0
    sinal_v = desloca((fora & (c > desloca(h))).astype(float), 1) > 0
    cs = desloca(c, 1)
    cond_c = sinal_c & (o < cs)
    cond_v = (sinal_v & (o > cs)) if lado_venda else np.zeros(len(o), dtype=bool)
    if modo == "A_MERCADO_NA_ABERTURA":
        tipo, nivel = MERCADO, o
    elif modo == "LIMITE_NO_FECHAMENTO_S":
        tipo, nivel = LIMITE, cs
    else:
        raise ValueError(modo)
    return Sinais("OUTSIDE", np.where(cond_c, nivel, np.nan), np.where(cond_v, nivel, np.nan),
                  tipo, tipo, base_stop=r1)


# ----------------------------------------------------------------------------
# GSV [LIVRO cap.8 -- confianca baixa nos detalhes]
# ----------------------------------------------------------------------------
def valor_gsv(h, l, lado: str) -> np.ndarray:
    """GSV_j do dia j. Compra: max(H[j-3]-L[j], H[j-1]-L[j-3]); venda (espelho):
    max(H[j]-L[j-3], H[j-3]-L[j-1])."""
    if lado == "C":
        return np.fmax(desloca(h, 3) - l, desloca(h, 1) - desloca(l, 3))
    return np.fmax(h - desloca(l, 3), desloca(h, 3) - desloca(l, 1))


def setup_gsv(o, h, l, c, n: int = 4, kc: float = 0.8, kv: float = 1.2) -> Sinais:
    """Compra: buy stop em O + kc*media_n(GSV compra), so' apos dia de baixa (C(D-1)<O(D-1));
    venda: sell stop em O - kv*media_n(GSV venda), so' apos dia de alta."""
    r1 = range_ontem(h, l)
    mc = desloca(media_janela(valor_gsv(h, l, "C"), n), 1)
    mv = desloca(media_janela(valor_gsv(h, l, "V"), n), 1)
    dia_baixa = desloca((c < o).astype(float), 1) > 0
    dia_alta = desloca((c > o).astype(float), 1) > 0
    return Sinais("GSV", np.where(dia_baixa, o + kc * mc, np.nan),
                  np.where(dia_alta, o - kv * mv, np.nan), STOP, STOP, base_stop=r1)


# ----------------------------------------------------------------------------
# WR -- Williams %R [LIVRO 1973]
# ----------------------------------------------------------------------------
def gatilhos_wr(r: np.ndarray, espera: int, gatilho: float,
                toque: float = 100.0) -> tuple[np.ndarray, np.ndarray]:
    """Booleanos (compra, venda) calculados NO FECHAMENTO de t.

    Compra: %R tocou `toque` (livro: 100 = sobrevendido), passaram `espera` pregoes e %R voltou a
    < gatilho. Venda: %R tocou 100-`toque` (livro: 0), passaram `espera` pregoes e voltou a
    > 100-gatilho. Cada toque dispara no maximo uma vez.

    `toque` < 100 e' [INTERP] de tolerancia: em serie continua (futuros) o fechamento quase nunca
    iguala a minima de 10 dias, entao o toque literal em 100 praticamente nao ocorre."""
    n = len(r)
    sc = np.zeros(n, dtype=bool)
    sv = np.zeros(n, dtype=bool)
    toque_c = None
    toque_v = None
    for t in range(n):
        x = r[t]
        if np.isnan(x):
            continue
        if x >= toque - 1e-9:
            toque_c = t
        elif toque_c is not None and t - toque_c >= espera and x < gatilho:
            sc[t] = True
            toque_c = None
        if x <= 100.0 - toque + 1e-9:
            toque_v = t
        elif toque_v is not None and t - toque_v >= espera and x > 100.0 - gatilho:
            sv[t] = True
            toque_v = None
    return sc, sv


def setup_wr(o, h, l, c, n: int = 10, espera: int = 5, gatilho: float = 95.0,
             modo: str = "A_MERCADO_NA_ABERTURA", toque: float = 100.0) -> Sinais:
    """%R: compra na abertura de D se o gatilho de compra disparou no fechamento de D-1
    (venda idem). A TENDENCIA (obrigatoria no livro) entra por `aplicar_filtros`.
    `saida_osc`: sair da compra se %R(D-1) <= 100-gatilho; da venda se %R(D-1) >= gatilho."""
    r1 = range_ontem(h, l)
    r = percent_r(h, l, c, n)
    sc, sv = gatilhos_wr(r, espera, gatilho, toque)
    cond_c = desloca(sc.astype(float), 1) > 0
    cond_v = desloca(sv.astype(float), 1) > 0
    cs = desloca(c, 1)
    if modo == "A_MERCADO_NA_ABERTURA":
        tipo, nivel = MERCADO, o
    elif modo == "LIMITE_NO_FECHAMENTO_S":
        tipo, nivel = LIMITE, cs
    else:
        raise ValueError(modo)
    rs = desloca(r, 1)
    return Sinais("WR", np.where(cond_c, nivel, np.nan), np.where(cond_v, nivel, np.nan),
                  tipo, tipo, base_stop=r1,
                  saida_osc_c=rs <= (100.0 - gatilho), saida_osc_v=rs >= gatilho)


# ----------------------------------------------------------------------------
# UO -- Ultimate Oscillator [LIVRO: S&C abr/1985]
# ----------------------------------------------------------------------------
def gatilhos_uo(h, l, uo, uo_compra_max: float, uo_venda_min: float,
                validade: int) -> tuple[np.ndarray, np.ndarray]:
    """Booleanos (compra, venda) NO FECHAMENTO de t.

    Compra: duas minimas de preco (pivos de 3 barras confirmados) com preco2 < preco1 e
    UO2 > UO1 (divergencia altista), UO1 < `uo_compra_max`; gatilho = UO rompe acima do pico
    entre as duas minimas, em ate `validade` barras e antes de o preco perder a 2a minima.
    Venda espelhada (UO1 > `uo_venda_min`)."""
    n = len(h)
    sc = np.zeros(n, dtype=bool)
    sv = np.zeros(n, dtype=bool)
    pa, pb = pivos_3_barras(h, l)
    ult_b = None   # (j, preco, uo)
    ult_a = None
    arm_c = None   # (pico, expira, preco_fundo2)
    arm_v = None
    for t in range(n):
        j = t - 1
        if not np.isnan(pb[t]) and not np.isnan(uo[j]):
            if ult_b is not None and pb[t] < ult_b[1] and uo[j] > ult_b[2] and ult_b[2] < uo_compra_max:
                pico = np.nanmax(uo[ult_b[0]:j + 1])
                arm_c = (pico, t + validade, pb[t])
            ult_b = (j, pb[t], uo[j])
        if not np.isnan(pa[t]) and not np.isnan(uo[j]):
            if ult_a is not None and pa[t] > ult_a[1] and uo[j] < ult_a[2] and ult_a[2] > uo_venda_min:
                vale = np.nanmin(uo[ult_a[0]:j + 1])
                arm_v = (vale, t + validade, pa[t])
            ult_a = (j, pa[t], uo[j])
        if arm_c is not None:
            if t > arm_c[1] or l[t] < arm_c[2]:
                arm_c = None
            elif not np.isnan(uo[t]) and uo[t] > arm_c[0]:
                sc[t] = True
                arm_c = None
        if arm_v is not None:
            if t > arm_v[1] or h[t] > arm_v[2]:
                arm_v = None
            elif not np.isnan(uo[t]) and uo[t] < arm_v[0]:
                sv[t] = True
                arm_v = None
    return sc, sv


def saidas_uo(uo: np.ndarray, janela: int = 20) -> tuple[np.ndarray, np.ndarray]:
    """Saidas do livro, avaliadas no fechamento de t (executam na abertura de t+1).

    Comprado: UO > 70, ou UO < 45 tendo passado de 50 nas ultimas `janela` barras.
    Vendido: UO <= 30, ou UO > 65 tendo ficado abaixo de 50 nas ultimas `janela` barras."""
    max_j = maximo_janela(uo, janela)
    min_j = minimo_janela(uo, janela)
    sair_c = (uo > 70) | ((uo < 45) & (max_j > 50))
    sair_v = (uo <= 30) | ((uo > 65) & (min_j < 50))
    return sair_c, sair_v


def setup_uo(o, h, l, c, uo_compra_max: float = 30.0, uo_venda_min: float = 50.0,
             validade: int = 10, modo: str = "A_MERCADO_NA_ABERTURA") -> Sinais:
    r1 = range_ontem(h, l)
    uo = ultimate_oscillator(h, l, c)
    sc, sv = gatilhos_uo(h, l, uo, uo_compra_max, uo_venda_min, validade)
    cond_c = desloca(sc.astype(float), 1) > 0
    cond_v = desloca(sv.astype(float), 1) > 0
    cs = desloca(c, 1)
    if modo == "A_MERCADO_NA_ABERTURA":
        tipo, nivel = MERCADO, o
    else:
        tipo, nivel = LIMITE, cs
    sair_c, sair_v = saidas_uo(uo)
    sc_osc = desloca(sair_c.astype(float), 1) > 0
    sv_osc = desloca(sair_v.astype(float), 1) > 0
    return Sinais("UO", np.where(cond_c, nivel, np.nan), np.where(cond_v, nivel, np.nan),
                  tipo, tipo, base_stop=r1, saida_osc_c=sc_osc, saida_osc_v=sv_osc)


# ----------------------------------------------------------------------------
# TDM / TDW [LIVRO cap.4/6/10]
# ----------------------------------------------------------------------------
def setup_tdm(o, h, l, c, dom_pregao: np.ndarray, mes: np.ndarray,
              dias=(1,), meses_bloqueados=()) -> Sinais:
    """Compra na ABERTURA dos pregoes-do-mes listados em `dias` (1 = primeiro pregao)."""
    r1 = range_ontem(h, l)
    ok = np.isin(dom_pregao, list(dias)) & mascara_meses(mes, meses_bloqueados)
    return Sinais("TDM", np.where(ok, o, np.nan), _vazio(len(o)), MERCADO, MERCADO, base_stop=r1)


def setup_tdw(o, h, l, c, dow: np.ndarray, dias_compra=(0,), dias_venda=()) -> Sinais:
    """Compra (venda) na abertura nos dias da semana da mascara; saida = fechamento."""
    r1 = range_ontem(h, l)
    ok_c = np.isin(dow, list(dias_compra))
    ok_v = np.isin(dow, list(dias_venda))
    return Sinais("TDW", np.where(ok_c, o, np.nan), np.where(ok_v, o, np.nan),
                  MERCADO, MERCADO, base_stop=r1)


# ----------------------------------------------------------------------------
# TRES_BARRAS [LIVRO cap.9] -- niveis nas barras do timeframe intradiario
# ----------------------------------------------------------------------------
def sma3_extremos(h_tf: np.ndarray, l_tf: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(SMA3 das maximas, SMA3 das minimas) das 3 barras COMPLETAS anteriores a k.

    O valor em k usa as barras k-3..k-1 (a barra k ainda nao existe quando a ordem e' posta)."""
    return desloca(media_janela(h_tf, 3), 1), desloca(media_janela(l_tf, 3), 1)
