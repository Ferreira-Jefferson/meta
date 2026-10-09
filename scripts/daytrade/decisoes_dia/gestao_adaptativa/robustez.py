import numpy as np
from analise import *
rng = np.random.default_rng(1); ud = sorted(set(dias))
for k, reg in REG.items():
    diff = {}
    for d in ud:
        te = np.where(dias == d)[0]; trn = np.where(dias != d)[0]
        m, f = escolhe(trn, reg); diff[d] = aplica(te, reg, m, f) - G[te, f].sum()
    v = np.array([diff[d] for d in ud])
    bs = [rng.choice(v, len(v)).sum() for _ in range(5000)]
    print(f"{k}: LODO adapt-fixa = {v.sum():.0f}; IC95 bootstrap dias [{np.percentile(bs,2.5):.0f}; {np.percentile(bs,97.5):.0f}]; dias+ {int((v>0).sum())} / dias- {int((v<0).sum())}")
# fixa LODO vs atual por dia
v = []
for d in ud:
    te = np.where(dias == d)[0]; trn = np.where(dias != d)[0]; f = fixa(trn); v.append(G[te, f].sum() - ATUAL[te].sum())
v = np.array(v); bs = [rng.choice(v, len(v)).sum() for _ in range(5000)]
print(f"FIXA(LODO) - ATUAL = {v.sum():.0f}; IC95 [{np.percentile(bs,2.5):.0f}; {np.percentile(bs,97.5):.0f}]; dias+ {(v>0).sum()} dias- {(v<0).sum()}")
# sinal do efeito: por estado, correlacao da diferenca (sem alvo stop2 - atual) 
j0 = GRADE.index((2, None, "nenhum"))
for k in ("ef", "vol4", "volrel4", "hora", "d_vwap", "perna", "a_favor"):
    x = E_(k); ok = ~np.isnan(x)
    print(k, "corr(estado, R$ melhor-por-trade fixa stop2/sem)", np.corrcoef(x[ok], G[ok, j0])[0, 1].round(2), "| corr com 'indice do melhor stop'", np.corrcoef(x[ok], np.array([GRADE[j][0] for j in G.argmax(1)])[ok])[0, 1].round(2))
