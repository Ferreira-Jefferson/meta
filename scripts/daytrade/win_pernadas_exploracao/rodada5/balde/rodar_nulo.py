import sys, time, pickle
sys.path.insert(0,'.')
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
from balde_core import *
K=int(sys.argv[1]) if len(sys.argv)>1 else 40
if __name__=="__main__":
    days=load_days(); av=avg_range_prev(days)
    nd=len(days); t0=time.time()
    tasks=[]
    for r in range(K):
        for i in range(nd):
            tasks.append(dict(di=i,rep=r,d=days[i],avgr=av[i],otim=False,shuffle_seed=7919*r+i+1,full=False,blocks=False))
    acc=None; names=None
    def f(t):
        di,nm,F,B=run_day(t); return di,t['rep'],nm,F
    res={}
    with ProcessPoolExecutor(6) as ex:
        futs=[ex.submit(run_day,t) for t in tasks]
        meta={}
        k=0
        for fu,t in zip(futs,tasks): meta[fu]=(t['rep'],t['di'])
        for fu in as_completed(futs):
            di,nm,F,B=fu.result(); rep,_=meta[fu]
            if acc is None: acc=np.zeros((K,nd,F.shape[0],11),dtype=np.float32); names=nm
            acc[rep,di]=F; k+=1
            if k%400==0: print(k,len(tasks),round(time.time()-t0),flush=True)
    pickle.dump(dict(F=acc.astype(np.float32),names=names),open('nulo.pkl','wb'))
    print('ok',flush=True)
