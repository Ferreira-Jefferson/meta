import pandas as pd, numpy as np
K=["spec","cell","fill","side","geom"]
d=pd.read_pickle("tab_desc.pkl"); c=pd.read_pickle("tab_conf.pkl"); s=pd.read_pickle("tab_set.pkl")
dd=d[(d.fill==0)&(d.nf>=150)].set_index(K); cc=c[(c.fill==0)&(c.nf>=60)].set_index(K)
j=dd[["exc","z","exp"]].join(cc[["exc","z","exp"]],rsuffix="_c",how="inner")
print("cells em ambas",len(j),"corr exc desc x conf",j.exc.corr(j.exc_c).round(3))
for lim in (2,3):
    for sgn in (1,-1):
        m=(sgn*j.z>lim); print(f"desc z{'>' if sgn>0 else '<-'}{lim}: n={m.sum()}  conf mesmo sinal={((j.exc_c[m]*sgn)>0).mean():.2f}  conf z>1 mesmo lado={((j.z_c[m]*sgn)>1).mean():.2f}")
# media do excesso por lado x r (spec r) e por geom family
r=dd.reset_index(); r=r[r.spec=="r"]
r["fam"]=np.where(r.geom<16,"pts","A")
print(r.groupby(["side","cell","fam"]).exc.mean().unstack([0,2]).round(1))
rc=cc.reset_index(); rc=rc[rc.spec=="r"]; rc["fam"]=np.where(rc.geom<16,"pts","A")
print(rc.groupby(["side","cell","fam"]).exc.mean().unstack([0,2]).round(1))
a=d[(d.spec=="all")&(d.fill==0)]; print("desc all: exp medio por lado",a.groupby("side").exp.mean().round(1).to_dict(),"null",a.groupby("side")["mean"].mean().round(1).to_dict())
for nm,t in (("conf",c),("set",s)):
    a=t[(t.spec=="all")&(t.fill==0)]; print(nm,"all exp medio",a.groupby("side").exp.mean().round(1).to_dict(),"null",a.groupby("side")["mean"].mean().round(1).to_dict(),"frac",a.fr.mean().round(3))
