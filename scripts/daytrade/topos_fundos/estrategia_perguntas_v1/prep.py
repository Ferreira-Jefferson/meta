"""Calcula resultados por vela-lado para as 4 geometrias e salva."""
import pickle, numpy as np
from lib import *
GEOS = [(1.0, 4), (1.0, 8), (1.5, 4), (1.5, 8)]
if __name__ == "__main__":
    for per in PER:
        z = carrega(per); out = {}
        for g in GEOS:
            out[g] = resultados(z, *g); p = out[g][0]
            print(per, g, "enche", int(np.isfinite(p).sum()), "media pts/contrato", np.nanmean(p).round(1), flush=True)
        pickle.dump(out, open(f"res_{per}.pkl", "wb"))
