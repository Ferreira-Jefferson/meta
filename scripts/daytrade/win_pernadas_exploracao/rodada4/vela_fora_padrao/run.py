import sys, json, numpy as np, pickle
from concurrent.futures import ProcessPoolExecutor, as_completed
from lib import *; from feats import *
NS=(15,30,60)
def build(per):
    dias=carrega(); ks=sorted(dias)
    for d in ks: dias[d]['dia']=d
    st={tf:sametime(dias,tf) for tf in TFS}
    sel=[d for d in ks if ('2026-01'<=d<'2026-07' if per=='desc' else '2026-07'<=d<'2026-09')]
    return dias,st,sel
def dia_job(args):
    x,st_d,d=args
    st={tf:{d:st_d[tf]} for tf in TFS}
    V=variantes_dia(x,st); n=len(x['t']); out={}
    for nm,(f,dr,idx) in V.items():
        F=np.zeros(n,bool); D=np.zeros(n)
        F[idx[f]]=True; D[idx[f]]=np.asarray(dr)[f]
        out[nm]=(F,D)
    fw={N:forward(x,N) for N in NS}
    import pandas as pd
    tr=(pd.Series(x['h']).rolling(60,min_periods=20).max()-pd.Series(x['l']).rolling(60,min_periods=20).min()).values
    fw['tr']=tr
    return d,out,fw,(x['t']-540)//30
def main(per):
    dias,st,sel=build(per); tasks=[(dias[d],{tf:st[tf][d] for tf in TFS},d) for d in sel]
    R={}
    with ProcessPoolExecutor(4) as ex:
        futs=[ex.submit(dia_job,t) for t in tasks]
        for f in as_completed(futs):
            d,o,fw,sl=f.result(); R[d]=(o,fw,sl)
    pickle.dump(R,open(f'cache_{per}.pkl','wb'))
    print('ok',per,len(R),flush=True)
if __name__=='__main__': main(sys.argv[1])
