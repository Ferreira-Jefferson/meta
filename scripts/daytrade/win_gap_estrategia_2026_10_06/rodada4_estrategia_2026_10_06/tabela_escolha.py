# -*- coding: utf-8 -*-
"""Linhas da tabela padrao (report.py) das celulas S1200|none (escolhida) e S700|none, modos A e B, dois fills; e CSV de referencia do EA."""
import pickle, sys
from pathlib import Path
import numpy as np
import pandas as pd
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI)); sys.path.insert(0, str(AQUI.parent / "rodada2_2026_10_06"))
import analise as AN
sys.stdout.reconfigure(encoding="utf-8")
full = pickle.load(open(AQUI / "out" / "analise4_full.pkl", "rb"))
out, A, dias, ids = full["out"], full["A"], full["dias"], full["ids"]
linhas = []
for cid in ("S1200 | none", "S700 | none"):
    j = ids.index(cid)
    for fm in ("toque", "atrav+1t"):
        b = out[fm]["B"][cid]; a = A[fm][cid]
        pnl = b["real"][b["fil"]]
        st = dict(be=AN.stats_be(pnl), sem_fill=100 * (b["trig"].sum() - b["fil"].sum()) / b["trig"].sum(), atraso_med=float(np.median(b["atraso"])),
                  p=out[fm]["p_cel"][j], p_adj=out[fm]["p_adj"][j], be_a=AN.stats_be(np.array(a["pnls"])),
                  sem_fill_a=100 * (a["trig"] - a["recus"] - a["fills"]) / a["trig"], atraso_med_a=float(np.median(a["atraso"])))
        linhas += [AN.linha_b(cid, fm, b, dias, st), AN.linha_a(cid, fm, a, dias, st)]
print(AN.tabela(linhas, AN.EXTRAS, 12))
# CSV de referencia por dia (1 contrato)
res = pickle.load(open(AQUI / "out" / "dia_resultados.pkl", "rb"))
rows = []
for d in sorted(res):
    for cid in ("S1200 | none", "S700 | none"):
        r = res[d]["cel"][cid]
        if r is None:
            continue
        t = r["fills"]["toque"]["real"][1]
        rows.append(dict(dia=d, celula=cid, lado="compra" if r["side"] > 0 else "venda", entrada=(t["entry"] if t else None),
                         hora_fill=(f"{t['fill_t']//3600000:02d}:{t['fill_t']//60000%60:02d}:{t['fill_t']//1000%60:02d}" if t else None),
                         saida=(t["legs"][-1][3] if t else None), motivo=(t["legs"][-1][1] if t else "sem_fill"),
                         hora_saida=(f"{t['legs'][-1][2]//3600000:02d}:{t['legs'][-1][2]//60000%60:02d}:{t['legs'][-1][2]//1000%60:02d}" if t else None),
                         pnl_1_contrato_brl=(round(t["pnl"], 2) if t else 0.0)))
pd.DataFrame(rows).to_csv(AQUI / "EA_referencia_trades.csv", sep=";", decimal=",", index=False)
print("csv", len(rows))
