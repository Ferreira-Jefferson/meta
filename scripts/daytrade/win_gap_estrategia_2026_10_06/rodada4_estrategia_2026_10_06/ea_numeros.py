# -*- coding: utf-8 -*-
"""Numeros de referencia para o EA_SPEC: celula escolhida e S700, 1 contrato por sinal (lote fixo), IS, simulador a tick."""
import pickle, sys
from pathlib import Path
import numpy as np, pandas as pd
AQUI = Path(__file__).resolve().parent
res = pickle.load(open(AQUI / "out" / "dia_resultados.pkl", "rb"))
dias = sorted(res)
sys.stdout.reconfigure(encoding="utf-8")
for cid in ("S1200 | none", "S700 | none"):
    for fm in ("toque", "atrav+1t"):
        pn, sig, fil = [], 0, 0
        stops = 0; flat = 0; meses = {}
        for d in dias:
            r = res[d]["cel"][cid]
            if r is None:
                continue
            sig += 1
            t = r["fills"][fm]["real"][1]
            if t is None:
                continue
            fil += 1; pn.append(t["pnl"])
            rs = t["legs"][-1][1]
            stops += rs == "stop"; flat += rs == "flatten"
            meses[d.strftime("%Y-%m")] = meses.get(d.strftime("%Y-%m"), 0) + t["pnl"]
        pn = np.array(pn); eq = np.cumsum(pn); dd = (np.maximum.accumulate(eq) - eq).max()
        g = pn[pn > 0]; p = -pn[pn < 0]
        seq = at = 0
        for x in pn:
            at = at + 1 if x < 0 else 0; seq = max(seq, at)
        print(f"{cid:<14}{fm:<9} sinais {sig} fills {fil} sem fill {100*(sig-fil)/sig:.1f}% | 1 contrato: liquido R${pn.sum():,.0f} R$/trade {pn.mean():.1f} win {100*len(g)/len(pn):.1f}% BE {100*p.mean()/(g.mean()+p.mean()):.1f}% "
              f"ganho medio {g.mean():.0f} perda media {p.mean():.0f} maxDD R${dd:,.0f} maior seq perdas {seq} stops {stops} flatten {flat} pior {pn.min():.0f}")
        print("   por mes:", {k: round(v) for k, v in meses.items()})
