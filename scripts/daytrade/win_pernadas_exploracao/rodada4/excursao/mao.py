import sys, numpy as np, pandas as pd
sys.path.insert(0,"../decisao"); import motor, cand, exc
d=pd.read_csv("candidatos_desc.csv")
for _,r in d.iterrows():
    g=[i for i in range(exc.NG) if cand.gname(i)==r.geom][0]; t=exc.GEOMS[g]
    dd,R=cand.W["desc"]; m=cand.mask(dd,r.cell); A=dd.A[m].mean()
    T,S=(t[1],t[2]) if t[0]=="p" else (exc.r5(t[1]*A),exc.r5(t[2]*A))
    gan,per=motor.ganho_perda(T,S); be=motor.breakeven_p(gan,per)
    k=int(round(r.win*r.nf)); pe=motor.p_encolhido(k,int(r.nf),be)
    n=motor.tamanho(pe,gan,per,250.0)
    print(r.cell,r.geom,f"T={T:.0f} S={S:.0f} perda1ct=R${per*0.2:.0f} be={be:.3f} p_obs={r.win:.3f} p_enc={pe:.3f} esp_enc={motor.esperanca(pe,gan,per):.1f}pts mao={n}")
