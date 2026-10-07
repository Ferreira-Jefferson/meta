import sys, time, pickle
from concurrent.futures import ProcessPoolExecutor, as_completed
import fractal_core as fc
per, ndraw = sys.argv[1], int(sys.argv[2])
ini, fim = fc.PERIODOS[per]
def unit(seed):
    t=time.time(); ev=fc.processa(ini, fim, seed=seed); ev["draw"]=-1 if seed is None else seed
    return seed, ev, time.time()-t
if __name__=="__main__":
    out=[]
    with ProcessPoolExecutor(4) as ex:
        futs=[ex.submit(unit, None)]+[ex.submit(unit, 1000+i) for i in range(ndraw)]
        for f in as_completed(futs):
            s,ev,dt=f.result(); out.append(ev); print(per,"seed",s,len(ev),f"{dt:.0f}s",flush=True)
    import pandas as pd
    pd.concat(out).to_pickle(f"ev_{per}.pkl")
