import time, numpy as np, core
t=time.time(); raw=core.load_raw(); print(len(raw), time.time()-t, flush=True)
D=core.Data(raw); print('data', time.time()-t, D.N, np.bincount(D.win), flush=True)
P=(9,21,50,'ema')
for ltf,htf in [(5,15),(15,60),(5,30),(10,30),(5,60),(60,0)]:
  for var in 'cf':
    cfg=dict(ltf=ltf,htf=htf,var=var,trend='strict',breach='fms',ref='m',x=0.5,P=P)
    t1=time.time()
    for s in (1,-1):
        e=core.gen_events(D,cfg,s)
        print(ltf,htf,var,s,{k:int(((D.win[v]==1)).sum()) for k,v in e.items()}, round(time.time()-t1,2), flush=True)
