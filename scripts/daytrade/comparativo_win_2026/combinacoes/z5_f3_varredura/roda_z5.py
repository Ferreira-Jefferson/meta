# -*- coding: utf-8 -*-
"""python roda_z5.py <2022_2025|2026> <k> [sempos] -> trades/k<k>_<per>[_sempos].csv
f3 parametrizado: arma so' se faixa_dia_atrd >= k (k=0 = base, k=0,5 = f3 da Z4). Usa port_z4 sem editar."""
import sys, time
from pathlib import Path
import pandas as pd
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "z4_ret2024"))
import port_z4  # noqa: E402

per, ks = sys.argv[1], sys.argv[2]
sem_pos = len(sys.argv) > 3 and sys.argv[3] == "sempos"
k = float(ks)
filtro = (lambda c: c["faixa_dia_atrd"] >= k) if k > 0 else None
t0 = time.time()
df, nb = port_z4.roda(per, filtro, sem_pos)
out = AQUI / "trades" / f"k{ks}_{per}{'_sempos' if sem_pos else ''}.csv"
df.to_csv(out, index=False)
print(f"k={ks} {per} sempos={sem_pos} ops={len(df)} bruto={df.rs.sum():.2f} bloq={nb} {time.time()-t0:.0f}s", flush=True)
