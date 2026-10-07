from lib import *
ev=pd.read_pickle("ev_desc.pkl"); r=pd.read_pickle("res_desc.pkl")
cells={key_str(k):m for k,m in cellmasks(ev).items()}
r["marg"]=np.where(r["diff"]>0,r.lo,-r.hi)
r["tier"]=np.where((r.lo*r.hi>0),1,2)
c=r[(r.dias>=30)&(r["diff"].abs()>=0.10)].sort_values(["tier","marg"],ascending=[True,False])
print("candidatos |diff|>=10pp:",len(c),"tier1:",(c.tier==1).sum())
sel=[];masks=[];used=set()
for _,row in c.iterrows():
    m=cells[row.cell]
    if row.cell in used: continue
    if any((m&mm).sum()/(m|mm).sum()>0.5 for mm in masks): continue
    sel.append(row);masks.append(m);used.add(row.cell)
    if len(sel)>=20: break
fz=pd.DataFrame(sel)
fz[["cell","out","n","dias","p","base","diff","lo","hi","tier"]].to_csv("congelada.csv",index=False)
print(fz[["cell","out","n","dias","p","base","diff","lo","hi","tier"]].round(3).to_string())
