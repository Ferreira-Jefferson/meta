import json, sys
import numpy as np, pandas as pd
arq = sys.argv[1] if len(sys.argv) > 1 else "varre.json"
V = json.load(open(arq))
if arq != "varre.json":
    V.update({k: v for k, v in json.load(open("varre.json")).items() if k not in V})
import motor
info = {d: (t, c) for d, t, c in motor.dias50()}
dias = sorted(info)
c01 = [d for d in dias if info[d][1] in (0, 1)]; c2 = [d for d in dias if info[d][1] == 2]
base = V["base"]
def s(n, ds): return sum(V[n][d][0] for d in ds)
rows = []
for n in V:
    d = {x: V[n][x][0] - base[x][0] for x in dias}
    rows.append(dict(config=n, total=s(n, dias), delta50=s(n, dias) - s("base", dias), delta_c01=s(n, c01) - s("base", c01), delta_c2=s(n, c2) - s("base", c2),
                     dias_melhor=sum(v > 0.5 for v in d.values()), dias_pior=sum(v < -0.5 for v in d.values()),
                     pior_dia=min(V[n][x][0] for x in dias), pior_trade=min(V[n][x][2] for x in dias), ops=sum(V[n][x][1] for x in dias),
                     pior_dia_delta=min(d.values())))
T = pd.DataFrame(rows).round(1)
print(T.to_string(index=False))
# selecao em 0+1, verificacao em 2
print("\nSelecao por familia (melhor em ciclos 0+1 -> efeito no ciclo 2):")
fam = {}
for n in V:
    if n == "base": continue
    fam.setdefault(n.split("_")[0], []).append(n)
for f, ns in fam.items():
    best = max(ns, key=lambda n: s(n, c01) - s("base", c01))
    print(f, best, "d01=", round(s(best, c01) - s("base", c01), 1), "d2=", round(s(best, c2) - s("base", c2), 1))
# LODO: escolhe a melhor config entre TODAS (inclui base) nos outros 49 dias, aplica no dia deixado de fora
names = list(V)
tot = {n: s(n, dias) for n in names}
lodo = 0.0; esc = {}
for d in dias:
    b = max(names, key=lambda n: tot[n] - V[n][d][0])
    esc[b] = esc.get(b, 0) + 1; lodo += V[b][d][0]
print("\nLODO (seleciona entre todas as configs nos 49 dias, aplica no dia fora):", round(lodo, 1), "vs base", round(s("base", dias), 1), esc)
# LODO so entre uma familia (+base)
for f, ns in fam.items():
    cand = ["base"] + ns; l = 0.0
    for d in dias:
        b = max(cand, key=lambda n: tot[n] - V[n][d][0]); l += V[b][d][0]
    print("  LODO familia", f, round(l, 1), "delta", round(l - s("base", dias), 1))
T.to_csv("avalia_" + arq.replace(".json", "") + ".csv", index=False)
