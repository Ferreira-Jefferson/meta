import sys, json, datetime; sys.path.insert(0,'.')
import pandas as pd
df=pd.read_pickle('desc_cells.pkl'); df=df[df.nf>=150]
top=df.sort_values('t',ascending=False).head(12)
ref=df[df.key.str.contains(", 100, 750")&(df.kind=='F')].sort_values('t',ascending=False).head(3)
sel=pd.concat([top,ref]).drop_duplicates(['key','trig','dir'])
out=[dict(key=r.key,trig=r.trig,dir=r.dir,t_desc=round(r.t,3),mean_desc=round(r['mean'],2),nf_desc=int(r.nf)) for _,r in sel.iterrows()]
json.dump(dict(congelado_em=str(datetime.datetime.now()),criterio='top-12 por t (desc jan-jun, n>=150, cons) + 3 melhores 100/750 F; nenhum chegou a t>=3',cells=out),open('congelado_ANTES_da_confirmacao.json','w'),indent=1,ensure_ascii=False)
print(len(out)); print(sel[['key','trig','dir','nf','mean','t']].to_string())
