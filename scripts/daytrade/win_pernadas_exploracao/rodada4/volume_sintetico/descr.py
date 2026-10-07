import numpy as np, pandas as pd, pickle, json
df=pd.read_pickle("eventos_real.pkl"); dates=pickle.load(open("dates.pkl","rb")); thr=json.load(open("limiares.json"))
df["date"]=dates[df.day.values]; df["w"]=np.where(df.date<="2026.06.30","desc",np.where(df.date<="2026.08.31","conf","set"))
print("Base por nivel (desc):"); b=df[df.w=="desc"].groupby("lv").agg(n=("NH","size"),NH=("NH","mean"),P20=("P20","mean"),MFE30=("MFE30","median"),MAE30=("MAE30","median"),fill=("fill","mean"),Eg1=("E_g1","mean"),Eg2=("E_g2","mean")); print(b.round(3))
rows=[]
for f in ["N2","V2","D3","S1","E2"]:
    lo,hi=thr[f]
    for w in ("desc","conf"):
        s=df[(df.w==w)&df[f].notna()]
        for nome,m in (("baixo",s[f]<=lo),("meio",(s[f]>lo)&(s[f]<hi)),("alto",s[f]>=hi)):
            t=s[m]; r=dict(f=f,w=w,t=nome,n=len(t),NH=t.NH.mean(),P2A=t.P20.mean())
            for W in (15,30,60): r[f"MFE{W}"]=t[f"MFE{W}"].median(); r[f"MAE{W}"]=t[f"MAE{W}"].median()
            r["razao60"]=(t.MFE60/t.A).median(); r["Eg1"]=t.E_g1.mean(); r["Eg2"]=t.E_g2.mean(); rows.append(r)
T=pd.DataFrame(rows); T.to_csv("descritivo_tercis.csv",index=False); print(T.round(3).to_string())
print(df.groupby("w").size())
