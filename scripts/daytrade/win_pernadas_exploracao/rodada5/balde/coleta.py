import sys, pickle; sys.path.insert(0,'.')
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
import balde_core as bc
def w(task):
    bc.COLL.clear()
    bc.run_day(task)
    return task['di'], list(bc.COLL)
CELLS={'F50_1000_v2xonda_contra':(('F',50,1000),'v2x&onda','d_contra'),
       'TC5_7.5_v2xonda_contra':(('TC',5,7.5),'v2x&onda','d_contra'),
       'TC15_7.5_v2xonda_aleat':(('TC',15,7.5),'v2x&onda','a_aleat'),
       'F100_750_h11v2x_contra':(('F',100,750),'h<11&v2x','d_contra'),
       'F100_750_none_aleat':(('F',100,750),'none','a_aleat')}
if __name__=="__main__":
    days=bc.load_days(); av=bc.avg_range_prev(days)
    out={}
    for nm,cell in CELLS.items():
        full = cell[0][0]!='F'
        res={}
        with ProcessPoolExecutor(6) as ex:
            futs=[ex.submit(w,dict(di=i,d=days[i],avgr=av[i],otim=False,shuffle_seed=None,full=full,blocks=False,collect=cell)) for i in range(len(days)) if days[i]['month']<=8]
            for fu in as_completed(futs):
                di,c=fu.result(); res[di]=c
        pn=[];dias=[]
        for di in sorted(res):
            for (d_,rows,fil,pnl,cd,dur) in res[di]:
                pn+=list(pnl[fil]); dias+=[di]*int(fil.sum())
        out[nm]=dict(pnl=np.array(pn),dia=np.array(dias),n_dias=len(res))
        print(nm,len(pn),np.mean(pn),flush=True)
    pickle.dump(out,open('trades_celulas.pkl','wb'))
