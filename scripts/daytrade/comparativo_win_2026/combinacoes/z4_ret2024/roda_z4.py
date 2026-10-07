# -*- coding: utf-8 -*-
"""python roda_z4.py <2022_2025|2026> <base|nome_do_filtro> [sempos]  -> trades/<filtro>_<periodo>.csv (operacoes + contexto)
Na base confere contra y4b/trades/rettf_M15_<periodo>.csv (colunas do port, identicas)."""
import sys
import time
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import port_z4  # noqa: E402

per, nome = sys.argv[1], sys.argv[2]
sem_pos = len(sys.argv) > 3 and sys.argv[3] == "sempos"
suf = "_sempos" if sem_pos else ""
filtro = None
if nome != "base":
    import filtros
    filtro = filtros.FILTROS[nome]
t0 = time.time()
df, nb = port_z4.roda(per, filtro, sem_pos)
(AQUI / "trades").mkdir(exist_ok=True)
out = AQUI / "trades" / f"{nome}_{per}{suf}.csv"
df.to_csv(out, index=False)
msg = f"{nome}{suf} {per} ops={len(df)} liq_bruto={df.rs.sum():.2f} bloqueios={nb} {time.time()-t0:.0f}s -> {out.name}"
msg += f" velas_pos_no_hist={port_z4.CONTA_POS}"
if nome == "base" and not sem_pos:
    ref = pd.read_csv(port_z4.Y4B / "trades" / f"rettf_M15_{per}.csv")
    cols = list(ref.columns)
    a = df[cols].reset_index(drop=True)
    igual = len(a) == len(ref) and (a.astype(str).values == ref.astype(str).values).all()
    if not igual and len(a) == len(ref):
        igual = bool(((a.rs - ref.rs).abs() < 1e-9).all() and (a.entrada == ref.entrada).all() and (a.saida == ref.saida).all())
    msg += f" | confere com y4b: {'IGUAL' if igual else 'DIFERENTE'}"
print(msg, flush=True)
