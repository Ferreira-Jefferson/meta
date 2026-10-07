import sys, pickle
from datetime import date
sys.path.insert(0, r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\comparativo_win_2026")
import port_win_gap_barra1 as P
m1 = P.m1_total(); gt = P.ticks_fn(m1); todos = sorted(set(m1.index.date))
out = {}
for a, (i, f) in {"2023": (date(2023,1,1), date(2023,12,31)), "2026": (date(2026,1,1), date(2026,10,5))}.items():
    d = [x for x in todos if i <= x <= f]
    tr, s, q, dg = P.rodar(d, m1, gt)
    out[a] = (tr, dg)
pickle.dump(out, open(sys.argv[1], "wb"))
print({k: len(v[0]) for k, v in out.items()})
