import sys, time, pickle
sys.path.insert(0,'.')
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
from balde_core import *

if __name__=="__main__":
    days=load_days(); av=avg_range_prev(days)
    out={}
    t0=time.time()
    for otim in (False,True):
        tasks=[dict(di=i,d=days[i],avgr=av[i],otim=otim,shuffle_seed=None,full=True,blocks=(not otim)) for i in range(len(days))]
        Fs=[None]*len(days); Bs=[None]*len(days); names=None
        with ProcessPoolExecutor(6) as ex:
            futs=[ex.submit(run_day,t) for t in tasks]
            k=0
            for fu in as_completed(futs):
                di,nm,F,B=fu.result(); Fs[di]=F; Bs[di]=B; names=nm; k+=1
                if k%20==0: print(otim,k,round(time.time()-t0),flush=True)
        out[otim]=dict(F=np.stack(Fs),B=(np.stack(Bs) if Bs[0] is not None else None))
    out['names']=names
    out['dates']=[d['date'] for d in days]; out['months']=[d['month'] for d in days]
    pickle.dump(out,open('real.pkl','wb'))
    print('ok',time.time()-t0,flush=True)
