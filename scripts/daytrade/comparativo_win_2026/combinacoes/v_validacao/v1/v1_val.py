"""V1 etapa 3: VAL (2024-07-01 -> 2025-09-30), UMA vez. Roda as candidatas que seguiram (filtro_2026.csv, segue=True), grava
trades_val/<Ck>.csv, trades_val/orig_<robo>.csv e os sorteios nulos controles_val/<Ck>.npy (2.000 deltas, R$ com custo).
Retomavel por arquivo (so' refaz o que falta). V1_SMOKE=1: janela 2024-04..06 e saida em _smoke/ (teste de fumaca, nao e' VAL).
Uso: python v1_val.py"""
import os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np, pandas as pd
AQ = Path(__file__).resolve().parent
sys.path.insert(0, str(AQ))
import v1_regras as R

SMOKE = bool(os.environ.get("V1_SMOKE"))
OUT = AQ / ("_smoke" if SMOKE else ".")
NSORT = 2000 if not SMOKE else 40
SEED = 20261006
CH = 12   # pedacos do controle da C13


def _init_worker():
    R.init("val")
    global CTX, EST
    CTX = R.carrega_ctx("val")
    EST = R.roda("C13", *CTX, com_wdo=False)[1]


def _chunk(seeds):
    return [R._ctrl_c13_um(EST, s) for s in seeds]


def main():
    (OUT / "trades_val").mkdir(parents=True, exist_ok=True); (OUT / "controles_val").mkdir(parents=True, exist_ok=True)
    seg = pd.read_csv(AQ / "filtro_2026.csv")
    ids = list(seg[seg.segue].id)
    print("candidatas que chegam ao VAL:", ids, flush=True)
    R.init("val")
    votos, eventos, res, dados = R.carrega_ctx("val")
    for robo, t in res.items():
        R.original_janela(res, robo).to_csv(OUT / "trades_val" / f"orig_{robo}.csv", index=False)
    for cid in ids:
        f_t, f_c = OUT / "trades_val" / f"{cid}.csv", OUT / "controles_val" / f"{cid}.npy"
        if f_t.exists() and f_c.exists():
            print(f"[{cid}] ja feito, pulando", flush=True); continue
        t0 = time.time()
        trades, est = R.roda(cid, votos, eventos, res, dados, com_wdo=False)
        trades.to_csv(f_t, index=False)
        print(f"[{cid}] {R.CAND[cid][0]} {R.CAND[cid][1]}: {len(trades)} ops, liq R$2 {(trades.rs - R.CUSTO).sum():.1f} ({time.time()-t0:.0f}s)", flush=True)
        if R.CAND[cid][2] == "nova":
            seeds = [SEED + i for i in range(NSORT)]
            parts = [seeds[i::CH] for i in range(CH)]
            out = {}
            with ProcessPoolExecutor(max_workers=3, initializer=_init_worker) as ex:
                futs = {ex.submit(_chunk, p): j for j, p in enumerate(parts)}
                for fu in as_completed(futs):
                    out[futs[fu]] = fu.result()
                    print(f"  [{cid}] controle: pedaco {futs[fu]} pronto ({len(out)}/{CH})", flush=True)
            ctrl = np.empty(NSORT)
            for j, p in enumerate(parts):
                ctrl[j::CH] = out[j]
        else:
            ctrl = R.controle(cid, est, trades, res, n=NSORT, seed=SEED)
        np.save(f_c, ctrl)
        print(f"  [{cid}] controle {NSORT} sorteios: p50 {np.median(ctrl):.1f} p95 {np.percentile(ctrl, 95):.1f} ({time.time()-t0:.0f}s)", flush=True)
    print("VAL concluido", flush=True)


if __name__ == "__main__":
    main()
