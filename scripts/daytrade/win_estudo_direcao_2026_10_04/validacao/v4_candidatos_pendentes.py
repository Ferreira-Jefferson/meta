"""v4 - VALIDACAO dos candidatos fracos e hipoteses nao testadas (WIN@D e WDO@D, M1, ajuste por diferenca).

CRITERIO DE "VALIDADO" (escrito ANTES de rodar; nao muda depois)
  Para cada hipotese-teste com direcao de efeito (efeito = real - nulo/base, com sinal):
    (1) WIN pooled 2021-10..2026-09: p < 0,05 CORRIGIDO por Holm sobre toda a familia de testes
        primarios WIN deste script (todos os testes de hipotese do script, ver registro);
    (2) estabilidade: mesmo sinal do efeito pooled em >= 4 dos 5 anos cheios 2022..2026
        (2021 so mostrado);
    (3) replicacao em WDO: mesmo sinal e p < 0,05 (sem correcao; WDO e' replicacao, nao busca).
  NAO VALIDADO: p_pooled WIN (sem correcao) >= 0,05  OU  mesmo sinal em <= 3 de 5 anos.
  INCONCLUSIVO: o resto (p<0,05 sem correcao mas nao passa Holm, ou WDO ambiguo/n pequeno).
  Item 3 (autocorrelacao M1/M5/M15) e' DESCRITIVO: 'fenomeno estavel' = mesmo sinal em 5/5 anos
  e nos dois instrumentos; 'aproveitavel' so se o movimento esperado condicional (pontos) > custo
  (spread mediano + 1 tick). Nao entra no veredito de edge.
  Nulos: embaralhamento de BARRAS dentro do dia (item 2) e sorteio minuto-do-dia com vol do dia de
  destino (H12), >= 20 replicas. Janela OOS 2025+ ja foi vista: nao e' validacao independente.
"""
import math, sys, io, time
import numpy as np, pandas as pd
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

OUT = Path(__file__).parent
BASE = r"C:\Users\Jeffe\Documents\study\meta\data\wdo-mt5"
PATHS = {"WIN": BASE + r"\WIN@D_M1_202110010900_202610011717.csv",
         "WDO": BASE + r"\WDO@D_M1_202109290900_202609291020.csv"}
TICK = {"WIN": 5.0, "WDO": 0.5}
YEARS = [2022, 2023, 2024, 2025, 2026]
NREP = 20


def perr(*a):
    print(*a, flush=True)


def pn(z):
    return math.erfc(abs(z) / math.sqrt(2)) if z == z else np.nan


_cache = {}


def load(inst):
    if inst in _cache: return _cache[inst]
    f = pd.read_csv(PATHS[inst], sep="\t")
    f.columns = ["d", "t", "o", "h", "l", "c", "tv", "v", "sp"]
    f["date"] = pd.to_datetime(f.d, format="%Y.%m.%d")
    f["tod"] = f.t.str[:2].astype(int) * 60 + f.t.str[3:5].astype(int)
    g = f.groupby("date")
    s = pd.DataFrame({"n": g.size(), "t0": g.tod.first(), "t1": g.tod.last()})
    ok = s[(s.n >= 300) & (s.t0 < 600) & (s.t1 >= 1070)].index
    f = f[f.date.isin(ok)].reset_index(drop=True)
    f["year"] = f.date.dt.year
    g = f.groupby("date")
    D = pd.DataFrame({"O": g.o.first(), "H": g.h.max(), "L": g.l.min(), "C": g.c.last(), "V": g.v.sum(), "n": g.size()})
    pc = D.C.shift()
    D["tr"] = np.maximum(D.H - D.L, np.maximum((D.H - pc).abs(), (D.L - pc).abs()))
    D["atr"] = D.tr.rolling(14).mean().shift(1)
    D["gap"] = D.O - pc
    D["oc"] = D.C - D.O
    D["up"] = (D.oc > 0).astype(int)
    D["year"] = D.index.year
    D["rngn"] = (D.H - D.L) / D.atr
    # eficiencia M1
    prev = f.c.shift(); first = f.date != f.date.shift()
    prev = prev.where(~first, f.o)
    f["ad"] = (f.c - prev).abs(); f["dd"] = f.c - prev
    gg = f.groupby("date")
    D["eff"] = gg.dd.sum().abs() / gg.ad.sum()
    _cache[inst] = (f, D)
    return f, D


