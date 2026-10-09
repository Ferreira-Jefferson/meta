import sys; sys.path.insert(0,'ciclo3'); sys.path.insert(0,'.')
import ag2_lib as L, base, numpy as np, pandas as pd, json
from regras import c3_2025_06_20 as g
base_res=L.base70()
rows=[]
for dia in L.DIAS:
    tr=[t for t in base_res[dia]['trades'] if t['lado']=='venda']
    if not tr: continue
    alvo={pd.Timestamp(dia+' '+t['sinal']):t for t in tr}
    for t,ctx in base.contextos(dia):
        if t in alvo:
            h=ctx.hoje
            if len(h)<5: continue
            lo=float(g._p1(ctx).low.min()); c=float(h.close.iloc[-1])
            if not c<lo: continue
            tt=alvo[t]
            # distancia abaixo do nivel
            nb=int((h.close.iloc[-9:-1]<lo).sum())
            rows.append(dict(dia=dia,t=str(t.time()),fonte=tt['fonte'][:28],brl=tt['brl'],motivo=tt['motivo'],
              prof=round((lo-c)/ctx.atr15,2),hm=g._hm(ctx),ampl=round(g._ampl(ctx),2),desloc=round(g._desloc(ctx),2),efic=round(g._efic(ctx),2),
              volr=round(float(h.vol.iloc[-1]/h.vol.mean()),2),nb=nb,est=L.EST[L.DIAS.index(dia)],
              novo=int(c<h.low.iloc[:-1].min())))
df=pd.DataFrame(rows); df.to_csv('ciclo3/ag2_a2_liberadas.csv',index=False)
print(df.to_string())
