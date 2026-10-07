"""lib.py -- carga, colunas derivadas e comparacao real x nulo (embaralhado) x formula."""
import os, glob, pickle
import numpy as np, pandas as pd

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
PERIODOS = {"desc": ("2026-01-01", "2026-06-30"), "conf": ("2026-07-01", "2026-08-31"), "set": ("2026-09-01", "2026-09-30")}
RB = [0, .23, .38, .50, .62, .79, 1.01]
RBL = ["0-23", "23-38", "38-50", "50-62", "62-79", "79-100"]
NY_MUDA = pd.Timestamp("2026-03-08")   # inicio do horario de verao dos EUA (ate aqui NY abre 11:30 BRT; depois 10:30)


def hb(h):
    return np.where(h < 11, "a<11h", np.where(h < 13, "b11-13h", "c>=13h"))


def prep(rec, trd, per, T):
    a, b = PERIODOS[per]
    rec = rec[(rec.dia >= a) & (rec.dia <= b)].copy()
    trd = trd[(trd.dia >= a) & (trd.dia <= b)].copy()
    for d in (rec, trd):
        d["AT"] = d["A"] / T
        d["Abin"] = np.where(d.AT < 1.5, "A1:<1,5T", np.where(d.AT < 2.5, "A2:1,5-2,5T", "A3:>=2,5T"))
    rec["hora"] = rec.tconf / 60.0
    rec["hb"] = hb(rec.hora.values)
    rec["ny_off"] = np.where(rec.dia < NY_MUDA, 1.0, 0.0)
    rec["hb_ny"] = hb(rec.hora.values - rec.ny_off.values)
    trd["hora"] = trd.tmin / 60.0
    trd["hb"] = hb(trd.hora.values)
    trd["hb_ny"] = hb(trd.hora.values - np.where(trd.dia < NY_MUDA, 1.0, 0.0))
    rec["k"] = np.where(rec.k_elig >= 4, "4+", rec.k_elig.astype(int).astype(str))
    rec["kt"] = np.where(rec.k_total >= 4, "4+", rec.k_total.astype(int).astype(str))
    key = ["dia", "sgn", "ep", "k_total"]
    m = rec[key + ["k", "kt", "k_elig", "r_prev", "r_prev2", "first_ok", "res", "depth", "alcance"]]
    trd = trd.merge(m, on=key, how="left")
    trd["rA"] = trd.r / trd.A
    trd["rb"] = pd.cut(trd.rA, RB, labels=RBL, right=False).astype(str)
    trd["vsprev"] = np.where(trd.r_prev.isna(), "sem anterior", np.where(trd.r < trd.r_prev, "menor que o anterior", "maior/igual ao anterior"))
    return rec, trd


def carrega(T, div, per):
    def ld(nome):
        with open(os.path.join(OUT, nome), "rb") as f:
            return pickle.load(f)
    real = prep(*ld(f"ev_T{T}_d{div}_real0.pkl"), per, T)
    nulls = []
    for f in sorted(glob.glob(os.path.join(OUT, f"ev_T{T}_d{div}_chain*.pkl"))):
        nulls.append(prep(*ld(os.path.basename(f)), per, T))
    return real, nulls


def carrega_raw(T, div, per):
    out = []
    for f in sorted(glob.glob(os.path.join(OUT, f"ev_T{T}_d{div}_raw*.pkl"))):
        with open(f, "rb") as fh:
            out.append(prep(*pickle.load(fh), per, T))
    return out


def boot_ic(df, keys, val, B=300, seed=7):
    """IC95 bootstrap por DIA (cluster) da media de val em cada grupo."""
    rs = np.random.default_rng(seed)
    dias = np.array(sorted(df.dia.unique()))
    D = len(dias)
    if D == 0:
        return {}
    di = {d: i for i, d in enumerate(dias)}
    g = df.groupby(keys + ["dia"])[val].agg(["sum", "count"]).reset_index()
    g["di"] = g.dia.map(di)
    idx = rs.integers(0, D, size=(B, D))
    res = {}
    for k, gg in g.groupby(keys, sort=False):
        s = np.zeros(D); c = np.zeros(D)
        s[gg.di.values] = gg["sum"].values; c[gg.di.values] = gg["count"].values
        ss = s[idx].sum(1); cc = c[idx].sum(1)
        ok = cc > 0
        r = ss[ok] / cc[ok]
        res[k if isinstance(k, tuple) else (k,)] = (np.percentile(r, 2.5), np.percentile(r, 97.5)) if ok.sum() > 20 else (np.nan, np.nan)
    return res


CONT = {"cel": 0, "z2": 0, "z3": 0}


def compara(real, nulls, keys, val, nul=None, minn=30, ic=True, fmt="{:.3f}"):
    """real: df; nulls: lista de df (um por sorteio). val: coluna 0/1 ou numerica. nul: coluna da formula (por evento).
    Retorna df com n, real, formula, nulo(mean), sd_nulo, z, ic_lo, ic_hi."""
    g = real.groupby(keys)[val].agg(n="count", real="mean")
    if nul is not None:
        g["formula"] = real.groupby(keys)[nul].mean()
    cat = []
    for i, nd in enumerate(nulls):
        if len(nd) == 0:
            continue
        x = nd.groupby(keys)[val].agg(["mean", "count"]).reset_index()
        x["draw"] = i
        cat.append(x)
    if cat:
        c = pd.concat(cat)
        s = c.groupby(keys)["mean"].agg(nulo="mean", sd="std", nd="count")
        nn = c.groupby(keys)["count"].mean().rename("n_nulo")
        g = g.join(s).join(nn)
        g["z"] = (g["real"] - g["nulo"]) / g["sd"].replace(0, np.nan)
    g = g[g.n >= minn]
    if "z" in g:
        zz = g["z"].abs()
        CONT["cel"] += int(zz.notna().sum()); CONT["z2"] += int((zz > 2).sum()); CONT["z3"] += int((zz > 3).sum())
    if ic and len(g):
        bi = boot_ic(real, keys, val)
        lo, hi = [], []
        for k in g.index:
            kk = k if isinstance(k, tuple) else (k,)
            a, b = bi.get(kk, (np.nan, np.nan))
            lo.append(a); hi.append(b)
        g["ic_lo"] = lo; g["ic_hi"] = hi
    return g


def mostra(df, titulo, f=None, nd=3):
    pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 500)
    txt = f"\n### {titulo}\n" + df.round(nd).to_string() + "\n"
    if "z" in df.columns and os.environ.get("CELLS"):
        d = df.reset_index()
        num = ("n", "real", "formula", "nulo", "sd", "nd", "n_nulo", "z", "ic_lo", "ic_hi", "rho_real", "rho_nulo", "sd_nulo",
               "frac", "frac_nulo", "r_pts", "r_med", "rA_med", "dur_min")
        kc = [c for c in d.columns if c not in num]
        d["chave"] = d[kc].astype(str).agg("|".join, axis=1) if kc else ""
        d["tabela"] = titulo.split()[0]
        cols = [c for c in ("tabela", "chave", "n", "real", "nulo", "z") if c in d.columns]
        pth = os.environ["CELLS"]
        d[cols].to_csv(pth, mode="a", header=not os.path.exists(pth), index=False)
    print(txt, flush=True)
    if f is not None:
        f.write(txt)
    return txt
