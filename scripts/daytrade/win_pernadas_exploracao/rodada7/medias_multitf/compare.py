"""compare: encaixado x rompimento sem TF maior x TF maior rompendo x aleatorio x contra (mesma geometria)."""
import numpy as np, pandas as pd
import core, grid

BIG = core.BIG


def pud(D, cfg, idx, t, up_k, dn_k):
    """P(subir up_k*ATR antes de cair dn_k*ATR) em orientacao t. up/dn em multiplos do ATR do TF maior."""
    H = D.tf(cfg["htf"])
    a = H.acc(D, cfg["var"], idx, cfg["P"], t)
    LO, HI, CL = D.SG[t]
    res = []; nul = []
    for n, i in enumerate(idx):
        i = int(i); dend = int(D.dend[i])
        at = a["atr"][n]
        if not np.isfinite(at):
            continue
        up = max(50.0, round(up_k * at / 5) * 5); dn = max(50.0, round(dn_k * at / 5) * 5)
        c = CL[i]
        hi = np.flatnonzero(HI[i + 1:dend] >= c + up); lo = np.flatnonzero(LO[i + 1:dend] <= c - dn)
        h0 = hi[0] if len(hi) else BIG; l0 = lo[0] if len(lo) else BIG
        res.append(1 if h0 < l0 else (-1 if l0 < BIG else 0))
        nul.append(dn / (up + dn))
    res = np.array(res)
    return res, np.array(nul)


def rand_idx(D, ev_idx, win, rng):
    out = []
    pool = np.flatnonzero((D.win == win) & (D.m >= 570) & (D.m <= 1020) & (D.dend - np.arange(D.N) > 30))
    pm = D.m[pool]
    order = np.argsort(pm); pool = pool[order]; pm = pm[order]
    for i in ev_idx:
        m0 = D.m[i]
        lo = np.searchsorted(pm, m0 - 15); hi = np.searchsorted(pm, m0 + 15, side="right")
        out.append(pool[rng.integers(lo, hi)])
    return np.sort(np.array(out, int))


def group_stats(rr, nd, label):
    st = core.stats_from(rr)
    ci = core.boot_days(rr, 1000) if len(rr) > 5 else (np.nan, np.nan)
    d = dict(grupo=label, n=st["n"], por_dia=st["n"] / nd, acerto=st["win"], be_emp=st["be"], esp=st["mean"],
             ic_lo=ci[0], ic_hi=ci[1], payoff=st["payoff"], seq_perdas=st["maxloss"])
    if len(rr) and rr.shape[1] >= 11:
        d.update(mfe30=rr[:, 6].mean(), mae30=rr[:, 7].mean(), mfe60=rr[:, 8].mean(), mae60=rr[:, 9].mean())
    return d


def compare(D, cfg, geom, win, nrand=20, seed=7):
    nd = len(np.unique(D.day[D.win == win]))
    evs = grid.events_for(D, cfg)
    rows = []
    # padronizacao do evento (mediana em multiplos de ATR no ENC)
    ups = []; dns = []
    for s in (1, -1):
        idx = evs[s]["ENC"]; idx = idx[D.win[idx] == win]
        if len(idx):
            a = D.tf(cfg["htf"]).acc(D, cfg["var"], idx, cfg["P"], s)
            ups.append((a["hhi"] - a["px"]) / a["atr"]); dns.append((a["px"] - a["es"]) / a["atr"])
    ups = np.concatenate(ups); dns = np.concatenate(dns)
    up_k = float(np.nanmedian(ups)); dn_k = float(np.nanmedian(dns))
    pu_rows = []

    def add_pud(label, idxs_by_t):
        r = []; nu = []
        for t, idx in idxs_by_t:
            if len(idx):
                a, b = pud(D, cfg, idx, t, up_k, dn_k); r.append(a); nu.append(b)
        if not r: return
        r = np.concatenate(r); nu = np.concatenate(nu)
        pu = (r == 1).mean(); pdn = (r == -1).mean()
        pu_rows.append(dict(grupo=label, n=len(r), P_sobe=pu, P_cai=pdn, P_nenhum=(r == 0).mean(),
                            ruina=nu.mean(), excesso=pu / (pu + pdn) - nu.mean() if (pu + pdn) > 0 else np.nan))

    def wsel(idx):
        return idx[D.win[idx] == win]

    for which, tag in (("ENC", "ENCAIXADO (a favor)"), ("A1", "rompe, TF maior neutro"),
                       ("A2", "rompe, TF maior alinhado oposto"), ("B", "TF maior tambem rompendo")):
        if which == "ENC":
            sides = [("same", "a favor"), ("contra", "contra")]
        else:
            sides = [("same", "reversao"), ("contra", "continuacao")]
        for ts, nm in sides:
            rr, nsig, nfill, ninv = grid.run_trades(D, cfg, geom, which, win, ts, collect=True)
            rows.append(group_stats(rr, nd, f"{tag} -> {nm}"))
            add_pud(f"{tag} -> {nm}", [((s if ts == "same" else -s), wsel(evs[s][which])) for s in (1, -1)])
    # aleatorio
    rng = np.random.default_rng(seed)
    reps = []; allrr = []
    rand0 = []
    for r_ in range(nrand):
        rr_all = []
        for s in (1, -1):
            ei = wsel(evs[s]["ENC"])
            if len(ei) == 0: continue
            ri = rand_idx(D, ei, win, rng)
            a, a15 = grid.feats(D, cfg, ri, s)
            r = core.sim_events(D, ri, s, a, a15, geom, collect_exc=True)
            rr_all.append(np.hstack([r["rows"], np.full((len(r["rows"]), 1), float(s))]))
            if r_ == 0: rand0.append((s, ri))
        rr = np.vstack(rr_all) if rr_all else np.zeros((0, 11))
        reps.append(rr)
    add_pud("ALEATORIO (mesmo horario, mesmo lado)", rand0)
    m = [core.stats_from(x)["mean"] for x in reps]
    g = group_stats(np.vstack(reps), nd * nrand, "ALEATORIO (mesmo horario, mesmo lado)")
    g["n"] = int(np.mean([len(x) for x in reps])); g["por_dia"] = g["n"] / nd
    g["esp"] = float(np.mean(m)); g["ic_lo"] = float(np.percentile(m, 2.5)); g["ic_hi"] = float(np.percentile(m, 97.5))
    rows.append(g)
    return pd.DataFrame(rows), pd.DataFrame(pu_rows), (up_k, dn_k)
