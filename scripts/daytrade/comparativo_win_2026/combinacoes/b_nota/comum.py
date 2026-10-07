"""Nucleo da frente B: dados, features sem futuro, logistica propria (numpy), AUC, walk-forward mensal expansivo.

Convencoes
  - unidade = uma ENTRADA (eventos.parquet); y = acerto (rs > 0) da saida ORIGINAL; mes = mes da entrada (1..10).
  - "outras" = Win (Win_c1 nunca entra como feature), WinCincoMedias, WinDeslocamentoMatinal, WinRetanguloEma34, menos a propria.
    WdoRetangulo (placebo) NAO entra como feature. Para Win e Win_c1 as "outras" sao as 3 restantes (Cinco, Desloc, RetEma34).
  - Walk-forward: previsao do mes m usa modelo treinado so' em meses < m. Janeiro nao tem passado: opera sem filtro.
  - Limiar do mes m: fracao a pular f (grade) escolhida maximizando o liquido do passado, medido nas previsoes FORA DA AMOSTRA dos
    meses 2..m-1 (cada uma feita por modelo treinado so' nos meses anteriores a ela). Exige m >= MES_MIN_FILTRO; antes nao filtra.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

AQ = Path(__file__).resolve().parent
COMB = AQ.parent
BASE = COMB.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(COMB / "f0_fundacao"))

RS_PT = 0.2
CUSTO = 2.0
MES_MIN_FILTRO = 4
FRACS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
ESTR = ["Win", "Win_c1", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34", "WdoRetangulo"]
CART = [s for s in ESTR if s != "Win_c1"]
FAM_T = {"Win", "Win_c1", "WinCincoMedias", "WinDeslocamentoMatinal"}


def carrega() -> pd.DataFrame:
    e = pd.read_parquet(COMB / "f0_fundacao" / "eventos.parquet").sort_values(["entrada", "estrategia"], kind="stable").reset_index(drop=True)
    e["mes"] = e.entrada.dt.month
    e["y"] = (e.rs > 0).astype(int)
    nomes = ["Win", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34"]
    fav = np.zeros(len(e)); con = np.zeros(len(e)); nota = np.zeros(len(e))
    for nm in nomes:
        v = e[f"{nm}.voto"].to_numpy() * e.lado.to_numpy()
        f = e[f"{nm}.forca"].to_numpy()
        if nm == "Win":
            outra = ~e.estrategia.isin(["Win", "Win_c1"]).to_numpy()
        else:
            outra = (e.estrategia != nm).to_numpy()
        fav += np.where(outra & (v > 0), 1, 0); con += np.where(outra & (v < 0), 1, 0)
        nota += np.where(outra, v * f, 0.0)
    e["fav"] = fav; e["con"] = con
    e["nota"] = nota / 3.0
    e["forca_propria"] = np.select([e.estrategia == s for s in ESTR], [e[f"{s}.forca"] for s in ESTR])
    e["dist_lado"] = e.dist_abertura_atr_m5 * e.lado
    return e


def chegada(e: pd.DataFrame) -> pd.DataFrame:
    """Ideia 5 (ordem de chegada). Para cada entrada, olha as posicoes da OUTRA familia abertas nesse instante
    (entrada_o <= t < saida_o, pelos CSVs originais). MTM da outra = lado_o * (preco_entrada_deste - preco_entrada_o) (preco de agora =
    o do fill desta entrada: so' informacao ate' t). cheg: 0 = 1a (ninguem da outra familia), 1 = 2a a favor no lucro,
    2 = 2a a favor no prejuizo, 3 = contra. Se houver varias, vale a que abriu primeiro."""
    tr = e[["estrategia", "t_entrada_ms", "t_saida_ms", "lado", "preco_entrada"]]
    ret = {"WinRetanguloEma34", "WdoRetangulo"}
    cls = np.zeros(len(e), int); ant = np.full(len(e), np.nan)
    for i, r in enumerate(e.itertuples(index=False)):
        fam_t = r.estrategia in FAM_T
        outras = ret if fam_t else FAM_T
        oc = tr[tr.estrategia.isin(outras) & (tr.t_entrada_ms <= r.t_entrada_ms) & (tr.t_saida_ms > r.t_entrada_ms)]
        if len(oc):
            o = oc.sort_values("t_entrada_ms").iloc[0]
            mtm = o.lado * (r.preco_entrada - o.preco_entrada)
            ant[i] = (r.t_entrada_ms - o.t_entrada_ms) / 60000
            cls[i] = 3 if o.lado != r.lado else (1 if mtm > 0 else 2)
    e = e.copy(); e["cheg"] = cls; e["cheg_min"] = ant
    e["cheg_lucro"] = (cls == 1).astype(int); e["cheg_prej"] = (cls == 2).astype(int)
    return e


# --------------------------------------------------------------------------- modelos
def _sig(z):
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def logit_fit(X, y, lam=5.0, it=30):
    mu = X.mean(0); sd = X.std(0); sd[sd == 0] = 1
    Z = np.c_[np.ones(len(X)), (X - mu) / sd]
    w = np.zeros(Z.shape[1]); R = np.eye(Z.shape[1]) * lam; R[0, 0] = 0
    for _ in range(it):
        p = _sig(Z @ w)
        g = Z.T @ (p - y) + R @ w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + R + 1e-9 * np.eye(len(w))
        d = np.linalg.solve(H, g); w -= d
        if np.abs(d).max() < 1e-8:
            break
    return mu, sd, w


def logit_pred(m, X):
    mu, sd, w = m
    return _sig(np.c_[np.ones(len(X)), (X - mu) / sd] @ w)


def auc(y, s):
    y = np.asarray(y); s = np.asarray(s, float)
    ok = ~np.isnan(s); y = y[ok]; s = s[ok]
    n1 = y.sum(); n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return np.nan
    r = pd.Series(s).rank().to_numpy()
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def monta(e):
    """Matrizes fixas (as taxas por estrategia dependem do treino e entram em preve_mes)."""
    return dict(fav=np.minimum(e.fav.to_numpy().astype(int), 3), est=e.estrategia.to_numpy(), mes=e.mes.to_numpy(),
                A=np.c_[e.fav, e.con, e.forca_propria, e.cheg_lucro, e.cheg_prej], N=np.c_[e.nota])


def preve_mes(D, y, m, modelos=("tabela", "logit", "nota")):
    """Treina nos meses < m (rotulos y) e devolve as previsoes para as linhas do mes m."""
    mes = D["mes"]; tr = (mes < m) & (D["est"] != "Win_c1"); te = mes == m
    out = {}
    if "tabela" in modelos:
        fav = D["fav"]
        tab = {k: (y[tr & (fav == k)].sum() + 1) / ((tr & (fav == k)).sum() + 2) for k in range(0, 4)}
        out["tabela"] = np.array([tab[k] for k in fav[te]])
    if "logit" in modelos:
        est = D["est"]
        taxa = {s: (y[tr & (est == s)].mean() if (tr & (est == s)).any() else y[tr].mean()) for s in ESTR}
        tx = np.array([taxa[s] for s in est])
        X = np.c_[D["A"][:, :3], tx, D["A"][:, 3:]]
        out["logit"] = logit_pred(logit_fit(X[tr], y[tr]), X[te])
    if "nota" in modelos:
        out["nota"] = logit_pred(logit_fit(D["N"][tr], y[tr], lam=0.5), D["N"][te])
    return out


def previsoes_oos(D, y, modelos=("tabela", "logit", "nota")):
    n = len(y)
    P = {k: np.full(n, np.nan) for k in modelos}
    for m in range(2, 11):
        te = D["mes"] == m
        for k, v in preve_mes(D, y, m, modelos).items():
            P[k][te] = v
    return P


def escolhe_limiar(mes, p, m, rs_liq, grade=FRACS):
    """(f, limiar) do mes m com so' meses 2..m-1 (previsoes OOS). m < MES_MIN_FILTRO -> (0, -inf)."""
    if m < MES_MIN_FILTRO:
        return 0.0, -np.inf
    s = (mes >= 2) & (mes < m) & ~np.isnan(p)
    ps, rs = p[s], rs_liq[s]
    best = (0.0, -np.inf, rs.sum())
    for f in grade:
        thr = -np.inf if f == 0 else np.quantile(ps, f)
        v = rs[ps >= thr].sum()
        if v > best[2] + 1e-9:
            best = (f, thr, v)
    return best[0], best[1]


def mantidos(mes, p, rs_liq, grade=FRACS):
    keep = np.ones(len(mes), bool); info = []
    for m in range(1, 11):
        f, thr = escolhe_limiar(mes, p, m, rs_liq, grade)
        mm = mes == m
        if f > 0:
            keep[mm] = np.where(np.isnan(p[mm]), True, p[mm] >= thr)
        info.append((m, f, thr))
    return keep, info


def equity(rs_liq, saida, cap=1000.0):
    """Capital corrido por ordem de saida: (liquido, saldo minimo, quebrou)."""
    if len(rs_liq) == 0:
        return 0.0, cap, False
    o = np.argsort(saida, kind="stable")
    c = cap + np.cumsum(rs_liq[o])
    return float(c[-1] - cap), float(min(c.min(), cap)), bool((c <= 0).any())


def sorteio(grupos, keep, rng):
    """Controle: mantem ao acaso o MESMO numero de entradas por (mes, estrategia). grupos = lista de arrays de indices."""
    k2 = np.zeros(len(keep), bool)
    for idx in grupos:
        k2[rng.choice(idx, int(keep[idx].sum()), replace=False)] = True
    return k2
