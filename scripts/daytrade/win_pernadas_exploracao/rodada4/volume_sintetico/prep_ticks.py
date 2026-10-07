"""Agrega ticks -> tabela por minuto (negocios, contratos, delta pela regra do tick; delta real WINV26)."""
import sys, os, numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
ROOT="C:/Users/Jeffe/Documents/study/meta/data/cache_win_ticks"
OUT=os.path.dirname(os.path.abspath(__file__))

def tick_rule(last):
    d=np.sign(np.diff(last,prepend=last[0]))
    # herda o sinal anterior quando igual
    idx=np.where(d!=0,np.arange(len(d)),-1); np.maximum.accumulate(idx,out=idx)
    s=np.where(idx>=0,d[np.clip(idx,0,None)],0.0)
    return s
def minuto(df,sinal,real=False):
    m=((df.time_msc.values//60000)%1440).astype(int)
    v=df.volume.values.astype(float)
    out=pd.DataFrame({"mn":m,"nt":1.0,"v":v,"dt":sinal*v,"dn":sinal})
    if real:
        f=df["flags"].values
        b=((f&32)!=0); s=((f&64)!=0); sg=np.where(b&~s,1.0,np.where(s&~b,-1.0,0.0))
        out["dr"]=sg*v; out["drn"]=sg
    return out.groupby("mn").sum()
def um_dia(fonte,dia):
    df=pd.read_pickle(f"{ROOT}/{fonte}/{dia}.pkl")
    df=df[df.volume>0]
    sinal=tick_rule(df.last.values)
    r=minuto(df,sinal,real=(fonte=="WINV26")); r["date"]=dia.replace("-","."); r["fonte"]=fonte
    return r.reset_index()
def tarefa(a):
    return a, um_dia(*a)
if __name__=="__main__":
    tarefas=[]
    for f in sorted(os.listdir(f"{ROOT}/WIN@D")):
        if f.startswith("2026-"): tarefas.append(("WIN@D",f[:-4]))
    for f in sorted(os.listdir(f"{ROOT}/WINV26")):
        if f>="2026-08-12": tarefas.append(("WINV26",f[:-4]))
    res=[]
    with ProcessPoolExecutor(3) as ex:
        fs=[ex.submit(tarefa,t) for t in tarefas]
        for i,f in enumerate(as_completed(fs)):
            a,r=f.result(); res.append(r); print(i,a,len(r),flush=True)
    pd.concat(res).to_pickle(f"{OUT}/minutos_ticks.pkl")
