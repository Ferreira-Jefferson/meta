import sys, json
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, sys.argv[1])
from exp_padroes import carrega, dias_tf, features, analisa, TFS
from exp_padroes2 import tabela, legs_de

def unidade(tf, k):
    m1 = carrega(); dias = dias_tf(m1, TFS[tf]); f = features(dias)
    sel = [d for d in sorted(dias) if not np.isnan(f.loc[d, "atr_prev5"])]
    thr = {d: k * f.loc[d, "atr_prev5"] for d in sel}
    res = {d: analisa(dias[d], thr[d]) for d in sel}
    rows = legs_de(res, thr)
    ld = np.mean([len(v) for v in res.values()])
    sete = {d: round(float(f.loc[d, "atr_prev5"]), 1) for d in sel if d.startswith("2026-09")}
    allc = [c for r in rows for c in r[1]]
    return dict(tf=tf, k=k, legs_dia=ld, corr_leg=len(allc)/len(rows),
                t5=tabela([r[:3] for r in rows]), tset=tabela([r[:3] for r in rows if r[3].startswith("2026-09")]),
                atr_set=sete)

if __name__ == "__main__":
    out = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(unidade, tf, k) for tf in TFS for k in (1.0, 2.0, 3.0)]
        for fu in as_completed(futs):
            r = fu.result(); out.append(r)
            print(f"{r['tf']} k={r['k']} pernadas/dia={r['legs_dia']:.1f} corr/pernada={r['corr_leg']:.2f}", {m: round(v['corr'], 2) for m, v in r['t5'].items()}, flush=True)
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
