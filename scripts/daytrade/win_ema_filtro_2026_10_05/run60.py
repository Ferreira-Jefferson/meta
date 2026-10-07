"""60 meses WIN@D (simulador M1 do HTML): base (Teste 13) vs base+EMA {50,100,150,200} x {close, vela}.
Saidas: run60_resultados.csv, run60_blocos.csv, run60_trades_<var>.csv. Uso: python run60.py"""
import sys, os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sim60_m1 as S
OUT = Path(__file__).resolve().parent
_C = {}

def met(rs):
    rs = np.asarray(rs, float)
    if not len(rs): return dict(n=0, win=0, liq=0, dd=0, pf=0, op=0, be=float("nan"))
    g = rs[rs > 0]; l = -rs[rs < 0]; eq = np.cumsum(rs); pk = np.maximum.accumulate(np.r_[0, eq])[1:]
    be = l.mean() / (g.mean() + l.mean()) * 100 if len(g) and len(l) else float("nan")
    return dict(n=len(rs), win=round(100 * (rs > 0).mean(), 1), liq=round(rs.sum(), 0), dd=round((pk - eq).max(), 0),
                pf=round(g.sum() / l.sum(), 2) if l.sum() else None, op=round(rs.mean(), 2), be=round(be, 1))

def unidade(nome, ema, modo):
    if "d" not in _C: _C["d"] = S.preparar()
    m1, b = _C["d"]
    t = S.rodar(m1, b, True, ema, modo)
    t.to_csv(OUT / f"run60_trades_{nome}.csv", index=False)
    rss = None
    try:
        import psutil; rss = round(psutil.Process().memory_info().rss / 1e6)
    except Exception: pass
    return nome, t, rss

if __name__ == "__main__":
    var = [("base", None, "close")]
    for per in (50, 100, 150, 200):
        var += [(f"ema{per}_close", per, "close"), (f"ema{per}_vela", per, "vela")]
    T, res = {}, []
    with ProcessPoolExecutor(4) as ex:
        fu = [ex.submit(unidade, *v) for v in var]
        for f in as_completed(fu):
            n, t, rss = f.result(); T[n] = t; m = met(t.rs); res.append(dict(variante=n, **m))
            print(n, m, "RSS_MB", rss, flush=True)
            pd.DataFrame(res).to_csv(OUT / "run60_resultados.csv", index=False)
    # blocos + bootstrap por dia da diferenca (filtro - base)
    dias = sorted(set().union(*[set(map(str, t.dia)) for t in T.values()]))
    daily = {n: t.assign(dia=t.dia.astype(str)).groupby("dia").rs.sum().reindex(dias, fill_value=0.0) for n, t in T.items()}
    rng = np.random.default_rng(7); N = 20000; idx = rng.integers(0, len(dias), (N, len(dias)))
    blocos, boot = [], []
    bl = [("2021-10..2025-05", "2021-10-01", "2025-05-31"), ("2025-06..2026-10", "2025-06-01", "2026-10-31")] + \
         [(str(y), f"{y}-01-01", f"{y}-12-31") for y in range(2021, 2027)]
    for n in T:
        for nm, a, z in bl:
            x = T[n][(T[n].dia.astype(str) >= a) & (T[n].dia.astype(str) <= z)]
            blocos.append(dict(variante=n, bloco=nm, **met(x.rs)))
        if n == "base": continue
        d = (daily[n] - daily["base"]).to_numpy(); s = d[idx].sum(1)
        lo, hi = np.percentile(s, [2.5, 97.5])
        boot.append(dict(variante=n, dif_liquido=round(d.sum(), 0), ic95_lo=round(lo, 0), ic95_hi=round(hi, 0), dias=len(dias), dias_com_diferenca=int((d != 0).sum()),
                         trades_removidos=len(T["base"]) - len(T[n])))
        print("BOOT", boot[-1], flush=True)
    pd.DataFrame(blocos).to_csv(OUT / "run60_blocos.csv", index=False)
    pd.DataFrame(boot).to_csv(OUT / "run60_bootstrap.csv", index=False)