# ---------------- registro de testes ----------------
REG = []   # dict(hyp, test, inst, effect, p, yrs_same, yrs, claim)


def add(hyp, test, inst, eff, p, peryear, primary=True, note=""):
    ys = [peryear.get(y, np.nan) for y in YEARS]
    s = np.sign(eff)
    same = int(sum(1 for v in ys if v == v and np.sign(v) == s and s != 0))
    REG.append(dict(hyp=hyp, test=test, inst=inst, efeito=eff, p=p, anos_mesmo_sinal=same,
                    por_ano=" | ".join("" if v != v else f"{v:.3f}".replace(".", ",") for v in ys),
                    primario=primary, nota=note))


def rate_test(mask, y, D, base):
    """taxa de y|mask vs base; devolve (diff, p, n, taxa, peryear dict)."""
    m = mask.fillna(False).astype(bool)
    n = int(m.sum()); k = float(y[m].sum()); r = k / n if n else np.nan
    p = pn((r - base) / math.sqrt(base * (1 - base) / n)) if n > 5 else np.nan
    py = {}
    for yr in range(2021, 2027):
        mm = m & (D.year == yr); nn = int(mm.sum())
        if nn >= 5: py[yr] = y[mm].mean() - y[D.year == yr].mean()
    return r - base, p, n, r, py


def two_prop(ma, mb, y, D):
    ma = ma.fillna(False).astype(bool); mb = mb.fillna(False).astype(bool)
    na, nb = ma.sum(), mb.sum(); pa, pb = y[ma].mean(), y[mb].mean()
    pp = (y[ma].sum() + y[mb].sum()) / (na + nb)
    p = pn((pa - pb) / math.sqrt(pp * (1 - pp) * (1 / na + 1 / nb)))
    py = {}
    for yr in range(2021, 2027):
        a = ma & (D.year == yr); b = mb & (D.year == yr)
        if a.sum() >= 5 and b.sum() >= 5: py[yr] = y[a].mean() - y[b].mean()
    return pa - pb, p, int(na), int(nb), py


def rank_resid(v, C):
    if C is None or C.shape[1] == 0: return v
    X = np.c_[np.ones(len(v)), C]
    b = np.linalg.lstsq(X, v, rcond=None)[0]
    return v - X @ b


def pspearman(x, y, ctrl=()):
    df = pd.concat([x.rename("x"), y.rename("y")] + [c.rename(f"c{i}") for i, c in enumerate(ctrl)], axis=1).dropna()
    n = len(df)
    if n < 30: return np.nan, np.nan, n
    R = df.rank()
    C = R[[c for c in R.columns if c.startswith("c")]].values if ctrl else None
    rx = rank_resid(R.x.values, C); ry = rank_resid(R.y.values, C)
    r = np.corrcoef(rx, ry)[0, 1]; k = 0 if C is None else C.shape[1]
    t = r * math.sqrt((n - 2 - k) / max(1 - r * r, 1e-12))
    return r, pn(t), n


def sp_test(x, y, D, ctrl=()):
    r, p, n = pspearman(x, y, ctrl)
    py = {}
    for yr in range(2021, 2027):
        mk = (D.year == yr)
        rr, _, nn = pspearman(x[mk], y[mk], [c[mk] for c in ctrl])
        if nn >= 30: py[yr] = rr
    return r, p, n, py


def save(df, name):
    df.to_csv(OUT / name, sep=";", decimal=",", index=False, float_format="%.4f")


def fy(py):
    return " | ".join(f"{py.get(y, np.nan):.3f}" for y in range(2021, 2027))


