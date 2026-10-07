"""Sensibilidade: mesmo pipeline sobre o caminho de TICKS (so pontos de virada) vs caminho M1, nos mesmos dias (mar-jun/2026)."""
import glob, os, sys
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
import fractal_core as fc

TICKS = "C:/Users/Jeffe/Documents/study/meta/data/cache_win_ticks/WIN@D/"
ESC = [(250, 65), (500, 125), (750, 190)]


def virada(pr, tm):
    """So pontos de virada (extremos locais) + primeiro e ultimo."""
    d = np.diff(pr)
    nz = np.nonzero(d)[0]
    pr2 = np.concatenate([[pr[0]], pr[nz + 1]])
    tm2 = np.concatenate([[tm[0]], tm[nz + 1]])
    if len(pr2) < 3: return pr2, tm2
    dd = np.sign(np.diff(pr2))
    keep = np.concatenate([[True], dd[1:] != dd[:-1], [True]])
    return pr2[keep], tm2[keep]


def dia(path):
    d = pd.Timestamp(os.path.basename(path)[:10])
    tk = pd.read_pickle(path, compression=None)
    tk = tk[tk["last"] > 0]
    t = pd.to_datetime(tk.time_msc.values, unit="ms")
    m = (t.hour * 60 + t.minute).values
    ok = (m >= 540) & (m <= 1075) & (t.normalize() == d)
    pr = tk["last"].values[ok]; tm = m[ok]
    if len(pr) < 1000: return d, None, None, 0
    m1 = fc.carregar_m1(str(d.date()), str((d + pd.Timedelta(days=1)).date()))
    # tick@D mistura niveis (contratos/ajuste): alinha ao M1 (offset = mediana tick-M1) e descarta ticks fora da faixa do minuto +-100
    mm = (m1.index.hour * 60 + m1.index.minute).values
    lo = np.full(1500, np.nan); hi = np.full(1500, np.nan); cl = np.full(1500, np.nan)
    lo[mm] = m1.low.values; hi[mm] = m1.high.values; cl[mm] = m1.close.values
    ok2 = ~np.isnan(cl[tm])
    pr, tm = pr[ok2], tm[ok2]
    off = np.median(pr - cl[tm])
    ok3 = (pr - off >= lo[tm] - 100) & (pr - off <= hi[tm] + 100)
    pr, tm = pr[ok3] - off, tm[ok3]
    if len(pr) < 1000: return d, None, None, 0
    pr, tm = virada(pr, tm)
    a = fc.eventos_dia(m1, d, ESC, pr_tm=(tm, pr))
    b = fc.eventos_dia(m1, d, ESC)
    return d, a, b, len(pr)


if __name__ == "__main__":
    files = sorted(glob.glob(TICKS + "2026-0[3-6]-*.pkl"))
    A, B = [], []
    with ProcessPoolExecutor(4) as ex:
        futs = [ex.submit(dia, p) for p in files]
        for fu in as_completed(futs):
            d, a, b, n = fu.result()
            if a is None: print(d, "pulado", flush=True); continue
            A += a; B += b
            print(d.date(), len(a), len(b), n, flush=True)
    A = pd.DataFrame(A); B = pd.DataFrame(B)
    A.to_pickle("ev_tick.pkl"); B.to_pickle("ev_m1_tickdias.pkl")
