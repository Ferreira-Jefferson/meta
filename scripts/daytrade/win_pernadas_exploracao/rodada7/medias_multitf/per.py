import sys, pickle, time, numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
import grid, rules
if __name__ == "__main__":
    cells = [c for f in rules.FAMS for c in rules.period_cells(f)]
    print(len(cells), flush=True)
    chunks = [cells[i::12] for i in range(12)]
    out = []
    with ProcessPoolExecutor(4, initializer=grid.init_worker, initargs=(None,)) as ex:
        for fu in as_completed([ex.submit(grid.task_chunk, (ch, 1, True)) for ch in chunks]):
            out += fu.result()
    pickle.dump(out, open("per_real.pkl", "wb")); print("real ok", flush=True)
    nul = {}
    with ProcessPoolExecutor(4) as ex:
        for fu in as_completed([ex.submit(grid.task_null, (sd, cells, 1)) for sd in range(100, 130)]):
            sd, r = fu.result(); nul[sd] = r; print("null", sd, len(nul), flush=True)
            pickle.dump(nul, open("per_null.pkl", "wb"))
