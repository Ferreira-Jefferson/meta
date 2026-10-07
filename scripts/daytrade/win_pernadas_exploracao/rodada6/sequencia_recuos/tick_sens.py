"""Sensibilidade ticks x M1 (mar-jun/2026, mesmos dias): mesma maquina, caminho = pontos de virada dos ticks vs 2 pts/vela."""
import glob, os, sys
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
import gera

TICKS = "C:/Users/Jeffe/Documents/study/meta/data/cache_win_ticks/WIN@D/"
CFG = [(T, dv) for T in (250, 500, 750) for dv in (5, 8)]


def virada(pr, tm):
    d = np.diff(pr); nz = np.nonzero(d)[0]
    pr2 = np.concatenate([[pr[0]], pr[nz + 1]]); tm2 = np.concatenate([[tm[0]], tm[nz + 1]])
    if len(pr2) < 3: return pr2, tm2
    dd = np.sign(np.diff(pr2))
    keep = np.concatenate([[True], dd[1:] != dd[:-1], [True]])
    return pr2[keep], tm2[keep]


def dia(path):
    d = pd.Timestamp(os.path.basename(path)[:10])
    dias, atr, ds = gera.carrega()
    v = dias[d]
    tk = pd.read_pickle(path, compression=None); tk = tk[tk["last"] > 0]
    t = pd.to_datetime(tk.time_msc.values, unit="ms")
    m = (t.hour * 60 + t.minute).values
    ok = (m >= 540) & (m <= 1075) & (t.normalize() == d)
    pr = tk["last"].values[ok]; tm = m[ok]
    mm = v["min"]
    lo = np.full(1500, np.nan); hi = np.full(1500, np.nan); cl = np.full(1500, np.nan)
    lo[mm] = v["l"]; hi[mm] = v["h"]; cl[mm] = v["c"]
    ok2 = ~np.isnan(cl[tm]); pr, tm = pr[ok2], tm[ok2]
    if len(pr) < 1000: return d, None
    off = np.median(pr - cl[tm])
    ok3 = (pr - off >= lo[tm] - 100) & (pr - off <= hi[tm] + 100)
    pr, tm = pr[ok3] - off, tm[ok3]
    if len(pr) < 1000: return d, None
    pr, tm = virada(pr, tm)
    out = {}
    Pm, TMm = gera.caminho(v)
    for T, dv in CFG:
        for nome, (P, TM) in (("tick", (pr, tm)), ("m1", (Pm, TMm))):
            R, Tr = [], []
            for sgn in (1, -1):
                r0, t0 = [], []
                gera.maquina(P, TM, T, T / dv, sgn, d, r0, t0); gera.pos_trades(P, t0, sgn)
                R += r0; Tr += t0
            out[(T, dv, nome)] = (R, Tr)
    return d, out


if __name__ == "__main__":
    files = sorted(glob.glob(TICKS + "2026-0[3-6]-*.pkl"))
    acc = {}
    with ProcessPoolExecutor(4) as ex:
        futs = [ex.submit(dia, p) for p in files]
        for fu in as_completed(futs):
            d, out = fu.result()
            if out is None: print(d.date(), "pulado", flush=True); continue
            for k, (R, Tr) in out.items():
                a = acc.setdefault(k, ([], []))
                a[0].extend(R); a[1].extend(Tr)
            print(d.date(), "ok", flush=True)
    rows = []
    for (T, dv, nome), (R, Tr) in sorted(acc.items()):
        rec = gera.sequencia(pd.DataFrame(R)); trd = pd.DataFrame(Tr)
        e = rec[rec.elig]; ee = e[e.res.isin(["S", "M"])]
        j1 = trd[(trd.j == 1) & trd.elig]
        j1f = j1.merge(rec[["dia", "sgn", "ep", "k_total", "first_ok"]], on=["dia", "sgn", "ep", "k_total"], how="left")
        S = rec[rec.elig & (rec.res == "S")].sort_values(["dia", "sgn", "ep", "k_total"])
        g = S.groupby(["dia", "sgn", "ep"], sort=False)
        S = S.assign(nxd=g["depth"].shift(-1), nxk=g["k_total"].shift(-1)); S = S[S.nxk == S.k_total + 1]
        s1 = S[S.k_elig == 1]
        att = ee.att
        rows.append(dict(T=T, m=int(T / dv), caminho=nome, n_rec_eleg=len(e), n_dias=rec.dia.nunique(),
                         P_S_conf=(ee.res == "S").mean(), att1=(att == 1).mean(), att2=(att == 2).mean(), att3=(att == 3).mean(), att4p=(att >= 4).mean(),
                         P_1a=j1f.first_ok.mean(), r1_med=e[e.k_elig == 1].depth.median(), r2_med=e[e.k_elig == 2].depth.median(),
                         P_r2_lt_r1=(s1.nxd < s1.depth).mean(), n_pares=len(s1),
                         P3R=(j1.mfe >= 3).mean(), P5R=(j1.mfe >= 5).mean(), P10R=(j1.mfe >= 10).mean(), n_trd=len(j1)))
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    txt = df.round(3).to_string()
    print(txt); open("out_txt/tick_sens.txt", "w", encoding="utf-8").write(txt)