# =========================================================================================
# 1. SEXTA DEPOIS DE SEMANA DE BAIXA
# =========================================================================================
def t1():
    perr("== T1 dow x semana anterior")
    rows = []; cellrows = []
    for inst in ("WIN", "WDO"):
        f, D = load(inst)
        d = D.copy()
        iso = d.index.isocalendar(); d["wk"] = iso.year.astype(str) + "-" + iso.week.astype(str).str.zfill(2)
        d["dow"] = d.index.dayofweek
        W = d.groupby("wk").agg(o=("O", "first"), c=("C", "last"))
        W["wup"] = (W.c > W.o).astype(float); W["prev"] = W.wup.shift()
        d["prev"] = d.wk.map(W.prev)
        base = d.up.mean()
        combos = []
        for dow in range(5):
            for pv in (0.0, 1.0):
                m = (d.dow == dow) & (d.prev == pv)
                diff, p, n, r, py = rate_test(m, d.up, d, base)
                lab = f"{['seg','ter','qua','qui','sex'][dow]} | sem ant {'alta' if pv else 'baixa'}"
                rows.append(dict(inst=inst, combo=lab, n=n, taxa_alta=r * 100, base=base * 100, dif_pp=diff * 100, p=p))
                for yr, v in py.items():
                    cellrows.append(dict(inst=inst, combo=lab, ano=yr, dif_pp=v * 100,
                                         n=int((m & (d.year == yr)).sum()), taxa=(d.up[m & (d.year == yr)].mean()) * 100))
                add("T1", lab, inst, diff, p, py, primary=(inst == "WIN"))
                combos.append((m.values, diff, p))
        if inst == "WIN":
            rng = np.random.default_rng(11)
            up = d.up.values.astype(float)
            masks = [c[0] for c in combos]
            obs_z = np.array([(up[m].mean() - base) / math.sqrt(base * (1 - base) / m.sum()) for m in masks])
            maxabs = []; cnt05 = []
            sexdn_idx = 2 * 4 + 0  # sex, baixa
            for _ in range(5000):
                pu = rng.permutation(up)
                z = np.array([(pu[m].mean() - base) / math.sqrt(base * (1 - base) / m.sum()) for m in masks])
                maxabs.append(np.abs(z).max()); cnt05.append((np.abs(z) > 1.96).sum())
            maxabs = np.array(maxabs); cnt05 = np.array(cnt05)
            mc = dict(z_sex_baixa=obs_z[sexdn_idx], P_max_abs_z_perm_ge_obs_sexbaixa=(maxabs >= abs(obs_z[sexdn_idx])).mean(),
                      media_testes_p05_por_acaso=cnt05.mean(), P_pelo_menos_1_p05=(cnt05 >= 1).mean(),
                      obs_testes_p05=int((np.abs(obs_z) > 1.96).sum()))
            pd.DataFrame([mc]).to_csv(OUT / "v4_t1_montecarlo.csv", sep=";", decimal=",", index=False, float_format="%.4f")
            perr(mc)
    save(pd.DataFrame(rows), "v4_t1_combos.csv"); save(pd.DataFrame(cellrows), "v4_t1_por_ano.csv")
    perr(pd.DataFrame(rows).round(3).to_string())
    cr = pd.DataFrame(cellrows)
    perr(cr[cr.combo.str.startswith("sex")].round(1).to_string())


# =========================================================================================
# 2. MICRO-CORRECOES, 5 limiares, closes e H/L, nulo de embaralhamento de BARRAS
# =========================================================================================
KS = [0.05, 0.07, 0.10, 0.15, 0.20]
FIB = [0.382, 0.5, 0.618, 0.786]; HW = 0.025


def zz_hl(h, l, thr):
    n = len(h); pp = []
    hi = h[0]; lo = l[0]; d = 0; ext = 0.0
    for i in range(1, n):
        hh = h[i]; ll = l[i]
        if d == 0:
            if hh - lo >= thr: pp.append(lo); d = 1; ext = hh
            elif hi - ll >= thr: pp.append(hi); d = -1; ext = ll
            else:
                if hh > hi: hi = hh
                if ll < lo: lo = ll
        elif d == 1:
            if ext - ll >= thr: pp.append(ext); d = -1; ext = ll
            elif hh > ext: ext = hh
        else:
            if hh - ext >= thr: pp.append(ext); d = 1; ext = hh
            elif ll < ext: ext = ll
    return pp


def band_counts(pp):
    if len(pp) < 3: return None
    p = np.asarray(pp); imp = np.abs(np.diff(p))
    imp_prev = imp[:-1]
    r = imp[1:][imp_prev > 0] / imp_prev[imp_prev > 0]
    out = [len(r)]
    for fb in FIB: out.append(int(((r >= fb - HW) & (r < fb + HW)).sum()))
    return out


