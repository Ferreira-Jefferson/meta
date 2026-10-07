"""Nulo: mesmo pipeline (selecao de variantes por plato + varredura de geometria + CV por mes) com rotulos embaralhados
dentro de blocos de 10 pregoes (jan-jun). Subgrade de geometria: m in {150,250}, S in {15,30} (300 variantes) por repeticao."""
import json, sys, time
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
from lib import *
from pipe import *

G = {}
NREP = int(sys.argv[1]) if len(sys.argv) > 1 else 12
MS_N, SS_N = (150, 250), (15, 30)


def _init():
    C, Y, PN, EX = carregar()
    X = construir_X(C)
    G.update(X=X, Y=Y, PN=PN, mes=C.mes.values, mi=C["mi"].values, recuo=C["recuo"].values, dia=C.dia.values)


def perm_blocos(rng, dias, mes, bloco=10):
    idx = np.arange(len(dias))
    out = idx.copy()
    tr = np.where(mes <= 6)[0]
    ud = np.unique(dias[tr])
    for b in range(0, len(ud), bloco):
        ds = ud[b:b + bloco]
        rows = tr[np.isin(dias[tr], ds)]
        out[rows] = rng.permutation(rows)
    return out


def rep(seed):
    t = time.time()
    rng = np.random.default_rng(seed)
    p = perm_blocos(rng, G["dia"], G["mes"])
    Y, PN = G["Y"][p], G["PN"][p]
    mes = G["mes"]
    iN, iP, iK = NS.index(REF["N"]), PISOS.index(REF["piso"]), KS.index(REF["K"])
    g = (mes <= 6) & mask_geom_arr(G, REF["m"], REF["S"])
    yw = np.where(Y[:, iN, iP, iK, 0] >= 0, Y[:, iN, iP, iK, 0], np.nan).astype(float)
    esc, _ = selecionar_variantes(G["X"], yw, mes, g & ~np.isnan(yw))
    cols = [c for f, c in esc.items() if not f.startswith("ctrl_")]
    Xm = G["X"][cols].values
    rows = varrer_geometrias(Xm, Y, PN, mes, G["mi"], G["recuo"], MS_N, SS_N)
    df = pd.DataFrame(rows)
    df["esp_top_suav"] = suavizar_criterio(df, "esp_top")
    df["auc_suav"] = suavizar_criterio(df, "auc")
    ok = df.n >= 250
    best = df[ok].sort_values("esp_top_suav", ascending=False).iloc[0]
    return dict(seed=seed, auc_medio=df.auc.mean(), auc_max=df.auc.max(), auc_suav_max=df[ok].auc_suav.max(),
                esp_top_max=df[ok].esp_top.max(), esp_top_suav_max=best.esp_top_suav, acerto_top_sel=best.acerto_top,
                be_top_sel=best.be_top, auc_sel=best.auc, esp_top_medio=df.esp_top.mean(), s=time.time() - t)


def mask_geom_arr(G, m, S):
    return (G["recuo"] >= m) & (G["mi"] % S == 0)


if __name__ == "__main__":
    out = []
    with ProcessPoolExecutor(3, initializer=_init) as ex:
        futs = [ex.submit(rep, s) for s in range(NREP)]
        for f in as_completed(futs):
            r = f.result(); out.append(r)
            print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}, flush=True)
    pd.DataFrame(out).to_csv(PASTA + "nulo_pipeline.csv", index=False)
