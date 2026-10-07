"""Holdout UNICO do stop congelado (1500). Roda uma vez."""
import sys, numpy as np, pandas as pd
from datetime import date
sys.path.insert(0, r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\comparativo_win_2026")
import port_win_gap_barra1 as P
from metricas import metr
STOP = 1500.0
m1 = P.m1_total(); gt = P.ticks_fn(m1); todos = sorted(set(m1.index.date))
dias = [d for d in todos if date(2025,10,1) <= d <= date(2025,12,18)]
tr, s, q, dg = P.rodar(dias, m1, gt, stop=STOP)
x = metr(tr)
print("HOLDOUT", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in x.items()}); print("diag", dg)
rt = x["liq"] / x["n"]; print("R$/trade holdout", round(rt, 2), "selecao 29.65 -> razao", round(rt / 29.65, 3))
# nulo: direcao aleatoria nos mesmos dias de sinal (mesmo stop, mesmo flatten, mesma regra de fill)
res = {}
for lado in (1, -1):
    t_, *_ = P.rodar(dias, m1, gt, stop=STOP, lado_forcado=lado)
    res[lado] = {r["entrada"][:10]: r["rs"] - 2.0 * r["qtd"] for r in t_}
sinal = sorted(set(res[1]) | set(res[-1]))
# dias de sinal = todos com ordem enviada (inclui os nao preenchidos de um lado = 0)
dias_sinal = [d for d in dias]
a = np.array([[res[1].get(str(d), 0.0), res[-1].get(str(d), 0.0)] for d in dias_sinal])
a = a[(a != 0).any(axis=1)]
obs = x["liq"]
rng = np.random.default_rng(20251001)
N = 200000
esc = rng.integers(0, 2, size=(N, len(a)))
tot = a[np.arange(len(a)), esc].sum(axis=1)
p = float((tot >= obs).mean())
print("dias de sinal com algum fill possivel", len(a), "obs liq", round(obs, 2), "nulo media", round(tot.mean(), 1), "sd", round(tot.std(), 1), "p(>=obs)", p, "draws", N)
sd = np.std([r["rs"] - 2.0 for r in tr], ddof=1)
n = x["n"]; mde = (1.645 + 0.8416) * sd / np.sqrt(n)
print("sd por operacao", round(sd, 1), "n", n, "efeito minimo detectavel (80% poder, alfa 5% unilateral) R$/op", round(mde, 1), "total", round(mde * n))
