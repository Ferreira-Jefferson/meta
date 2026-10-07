import sys, pickle
from datetime import date
sys.path.insert(0, r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\comparativo_win_2026")
import port_win_gap_barra1 as P
a = pickle.load(open("out/base_antes.pkl","rb"))
m1 = P.m1_total(); gt = P.ticks_fn(m1); todos = sorted(set(m1.index.date))
for k,(i,f) in {"2023": (date(2023,1,1), date(2023,12,31)), "2026": (date(2026,1,1), date(2026,10,5))}.items():
    tr, s, q, dg = P.rodar([x for x in todos if i<=x<=f], m1, gt)
    print(k, "identico:", tr == a[k][0] and dg == a[k][1])
