import sys, numpy as np, pandas as pd, json, pickle
from concurrent.futures import ProcessPoolExecutor, as_completed
from eventos import *
from lib_an import *
NSIM=int(sys.argv[1]) if len(sys.argv)>1 else 300
def g():
    c=pd.read_pickle("candles.pkl"); return prep_days(c)
def worker(seeds):
    days=g(); dates=day_dates(days); thr=json.load(open("limiares.json"))
    res=[]
    for s in seeds:
        df=events_table(days,seed=s); res.append((s,stat_vector(df,thr,dates)))
    return res
if __name__=="__main__":
    days=g(); dates=day_dates(days)
    real=events_table(days); real.to_pickle("eventos_real.pkl")
    desc=real[dates[real.day.values]<=WIN["desc"][1]]
    thr=terciles(desc); json.dump(thr,open("limiares.json","w"),indent=1)   # congelados: so distribuicao das features
    pickle.dump(dates,open("dates.pkl","wb"))
    pickle.dump(stat_vector(real,thr,dates),open("stat_real.pkl","wb"))
    seeds=list(range(1000,1000+NSIM)); chunks=[seeds[i::10] for i in range(10)]
    allr=[]
    with ProcessPoolExecutor(10) as ex:
        for f in as_completed([ex.submit(worker,c) for c in chunks]):
            allr+=f.result(); print(len(allr),flush=True)
    pickle.dump(allr,open("stat_nulo.pkl","wb"))
