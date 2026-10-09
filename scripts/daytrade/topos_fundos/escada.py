"""Escada de topos e fundos no pregão: pivôs ZigZag K x ATR e estágio de cada pivô confirmado.

Pivô = (tipo "T"/"F", barra do pivô, preço, barra em que foi CONFIRMADO, ATR na confirmação). Confirmado sem
look-ahead e reiniciado a cada pregão. Estágio no fundo F_k (compra): 0 se F_k <= F_k-1; 1 se F_k > F_k-1;
+1 para cada par anterior em que o fundo E o topo intermediário também subiram (teto 6). Venda = espelho.
"""
import numpy as np
import pandas as pd

K = 1.5


def zigzag(h, l, atr, k=K):
    piv, dirc, hi_i, lo_i = [], 0, 0, 0
    for t in range(len(h)):
        if np.isnan(atr[t]):
            hi_i = lo_i = t
            continue
        if h[t] >= h[hi_i]: hi_i = t
        if l[t] <= l[lo_i]: lo_i = t
        a = atr[t] * k
        if dirc != -1 and hi_i < t and h[hi_i] - l[t] >= a:
            piv.append(("T", hi_i, h[hi_i], t, atr[t])); dirc, lo_i = -1, t
        elif dirc != 1 and lo_i < t and h[t] - l[lo_i] >= a:
            piv.append(("F", lo_i, l[lo_i], t, atr[t])); dirc, hi_i = 1, t
    return piv


def estagio(piv, i):
    """(lado, estágio) no pivô i; estágio None se ainda não há pivô anterior do mesmo tipo."""
    tipo = piv[i][0]; lado = 1 if tipo == "F" else -1
    mesmos = [j for j in range(i, -1, -1) if piv[j][0] == tipo]
    if len(mesmos) < 2: return lado, None
    melhor = (lambda a, b: a > b) if lado == 1 else (lambda a, b: a < b)
    if not melhor(piv[mesmos[0]][2], piv[mesmos[1]][2]): return lado, 0
    s = 1
    for q in range(1, len(mesmos) - 1):
        a, b, c = mesmos[q - 1], mesmos[q], mesmos[q + 1]
        if a - 1 <= b or b - 1 <= c: break
        if melhor(piv[b][2], piv[c][2]) and melhor(piv[a - 1][2], piv[b - 1][2]):
            s += 1
            if s >= 6: break
        else: break
    return lado, s


def pregoes(b, k=K):
    """Um dict por pregão: arrays de todas as colunas numéricas de b, 'dia', 'ini' (linha global da 1ª barra) e
    'pivos' (barra de confirmação -> pivô). Colunas extras (indicadores) entram junto se já estiverem em b."""
    cols = [c for c in b.columns if c not in ("dia",)]
    out, ini = [], 0
    for dia, g in b.groupby(b.dia.values):
        D = {c: g[c].to_numpy() for c in cols}
        D["dia"], D["ini"] = pd.Timestamp(dia), ini
        D["piv"] = zigzag(D["high"], D["low"], D["atr"], k)
        D["pivos"] = {p[3]: p for p in D["piv"]}
        out.append(D); ini += len(g)
    return out


def sinais(dias, est_min=1):
    """Sinais da escada: um por pivô confirmado com estágio >= est_min e barra seguinte no pregão.
    seg = pregão; t0 = barra da entrada (confirmação + 1); pos = linha global da barra de confirmação;
    stop = preço do pivô; i = índice do pivô no pregão."""
    rows = []
    for seg, D in enumerate(dias):
        piv = D["piv"]
        for i in range(len(piv)):
            lado, est = estagio(piv, i)
            t0 = piv[i][3] + 1
            if est is None or est < est_min or t0 >= len(D["open"]): continue
            rows.append(dict(seg=seg, i=i, t0=t0, pos=D["ini"] + t0 - 1, lado=lado, est=est, stop=piv[i][2]))
    return pd.DataFrame(rows)
