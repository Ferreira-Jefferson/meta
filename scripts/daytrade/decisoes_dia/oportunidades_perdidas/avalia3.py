import json
import numpy as np, pandas as pd
import motor
V = {}
for f in ("varre_1.json", "varre2_keep.json", "varre3.json", "varre4.json"): V.update(json.load(open(f)))
info = {d: (t, c) for d, t, c in motor.dias50()}
dias = sorted(info)
tipos = {t: [d for d in dias if info[d][0] == t] for t in ("bom", "ruim", "c0")}
c01 = [d for d in dias if info[d][1] in (0, 1)]; c2 = [d for d in dias if info[d][1] == 2]
def s(n, ds): return sum(V[n][d][0] for d in ds)
rows = []
for n in V:
    if n == "base": continue
    db = (s(n, tipos["bom"]) - s("base", tipos["bom"])) / 20
    dr = (s(n, tipos["ruim"]) - s("base", tipos["ruim"])) / 20
    d0 = (s(n, tipos["c0"]) - s("base", tipos["c0"])) / 10
    pop = 0.05 * db + 0.95 * dr
    rows.append(dict(config=n, d50=round(s(n, dias) - s("base", dias)), d_bom=round(s(n, tipos["bom"]) - s("base", tipos["bom"])), d_ruim=round(s(n, tipos["ruim"]) - s("base", tipos["ruim"])),
                     d_c0=round(s(n, tipos["c0"]) - s("base", tipos["c0"])), d_c01=round(s(n, c01) - s("base", c01)), d_c2=round(s(n, c2) - s("base", c2)),
                     pop_dia=round(pop, 1), pior_dia=round(min(V[n][x][0] for x in dias))))
T = pd.DataFrame(rows).sort_values("pop_dia", ascending=False)
print(T.to_string(index=False))
b = "base"
print("base por tipo", {t: round(s(b, ds)) for t, ds in tipos.items()}, "por dia bom/ruim", round(s(b, tipos["bom"]) / 20, 1), round(s(b, tipos["ruim"]) / 20, 1))
T.to_csv("avalia3.csv", index=False)
