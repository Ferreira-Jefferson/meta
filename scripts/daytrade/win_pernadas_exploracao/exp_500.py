"""Referência de 5 anos com pernada mínima FIXA em pontos (>=500), para M5/M15/H1 (zera a cada pregão) e W1 (contínuo)."""
import sys, json
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, sys.argv[1])
from exp_padroes import carrega, dias_tf, analisa, TFS
from exp_padroes2 import tabela

PTS = [500, 750, 1000, 1500, 2000]

def semanas(m1):
    g = m1.groupby([m1.index.isocalendar().year.values, m1.index.isocalendar().week.values])
    rows = [[x.open.iloc[0], x.high.max(), x.low.min(), x.close.iloc[-1], x.vol.sum()] for _, x in g]
    idx = [str(x.index[0].date()) for _, x in g]
    return idx, np.array(rows, float)

def rows_de(legs, thr, rotulo):
    return [(s / thr, [c[0] for c in cc], [c[1] for c in cc if c[2] >= 20], rotulo) for s, ab, cc in legs if not ab]

def unidade(tf, pts):
    m1 = carrega()
    if tf == "W1":
        idx, b = semanas(m1)
        legs = analisa(b, pts)
        rows = rows_de(legs, pts, "")
        dias = len(np.unique(m1.index.date))
        return dict(tf=tf, pts=pts, legs_dia=len(legs) / dias, t5=tabela([r[:3] for r in rows]))
    dias = dias_tf(m1, TFS[tf]); rows = []; n = 0
    for d in sorted(dias):
        legs = analisa(dias[d], pts); n += len(legs); rows += rows_de(legs, pts, d)
    return dict(tf=tf, pts=pts, legs_dia=n / len(dias), t5=tabela([r[:3] for r in rows]),
                tset=tabela([r[:3] for r in rows if r[3].startswith("2026-09")]))

if __name__ == "__main__":
    out = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(unidade, tf, p) for tf in ["M5", "M15", "H1", "W1"] for p in PTS]
        for fu in as_completed(futs):
            r = fu.result(); out.append(r)
            print(r["tf"], r["pts"], f"pernadas/dia={r['legs_dia']:.2f}", {m: (v["n"], round(v["corr"], 2)) for m, v in r["t5"].items()},
                  {m: (v["n"], round(v["corr"], 2)) for m, v in r.get("tset", {}).items()}, flush=True)
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
