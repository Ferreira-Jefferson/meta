"""W1: pernadas do gráfico semanal; correções medidas dentro delas nas velas de H1 ou M15 (série contínua)."""
import sys, json
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, sys.argv[1])
from exp_padroes import carrega, caminho, zigzag, correcoes, TFS
from exp_padroes2 import tabela

def unidade(inner, pts):
    m1 = carrega()
    iso = m1.index.isocalendar(); wk = (iso.year.values * 100 + iso.week.values)
    m1 = m1.assign(wk=wk)
    W = m1.groupby("wk").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), vol=("vol", "sum"))
    r = m1.resample(TFS[inner], label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last", "vol": "sum", "wk": "first"}).dropna()
    pw, iw = caminho(W[["open", "high", "low", "close", "vol"]].to_numpy(float))
    pi, ii = caminho(r[["open", "high", "low", "close", "vol"]].to_numpy(float))
    wk_of_pt = r["wk"].to_numpy()[ii]; wks = W.index.to_numpy()
    piv = zigzag(pw, pts); rows = []
    def acha(k, ini):
        w = wks[iw[k]]; cand = np.where((wk_of_pt == w) & (pi == pw[k]))[0]
        cand = cand[cand >= ini]
        return int(cand[0]) if len(cand) else None
    last = 0; rot = []
    for j in range(len(piv) - 1):
        a, b = piv[j], piv[j + 1]
        if j + 2 == len(piv): break
        ka = acha(a, last); kb = acha(b, ka if ka is not None else last)
        if ka is None or kb is None or kb <= ka: continue
        last = kb; cc = correcoes(pi, ka, kb); size = abs(pw[b] - pw[a])
        rows.append((size / pts, [c[0] for c in cc], [c[1] for c in cc if c[2] >= 20]))
    return dict(tf="W1", inner=inner, pts=pts, n=len(rows), t5=tabela(rows))

if __name__ == "__main__":
    out = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(unidade, inn, p) for inn in ["H1", "M15"] for p in [500, 750, 1000, 1500, 2000]]
        for fu in as_completed(futs):
            r = fu.result(); out.append(r)
            print(r["inner"], r["pts"], r["n"], {m: (v["n"], round(v["corr"], 2)) for m, v in r["t5"].items()}, flush=True)
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
