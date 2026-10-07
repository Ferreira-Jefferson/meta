"""Varredura de geometria (900 variantes) com CV por mes em jan-jun. 4 workers, uma unidade = (m,S)."""
import json, sys, time, os
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
from lib import *
from pipe import *

G = {}


def _init():
    C, Y, PN, EX = carregar()
    X = construir_X(C)
    esc = json.load(open(PASTA + "variantes_escolhidas.json"))
    cols = [c for f, c in esc.items() if not f.startswith("ctrl_")]
    G.update(Xm=X[cols].values, Y=Y, PN=PN, mes=C.mes.values, mi=C["mi"].values, recuo=C["recuo"].values)


def unidade(args):
    m, S = args
    t = time.time()
    rows = varrer_geometrias(G["Xm"], G["Y"], G["PN"], G["mes"], G["mi"], G["recuo"], [m], [S])
    return m, S, rows, time.time() - t


if __name__ == "__main__":
    unidades = [(m, S) for m in MS for S in SS]
    allrows = []
    with ProcessPoolExecutor(4, initializer=_init) as ex:
        futs = [ex.submit(unidade, u) for u in unidades]
        for f in as_completed(futs):
            m, S, rows, dt_ = f.result()
            allrows += rows
            d = pd.DataFrame(rows)
            print(f"m={m} S={S}: {len(rows)} geometrias, {dt_:.0f}s, AUC medio {d.auc.mean():.3f}, esp_top medio {d.esp_top.mean():+.1f}", flush=True)
    df = pd.DataFrame(allrows)
    df["esp_top_suav"] = suavizar_criterio(df, "esp_top")
    df["auc_suav"] = suavizar_criterio(df, "auc")
    df.to_csv(PASTA + "geometrias_cv_janjun.csv", index=False)
    print("total geometrias", len(df), flush=True)
