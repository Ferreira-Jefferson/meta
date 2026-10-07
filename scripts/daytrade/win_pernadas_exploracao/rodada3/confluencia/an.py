import pickle, numpy as np, lib
M = lib.METRICS
def rates(S):  # S (NB,9) -> n, rates
    n = S[:, 0]; return n, S[:, 1:]
def reweighted(null_list, nobs):
    """null_list: lista de S(NB,9) por rep; retorna vetor (reps, 8) da taxa reponderada ao mix obs."""
    out = []
    for S in null_list:
        n = S[:, 0]; ok = (n >= 3) & (nobs > 0)
        if not ok.any(): out.append(np.full(8, np.nan)); continue
        r = S[ok, 1:] / n[ok, None]
        w = nobs[ok] / nobs[ok].sum()
        out.append((r * w[:, None]).sum(0))
    return np.array(out)
def summarize(obs, shift, shuf, periods=(0, 1)):
    rows = []
    for key, S in obs.items():
        So = S.sum(0); nobs = So[:, 0]; n = nobs.sum()
        if n < 1: continue
        ro = So[:, 1:].sum(0) / n
        sh = reweighted([x[key].sum(0) for x in shift], nobs)
        su = reweighted([x[key].sum(0) for x in shuf], nobs) if shuf else None
        mu, sd = np.nanmean(sh, 0), np.nanstd(sh, 0)
        bin_sd = np.sqrt(np.maximum(mu * (1 - mu), 1e-9) / n)
        z = (ro - mu) / np.maximum(sd, bin_sd)
        zs = None
        if su is not None:
            ms, ss = np.nanmean(su, 0), np.nanstd(su, 0)
            zs = (ro - ms) / np.maximum(ss, bin_sd)
        # metades
        halves = []
        for p in (0, 1):
            Sp = S[p]; npp = Sp[:, 0]
            if npp.sum() < 5: halves.append(np.nan); continue
            rp = Sp[:, 1:].sum(0) / npp.sum()
            mp = reweighted([x[key].sum(0) for x in shift], npp)
            halves.append(rp[1] - np.nanmean(mp, 0)[1])
        rows.append(dict(key=key, n=int(n), ro=ro, mu=mu, z=z, zs=zs, mus=(np.nanmean(su, 0) if su is not None else None), halves=halves))
    return rows
