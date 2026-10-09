import json
import numpy as np, pandas as pd
import motor
V = {}
for f in ("varre_1.json", "varre2_keep.json", "varre3.json"): V.update(json.load(open(f)))
info = {d: (t, c) for d, t, c in motor.dias50()}
dias = sorted(info)
c01 = [d for d in dias if info[d][1] in (0, 1)]; c2 = [d for d in dias if info[d][1] == 2]
def s(n, ds): return sum(V[n][d][0] for d in ds)
def dd(n):
    cum = np.cumsum([V[n][d][0] for d in dias]); return float((np.maximum.accumulate(cum) - cum).max())
escada = ["base", "V_desloc<0", "X_Vd0+T5ult", "Y_Vd0+T5ult+pira0", "Y_Vd0+T5ult+pira0+dois", "Y_Vd0+T5ult+pira0.5atr+dois", "X_Vd0+tudo(T5ult,pira,dois)", "Y_Vd0+T5ult+pira_d>=1+dois+alvo2x",
          "X_Vd0+alvo2.0x_desloc>=1.0", "V_so_venda", "V2_venda&desloc<1", "veto_off", "Y_Vd0+pira0"]
rows = []
for n in escada:
    d = {x: V[n][x][0] - V["base"][x][0] for x in dias}
    rows.append(dict(config=n, total50=round(s(n, dias)), d_c01=round(s(n, c01) - s("base", c01)), d_c2=round(s(n, c2) - s("base", c2)),
                     melhor=sum(v > .5 for v in d.values()), pior=sum(v < -.5 for v in d.values()), pior_dia=round(min(V[n][x][0] for x in dias)),
                     pior_delta=round(min(d.values())), ops=sum(V[n][x][1] for x in dias), dd_cron=round(dd(n)),
                     top5_dias=round(sum(sorted(d.values())[-5:]))))
print(pd.DataFrame(rows).to_string(index=False))
# LODO na escada (sem a base ser sempre vencida): seleciona nos 49 dias, aplica fora
for nome, cand in (("escada empilhada", escada[:6]), ("todas", list(V))):
    l = 0.0; esc = {}
    for d in dias:
        b = max(cand, key=lambda n: s(n, dias) - V[n][d][0]); l += V[b][d][0]; esc[b] = esc.get(b, 0) + 1
    print("LODO", nome, round(l), "delta", round(l - s("base", dias)), esc)
# estabilidade por ano/ciclo da melhor pre-registrada
n = "Y_Vd0+T5ult+pira0"
byy = {}
for d in dias: byy[d[:4]] = byy.get(d[:4], 0) + V[n][d][0] - V["base"][d][0]
print("delta por ano", {k: round(v) for k, v in byy.items()})
n = "V_desloc<0"; byy = {}
for d in dias: byy[d[:4]] = byy.get(d[:4], 0) + V[n][d][0] - V["base"][d][0]
print("delta por ano V_desloc<0", {k: round(v) for k, v in byy.items()})
# tipo de dia
for n in ("base", "V_desloc<0", "Y_Vd0+T5ult+pira0"):
    print(n, {t: round(sum(V[n][d][0] for d in dias if info[d][0] == t)) for t in ("bom", "ruim", "c0")})
