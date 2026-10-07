"""Passo 1: taxa-base, preenchimento, breakeven por geometria (SOMENTE jan-jun)."""
import numpy as np, pandas as pd
from lib import *
C, Y, PN, EX = carregar()
X = construir_X(C)
print("candidatos", len(C), "jan-jun", (C.mes <= 6).sum(), "jul-ago", C.mes.between(7, 8).sum(), "set", (C.mes == 9).sum())
print("NaN por coluna (top):"); print(X.isna().mean().sort_values(ascending=False).head(8))
tr = (C.mes.values <= 6)
iN, iP = NS.index(5), PISOS.index(1.0)
print("\n== preenchimento e taxa-base por K (N5 piso1 m150 S15, jan-jun) ==")
g = tr & mask_geom(C, 150, 15)
for d, nome in ((0, "a favor"), (1, "contra")):
    for k, Kx in enumerate(KS):
        y = Y[g, iN, iP, k, d]; pn = PN[g, iN, iP, k, d]
        f = y >= 0
        print(nome, "K", Kx, "n", len(y), "fill %.1f%%" % (100 * f.mean()), "acerto %.2f%%" % (100 * (y[f] == 1).mean()),
              "BE emp %.2f%%" % (100 * breakeven_emp(pn[f], y[f])), "esp pts/op %.1f" % pn[f].mean())
print("\n== risco medio (pts) implícito: K5 esperanca por N x piso, a favor ==")
for a, N in enumerate(NS):
    print(N, [round(float(PN[g, a, b, KS.index(5), 0][Y[g, a, b, KS.index(5), 0] >= 0].mean()), 1) for b in range(len(PISOS))])
