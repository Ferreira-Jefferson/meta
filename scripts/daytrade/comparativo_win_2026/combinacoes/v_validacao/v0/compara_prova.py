import pandas as pd
from pathlib import Path
A = Path(__file__).resolve().parent
R = A.parents[2] / "resultados"
for nm in ["Win", "Win_c1", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34"]:
    a = pd.read_csv(R / f"{nm}.csv"); b = pd.read_csv(A / "prova_2026" / f"{nm}.csv")
    ident = a.equals(b)
    ka = set(map(tuple, a.drop(columns=["estrategia"]).astype(str).values)); kb = set(map(tuple, b.drop(columns=["estrategia"]).astype(str).values))
    com = len(ka & kb)
    set_ = a[a.entrada >= "2026-09-01"]; sep_b = b[b.entrada >= "2026-09-01"]
    real = a[a.entrada >= "2026-02-20"]
    kr = set(map(tuple, real.drop(columns=["estrategia"]).astype(str).values))
    print(f"{nm:24s} original {len(a)} ops / shim {len(b)} | identicas {com}/{len(a)} | CSV byte-igual {ident} | set/26 {len(set_)} vs {len(sep_b)} | ticks reais (>=20/02) {len(kr & kb)}/{len(real)} | rs {a.rs.sum():.2f} vs {b.rs.sum():.2f}", flush=True)
