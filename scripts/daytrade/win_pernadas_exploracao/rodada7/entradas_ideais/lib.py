"""lib.py -- matriz de features assinadas, familias, AUC, logistica L2, utilitarios."""
from __future__ import annotations
import pickle
import numpy as np, pandas as pd
from base import PASTA, NS, PISOS, KS, MS, SS, REF

GRUPOS = {}      # coluna -> grupo (ablacao)
FAMILIAS = {}    # familia -> [colunas variantes]


def _fam(fam, grupo, cols):
    FAMILIAS[fam] = list(cols)
    for c in cols:
        GRUPOS[c] = grupo


def carregar():
    with open(PASTA + "universo.pkl", "rb") as fh:
        u = pickle.load(fh)
    return u["C"], u["Y"], u["PN"], u["EX"]


def construir_X(C: pd.DataFrame, seed=7) -> pd.DataFrame:
    s = C["edir"].values.astype(float)
    X = pd.DataFrame(index=C.index)
    FAMILIAS.clear(); GRUPOS.clear()
    atr = C["atr14_M5"].values
    # relogio
    for c in ("hora_aj", "manha", "tarde", "m0030"):
        X[c] = C[c].values
    _fam("relogio_hora", "relogio", ["hora_aj"]); _fam("relogio_manha", "relogio", ["manha"])
    _fam("relogio_tarde", "relogio", ["tarde"]); _fam("relogio_m0030", "relogio", ["m0030"])
    # volatilidade
    X["rh_M5"], X["rh_M15"], X["vol30_300"] = C["rh_M5"].values, C["rh_M15"].values, C["vol30_300"].values
    _fam("vol_rh", "volatilidade", ["rh_M5", "rh_M15"]); _fam("vol_30_300", "volatilidade", ["vol30_300"])
    cols = []
    for w in (5, 10, 15, 30, 60):
        X[f"onda_{w}"] = np.log(C[f"onda_{w}"].clip(lower=0.05)).values; cols.append(f"onda_{w}")
    _fam("vol_onda", "volatilidade", cols)
    cols = []
    for w in (5, 10, 20, 30):
        X[f"vela_{w}"] = np.log(C[f"vela_{w}"].clip(lower=0.05)).values; cols.append(f"vela_{w}")
    _fam("vol_vela", "volatilidade", cols)
    cols = []
    for w in (10, 20, 30, 60):
        X[f"caixa_{w}"] = np.log1p(C[f"caixa_{w}"].values); cols.append(f"caixa_{w}")
    _fam("vol_caixa", "volatilidade", cols)
    # estrutura
    X["recuo"] = np.log(C["recuo"].values); X["leg"] = np.log1p(C["leg"].values)
    X["leg_age"] = np.log1p(C["leg_age"].values); X["E_age"] = np.log1p(C["E_age"].values)
    depth = C["recuo"].values / np.maximum(C["leg"].values, 1)
    X["depth"] = np.clip(depth, 0, 3)
    X["ordem"] = np.clip(C["ordem"].values, 0, 5); X["fundo_dif"] = C["fundo_dif"].values / atr
    X["n_piv"] = np.clip(C["n_piv"].values, 0, 6)
    for c in ("recuo", "leg", "leg_age", "E_age", "ordem", "fundo_dif", "n_piv"):
        _fam("est_" + c, "estrutura", [c])
    _fam("est_depth", "estrutura", ["depth"])
    cols = []
    for nm, (a, b) in {"a": (.20, .35), "b": (.23, .38), "c": (.25, .40), "d": (.30, .50)}.items():
        X[f"raso_{nm}"] = ((depth >= a) & (depth <= b)).astype(float); cols.append(f"raso_{nm}")
    _fam("est_raso", "estrutura", cols)
    # esticamento
    X["dvwap"] = s * C["dvwap"].values
    _fam("est_dvwap", "esticamento", ["dvwap"])
    cols = []
    for w in (15, 30, 60):
        X[f"sub_{w}"] = s * C[f"sub_{w}"].values / atr; cols.append(f"sub_{w}")
    _fam("est_sub", "esticamento", cols)
    dext = np.where(s > 0, C["hi_dia"].values - C["close"].values, C["close"].values - C["lo_dia"].values)
    X["dext"] = np.log1p(np.maximum(dext, 0))
    pos = np.where(s > 0, C["pos_dia"].values, 1 - C["pos_dia"].values)
    X["pos_dia"] = pos
    _fam("est_dext", "esticamento", ["dext"]); _fam("est_pos", "esticamento", ["pos_dia"])
    cols = []
    sub30 = s * C["sub_30"].values
    for thr in (1.0, 1.5, 2.0):
        for rise in (200, 300, 400):
            X[f"estic_{thr}_{rise}"] = ((s * C["dvwap"].values > thr) & (sub30 >= rise) & (dext <= 500)).astype(float)
            cols.append(f"estic_{thr}_{rise}")
    _fam("est_esticado", "esticamento", cols)
    # micro / fluxo
    cols = []
    for w in (5, 10, 15, 20):
        X[f"saldo_{w}"] = s * C[f"saldo_{w}"].values; cols.append(f"saldo_{w}")
    _fam("micro_saldo", "micro", cols)
    cols = []
    for w in (5, 10, 30):
        X[f"dcorpo_{w}"] = s * C[f"dcorpo_{w}"].values; cols.append(f"dcorpo_{w}")
    _fam("fluxo_dcorpo", "fluxo", cols)
    cols = []
    for w in (5, 10, 30):
        X[f"tvr_{w}"] = np.log(C[f"tvr_{w}"].clip(lower=0.05)).values; cols.append(f"tvr_{w}")
    _fam("fluxo_tvr", "fluxo", cols)
    # medias
    for tf in ("M5", "M15", "H1"):
        for kind, nm in (("emaal", "al"), ("emadi", "di")):
            cols = []
            for st in ("s1", "s2", "s3", "s4"):
                X[f"{kind}_{tf}_{st}"] = s * C[f"{kind}_{tf}_{st}"].values; cols.append(f"{kind}_{tf}_{st}")
            _fam(f"med_{nm}_{tf}", "medias", cols)
    # dia
    X["gap_atr"] = s * C["gap_atr"].values; X["gap_abs"] = np.abs(C["gap_atr"].values)
    X["rdia"] = C["rdia"].values
    X["seg"] = (C["dow"].values == 0).astype(float); X["sex"] = (C["dow"].values == 4).astype(float)
    _fam("dia_gap", "dia", ["gap_atr"]); _fam("dia_gapabs", "dia", ["gap_abs"]); _fam("dia_rdia", "dia", ["rdia"])
    _fam("dia_seg", "dia", ["seg"]); _fam("dia_sex", "dia", ["sex"])
    # controles negativos
    rng = np.random.default_rng(seed)
    X["ctrl_ruido1"], X["ctrl_ruido2"] = rng.standard_normal(len(X)), rng.standard_normal(len(X))
    _fam("ctrl_ruido1", "controle", ["ctrl_ruido1"]); _fam("ctrl_ruido2", "controle", ["ctrl_ruido2"])
    X = X.replace([np.inf, -np.inf], np.nan)
    return X