def day_arrays(inst):
    f, D = load(inst)
    out = []
    for dt, g in f.groupby("date"):
        a = D.atr.get(dt, np.nan)
        if a != a: continue
        out.append((dt, g.o.values.astype(float), g.h.values.astype(float), g.l.values.astype(float), g.c.values.astype(float), a))
    return out


def t2_unit(inst, rep):
    rng = np.random.default_rng(5000 + rep * 7 + (0 if inst == "WIN" else 1))
    rows = []
    for di, (dt, o, h, l, c, atr) in enumerate(day_arrays(inst)):
        if rep > 0:
            pc = np.r_[o[0], c[:-1]]
            ho, lo_, co = h - pc, l - pc, c - pc
            idx = rng.permutation(len(c))
            nc = o[0] + np.cumsum(co[idx]); npc = np.r_[o[0], nc[:-1]]
            h = npc + ho[idx]; l = npc + lo_[idx]; c = nc
        hl = h.tolist(); ll_ = l.tolist(); cl = c.tolist()
        for ki, k in enumerate(KS):
            thr = k * atr
            for mi, mode in enumerate(("close", "hl")):
                pp = zz_hl(cl, cl, thr) if mode == "close" else zz_hl(hl, ll_, thr)
                bc = band_counts(pp)
                if bc: rows.append((di, pd.Timestamp(dt).year, ki, mi, *bc))
    return inst, rep, np.array(rows)


def t2():
    perr("== T2 micro-correcoes")
    res = {"WIN": {}, "WDO": {}}
    t0 = time.time()
    with ProcessPoolExecutor(3) as ex:
        futs = [ex.submit(t2_unit, inst, rep) for inst in ("WIN", "WDO") for rep in range(NREP + 1)]
        for fu in as_completed(futs):
            inst, rep, arr = fu.result(); res[inst][rep] = arr
            perr(f"  {inst} rep {rep} ok ({time.time()-t0:.0f}s, {len(arr)} linhas)")
    rng = np.random.default_rng(3)
    rows = []; yrrows = []
    for inst in ("WIN", "WDO"):
        for ki, k in enumerate(KS):
            for mi, mode in enumerate(("close", "hl")):
                def agg(arr, yr=None):
                    a = arr[(arr[:, 2] == ki) & (arr[:, 3] == mi)]
                    if yr is not None: a = a[a[:, 1] == yr]
                    return a
                real = agg(res[inst][0])
                days = np.unique(real[:, 0])
                tot = np.zeros((len(days), 5))
                dmap = {dd: j for j, dd in enumerate(days)}
                for row in real: tot[dmap[row[0]]] += row[4:9]
                bs = rng.integers(0, len(days), (300, len(days)))
                for bi, fb in enumerate(FIB):
                    share_r = tot[:, 1 + bi].sum() / tot[:, 0].sum()
                    bsh = tot[bs, 1 + bi].sum(1) / tot[bs, 0].sum(1)
                    nl = np.array([agg(res[inst][rep])[:, 5 + bi].sum() / agg(res[inst][rep])[:, 4].sum() for rep in range(1, NREP + 1)])
                    z = (share_r - nl.mean()) / math.hypot(bsh.std(), nl.std() + 1e-12)
                    py = {}
                    for yr in range(2021, 2027):
                        ar = agg(res[inst][0], yr)
                        if len(ar) == 0: continue
                        sr = ar[:, 5 + bi].sum() / ar[:, 4].sum()
                        sn = np.mean([agg(res[inst][rep], yr)[:, 5 + bi].sum() / agg(res[inst][rep], yr)[:, 4].sum() for rep in range(1, NREP + 1)])
                        py[yr] = sr / sn - 1
                        yrrows.append(dict(inst=inst, k_atr=k, serie=mode, fib=fb, ano=yr, share_real=sr * 100, share_nulo=sn * 100, razao=sr / sn))
                    rows.append(dict(inst=inst, k_atr=k, serie=mode, fib=fb, n_correcoes=int(tot[:, 0].sum()), share_real=share_r * 100,
                                     share_nulo=nl.mean() * 100, razao=share_r / nl.mean(), z=z, p=pn(z)))
                    add("T2", f"corr. micro {fb} k={k} {mode}", inst, share_r / nl.mean() - 1, pn(z), py, primary=(fb == 0.618 and inst == "WIN"),
                        note="" if fb == 0.618 else "informativo (fib != 0,618)")
    R = pd.DataFrame(rows); save(R, "v4_t2_micro_fib.csv"); save(pd.DataFrame(yrrows), "v4_t2_por_ano.csv")
    perr(R[R.fib == 0.618].round(3).to_string())
    perr(R.round(3).to_string())


