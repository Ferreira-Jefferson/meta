"""pipe.py -- selecao de variantes, CV por mes, varredura de geometria. Tudo SO jan-jun ate o congelamento."""
from __future__ import annotations
import numpy as np, pandas as pd
from lib import *

LAM_PADRAO = 30.0
TOPQ = 0.20
MESES_TR = (1, 2, 3, 4, 5, 6)


def score_variantes(Xdf, y, mes, linhas):
    """Por variante: AUC mensal medio (orientado) e dispersao, nas linhas dadas. y NaN = fora."""
    res = {}
    for col in Xdf.columns:
        v = Xdf[col].values
        a = []
        for m in MESES_TR:
            k = linhas & (mes == m) & ~np.isnan(y)
            if k.sum() < 30 or len(np.unique(y[k])) < 2:
                continue
            a.append(auc(y[k], v[k]))
        a = np.array(a, float)
        if len(a) < 3 or np.isnan(a).all():
            res[col] = (np.nan, np.nan, 0.0)
            continue
        mu = np.nanmean(a)
        res[col] = (mu, np.nanstd(a), np.sign(mu - 0.5))
    return res


def selecionar_variantes(Xdf, y, mes, linhas):
    """Uma variante por familia: maximiza o score suavizado (platô) = orientado(AUC-0,5) - 0,25*desvio mensal."""
    sc = score_variantes(Xdf, y, mes, linhas)
    escolhidas = {}
    for fam, cols in FAMILIAS.items():
        s = []
        for c in cols:
            mu, sd, sg = sc[c]
            s.append(-9.0 if np.isnan(mu) else sg * (mu - 0.5) - 0.25 * sd)
        s = np.array(s)
        sm = np.array([s[max(0, i - 1):i + 2].mean() for i in range(len(s))])
        escolhidas[fam] = cols[int(np.argmax(sm))]
    return escolhidas, sc


def ajusta(Xtr, ytr, lam):
    P = Padroniza().fit(Xtr)
    w = logit_fit(P.transform(Xtr), ytr, lam)
    return P, w


def preve(P, w, X):
    return logit_pred(w, P.transform(X))


def oof_lomo(Xm, y, mes, lam):
    """Predicao fora da amostra deixando um mes de fora (meses 1-6). Retorna vetor com NaN onde nao ha fold."""
    out = np.full(len(y), np.nan)
    for m in MESES_TR:
        te = mes == m
        trn = (mes != m) & (mes <= 6)
        if te.sum() == 0 or trn.sum() < 100 or len(np.unique(y[trn])) < 2:
            continue
        P, w = ajusta(Xm[trn], y[trn], lam)
        out[te] = preve(P, w, Xm[te])
    return out


def resumo_oof(oof, y, pnl, mes, dias=None):
    ok = ~np.isnan(oof)
    if ok.sum() < 50:
        return None
    o, yy, pp = oof[ok], y[ok], pnl[ok]
    th = np.quantile(o, 1 - TOPQ)
    top = o >= th
    a_m = []
    mm = mes[ok]
    for m in MESES_TR:
        k = mm == m
        if k.sum() > 30 and len(np.unique(yy[k])) > 1:
            a_m.append(auc(yy[k], o[k]))
    return dict(n=int(ok.sum()), base=float(yy.mean()), be=float(breakeven_emp(pp, yy)), auc=auc(yy, o),
                auc_mes=float(np.mean(a_m)) if a_m else np.nan, n_top=int(top.sum()), acerto_top=float(yy[top].mean()),
                be_top=float(breakeven_emp(pp[top], yy[top])) if top.sum() > 10 else np.nan,
                esp_top=float(pp[top].mean()), esp_all=float(pp.mean()))


def varrer_geometrias(Xm, Y, PN, mes, mi, recuo, ms, ss, lam=LAM_PADRAO, d=0):
    """Para cada (m,S,N,piso,K): CV por mes. Linhas jan-jun preenchidas (a favor, d=0)."""
    rows = []
    for m in ms:
        for S in ss:
            g = (recuo >= m) & (mi % S == 0) & (mes <= 6)
            for a, N in enumerate(NS):
                for b, piso in enumerate(PISOS):
                    for k, Kx in enumerate(KS):
                        y0 = Y[:, a, b, k, d]
                        sel = g & (y0 >= 0)
                        idx = np.where(sel)[0]
                        r = resumo_oof(oof_lomo(Xm[idx], y0[idx].astype(float), mes[idx], lam), y0[idx].astype(float),
                                       PN[idx, a, b, k, d], mes[idx])
                        if r is None:
                            continue
                        r.update(m=m, S=S, N=N, piso=piso, K=Kx)
                        rows.append(r)
    return rows


def suavizar_criterio(df, col="esp_top"):
    """Media sobre vizinhos (N, piso, K +-1) no mesmo (m,S)."""
    out = np.full(len(df), np.nan)
    key = {(r.m, r.S, r.N, r.piso, r.K): i for i, r in enumerate(df.itertuples())}
    val = df[col].values
    for i, r in enumerate(df.itertuples()):
        a, b, k = NS.index(r.N), PISOS.index(r.piso), KS.index(r.K)
        vs = []
        for da in (-1, 0, 1):
            for db in (-1, 0, 1):
                for dk in (-1, 0, 1):
                    aa, bb, kk = a + da, b + db, k + dk
                    if 0 <= aa < len(NS) and 0 <= bb < len(PISOS) and 0 <= kk < len(KS):
                        j = key.get((r.m, r.S, NS[aa], PISOS[bb], KS[kk]))
                        if j is not None:
                            vs.append(val[j])
        out[i] = np.mean(vs) if vs else np.nan
    return out
