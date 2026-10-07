import pickle,sys,numpy as np,pandas as pd
from lib import LEVELS
def tab(per,dims=("all","ab","hb","ob","db"),minn=30):
    r=pickle.load(open(f"res_{per}.pkl","rb"))
    rows=[]
    for k,(a,b,c,n) in r["real"].items():
        if n<minn: continue
        ns=[s[k] for s in r["null"] if k in s]
        if len(ns)<50: continue
        ns=np.array([x[:3] for x in ns])
        for j,m in enumerate(["NH","P1.5A","P2A"]):
            v=(a,b,c)[j]; mu=np.nanmean(ns[:,j]); sd=np.nanstd(ns[:,j])
            rows.append(dict(dim=k[0],lv=(LEVELS[int(k[1])] if k[0] not in ("F1","F2","F3") else -1),sub=k[2],m=m,n=n,real=v,nulo=mu,exc=v-mu,z=(v-mu)/sd if sd>0 else 0))
    return pd.DataFrame(rows)
if __name__=="__main__":
    per=sys.argv[1];t=tab(per)
    pd.set_option("display.width",250);pd.set_option("display.max_rows",2000)
    t["lv"]=t.lv.astype(float)
    t.to_pickle(f"tab_{per}.pkl")
    print(len(t),"cells; |z|>=2:",(t.z.abs()>=2).sum())
    print(t[t.dim=="all"].round(3).to_string())
    print(t[(t.z.abs()>=2.5)&(t.dim!="all")].round(3).to_string())
