"""Estudo descritivo WIN: pernadas (zigue-zague relativo ao ATR) em relacao a linha de abertura.

Caminho do dia: p0 = OPEN da 1a barra, p[i] = CLOSE da barra i-1.
Limiar do zigue-zague = K x ATR14 diario ate D-1 (SMA do TR, sem look-ahead), K em {0.1,0.2,0.3}.
Banda morta da linha de abertura = 0.05 x ATR(D-1), com histerese (so troca de lado ao ultrapassar a banda oposta).
Nulo: embaralha os retornos do caminho (diffs M1) dentro de cada dia, NREP vezes (preserva soma/volatilidade).
IS 2021-10-01..2024-12-31, OOS 2025-01-01..fim.
"""
import sys, os
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = r"C:\Users\Jeffe\Documents\study\meta\data\wdo-mt5\WIN@D_M1_202110010900_202610011717.csv"
KS = [0.1, 0.2, 0.3]
BAND_K = 0.05
NREP = 8
MIN_BARS = 200


def load():
    d = pd.read_csv(CSV, sep="\t")
    d.columns = [c.strip("<>").lower() for c in d.columns]
    d["dt"] = pd.to_datetime(d["date"] + " " + d["time"], format="%Y.%m.%d %H:%M:%S")
    return d


def zigzag(p, thr):
    """retorna lista de pivots (idx, preco, tipo +1 topo/-1 fundo, idx_confirmacao)."""
    n = len(p)
    piv = []
    dirn = 0
    lo = hi = p[0]; lo_i = hi_i = 0
    ext = p[0]; ext_i = 0
    for i in range(1, n):
        x = p[i]
        if dirn == 0:
            if x < lo: lo, lo_i = x, i
            if x > hi: hi, hi_i = x, i
            if x - lo >= thr and lo_i < i:
                piv.append((lo_i, lo, -1, i)); dirn = 1; ext, ext_i = x, i
            elif hi - x >= thr and hi_i < i:
                piv.append((hi_i, hi, 1, i)); dirn = -1; ext, ext_i = x, i
        elif dirn == 1:
            if x > ext: ext, ext_i = x, i
            elif ext - x >= thr:
                piv.append((ext_i, ext, 1, i)); dirn = -1; ext, ext_i = x, i
        else:
            if x < ext: ext, ext_i = x, i
            elif x - ext >= thr:
                piv.append((ext_i, ext, -1, i)); dirn = 1; ext, ext_i = x, i
    if dirn != 0:
        piv.append((ext_i, ext, 1 if dirn == 1 else -1, n))  # perna em curso (sem confirmacao)
    return piv


def estado(p, op, band):
    s = np.zeros(len(p), dtype=np.int8)
    cur = 0
    up = op + band; dn = op - band
    for i in range(len(p)):
        x = p[i]
        if x > up: cur = 1
        elif x < dn: cur = -1
        s[i] = cur
    return s