# =========================================================================================
# 3. AUTOCORRELACAO M1/M5/M15 por faixa horaria
# =========================================================================================
def t3():
    perr("== T3 autocorrelacao")
    rows = []; summ = []
    for inst in ("WIN", "WDO"):
        f, D = load(inst)
        sp = f.sp[f.sp > 0]
        perr(inst, "spread raw: mediana(>0)", sp.median(), "pct>0", (f.sp > 0).mean(), "media", f.sp.mean())
        for TF in (1, 5, 15):
            f["b"] = (f.tod - 540) // TF
            bc = f.groupby(["date", "b"]).c.last().reset_index()
            bc["ret"] = bc.groupby("date").c.diff()
            bc["year"] = bc.date.dt.year; bc["hr"] = (540 + bc.b * TF) // 60
            bc = bc.dropna(subset=["ret"]).reset_index(drop=True)
            sdv = bc.ret.std(); bc["ret"] = bc.ret.clip(-6 * sdv, 6 * sdv)
            for lag in range(1, 6):
                y = bc.ret.shift(lag)
                ok = (bc.date == bc.date.shift(lag)) & (bc.b - bc.b.shift(lag) == lag)
                t = pd.DataFrame({"x": bc.ret[ok], "y": y[ok], "year": bc.year[ok], "hr": bc.hr[ok]})
                t["xy"] = t.x * t.y; t["xx"] = t.x ** 2; t["yy"] = t.y ** 2
                for keys, lab in ((["year", "hr"], "hr"), (["year"], "todos")):
                    g = t.groupby(keys).agg(n=("x", "size"), xy=("xy", "sum"), xx=("xx", "sum"), yy=("yy", "sum"))
                    g["corr"] = g.xy / np.sqrt(g.xx * g.yy); g["sd_pts"] = np.sqrt(g.xx / g.n)
                    g = g.reset_index()
                    if lab == "todos": g["hr"] = -1
                    g["inst"] = inst; g["tf"] = TF; g["lag"] = lag
                    rows.append(g)
                n = len(t); c = t.xy.sum() / math.sqrt(t.xx.sum() * t.yy.sum()); sd = math.sqrt(t.xx.mean())
                py = {}
                for yr in range(2021, 2027):
                    s = t[t.year == yr]; py[yr] = s.xy.sum() / math.sqrt(s.xx.sum() * s.yy.sum())
                se = 1 / math.sqrt(n); p = pn(c / se)
                same = sum(1 for yr in YEARS if np.sign(py[yr]) == np.sign(c))
                summ.append(dict(inst=inst, tf=TF, lag=lag, n=n, corr=c, p=p, anos_mesmo_sinal=same,
                                 por_ano=" | ".join(f"{py[y]:.3f}".replace(".", ",") for y in range(2021, 2027)),
                                 sd_pts=sd, mov_esperado_pts_apos_1sd=abs(c) * sd, tick=TICK[inst]))
                add("T3", f"autocorr lag{lag} M{TF}", inst, c, p, py, primary=False, note="descritivo")
    A = pd.concat(rows); save(A, "v4_t3_autocorr_ano_faixa.csv")
    S = pd.DataFrame(summ); save(S, "v4_t3_autocorr_pooled.csv")
    perr(S.round(4).to_string())
    L1 = A[(A.lag == 1) & (A.hr >= 0) & (A.year.isin(YEARS))]
    st = L1.groupby(["inst", "tf", "hr"]).apply(lambda s: pd.Series(dict(anos_neg=int((s["corr"] < 0).sum()), anos=len(s), corr_med=s["corr"].median(),
                                                                          n_min=s.n.min())), include_groups=False).reset_index()
    save(st, "v4_t3_lag1_estabilidade_faixa.csv"); perr(st.round(3).to_string())