# ----------------------------------------------------------------- estatistica
def auc(y, score):
    y = np.asarray(y); sc = np.asarray(score, float)
    ok = ~np.isnan(sc) & ~np.isnan(y)
    y, sc = y[ok], sc[ok]
    n1 = int((y == 1).sum()); n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return np.nan
    r = pd.Series(sc).rank().values
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


class Padroniza:
    def fit(self, X):
        X = np.asarray(X, float)
        self.med = np.nanmedian(X, 0)
        self.lo, self.hi = np.nanpercentile(X, 1, 0), np.nanpercentile(X, 99, 0)
        Xc = self._clip(X)
        self.mu, self.sd = Xc.mean(0), Xc.std(0)
        self.sd[self.sd < 1e-9] = 1.0
        return self

    def _clip(self, X):
        X = np.where(np.isnan(X), self.med, X)
        return np.clip(X, self.lo, self.hi)

    def transform(self, X):
        return (self._clip(np.asarray(X, float)) - self.mu) / self.sd


def logit_fit(Z, y, lam=10.0, it=12):
    n, p = Z.shape
    A = np.c_[np.ones(n), Z]
    w = np.zeros(p + 1)
    pen = np.r_[0, np.full(p, lam)]
    for _ in range(it):
        pr = sigmoid(A @ w)
        W = pr * (1 - pr) + 1e-6
        g = A.T @ (pr - y) + pen * w
        H = (A * W[:, None]).T @ A + np.diag(pen + 1e-6)
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-6:
            break
    return w


def logit_pred(w, Z):
    return sigmoid(np.c_[np.ones(len(Z)), Z] @ w)


def mask_geom(C, m, S):
    return (C["recuo"].values >= m) & (C["mi"].values % S == 0)


def boot_dias(vals, dias, B=1000, seed=0, fn=np.mean):
    """IC 95% por bootstrap de DIAS: vals (n,), dias (n,) -> (lo, hi)."""
    rng = np.random.default_rng(seed)
    ud, inv = np.unique(dias, return_inverse=True)
    sums = np.bincount(inv, weights=vals, minlength=len(ud)); cnt = np.bincount(inv, minlength=len(ud)).astype(float)
    out = []
    for _ in range(B):
        k = rng.integers(0, len(ud), len(ud))
        out.append(sums[k].sum() / max(cnt[k].sum(), 1))
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def breakeven_emp(pnl, y):
    pnl = np.asarray(pnl); y = np.asarray(y)
    g = pnl[y == 1]; l = -pnl[y == 0]
    if len(g) == 0 or len(l) == 0:
        return np.nan
    return l.mean() / (g.mean() + l.mean())
