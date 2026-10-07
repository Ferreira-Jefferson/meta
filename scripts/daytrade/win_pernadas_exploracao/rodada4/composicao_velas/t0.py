import time, core
t=time.time(); d=core.ler(); print(len(d), list(d)[:2], list(d)[-2:], time.time()-t, flush=True)
t=time.time(); tb=core.tudo(d); print(tb.shape, time.time()-t)
print(tb.filter(regex="^_").describe().T)
tb.to_pickle("real.pkl")
