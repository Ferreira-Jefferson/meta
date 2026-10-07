"""Camada de DECISAO E RISCO para o WIN (mini indice), independente do sinal.

Funcoes puras (numpy). Unidade de resultado: PONTOS por contrato; R$ = pts * VALOR_PONTO.
Nada aqui le dados nem decide direcao: recebe probabilidades/volatilidades e devolve
tamanho, stop, alvo, risco e metricas.

Fatos do contrato (CLAUDE.md do projeto): R$0,20/pt, tick 5, custo ~2 pts/op,
deslize de 5 pts no stop, margem crua R$100/contrato, 2o contrato em diante exige
margem*2*1,25 = R$250 por contrato, capital minimo de partida R$250.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

VALOR_PONTO = 0.20
TICK = 5.0
CUSTO_PTS = 2.0
DESLIZE_STOP_PTS = 5.0
MARGEM_CRUA = 100.0
MARGEM_POR_CONTRATO_ESCALA = 100.0 * 2.0 * 1.25  # R$250
CAPITAL_MINIMO = 250.0


# ----------------------------------------------------------------- geometria
def ganho_perda(alvo: float, stop: float, custo: float = CUSTO_PTS,
                deslize_stop: float = DESLIZE_STOP_PTS) -> tuple[float, float]:
    """(ganho liquido, perda liquida) em pts por contrato; perda em modulo."""
    return alvo - custo, stop + deslize_stop + custo


def breakeven_p(ganho: float, perda: float) -> float:
    """Acerto minimo para esperanca zero: perda/(ganho+perda)."""
    return perda / (ganho + perda)


def nulo_p(alvo: float, stop: float) -> float:
    """Chance de tocar o alvo antes do stop num passeio aleatorio (R14): stop/(alvo+stop)."""
    return stop / (alvo + stop)


def esperanca(p: float, ganho: float, perda: float) -> float:
    return p * ganho - (1.0 - p) * perda


def payoff(ganho: float, perda: float) -> float:
    return ganho / perda


def resumo_distribuicao(res: np.ndarray, probs: np.ndarray | None = None) -> dict:
    """Esperanca, desvio, payoff, win%, breakeven empirico de uma distribuicao de resultados."""
    res = np.asarray(res, float)
    w = np.full(len(res), 1.0 / len(res)) if probs is None else np.asarray(probs, float)
    w = w / w.sum()
    e = float((res * w).sum())
    sd = float(math.sqrt(((res - e) ** 2 * w).sum()))
    pg = float(w[res > 0].sum())
    gm = float((res[res > 0] * w[res > 0]).sum() / pg) if pg > 0 else 0.0
    perdas = res[res <= 0]
    pl = 1 - pg
    lm = float(-(res[res <= 0] * w[res <= 0]).sum() / pl) if pl > 0 and len(perdas) else 0.0
    return dict(esperanca=e, desvio=sd, win=pg, ganho_medio=gm, perda_media=lm,
                payoff=(gm / lm if lm > 0 else float("inf")),
                breakeven_emp=(lm / (gm + lm) if gm + lm > 0 else float("nan")))


# ----------------------------------------------------------------- ruina
def _lundberg_theta(res: np.ndarray, w: np.ndarray) -> float | None:
    """theta > 0 com E[exp(-theta*X)] = 1 (existe so se E[X] > 0)."""
    if float((res * w).sum()) <= 0 or res.min() >= 0:
        return None
    f = lambda t: float((w * np.exp(-t * res)).sum()) - 1.0
    lo, hi = 1e-12, 1.0 / abs(res.min())
    while f(hi) < 0:
        hi *= 2
        if hi > 1e6:
            return None
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def ruina_formula(res_brl: np.ndarray, probs: np.ndarray | None, caixa: float,
                  piso: float = MARGEM_CRUA) -> float:
    """Risco de ruina (horizonte infinito, tamanho FIXO) pela aproximacao de Lundberg:
    P ~ exp(-theta*(caixa-piso)). res_brl = resultado liquido por operacao em R$ (ja x contratos).
    E[X]<=0 -> 1,0. Aproximacao (ignora o excesso sobre a barreira) -- levemente otimista;
    para binario com perda >> barreira use o Monte Carlo."""
    res = np.asarray(res_brl, float)
    w = np.full(len(res), 1.0 / len(res)) if probs is None else np.asarray(probs, float)
    w = w / w.sum()
    if caixa <= piso:
        return 1.0
    th = _lundberg_theta(res, w)
    if th is None:
        return 1.0
    return float(min(1.0, math.exp(-th * (caixa - piso))))


def ruina_mc(res_brl: np.ndarray, probs: np.ndarray | None, caixa: float, n_ops: int,
             n_caminhos: int = 5000, piso: float = MARGEM_CRUA, seed: int = 0) -> dict:
    """Monte Carlo de ruina com tamanho FIXO. Ruina = caixa < piso (nao da para manter 1 contrato).
    Devolve P(ruina em n_ops), tempo mediano ate quebrar (entre os que quebram), caixa final mediana."""
    rng = np.random.default_rng(seed)
    res = np.asarray(res_brl, float)
    w = np.full(len(res), 1.0 / len(res)) if probs is None else np.asarray(probs, float)
    w = w / w.sum()
    idx = rng.choice(len(res), size=(n_caminhos, n_ops), p=w)
    cx = caixa + np.cumsum(res[idx], axis=1)
    quebrou = cx < piso
    q_any = quebrou.any(axis=1)
    t = np.where(q_any, quebrou.argmax(axis=1) + 1, 0)
    return dict(p_ruina=float(q_any.mean()),
                t_mediano=(float(np.median(t[q_any])) if q_any.any() else float("nan")),
                caixa_final_mediana=float(np.median(np.where(q_any, np.minimum(cx[:, -1], piso), cx[:, -1]))))


# ----------------------------------------------------------------- p bayesiano
def p_encolhido(k: int, n: int, p_base: float, n0: float = 100.0) -> float:
    """Media a posteriori Beta(n0*p_base, n0*(1-p_base)) apos k acertos em n: (k+n0*p_base)/(n+n0).
    n0 = 'forca do prior' (operacoes equivalentes). Com n<<n0 o p fica na base (= sem vantagem)."""
    return (k + n0 * p_base) / (n + n0)


def p_limite_inferior(k: int, n: int, p_base: float, n0: float = 100.0, z: float = 1.0) -> float:
    """Limite inferior (z desvios) da posteriori Beta -- versao conservadora."""
    a, b = k + n0 * p_base, (n - k) + n0 * (1 - p_base)
    m = a / (a + b)
    sd = math.sqrt(a * b / ((a + b) ** 2 * (a + b + 1)))
    return m - z * sd


def n_para_confirmar(p_base: float, delta: float, z: float = 1.64) -> int:
    """Operacoes necessarias para que um acerto observado p_base+delta exclua a base (1 lado, z)."""
    sd = math.sqrt(p_base * (1 - p_base))
    return int(math.ceil((z * sd / delta) ** 2))


# ----------------------------------------------------------------- tamanho
def contratos_por_caixa(caixa: float) -> int:
    """Teto de margem: 1 contrato exige so a margem crua; do 2o em diante R$250 cada."""
    if caixa < MARGEM_CRUA:
        return 0
    return max(1, int(caixa // MARGEM_POR_CONTRATO_ESCALA))


def kelly_contratos(p: float, ganho_pts: float, perda_pts: float, caixa: float,
                    fracao: float = 0.25) -> float:
    """Numero (fracionario) de contratos de Kelly: n* = C*(p*w - q*l)/(w*l), w,l em R$/contrato."""
    w, l = ganho_pts * VALOR_PONTO, perda_pts * VALOR_PONTO
    n = caixa * (p * w - (1 - p) * l) / (w * l)
    return max(0.0, fracao * n)


def tamanho(p_est: float, ganho_pts: float, perda_pts: float, caixa: float, *,
            fracao_kelly: float = 0.25, teto_pior_caso: float = 0.25,
            minimo_um_se_positivo: bool = True) -> int:
    """Contratos = Kelly fracionario, limitado por (a) pior caso: n*perda_R$ <= teto*caixa,
    (b) margem. Edge<=0 -> 0 (nao entra). Edge>0 mas Kelly<1 -> 1 (se minimo_um_se_positivo),
    desde que o pior caso de 1 contrato caiba no teto -- senao 0."""
    if esperanca(p_est, ganho_pts, perda_pts) <= 0:
        return 0
    perda_brl = perda_pts * VALOR_PONTO
    n_pior = int(math.floor(teto_pior_caso * caixa / perda_brl))
    n_marg = contratos_por_caixa(caixa)
    n_k = kelly_contratos(p_est, ganho_pts, perda_pts, caixa, fracao_kelly)
    n = int(math.floor(n_k))
    if n < 1 and minimo_um_se_positivo:
        n = 1
    n = min(n, n_pior, n_marg)
    return max(0, n)


def n_minimo_para_tamanho_cheio(p_base: float, delta: float, n0: float = 100.0) -> int:
    """Quantas operacoes ate o p encolhido capturar 50% da vantagem verdadeira delta
    (se o p observado fosse exatamente p_base+delta): n = n0."""
    return int(n0)


def teto_tamanho_por_n(n: int, n0: float = 100.0, n_max_total: int = 4) -> int:
    """Regra pratica de teto de contratos conforme o n de operacoes observadas do sinal:
    n < n0/4 -> 1; n < n0 -> 2 (se n_max_total permitir); n >= n0 -> n_max_total."""
    if n < n0 / 4:
        return 1
    if n < n0:
        return min(2, n_max_total)
    return n_max_total


# ----------------------------------------------------------------- volatilidade/relogio
def dst_eua(data) -> bool:
    """Horario de verao dos EUA (R28): do 2o domingo de marco ao 1o domingo de novembro."""
    import datetime as dt
    d = data if isinstance(data, dt.date) else data.date()
    def nth_sunday(y, m, n):
        d0 = dt.date(y, m, 1)
        off = (6 - d0.weekday()) % 7
        return d0 + dt.timedelta(days=off + 7 * (n - 1))
    ini, fim = nth_sunday(d.year, 3, 2), nth_sunday(d.year, 11, 1)
    return ini <= d < fim


def indice_vol_horario(minutos_do_dia: np.ndarray, amplitude: np.ndarray, dst: np.ndarray,
                       bloco_min: int = 30) -> dict:
    """Relogio de volatilidade: amplitude media (high-low da M1) por bloco de `bloco_min` e regime
    (dst True/False), normalizada para media 1 no regime. Devolve {(dst, bloco_inicio_min): indice}."""
    out = {}
    blocos = (np.asarray(minutos_do_dia) // bloco_min) * bloco_min
    for regime in (True, False):
        m = dst == regime
        if not m.any():
            continue
        g = {}
        for b in np.unique(blocos[m]):
            g[int(b)] = float(np.mean(amplitude[m & (blocos == b)]))
        media = float(np.mean(amplitude[m]))
        for b, v in g.items():
            out[(regime, b)] = v / media
    return out


def vol_do_horario(indice: dict, dst: bool, minuto: int, bloco_min: int = 30) -> float:
    b = (minuto // bloco_min) * bloco_min
    return indice.get((dst, b), indice.get((not dst, b), 1.0))


def tamanho_ajustado_vol(caixa: float, stop_pts: float, risco_frac: float = 0.10) -> int:
    """Contratos tais que a perda do stop (pior caso, com deslize+custo) ~ risco_frac*caixa.
    Stop largo (horario volatil) -> menos contratos; stop curto -> mais. Limitado pela margem."""
    perda_brl = (stop_pts + DESLIZE_STOP_PTS + CUSTO_PTS) * VALOR_PONTO
    n = int(math.floor(risco_frac * caixa / perda_brl))
    return max(0, min(n, contratos_por_caixa(caixa))) if caixa >= MARGEM_CRUA else 0


def arredonda_tick(x: float) -> float:
    return max(TICK, round(x / TICK) * TICK)


def stop_alvo_por_vol(vol_idx: float, stop_base: float, razao_alvo: float = 0.5) -> tuple[float, float]:
    """Stop e alvo proporcionais a volatilidade esperada do horario (indice com media 1).
    stop = stop_base*vol_idx; alvo = razao_alvo*stop. Mantem o nulo S/(S+T) constante: a geometria
    nao ganha vantagem, mas o custo fixo (7 pts) pesa menos quando o stop e largo."""
    s = arredonda_tick(stop_base * vol_idx)
    return s, arredonda_tick(razao_alvo * s)


# ----------------------------------------------------------------- sinais fracos
def logit(p: float) -> float:
    return math.log(p / (1 - p))


def inv_logit(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def combina_sinais(p_base: float, ps_sinais: list[float], rho_medio: float = 0.5,
                   encolhe: list[float] | None = None) -> float:
    """Combina sinais fracos em log-odds. Cada sinal i traz delta_i = logit(p_i)-logit(p_base)
    (p_i = acerto condicionado so naquele sinal). Soma ingenua assume independencia (superconfianca);
    penalizacao de correlacao: sum(delta)/(1+(k-1)*rho). `encolhe` = fator 0..1 por sinal (ex.: n/(n+n0))."""
    k = len(ps_sinais)
    if k == 0:
        return p_base
    base = logit(p_base)
    deltas = [(logit(p) - base) * (1.0 if encolhe is None else encolhe[i]) for i, p in enumerate(ps_sinais)]
    return inv_logit(base + sum(deltas) / (1.0 + (k - 1) * rho_medio))


# ----------------------------------------------------------------- parada no dia
@dataclass(frozen=True)
class ParadaDia:
    perda_max_brl: float = float("inf")   # para o dia quando resultado do dia <= -perda_max_brl
    n_max_ops: int = 10_000               # para o dia apos n operacoes
    n_max_stops: int = 10_000             # para o dia apos n stops
    ganho_trava_brl: float = float("inf")  # opcional: trava o dia ao atingir este ganho

    def pode_operar(self, resultado_dia: float, n_ops: int, n_stops: int) -> bool:
        return (resultado_dia > -self.perda_max_brl and n_ops < self.n_max_ops
                and n_stops < self.n_max_stops and resultado_dia < self.ganho_trava_brl)


def perda_diaria_max_por_ruina(caixa: float, frac: float = 0.15) -> float:
    """Regra pratica: perda diaria maxima = frac da caixa (nunca menos que 1 perda de 1 contrato
    e nunca mais que caixa - margem crua)."""
    return float(max(0.0, min(frac * caixa, caixa - MARGEM_CRUA)))


# ----------------------------------------------------------------- constancia
def drawdown_max(curva: np.ndarray) -> tuple[float, float]:
    """(DD maximo em R$, DD maximo em fracao do pico)."""
    c = np.asarray(curva, float)
    pico = np.maximum.accumulate(c)
    dd = pico - c
    return float(dd.max()), float((dd / np.where(pico > 0, pico, np.nan)).max())


def ulcer_index(curva: np.ndarray) -> float:
    """Raiz da media dos quadrados do drawdown percentual (em %) -- penaliza profundidade e duracao."""
    c = np.asarray(curva, float)
    pico = np.maximum.accumulate(c)
    dd = 100.0 * (c - pico) / np.where(pico > 0, pico, np.nan)
    return float(np.sqrt(np.nanmean(dd ** 2)))


def pior_sequencia(resultados: np.ndarray) -> tuple[int, float]:
    """(maior sequencia de perdas consecutivas, pior soma consecutiva de perdas em R$)."""
    r = np.asarray(resultados, float)
    best_n = cur_n = 0
    best_s = cur_s = 0.0
    for x in r:
        if x < 0:
            cur_n += 1
            cur_s += x
            best_n = max(best_n, cur_n)
            best_s = min(best_s, cur_s)
        else:
            cur_n, cur_s = 0, 0.0
    return best_n, best_s


def pct_meses_positivos(resultados: np.ndarray, mes: np.ndarray) -> float:
    r = np.asarray(resultados, float)
    m = np.asarray(mes)
    ms = np.unique(m)
    if len(ms) == 0:
        return float("nan")
    return float(np.mean([r[m == k].sum() > 0 for k in ms]))


def pior_mes(resultados: np.ndarray, mes: np.ndarray) -> float:
    r = np.asarray(resultados, float)
    m = np.asarray(mes)
    return float(min(r[m == k].sum() for k in np.unique(m)))


def metricas_constancia(resultados_brl: np.ndarray, mes: np.ndarray, caixa0: float) -> dict:
    """Pacote padrao para comparar estrategias: resultados por operacao (R$) e o mes de cada uma."""
    r = np.asarray(resultados_brl, float)
    curva = caixa0 + np.cumsum(r)
    dd_brl, dd_pct = drawdown_max(np.concatenate([[caixa0], curva]))
    seq_n, seq_brl = pior_sequencia(r)
    return dict(liquido=float(r.sum()), meses_pos=pct_meses_positivos(r, mes),
                pior_mes=pior_mes(r, mes), maxdd_brl=dd_brl, maxdd_pct=dd_pct,
                ulcer=ulcer_index(np.concatenate([[caixa0], curva])),
                pior_seq_ops=seq_n, pior_seq_brl=seq_brl,
                lucro_dd=(float(r.sum()) / dd_brl if dd_brl > 0 else float("inf")))


# ----------------------------------------------------------------- versao vetorizada (simulacoes)
def tamanho_vec(p_est, ganho_pts, perda_pts, caixa, *, fracao_kelly=0.25, teto_pior_caso=0.25,
                minimo_um_se_positivo=True):
    """Mesma regra de `tamanho`, em arrays (p_est, ganho, perda, caixa broadcastaveis). Devolve int array."""
    p = np.asarray(p_est, float); g = np.asarray(ganho_pts, float); l = np.asarray(perda_pts, float)
    c = np.asarray(caixa, float)
    edge = p * g - (1 - p) * l
    w, lo = g * VALOR_PONTO, l * VALOR_PONTO
    n_k = np.floor(np.maximum(0.0, fracao_kelly * c * (p * w - (1 - p) * lo) / (w * lo)))
    if minimo_um_se_positivo:
        n_k = np.maximum(n_k, 1.0)
    n_pior = np.floor(teto_pior_caso * c / lo)
    n_marg = np.where(c < MARGEM_CRUA, 0.0, np.maximum(1.0, np.floor(c / MARGEM_POR_CONTRATO_ESCALA)))
    n = np.minimum(np.minimum(n_k, n_pior), n_marg)
    return np.where(edge > 0, np.maximum(n, 0.0), 0.0).astype(int)
