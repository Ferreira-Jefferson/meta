"""Correcao de multiplicidade: Deflated Sharpe Ratio e PBO por CSCV.

Por que este arquivo e obrigatorio nesta busca
----------------------------------------------
O protocolo de teste cego do projeto tem quatro niveis de cegueira e nenhum
deles responde a pergunta "rodamos 120 estrategias, a melhor e real?". Essa
pergunta tem ferramenta propria na literatura, e e esta:

  - Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014): desconta o Sharpe do
    vencedor pelo NUMERO de tentativas e pela dispersao dos Sharpes dos ensaios.
    Com N grande, o melhor de N series de puro ruido tem Sharpe alto por
    construcao; o DSR diz qual Sharpe seria necessario para nao ser isso.

  - PBO por CSCV (Bailey, Borwein, Lopez de Prado & Zhu, 2016): parte a serie em
    S blocos, testa todas as C(S, S/2) formas de dividir entre dentro e fora da
    amostra, escolhe o melhor DENTRO em cada divisao e olha onde ele cai FORA.
    PBO e a fracao de divisoes em que o escolhido fica abaixo da mediana fora da
    amostra. PBO alto significa que o processo de selecao nao seleciona nada.

Sem dependencia nova: `scipy` nao esta instalado e o AGENTS.md proibe adicionar
dependencia sem justificativa. A normal acumulada sai de `math.erf` (exata) e a
inversa da aproximacao racional de Acklam, com erro relativo < 1,15e-9 — ordens
de grandeza abaixo do ruido de qualquer coisa medida aqui.
"""
from __future__ import annotations

import math
from itertools import combinations

import numpy as np

EULER_GAMMA = 0.5772156649015329


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """Inversa da normal padrao — aproximacao racional de Acklam."""
    if not 0.0 < p < 1.0:
        raise ValueError(f"p fora de (0,1): {p}")
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def sharpe_per_obs(ret: np.ndarray) -> float:
    """Sharpe POR OBSERVACAO (nao anualizado) — e a escala que o DSR pede."""
    ret = np.asarray(ret, dtype=float)
    ret = ret[np.isfinite(ret)]
    if len(ret) < 2 or ret.std(ddof=1) == 0:
        return 0.0
    return float(ret.mean() / ret.std(ddof=1))


def expected_max_sharpe(sharpes: np.ndarray) -> float:
    """SR0 — Sharpe esperado do MELHOR de N ensaios sob a hipotese nula.

    E o coracao da deflacao: com N ensaios cujos Sharpes tem variancia V, o
    maximo esperado por puro acaso cresce com sqrt(V) e com sqrt(log N). Um
    vencedor abaixo disto nao e vencedor, e o maximo de uma amostra.
    """
    s = np.asarray([x for x in sharpes if np.isfinite(x)], dtype=float)
    n = len(s)
    if n < 2:
        return 0.0
    v = float(s.var(ddof=1))
    if v <= 0:
        return 0.0
    termo = ((1 - EULER_GAMMA) * norm_ppf(1 - 1.0 / n)
             + EULER_GAMMA * norm_ppf(1 - 1.0 / (n * math.e)))
    return math.sqrt(v) * termo


def deflated_sharpe(ret_vencedor: np.ndarray, sharpes_ensaios: np.ndarray) -> dict:
    """DSR do vencedor. Devolve tambem as pecas, para a tabela ser auditavel.

    `ret_vencedor` sao os retornos periodicos (mensais, aqui) do candidato
    escolhido; `sharpes_ensaios` sao os Sharpes POR OBSERVACAO de TODOS os
    ensaios medidos — inclusive os que fracassaram. Excluir os fracassos
    subestima a variancia e infla o DSR, que e a forma mais facil de mentir
    com esta ferramenta.
    """
    r = np.asarray(ret_vencedor, dtype=float)
    r = r[np.isfinite(r)]
    t = len(r)
    if t < 8:
        return {"dsr": float("nan"), "motivo": f"apenas {t} observacoes"}
    sr = sharpe_per_obs(r)
    sr0 = expected_max_sharpe(sharpes_ensaios)
    m = r.mean()
    sd = r.std(ddof=1)
    skew = float(((r - m) ** 3).mean() / sd ** 3) if sd > 0 else 0.0
    kurt = float(((r - m) ** 4).mean() / sd ** 4) if sd > 0 else 3.0
    den = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2
    if den <= 0:
        return {"dsr": float("nan"), "motivo": "denominador nao-positivo", "sr": sr, "sr0": sr0}
    z = (sr - sr0) * math.sqrt(t - 1) / math.sqrt(den)
    return {
        "dsr": norm_cdf(z), "sr_obs": sr, "sr0_esperado_max": sr0,
        "n_ensaios": int(len([x for x in sharpes_ensaios if np.isfinite(x)])),
        "t_obs": t, "skew": skew, "kurt": kurt,
        "sr_anual": sr * math.sqrt(12.0),
    }


