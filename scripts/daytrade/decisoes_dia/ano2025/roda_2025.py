"""v1, v2, v3, v4 em todos os pregoes de 2025 (pedido do dono, 2026-10-09). Base IS (ate 2025-09-30) + OOS cortado em 2025-12-31.
Nada de 2026 entra. Separa dias ja usados nos ciclos (dentro da amostra) dos nunca vistos."""
import sys, json
from pathlib import Path
AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
for p in (RAIZ, RAIZ / "ciclo3", RAIZ / "ciclo4"): sys.path.insert(0, str(p))
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
import base

OOS = base.RAIZ / "data/win_sem_leiloes/m1_WIN$N.parquet"


def _init():
    a = pd.read_parquet(base.ARQ)
    b = pd.read_parquet(OOS)
    b = b[b.index < "2026-01-01"]
    base._M1 = pd.concat([a, b]).sort_index()


def _roda(args):
    versao, dia = args
    import robo, cfg3, robo_v3, robo_v4, p4_validacao as p4
    if versao == "v1":
        tr, _, _ = robo.roda_robo(dia)
    elif versao == "v2":
        tr, _ = cfg3.roda(dia, cfg3.monta([]))
    elif versao == "v3":
        tr, _ = cfg3.roda(dia, cfg3.monta(robo_v3.IDS))
    else:
        tr, _ = robo_v4.roda_v4(dia)
    return versao, dia, p4._res(tr)


def dias_2025():
    _init()
    m = base._M1
    m = m[(m.index >= "2025-01-01") & (m.index < "2026-01-01")]
    g = m.groupby(m.index.normalize()).size()
    return [str(d.date()) for d, n in g.items() if n >= 300]


if __name__ == "__main__":
    dias = dias_2025()
    du = json.load(open(RAIZ / "dias_usados.json"))
    usados = set(du["ciclo0"]["dias"]) | {x["dia"] for c in ("ciclo1", "ciclo2", "ciclo3", "ciclo4") for x in du[c]["dias"]}
    print("pregoes 2025:", len(dias), "| ja usados nos ciclos:", len([d for d in dias if d in usados]), flush=True)
    R = {v: {} for v in ("v1", "v2", "v3", "v4")}
    with ProcessPoolExecutor(8, initializer=_init) as ex:
        fut = [ex.submit(_roda, (v, d)) for d in dias for v in R]
        n = 0
        for f in as_completed(fut):
            v, d, r = f.result(); R[v][d] = r; n += 1
            if n % 100 == 0: print(f"  {n}/{len(fut)}", flush=True)
    json.dump(dict(dias=dias, usados=sorted(usados & set(dias)), R=R), open(AQUI / "resultado_2025.json", "w"), indent=1, default=str)
    print("ok", flush=True)
