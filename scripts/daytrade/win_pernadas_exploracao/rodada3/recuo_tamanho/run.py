import sys,pickle,numpy as np,pandas as pd
from concurrent.futures import ProcessPoolExecutor,as_completed
from lib import *
PER={"desc":(1,6),"conf":(7,8),"set":(9,9)}
NS=300
def slices(e):
    e=e.copy()
    e["ab"]=pd.cut(e.A,[0,250,375,750,1e9],labels=["150-250","250-375","375-750",">=750"],right=False).astype(str)
    e["hb"]=pd.cut(e.hh,[0,660,780,2000],labels=["<11h","11-13h",">=13h"],right=False).astype(str)
    e["ob"]=np.minimum(e["ord"],3).astype(str)
    e["db"]=pd.cut(e.dur,[-1,2,8,10**6],labels=["<=2","3-8",">8"]).astype(str)
    st={}
    for dim in ["all","ab","hb","ob","db"]:
        keys=["lv"] if dim=="all" else ["lv",dim]
        for k,g in e.groupby(keys):
            kk=(dim,)+(k if isinstance(k,tuple) else (k,))
            if dim=="all": kk=("all",str(k[0]) if isinstance(k,tuple) else str(k),"-")
            st[kk]=(g.NH.mean(),g.P15.mean(),g.P20.mean(),len(g))
    for nm,msk in [("F1",(e.A>=375)&(e.lv>=3)),("F2",(e.A<375)&(e.lv>=3)),("F3",(e['ord']>=2)&(e.lv>=4))]:
        g=e[msk]; st[(nm,"9","-")]=(g.NH.mean(),g.P15.mean(),g.P20.mean(),len(g))
    return st
def one(args):
    per,sid=args
    days=load_days(*PER[per])
    if sid<0:
        e=events_all(days); return sid,slices(e),e
    return sid,slices(events_all(days,np.random.default_rng(1000+sid))),None
if __name__=="__main__":
    per=sys.argv[1]
    out={"null":[]}
    with ProcessPoolExecutor(4) as ex:
        fs=[ex.submit(one,(per,s)) for s in [-1]+list(range(NS))]
        for f in as_completed(fs):
            sid,st,e=f.result()
            if sid<0: out["real"]=st;out["ev"]=e;print("real done",len(e),e.day.nunique(),flush=True)
            else: out["null"].append(st)
    pickle.dump(out,open(f"res_{per}.pkl","wb"));print("ok",per,flush=True)