def analisa(p, tmin, atr, k):
    """p: caminho (n+1), tmin: minuto do dia por elemento do caminho."""
    n = len(p)
    thr = k * atr
    op = p[0]
    st = estado(p, op, BAND_K * atr)
    piv = zigzag(p, thr)
    # legs: entre pivots consecutivos; direcao pelo tipo do pivot final
    cm = np.maximum.accumulate(p); cn = np.minimum.accumulate(p)
    leg_end = []; leg_dir = []; leg_start = []
    for a, b in zip(piv[:-1], piv[1:]):
        leg_end.append(b[0]); leg_dir.append(b[2]); leg_start.append(a[0])
    leg_end = np.array(leg_end, dtype=int); leg_dir = np.array(leg_dir, dtype=int); leg_start = np.array(leg_start, dtype=int)
    n_up = int((leg_dir == 1).sum()); n_dn = int((leg_dir == -1).sum())
    # novas maximas/minimas do dia por perna
    nh_t = []; nl_t = []
    for e, d, s0 in zip(leg_end, leg_dir, leg_start):
        if d == 1 and p[e] > cm[s0]: nh_t.append(tmin[e])
        if d == -1 and p[e] < cn[s0]: nl_t.append(tmin[e])
    # cruzamentos
    nz = st[st != 0]
    cross = int((np.diff(nz) != 0).sum()) if len(nz) > 1 else 0
    hi, lo, cl = p.max(), p.min(), p[-1]
    rng = hi - lo
    day = dict(n_up=n_up, n_dn=n_dn, n_legs=n_up + n_dn, cross=cross, new_hi=len(nh_t), new_lo=len(nl_t),
               range_atr=rng / atr, dir_atr=(cl - op) / atr,
               trend=int(rng > 0 and ((cl - lo) / rng >= 0.8 or (cl - lo) / rng <= 0.2)),
               pos_close=(cl - lo) / rng if rng > 0 else 0.5, nh_t=nh_t, nl_t=nl_t)
    # episodios
    eps = []
    idx_nz = np.where(st != 0)[0]
    if len(idx_nz):
        s_nz = st[idx_nz[0]:]
        off = idx_nz[0]
        chg = np.r_[0, np.where(np.diff(s_nz) != 0)[0] + 1, len(s_nz)]
        epid = np.full(n, -1)
        for j in range(len(chg) - 1):
            a, b = chg[j] + off, chg[j + 1] + off
            epid[a:b] = j
            side = int(s_nz[chg[j]])
            seg = p[a:b] - op
            exc = (seg.max() if side == 1 else -seg.min()) / atr
            m = (leg_end >= a) & (leg_end < b)
            eps.append(dict(side=side, dur=b - a, exc_atr=exc,
                            legs_up=int((leg_dir[m] == 1).sum()), legs_dn=int((leg_dir[m] == -1).sum())))
    else:
        epid = np.full(n, -1)
    # condicional 5 (pivots confirmados antes do fim)
    c5 = []
    fut_max = np.maximum.accumulate(p[::-1])[::-1]  # max de p[j:]
    fut_min = np.minimum.accumulate(p[::-1])[::-1]
    fut_below = np.maximum.accumulate((st == -1)[::-1].astype(np.int8))[::-1]
    fut_above = np.maximum.accumulate((st == 1)[::-1].astype(np.int8))[::-1]
    cnt = {}
    for (ix, pr, tp, cf), ld_end in zip(piv[1:], leg_end):
        pass
    for a, b in zip(piv[:-1], piv[1:]):
        ix, pr, tp, cf = b
        if cf >= n - 1: continue
        # topo com preco acima da abertura na confirmacao e no pivot, mesmo episodio
        if epid[ix] < 0 or epid[ix] != epid[cf]: continue
        side = st[cf]
        if tp == 1 and side == 1:
            key = (epid[ix], 1); cnt[key] = cnt.get(key, 0) + 1
            nh_later = int(fut_max[cf + 1] > cm[cf])
            back = int(fut_below[cf + 1])
            c5.append(dict(side=1, k=cnt[key], extreme_later=nh_later, cross_back=back))
        elif tp == -1 and side == -1:
            key = (epid[ix], -1); cnt[key] = cnt.get(key, 0) + 1
            nl_later = int(fut_min[cf + 1] < cn[cf])
            back = int(fut_above[cf + 1])
            c5.append(dict(side=-1, k=cnt[key], extreme_later=nl_later, cross_back=back))
    return day, eps, c5


def run_k(k):
    d = load()
    d["dia"] = d["dt"].dt.date
    g = d.groupby("dia")
    daily = g.agg(h=("high", "max"), l=("low", "min"), c=("close", "last"), o=("open", "first"), nb=("close", "size"),
                  t0=("dt", "min"), t1=("dt", "max"))
    tr = np.maximum(daily.h - daily.l, np.maximum((daily.h - daily.c.shift()).abs(), (daily.l - daily.c.shift()).abs()))
    atr = tr.rolling(14).mean().shift(1)
    rng = np.random.default_rng(12345 + int(k * 100))
    days, epl, c5l = [], [], []
    for dia, sub in g:
        a = atr.loc[dia]
        if not np.isfinite(a) or a <= 0 or len(sub) < MIN_BARS: continue
        p = np.r_[sub.open.values[0], sub.close.values].astype(float)
        tmin = np.r_[sub.dt.dt.hour.values[0] * 60 + sub.dt.dt.minute.values[0],
                     (sub.dt.dt.hour * 60 + sub.dt.dt.minute).values]
        dp = np.diff(p)
        for rep in range(-1, NREP):
            if rep == -1: pp = p
            else: pp = np.r_[p[0], p[0] + np.cumsum(rng.permutation(dp))]
            day, eps, c5 = analisa(pp, tmin, a, k)
            day.update(dia=pd.Timestamp(dia), rep=rep, atr=a, nb=len(sub))
            days.append(day)
            for e in eps: e.update(dia=pd.Timestamp(dia), rep=rep); epl.append(e)
            for e in c5: e.update(dia=pd.Timestamp(dia), rep=rep); c5l.append(e)
    D = pd.DataFrame(days); E = pd.DataFrame(epl); C = pd.DataFrame(c5l)
    D["k"] = E["k"] = C["k_atr"] = k
    E["k"] = k; C = C.rename(columns={"k": "kpern"}); C["k_atr"] = k
    D["nh_t"] = D["nh_t"].apply(lambda x: ";".join(map(str, x)))
    D["nl_t"] = D["nl_t"].apply(lambda x: ";".join(map(str, x)))
    tag = f"{int(k*10):02d}"
    D.to_csv(os.path.join(HERE, f"c_dias_k{tag}.csv"), index=False, sep=";", decimal=",")
    E.to_csv(os.path.join(HERE, f"c_episodios_k{tag}.csv"), index=False, sep=";", decimal=",")
    C.to_csv(os.path.join(HERE, f"c_cond5_k{tag}.csv"), index=False, sep=";", decimal=",")
    return k, D, E, C