# =========================================================================================
# 4. H13, H15, H12 ; 5. Eficiencia
# =========================================================================================
def h13():
    perr("== H13")
    out = []
    for inst in ("WIN", "WDO"):
        f, D = load(inst)
        d = D.copy()
        d["body"] = ((d.C - d.O).abs() / (d.H - d.L)).replace([np.inf], np.nan)
        d["body_p"] = d.body.shift(1); d["rng_p"] = d.rngn.shift(1)
        d["vrel_p"] = (d.V / d.V.rolling(20).mean().shift(1)).shift(1)
        d["sgn_p"] = np.sign(d.oc).shift(1)
        d["cont"] = (np.sign(d.oc) == d.sgn_p).astype(float).where(d.oc != 0)
        d["gabs"] = d.gap.abs() / d.atr
        d["gcontra"] = (np.sign(d.gap) == -d.sgn_p).astype(float).where(d.gap != 0)
        d = d.dropna(subset=["atr", "body_p", "rng_p", "vrel_p"])
        d = d[d.sgn_p != 0]
        cheio = d.body_p >= 0.6; pavio = d.body_p <= 0.3
        perr(inst, "n", len(d), "cheio", int(cheio.sum()), "pavio", int(pavio.sum()), "body mediana", d.body_p.median())
        for nm, ctrl in (("bruto", ()), ("parcial(rng D-1,vol rel D-1)", (d.rng_p, d.vrel_p))):
            r, p, n, py = sp_test(d.body_p, d.rngn, d, ctrl)
            out.append(dict(inst=inst, teste="H13a corpo/range D-1 -> range D/ATR", controle=nm, n=n, efeito=r, p=p, por_ano=fy(py)))
            if ctrl: add("H13", "a) corpo D-1 -> range D (parcial)", inst, r, p, py, primary=(inst == "WIN"))
        e, p, na, nb, py = two_prop(cheio, pavio, d.cont, d)
        out.append(dict(inst=inst, teste="H13b P(D continua D-1 | corpo cheio) - P(|pavio)", controle="", n=na + nb, efeito=e, p=p, por_ano=fy(py)))
        add("H13", "b) continuacao: cheio - pavio", inst, e, p, py, primary=(inst == "WIN"))
        for nm, m in (("cheio", cheio), ("pavio", pavio)):
            diff, p, n, r, py = rate_test(m, d.up, d, d.up.mean())
            out.append(dict(inst=inst, teste=f"H13b' P(D alta | corpo {nm}) - base", controle="", n=n, efeito=diff, p=p, por_ano=fy(py)))
        for nm, ctrl in (("bruto", ()), ("parcial", (d.rng_p, d.vrel_p))):
            r, p, n, py = sp_test(d.body_p, d.gabs, d, ctrl)
            out.append(dict(inst=inst, teste="H13c corpo D-1 -> |gap|/ATR", controle=nm, n=n, efeito=r, p=p, por_ano=fy(py)))
            if ctrl: add("H13", "c) corpo D-1 -> |gap| (parcial)", inst, r, p, py, primary=(inst == "WIN"))
        e, p, na, nb, py = two_prop(cheio, pavio, d.gcontra, d)
        out.append(dict(inst=inst, teste="H13d P(gap contra D-1 | cheio) - P(|pavio)", controle="", n=na + nb, efeito=e, p=p, por_ano=fy(py)))
        add("H13", "d) gap contra D-1: cheio - pavio", inst, e, p, py, primary=(inst == "WIN"))
    save(pd.DataFrame(out), "v4_h13.csv"); perr(pd.DataFrame(out).round(3).to_string())