def pbo_cscv(matriz: np.ndarray, s_blocos: int = 16) -> dict:
    """PBO por Combinatorially Symmetric Cross-Validation.

    `matriz` e T x N: T observacoes periodicas (linhas) por N estrategias
    (colunas). Divide T em `s_blocos` blocos contiguos, e para cada uma das
    C(S, S/2) escolhas de metade-dentro / metade-fora: escolhe a coluna com
    maior Sharpe DENTRO e mede o rank relativo dela FORA.

    PBO = fracao das divisoes em que o escolhido caiu ABAIXO da mediana fora da
    amostra. Interpretacao direta: 0,50 e o mesmo que escolher no sorteio.
    """
    m = np.asarray(matriz, dtype=float)
    if m.ndim != 2 or m.shape[1] < 3:
        return {"pbo": float("nan"), "motivo": f"matriz {m.shape} insuficiente"}
    t, n = m.shape
    s = min(s_blocos, t)
    if s % 2:
        s -= 1
    if s < 4:
        return {"pbo": float("nan"), "motivo": f"apenas {t} observacoes"}

    # Agregados por bloco. C(16,8)=12870 divisoes x N estrategias em Python puro
    # sao milhoes de recalculos da MESMA soma; guardando contagem, soma e soma de
    # quadrados por bloco, o Sharpe de qualquer uniao de blocos sai de tres
    # produtos de matriz. Blocos sao concatenacao de observacoes, entao a media e
    # a variancia agrupadas sao exatas — nao e aproximacao.
    limites = np.array_split(np.arange(t), s)
    cont = np.array([[np.isfinite(m[idx, j]).sum() for j in range(n)] for idx in limites], dtype=float)
    soma = np.array([[np.nansum(m[idx, j]) for j in range(n)] for idx in limites])
    soma2 = np.array([[np.nansum(m[idx, j] ** 2) for j in range(n)] for idx in limites])

    combos = list(combinations(range(s), s // 2))
    mask = np.zeros((len(combos), s), dtype=float)
    for i, c in enumerate(combos):
        mask[i, list(c)] = 1.0
    anti = 1.0 - mask

    def sharpes(msk: np.ndarray) -> np.ndarray:
        cnt = msk @ cont
        s1 = msk @ soma
        s2 = msk @ soma2
        with np.errstate(divide="ignore", invalid="ignore"):
            media = s1 / cnt
            var = (s2 - cnt * media ** 2) / (cnt - 1.0)
            out = media / np.sqrt(var)
        return np.where(np.isfinite(out), out, -np.inf)

    sr_dentro = sharpes(mask)   # (C, N)
    sr_fora = sharpes(anti)     # (C, N)

    escolhido = np.argmax(sr_dentro, axis=1)
    # Rank do escolhido FORA: quantas estrategias ele supera naquela divisao.
    proprio = sr_fora[np.arange(len(combos)), escolhido][:, None]
    piores = (sr_fora < proprio).sum(axis=1)
    omega = np.clip((piores + 1) / (n + 1), 1e-6, 1 - 1e-6)

    valido = np.isfinite(sr_dentro).any(axis=1)
    omega = omega[valido]
    if omega.size == 0:
        return {"pbo": float("nan"), "motivo": "nenhuma divisao valida"}
    return {
        "pbo": float((omega < 0.5).mean()),
        "divisoes": int(omega.size),
        "logit_medio": float(np.mean(np.log(omega / (1 - omega)))),
        "n_estrategias": n,
        "blocos": s,
    }
