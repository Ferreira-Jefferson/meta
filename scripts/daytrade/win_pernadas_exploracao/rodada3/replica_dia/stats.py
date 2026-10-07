"""Estatisticas por conjunto de dias (mes, jan-ago, regime US-DST) a partir das tabelas por dia."""
import numpy as np
from lib import CUTS, MESES

NAN = float("nan")
DST_INICIO = "2026-03-09"      # 1a segunda apos o inicio do horario de verao dos EUA (08/03/2026)


def conjuntos(days):
    """nome -> indices dos dias. 'JanAug' = jan-ago; 'inv'/'ver' = jan-ago antes/depois do DST dos EUA."""
    ym = np.array([d["ym"] for d in days]); dt = np.array([d["date"] for d in days])
    S = {m: np.flatnonzero(ym == m) for m in MESES}
    ja = np.flatnonzero(ym <= "2026-08")
    S["JanAug"] = ja
    S["inv"] = ja[dt[ja] < DST_INICIO]
    S["ver"] = ja[dt[ja] >= DST_INICIO]
    return S


def _kn(tab, key, idx, a=0, b=1):
    if len(idx) == 0: return 0, 0
    arr = np.array([tab[key][i] for i in idx], float)
    return arr[:, a].sum(), arr[:, b].sum()


def pct(k, n): return k / n if n > 0 else NAN


def stats_path(tab, idx):
    s = {}
    for nome, key in (("r01_on", "r01_on"), ("r01_off", "r01_off"), ("r03_tarde", "r03_tarde"),
                      ("r03_ate13", "r03_ate13"), ("r04_tarde", "r04_tarde"), ("r04_manha", "r04_manha")):
        k, n = _kn(tab, key, idx)
        s[nome + "_pct"] = pct(k, n); s[nome + "_n"] = n
    if len(idx):
        a = np.array([tab["r02"][i] for i in idx], float).sum(0)
        s["r02_cap"] = pct(a[0], a[1]); s["r02_tempo"] = pct(a[2], a[3]); s["r02_nper"] = a[1]
    else:
        s["r02_cap"] = s["r02_tempo"] = s["r02_nper"] = NAN
    if len(idx):
        a = np.array([tab["r11"][i] for i in idx], float).sum(0)
        s["r11_any"] = a[0] / len(idx); s["r11_both"] = a[1] / len(idx); s["r11_n"] = len(idx)
        t = np.array([tab["r12"][i] for i in idx], float)
        s["r12_max"] = np.median(t[:, 0]); s["r12_min"] = np.median(t[:, 1])
    else:
        s["r11_any"] = s["r11_both"] = s["r11_n"] = s["r12_max"] = s["r12_min"] = NAN
    legs = [x for i in idx for x in tab["r23"][i]]
    L = np.array(legs, float).reshape(-1, 4)
    for nome, m in (("m", L[:, 0] < 720), ("t", L[:, 0] >= 780)):
        g = L[m]
        s["r23_n_" + nome] = len(g)
        if len(g):
            s["r23_size_" + nome] = np.median(g[:, 1]); s["r23_vel_" + nome] = np.median(g[:, 1] / g[:, 2])
            s["r23_dur_" + nome] = np.median(g[:, 2])
            s["r23_corr_" + nome] = g[:, 3].mean(); s["r23_corr1000_" + nome] = g[:, 3].sum() / g[:, 1].sum() * 1000
        else:
            for k in ("size", "vel", "dur", "corr", "corr1000"): s["r23_%s_%s" % (k, nome)] = NAN
    s["r23_vel_razao"] = s["r23_vel_m"] / s["r23_vel_t"] if s["r23_vel_t"] == s["r23_vel_t"] and s["r23_vel_t"] > 0 else NAN
    s["r23_corr_razao"] = s["r23_corr_t"] / s["r23_corr_m"] if s["r23_corr_m"] and s["r23_corr_m"] > 0 else NAN
    s["r23_corr1000_razao"] = s["r23_corr1000_t"] / s["r23_corr1000_m"] if s["r23_corr1000_m"] and s["r23_corr1000_m"] > 0 else NAN
    s["r23_size_razao"] = s["r23_size_t"] / s["r23_size_m"] if s["r23_size_m"] and s["r23_size_m"] > 0 else NAN
    return s


def corr_adj(L, demean_dia=False):
    Z = L - np.nanmean(L, axis=0)
    if demean_dia: Z = Z - np.nanmean(Z, axis=1, keepdims=True)
    x, y = Z[:, :-1].ravel(), Z[:, 1:].ravel()
    m = np.isfinite(x) & np.isfinite(y)
    return np.corrcoef(x[m], y[m])[0, 1] if m.sum() > 5 else NAN


def vr5(parc):
    """parc: (nd,4) = S5, n5, S1, n1"""
    a = parc.sum(0)
    return (a[0] / a[1]) / (5 * a[2] / a[3]) if a[1] > 0 and a[2] > 0 else NAN


def sufic_vr(r, ok, inn):
    cs = np.r_[0, np.cumsum(r)]
    k = np.flatnonzero(ok)
    s5 = ((cs[k + 5] - cs[k]) ** 2).sum()
    return [s5, len(k), (r[inn] ** 2).sum(), inn.sum()]


