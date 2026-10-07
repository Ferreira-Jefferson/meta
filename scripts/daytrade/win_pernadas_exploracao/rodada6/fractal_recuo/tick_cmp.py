import pandas as pd, numpy as np
A=pd.read_pickle("ev_tick.pkl"); B=pd.read_pickle("ev_m1_tickdias.pkl")
print("dias",A.dia.nunique())
f=lambda x:f"{x:.1f}".replace(".",",")
print("| T/s | caminho | n | alto% | duplo% | baixo% | exc<=50 | exc<=100 | exc<=200 | acerto k=100 | pts/op k=100 | pts/op k=200 |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for T,s in [(250,65),(500,125),(750,190)]:
  for nm,D in [("M1",B),("tick",A)]:
    d=D[(D["T"]==T)&(D.s==s)]; r=d[d.forma!="s"]
    G=r.G.fillna(r.F-999)
    al=(G>r.F+10).mean()*100; du=((G-r.F).abs()<=10).mean()*100; ba=(G<r.F-10).mean()*100
    sup=d[d.out=="sup"]
    ex=[(sup.exc_min<=k).mean()*100 for k in (50,100,200)]
    h=d[d.g_fill==1]; res=[]
    for k in (100,200):
        e=h.g_mn_exc.values; w=(h.g_alvo.values==1)&(e<k); l=e>=k
        pts=np.where(w,h.d1.values-2,np.where(l,-(k+7),h.g_ult.values-2)); res.append(pts.mean() if len(h) else np.nan)
        if k==100: ac=w.sum()/max(w.sum()+l.sum(),1)*100
    print(f"| {T}/{s} | {nm} | {len(d)} | {f(al)} | {f(du)} | {f(ba)} | {f(ex[0])} | {f(ex[1])} | {f(ex[2])} | {f(ac)} | {f(res[0])} | {f(res[1])} |")
