import numpy as np, pandas as pd, pickle, json
from concurrent.futures import ProcessPoolExecutor, as_completed
from eventos import *
from lib_an import WIN
def corrs(df,dates):
    dd=dates[df.day.values]; out={}
    df=df.assign(y=df.MFE60/df.A,ab=np.digitize(df.A,[250,400,750]))
    for w,(a,b) in WIN.items():
        s=df[(dd>=a)&(dd<=b)]
        row=[]
        for f in FEATS:
            t=s[s[f].notna()&s.y.notna()]
            rf=t.groupby(["lv","hb","ab"])[f].rank(pct=True); ry=t.groupby(["lv","hb","ab"])["y"].rank(pct=True)
            row.append(np.corrcoef(rf,ry)[0,1] if len(t)>30 else np.nan)
        out[w]=np.array(row)
    return out
def work(seeds):
    c=pd.read_pickle("candles.pkl"); days=prep_days(c); dates=np.array([d["date"] for d in days])
    return [corrs(events_table(days,seed=s),dates) for s in seeds]
if __name__=="__main__":
    c=pd.read_pickle("candles.pkl"); days=prep_days(c); dates=np.array([d["date"] for d in days])
    real=corrs(pd.read_pickle("eventos_real.pkl"),dates)
    seeds=list(range(5000,5100)); res=[]
    with ProcessPoolExecutor(10) as ex:
        for f in as_completed([ex.submit(work,seeds[i::10]) for i in range(10)]): res+=f.result()
    rows=[]
    for w in WIN:
        arr=np.stack([r[w] for r in res]); mu=np.nanmean(arr,0); sd=np.nanstd(arr,0)
        for i,f in enumerate(FEATS): rows.append(dict(w=w,f=f,corr=real[w][i],nulo=mu[i],z=(real[w][i]-mu[i])/sd[i]))
    T=pd.DataFrame(rows); T.to_csv("alcance_tabela_estratoA.csv",index=False)
    print(T.pivot(index="f",columns="w",values="z").round(2)); print(T.pivot(index="f",columns="w",values="corr").round(3))