def stats_out(tab, idx):
    """Estatisticas das regras que nao precisam de nulo embaralhado (R05-R10, R20-R22, R24)."""
    s = {}
    if len(idx) == 0: return s
    a = np.array([tab["r05"][i][:2] for i in idx], float).sum(0)
    s["r05_k"], s["r05_n"], s["r05_pct"] = a[0], a[1], pct(a[0], a[1])
    v = np.array([tab["r05"][i][2] for i in idx], float); v = v[np.isfinite(v)]
    s["r05_med_pts"] = np.median(v) if len(v) else NAN
    a = np.array([tab["r05_dir"][i] for i in idx], float).sum(0)
    s["r05dir_pct"] = pct(a[0], a[1]); s["r05dir_n"] = a[1]
    for nm, rid in (("dp", "r06"), ("do", "r07"), ("dv", "r08")):
        G = np.array([tab["grade"][i][nm] for i in idx], float).sum(0)
        s[rid + "_in_pct"] = pct(G[2], G[3]); s[rid + "_in_n"] = G[3]
        s[rid + "_out_pct"] = pct(G[0] + G[4], G[1] + G[5]); s[rid + "_out_n"] = G[1] + G[5]
        s[rid + "_early_pct"] = pct(G[0], G[1]); s[rid + "_late_pct"] = pct(G[4], G[5])
    a = np.array([tab["r09"][i] for i in idx], float).sum(0)
    s["r09_pct"] = pct(a[0], a[2]); s["r09_mirror"] = pct(a[1], a[2]); s["gap_n"] = a[2]
    a = np.array([tab["r10"][i] for i in idx], float).sum(0)
    s["r10_pct"] = pct(a[0], a[2]); s["r10_alt_pct"] = pct(a[1], a[2])
    L = np.array([tab["r20"][i] for i in idx])
    s["r20_corr"] = corr_adj(L); s["r20_corr_semdia"] = corr_adj(L, True)
    ym = np.array([tab["ym"][i] for i in idx]); Lm = L.copy()
    for m in np.unique(ym): Lm[ym == m] = L[ym == m] - np.nanmean(L[ym == m], axis=0)
    x, y = Lm[:, :-1].ravel(), Lm[:, 1:].ravel(); mk = np.isfinite(x) & np.isfinite(y)
    s["r20_corr_mes"] = np.corrcoef(x[mk], y[mk])[0, 1]
    s["amp_dia"] = float(np.mean([tab["amp"][i] for i in idx]))
    R = np.concatenate([tab["r21"][i] for i in idx])
    s["r21_m00"] = np.nanmean(R[:, 0]); s["r21_m30"] = np.nanmean(R[:, 30])
    s["r21_outros"] = np.nanmean(np.delete(R, [0, 1, 2, 3, 15, 30], axis=1))
    P = np.array([tab["r22_par"][i] for i in idx], float)
    s["r22_vr5"] = vr5(P)
    A = np.array([tab["r24"][i] for i in idx])          # (nd,2,67)
    med = np.nanmedian(A, axis=0)                        # (2,67)
    ic = {"amp": 0, "vol": 1}
    for nm, j in ic.items():
        s["r24_%s_1030" % nm] = med[j, 0]; s["r24_%s_1130" % nm] = med[j, 12]
        ctrl = np.delete(med[j], 0)
        s["r24_%s_ctrl_med" % nm] = np.median(ctrl)
        s["r24_%s_ctrl_p5" % nm] = np.percentile(ctrl, 5); s["r24_%s_ctrl_p95" % nm] = np.percentile(ctrl, 95)
        s["r24_%s_rank1030" % nm] = int((med[j] > med[j, 0]).sum()) + 1      # 1 = maior de todos os cortes
        s["r24_%s_rank1130" % nm] = int((med[j] > med[j, 12]).sum()) + 1
    return s


def nulo_r20(tab, idx, rng, nsim=300):
    L = np.array([tab["r20"][i] for i in idx])
    Z = L - np.nanmean(L, axis=0)
    out = []
    for _ in range(nsim):
        W = Z.copy()
        for k in range(W.shape[1]):
            W[:, k] = W[rng.permutation(W.shape[0]), k]
        x, y = W[:, :-1].ravel(), W[:, 1:].ravel(); m = np.isfinite(x) & np.isfinite(y)
        out.append(np.corrcoef(x[m], y[m])[0, 1])
    return np.array(out)


def nulo_r21(tab, idx, rng, nsim=200):
    R = np.concatenate([tab["r21"][i] for i in idx])
    o0, o30 = [], []
    for _ in range(nsim):
        W = np.take_along_axis(R, np.argsort(rng.random(R.shape), axis=1), axis=1)
        o0.append(np.nanmean(W[:, 0])); o30.append(np.nanmean(W[:, 30]))
    return np.array(o0), np.array(o30)


def nulo_r22(days, tab, rng, nsim=100):
    """permuta os retornos dentro de cada dia; retorna (nsim, nd, 4) de sufic."""
    out = np.zeros((nsim, len(days), 4))
    for s in range(nsim):
        for i in range(len(days)):
            r = rng.permutation(tab["r22_r"][i])
            out[s, i] = sufic_vr(r, tab["r22_ok"][i], tab["r22_in"][i])
    return out