def h15():
    perr("== H15")
    fw, W = load("WIN"); fd, X = load("WDO")
    common = W.index.intersection(X.index)
    out = []
    for inst, A, B in (("WIN", W, X), ("WDO", X, W)):
        a = A.loc[common].copy(); b = B.loc[common]
        sa = np.sign(a.oc).shift(1); sb = np.sign(b.oc).shift(1)
        a["both_up"] = (sa > 0) & (sb > 0); a["both_dn"] = (sa < 0) & (sb < 0)
        a["div"] = a.both_up | a.both_dn
        a["sgn_p"] = sa; a["cont"] = (np.sign(a.oc) == sa).astype(float).where(a.oc != 0)
        a["sbp"] = sb
        a = a.dropna(subset=["atr"]).iloc[1:]
        a = a[(a.sgn_p != 0) & (a.sbp != 0)]
        perr(inst, "n", len(a), "frac divergencia (mesmo sinal)", a["div"].mean())
        lr = np.log(a.rngn.clip(lower=1e-3)); g1 = lr[a["div"]]; g0 = lr[~a["div"]]
        t = (g1.mean() - g0.mean()) / math.sqrt(g1.var() / len(g1) + g0.var() / len(g0))
        py = {}
        for yr in range(2021, 2027):
            q = a[a.year == yr]; l1 = lr[q.index][q["div"]]; l0 = lr[q.index][~q["div"]]
            if len(l1) >= 5 and len(l0) >= 5: py[yr] = l1.mean() - l0.mean()
        e = g1.mean() - g0.mean()
        out.append(dict(inst=inst, teste="H15a log(range D/ATR | div) - (| nao div)", n=len(a), efeito=e, p=pn(t), por_ano=fy(py)))
        add("H15", "a) divergencia D-1 -> range D", inst, e, pn(t), py, primary=(inst == "WIN"))
        base = a.up.mean()
        for nm in ("both_up", "both_dn"):
            diff, p, n, r, py = rate_test(a[nm], a.up, a, base)
            out.append(dict(inst=inst, teste=f"H15b P({inst} D alta | {nm}) - base", n=n, efeito=diff, p=p, por_ano=fy(py)))
            add("H15", f"b) dir D | {nm}", inst, diff, p, py, primary=(inst == "WIN"))
        e, p, na, nb, py = two_prop(a["div"], ~a["div"], a.cont, a)
        out.append(dict(inst=inst, teste="H15c P(continua D-1 | div) - P(| nao div)", n=na + nb, efeito=e, p=p, por_ano=fy(py)))
        add("H15", "c) continuacao | divergencia - nao", inst, e, p, py, primary=(inst == "WIN"))
    save(pd.DataFrame(out), "v4_h15.csv"); perr(pd.DataFrame(out).round(3).to_string())


def h12_matrix(inst):
    f, D = load(inst)
    days = sorted(f.date.unique()); di = {d: i for i, d in enumerate(days)}
    ND = len(days); NM = 1111 - 540
    C = np.full((ND, NM), np.nan)
    ii = f.date.map(di).values; mm = (f.tod.values - 540).clip(0, NM - 1)
    C[ii, mm] = f.c.values
    first = f.groupby("date").o.first(); O0 = np.array([first[d] for d in days])
    atr = np.array([D.atr.get(pd.Timestamp(d), np.nan) for d in days]); yr = np.array([pd.Timestamp(d).year for d in days])
    ok = ~np.isnan(atr)
    return C[ok], O0[ok], atr[ok], yr[ok]


def h12_stats(P, atr, thr_atr=0.10):
    """P: closes (NaN faltante). primeira hora = colunas 0..59."""
    fh = P[:, :60]; rest = P[:, 60:]
    mxf = np.nanmax(fh, 1); mnf = np.nanmin(fh, 1); mxr = np.nanmax(rest, 1); mnr = np.nanmin(rest, 1)
    s1h = mxf > mxr; s1l = mnf < mnr
    s2h = (mxf - mxr) >= thr_atr * atr; s2l = (mnr - mnf) >= thr_atr * atr
    return dict(S1=s1h | s1l, S2=s2h | s2l, S1h=s1h, S1l=s1l)


