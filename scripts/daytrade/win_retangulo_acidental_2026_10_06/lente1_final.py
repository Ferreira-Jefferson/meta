"""Finalistas da lente 1: toque x atravessa, nulo, metricas, e sd do sorteio de lado."""
from dataclasses import replace
import numpy as np, pandas as pd
from sim import Cfg, carregar, resumo, simula
from lente1_varredura import BASE, PER, CUSTO, _cut
D = carregar("WINV26", "2026-08-12", "2026-10-01")
F = {"A h0 W20 t.28": replace(BASE, janela=20, tol=.28),
     "B h11 W20 t.28": replace(BASE, janela=20, tol=.28, primeira_entrada=660),
     "C h11 W15 t.28": replace(BASE, janela=15, tol=.28, primeira_entrada=660),
     "D h13 W25 t.28": replace(BASE, janela=25, tol=.28, primeira_entrada=780),
     "E h13 W20 t.28": replace(BASE, janela=20, tol=.28, primeira_entrada=780),
     "F padrao W25 t.28 h0": BASE, "G h14 W20 t.28": replace(BASE, janela=20, tol=.28, primeira_entrada=840)}
for n, c in F.items():
    for fill in ("toque", "atravessa"):
        cc = replace(c, fill=fill); t = simula(D, cc); nu = simula(D, replace(cc, inverte=True))
        ln = f"{n:22s} {fill:9s}"
        for p, (a, b) in PER.items():
            r = resumo(_cut(t, a, b), CUSTO); rn = resumo(_cut(nu, a, b), CUSTO)
            x = _cut(t, a, b); rs = x.pts * 0.2 - CUSTO
            sd = float(np.sqrt((rs.add(CUSTO) ** 2).sum())) if len(x) else 0
            ln += f" | {p} {r['rs']:7.0f} nulo {rn['rs']:7.0f} n{r['trades']:3d} w{r['win']:3.0f} pf{r['pf']:4.1f} pior{r['pior_dia']:6.0f} dd{r['dd']:6.0f} sdSorteio{sd:5.0f}"
        print(ln, flush=True)
