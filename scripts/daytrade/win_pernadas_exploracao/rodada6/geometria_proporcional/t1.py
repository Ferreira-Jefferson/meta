import time, numpy as np, pandas as pd, geomlib as G, stage as st
t0=time.time()
days=G.load_days(); ars=G.avg_range_prev(days)
print(len(days), time.time()-t0, flush=True)
win=[i for i,d in enumerate(days) if not d["warm"] and d["month"]<=6]
print(len(win))
sub=win[:30]
t0=time.time(); b=st.build(days,ars,sub); print("build",time.time()-t0, flush=True)
for k,(evs,res,tk) in b.items(): print(k,len(evs), None if res is None else int(res['filled'][:,:,0].sum()))
t0=time.time(); cols,rows=st.grid_stats(b,sub); print("stats",time.time()-t0,len(rows))
df=pd.DataFrame(rows,columns=cols); print(df.sort_values('t',ascending=False).head(8)); print(df['mean'].describe())