def spear(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 30: return np.nan
    return float(np.corrcoef(pd.Series(x[m]).rank(), pd.Series(y[m]).rank())[0, 1])


def split(df, w):
    return df[df.dia <= "2024-12-31"] if w == "IS" else df[df.dia >= "2025-01-01"]


def resumo(D, E, C):
    rows = []
    k = D.k.iloc[0]

    def add(achado, fn):
        r = {"k_atr": k, "achado": achado}
        for w in ("IS", "OOS"):
            Dw, Ew, Cw = split(D, w), split(E, w), split(C, w)
            real = fn(Dw[Dw.rep == -1], Ew[Ew.rep == -1], Cw[Cw.rep == -1], Dw, True)
            nul = [fn(Dw[Dw.rep == r_], Ew[Ew.rep == r_], Cw[Cw.rep == r_], Dw, False) for r_ in range(NREP)]
            nul = np.array(nul, dtype=float)
            r[w] = real
            r[f"nulo_{w}"] = float(np.nanmean(nul))
            r[f"nulo_{w}_sd"] = float(np.nanstd(nul))
        rows.append(r)

    f = lambda col, q=None: (lambda d, e, c, a, rl: float(d[col].mean() if q is None else d[col].quantile(q)))
    add("pernadas alta/dia (media)", f("n_up"))
    add("pernadas baixa/dia (media)", f("n_dn"))
    add("pernadas total/dia (mediana)", f("n_legs", .5))
    add("pernadas total/dia (p25)", f("n_legs", .25))
    add("pernadas total/dia (p75)", f("n_legs", .75))
    add("cruzamentos da abertura/dia (media)", f("cross"))
    add("cruzamentos/dia (mediana)", f("cross", .5))
    for j in (0, 1, 2, 3):
        add(f"P(cruzamentos={j if j<3 else '>=3'})", (lambda j: lambda d, e, c, a, rl: float((d.cross == j).mean() if j < 3 else (d.cross >= 3).mean()))(j))
    add("novas maximas (pernadas)/dia", f("new_hi"))
    add("novas minimas (pernadas)/dia", f("new_lo"))

    def frac_hora(h0, h1, col):
        def fn(d, e, c, a, rl):
            ts = [int(x) for s in d[col] if isinstance(s, str) and s for x in s.split(";")]
            ts = np.array(ts)
            return float(((ts >= h0 * 60) & (ts < h1 * 60)).mean()) if len(ts) else np.nan
        return fn
    for h0, h1 in ((9, 10), (10, 12), (12, 15), (15, 18)):
        add(f"novas max: % entre {h0}h-{h1}h", frac_hora(h0, h1, "nh_t"))
    add("range/ATR (mediana)", f("range_atr", .5))
    add("P(dia de tendencia: fecha nos 20% do extremo)", f("trend"))
    add("Spearman(n_pernadas, range/ATR)", lambda d, e, c, a, rl: spear(d.n_legs.values, d.range_atr.values))
    add("Spearman(n_pernadas, |dir|/ATR)", lambda d, e, c, a, rl: spear(d.n_legs.values, d.dir_atr.abs().values))
    add("Spearman(n_up-n_dn, dir/ATR)", lambda d, e, c, a, rl: spear((d.n_up - d.n_dn).values, d.dir_atr.values))
    add("Spearman(cruzamentos, range/ATR)", lambda d, e, c, a, rl: spear(d.cross.values, d.range_atr.values))
    add("P(tendencia | pernadas<=mediana)", lambda d, e, c, a, rl: float(d[d.n_legs <= d.n_legs.median()].trend.mean()))
    add("P(tendencia | pernadas>mediana)", lambda d, e, c, a, rl: float(d[d.n_legs > d.n_legs.median()].trend.mean()))

    def prev(col_prev, col_cur, absc=False):
        def fn(d, e, c, a, rl):
            d = d.sort_values("dia")
            x = d[col_prev].shift(1).values
            y = d[col_cur].abs().values if absc else d[col_cur].values
            return spear(x, y)
        return fn
    add("D-1 n_pernadas -> D range/ATR (Spearman)", prev("n_legs", "range_atr"))
    add("D-1 cruzamentos -> D range/ATR (Spearman)", prev("cross", "range_atr"))
    add("D-1 n_pernadas -> D n_pernadas (Spearman)", prev("n_legs", "n_legs"))
    add("D-1 cruzamentos -> D cruzamentos (Spearman)", prev("cross", "cross"))
    add("D-1 n_pernadas -> D |dir|/ATR (Spearman)", prev("n_legs", "dir_atr", True))
    add("D-1 (n_up-n_dn) -> D dir/ATR (Spearman)",
        lambda d, e, c, a, rl: (lambda dd: spear((dd.n_up - dd.n_dn).shift(1).values, dd.dir_atr.values))(d.sort_values("dia")))
    # episodios
    for side, nm in ((1, "acima"), (-1, "abaixo")):
        add(f"episodio {nm}: duracao mediana (min)", (lambda s: lambda d, e, c, a, rl: float(e[e.side == s].dur.median()))(side))
        add(f"episodio {nm}: excursao max mediana (ATR)", (lambda s: lambda d, e, c, a, rl: float(e[e.side == s].exc_atr.median()))(side))
        add(f"episodio {nm}: pernadas a favor (media)", (lambda s: lambda d, e, c, a, rl: float(e[e.side == s][("legs_up" if s == 1 else "legs_dn")].mean()))(side))
        add(f"episodio {nm}: pernadas contra (media)", (lambda s: lambda d, e, c, a, rl: float(e[e.side == s][("legs_dn" if s == 1 else "legs_up")].mean()))(side))
        add(f"episodio {nm}: n por dia", (lambda s: lambda d, e, c, a, rl: float(len(e[e.side == s]) / max(d.dia.nunique(), 1)))(side))
    # cond 5 (lados espelhados juntos)
    for kk in (1, 2, 3, 4):
        sel = (lambda kk: lambda c: c[c.kpern == kk] if kk < 4 else c[c.kpern >= 4])(kk)
        lab = str(kk) if kk < 4 else ">=4"
        add(f"cond5 k={lab}: n eventos (por rep)", (lambda s: lambda d, e, c, a, rl: float(len(s(c))))(sel))
        add(f"cond5 k={lab}: P(nova max/min do dia depois)", (lambda s: lambda d, e, c, a, rl: float(s(c).extreme_later.mean()))(sel))
        add(f"cond5 k={lab}: P(volta ao outro lado da abertura)", (lambda s: lambda d, e, c, a, rl: float(s(c).cross_back.mean()))(sel))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out = []
    with ProcessPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(run_k, k) for k in KS]
        for f in as_completed(futs):
            k, D, E, C = f.result()
            print("k", k, "dias", D[D.rep == -1].shape[0], flush=True)
            R = resumo(D, E, C)
            out.append(R)
            R.to_csv(os.path.join(HERE, f"c_resumo_k{int(k*10):02d}.csv"), index=False, sep=";", decimal=",")
    R = pd.concat(out)
    R.to_csv(os.path.join(HERE, "c_resumo_tabela.csv"), index=False, sep=";", decimal=",")
    pd.set_option("display.width", 250, "display.max_rows", 500, "display.max_colwidth", 60)
    print(R.sort_values(["k_atr"]).round(3).to_string(), flush=True)
