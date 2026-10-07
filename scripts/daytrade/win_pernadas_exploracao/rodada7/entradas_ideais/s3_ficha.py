import json, numpy as np, pandas as pd
from lib import *
C,Y,PN,EX=carregar(); X=construir_X(C); mes=C.mes.values; mi=C["mi"].values; rec=C["recuo"].values
esc=json.load(open(PASTA+"variantes_escolhidas.json"))
geos={"REF(N5 p1 K5 m150 S15)":REF,"K5(N10 p.5 K5 m250 S5)":dict(N=10,piso=.5,K=5,m=250,S=5),"SEL(N15 p.5 K10 m250 S5)":dict(N=15,piso=.5,K=10,m=250,S=5)}
rows=[]
for fam,c in esc.items():
    r=dict(familia=fam,variante=c,grupo=GRUPOS[c])
    for gn,g in geos.items():
        a,b,k=NS.index(g["N"]),PISOS.index(g["piso"]),KS.index(g["K"])
        base=(rec>=g["m"])&(mi%g["S"]==0)&(Y[:,a,b,k,0]>=0)
        for jn,ms in (("jj",range(1,7)),("ja",(7,8)),("se",(9,))):
            s=base&np.isin(mes,list(ms))
            r[f"{gn[:3]}_{jn}"]=auc(Y[s,a,b,k,0].astype(float),X[c].values[s])
    rows.append(r)
d=pd.DataFrame(rows)
for g in ("REF","K5(","SEL"):
    pass
def cls(r):
    out=[]
    for g in ("REF","K5(","SEL"):
        v=[r[f"{g}_{j}"] for j in ("jj","ja","se")]
        sg=[np.sign(x-.5) for x in v]
        out.append("".join("+" if s>0 else "-" for s in sg))
    return out
d[["sinais_REF","sinais_K5","sinais_SEL"]]=[cls(r) for _,r in d.iterrows()]
d["consistente"]=d.apply(lambda r: sum(1 for s in (r.sinais_REF,r.sinais_K5,r.sinais_SEL) if len(set(s))==1 and abs(r[ "K5(_jj"]-.5)>=0),axis=1)
pd.set_option("display.width",250); pd.set_option("display.max_rows",200)
print(d.round(3).to_string(index=False))
d.to_csv(PASTA+"ficha_auc_por_janela.csv",index=False)
