import numpy as np, pandas as pd
from volume_sintetico import *
d=pd.read_pickle(HERE+"/candles.pkl")
r=pd.read_pickle(HERE+"/minutos_ticks.pkl"); r=r[r.fonte=="WINV26"][["date","mn","nt","v","dt","dr","drn"]].rename(columns={"nt":"nt_v","v":"v_v","dt":"dt_v"})
x=d.merge(r,on=["date","mn"],how="inner")
x=x[x.date>="2026.08.12"].sort_values(["date","mn"]).reset_index(drop=True)
print("dias",x.date.nunique(),"minutos",len(x))
def corr(a,b): return float(np.corrcoef(a,b)[0,1])
def sgn(a,b):
    m=(a!=0)&(b!=0); return float((np.sign(a[m])==np.sign(b[m])).mean())
cands={"regra do tick (WIN@D)":"dt","regra do tick (WINV26)":"dt_v","candle CLV (M1)":"dclv","candle corpo/range (M1)":"dsgn"}
x["csg"]=x.vol*np.sign(x.close-x.open); cands["sinal do corpo x vol (M1)"]="csg"
x["dn_real"]=x.drn
rows=[]
for nome,c in cands.items():
    row={"medida":nome}
    row["corr 1min"]=corr(x[c],x.dr); row["acerto sinal 1min"]=sgn(x[c].values,x.dr.values)
    for w in (5,15,30):
        g=x.groupby("date")
        a=g[c].transform(lambda s:s.rolling(w).sum()); b=g["dr"].transform(lambda s:s.rolling(w).sum())
        k=a.notna(); row[f"corr {w}min"]=corr(a[k],b[k]); row[f"sinal {w}min"]=sgn(a[k].values,b[k].values)
    # delta acumulado do dia
    a=x.groupby("date")[c].cumsum(); b=x.groupby("date")["dr"].cumsum()
    row["corr acum dia"]=corr(a,b)
    # por dia (corr do acumulado, mediana)
    cd=[corr(g[c].cumsum(),g["dr"].cumsum()) for _,g in x.groupby("date")]
    row["mediana corr acum/dia"]=float(np.median(cd))
    rows.append(row)
res=pd.DataFrame(rows).round(3); print(res.to_string())
# delta sintetico relativo ao volume (fracao): corr
x["fr_real"]=x.dr/x.v_v; x["fr_syn"]=x.dt/x.v
print("corr fracao delta/vol 1min (tick rule vs real):",round(corr(x.fr_real.fillna(0),x.fr_syn.fillna(0)),3))
# negocios: nt de WINV26 vs WIN@D, tickvol vs nt
print("corr nt(WIN@D) x nt(WINV26):",round(corr(x.nt.fillna(0),x.nt_v),3)," corr tickvol x nt:",round(corr(x.tickvol,x.nt.fillna(0)),3)," razao tickvol/nt:",round((x.tickvol.sum()/x.nt.sum()),2))
print("corr vol M1 x v ticks:",round(corr(x.vol,x.v.fillna(0)),4))
# calibracao: inclinacao delta_sint = k*delta_real
for c in ["dt","dclv","dsgn"]:
    k=(x[c]*x.dr).sum()/(x.dr**2).sum(); print("beta",c,round(k,3))
# por horario
x["h"]=pd.cut(x.mn,[0,600,660,780,1100],labels=["09-10","10-11","11-13","13+"])
print(x.groupby("h",observed=True).apply(lambda g:pd.Series({"corr tick":corr(g.dt,g.dr),"corr clv":corr(g.dclv,g.dr),"sinal tick":sgn(g.dt.values,g.dr.values)})).round(3))
# por mes
x["mes"]=x.date.str[5:7]
print(x.groupby("mes").apply(lambda g:pd.Series({"corr tick":corr(g.dt,g.dr),"corr clv":corr(g.dclv,g.dr)})).round(3))
res.to_csv(HERE+"/validacao.csv",index=False)
