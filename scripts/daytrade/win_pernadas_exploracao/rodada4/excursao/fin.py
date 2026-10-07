import pandas as pd, numpy as np, exc, cand
d=pd.read_pickle("tab_desc.pkl")
for f in (0,1):
    x=d[(d.fill==f)&(d.nf>=150)]; print("fill",f,"tests",len(x),"exp>0",(x.exp>0).sum(),"exp>0&z>=2",((x.exp>0)&(x.z>=2)).sum(),"max exp",x.exp.max().round(1), "fill rate medio",x.fr.mean().round(3))
a=d[(d.spec=="all")]
rows=[]
for g in (0,3,5,10,12,15,16,18,22):
    r=[cand.gname(g)]
    for f in (0,1):
        for s in (0,1):
            q=a[(a.fill==f)&(a.side==s)&(a.geom==g)].iloc[0]; r+= [f"{q.exp:.1f} ({q['mean']:.1f})", f"{q.win*100:.1f}/{q.be*100:.1f}"]
    rows.append("| "+" | ".join(r)+" |")
print("\n".join(rows))
c=pd.read_pickle("tab_conf.pkl"); c=c[(c.fill==0)&(c.nf>=60)]; print("conf cons exp>0:",(c.exp>0).sum(),"de",len(c))