def h12():
    perr("== H12")
    out = []; yrs_out = []
    for inst in ("WIN", "WDO"):
        C, O0, atr, yr = h12_matrix(inst)
        ND, NM = C.shape; valid = ~np.isnan(C)
        R = np.full_like(C, np.nan)
        for i in range(ND):
            v = np.where(valid[i])[0]; cc = C[i, v]
            R[i, v] = np.diff(np.r_[O0[i], cc])
        s_m = np.nanstd(R, 0); s_m[s_m == 0] = np.nan
        Z = R / s_m
        f_d = np.sqrt(np.nanmean(Z ** 2, 1))
        real = h12_stats(C, atr)
        rng = np.random.default_rng(99 if inst == "WIN" else 77)
        vi = [np.where(~np.isnan(Z[:, m]))[0] for m in range(NM)]
        nulls = {k: [] for k in real}
        for rep in range(NREP):
            Zn = np.full((ND, NM), np.nan)
            for m in range(NM):
                if len(vi[m]) == 0: continue
                src = vi[m][rng.integers(len(vi[m]), size=ND)]
                Zn[:, m] = Z[src, m] / f_d[src] * f_d
            Rn = np.nan_to_num(Zn * np.nan_to_num(s_m))
            Pn = O0[:, None] + np.cumsum(Rn, 1)
            Pn = np.where(valid, Pn, np.nan)
            st = h12_stats(Pn, atr)
            for k in st: nulls[k].append(st[k])
        for k in real:
            sr = real[k].mean(); nl = np.array([x.mean() for x in nulls[k]])
            bs = rng.integers(0, ND, (300, ND)); bsh = real[k].astype(float)[bs].mean(1)
            z = (sr - nl.mean()) / math.hypot(bsh.std(), nl.std() + 1e-12)
            py = {}
            for y in range(2021, 2027):
                my = yr == y
                sn = np.mean([x[my].mean() for x in nulls[k]])
                py[y] = real[k][my].mean() - sn
                yrs_out.append(dict(inst=inst, stat=k, ano=y, real=real[k][my].mean() * 100, nulo=sn * 100, dif_pp=py[y] * 100, n=int(my.sum())))
            out.append(dict(inst=inst, stat=k, n=ND, real=sr * 100, nulo=nl.mean() * 100, nulo_dp=nl.std() * 100, dif_pp=(sr - nl.mean()) * 100, z=z, p=pn(z)))
            if k in ("S1", "S2"):
                add("H12", f"1a hora faz extremo do dia {'(nunca superado)' if k=='S1' else '(nunca revisitado, 0,10 ATR)'}", inst, sr - nl.mean(), pn(z), py, primary=(inst == "WIN"))
    save(pd.DataFrame(out), "v4_h12.csv"); save(pd.DataFrame(yrs_out), "v4_h12_por_ano.csv")
    perr(pd.DataFrame(out).round(3).to_string())


def t5():
    perr("== T5 eficiencia")
    out = []
    for inst in ("WIN", "WDO"):
        f, D = load(inst)
        d = D.copy(); d["eff_p"] = d.eff.shift(1)
        d = d.dropna(subset=["eff", "eff_p"])
        r, p, n, py = sp_test(d.eff_p, d.eff, d)
        out.append(dict(inst=inst, escopo="pooled", n=n, rho=r, p=p))
        for y, v in py.items(): out.append(dict(inst=inst, escopo=str(y), n=int((d.year == y).sum()), rho=v, p=np.nan))
        for nm, mk in (("IS 2021-2024", d.year <= 2024), ("OOS 2025-26", d.year >= 2025)):
            rr, pp, nn = pspearman(d.eff_p[mk], d.eff[mk]); out.append(dict(inst=inst, escopo=nm, n=nn, rho=rr, p=pp))
        add("T5", "eficiencia M1 D-1 -> D (Spearman)", inst, r, p, py, primary=(inst == "WIN"))
    save(pd.DataFrame(out), "v4_t5_eficiencia.csv"); perr(pd.DataFrame(out).round(4).to_string())


def finish(REGL):
    R = pd.DataFrame(REGL)
    prim = R[(R.inst == "WIN") & R.primario].copy()
    prim = prim.sort_values("p").reset_index(drop=True)
    m = len(prim); prim["p_holm"] = np.nan; run = 0
    for i, row in prim.iterrows():
        run = max(run, min(1, (m - i) * row.p)); prim.loc[i, "p_holm"] = run
    R = R.merge(prim[["hyp", "test", "p_holm"]], on=["hyp", "test"], how="left")
    save(R, "v4_registro_testes.csv")
    perr("familia primaria WIN:", m, " esperados por acaso p<0,05:", m * 0.05)
    perr("total de linhas de teste (pooled WIN+WDO, incl. informativos):", len(R), " esperados p<0,05:", len(R) * 0.05, " observados p<0,05:", int((R.p < 0.05).sum()))
    pd.set_option("display.width", 250)
    perr(prim.round(4).to_string())


if __name__ == "__main__":
    import pickle
    which = sys.argv[1:] or ["t1", "t2", "t3", "h13", "h15", "h12", "t5"]
    for w in which:
        globals()[w]()
        pickle.dump(REG[:], open(OUT / f"_reg_{w}.pkl", "wb")); REG.clear()
    allreg = []
    for p in sorted(OUT.glob("_reg_*.pkl")):
        allreg += pickle.load(open(p, "rb"))
    finish(allreg)
