import time, sim
from lente2_sim import *
d=carregar("WINV26",*SET); a=carregar("WINV26",*AGO)
for nome,cf in [("defeito",Cfg(modo_defeito=True)),("certo4.5",Cfg())]:
    for dd,n in [(a,"ago"),(d,"set")]:
        t=time.time(); r=resumo(sim.simula(dd,cf),2.0); print(nome,n,{k:round(v,1) for k,v in r.items()},round(time.time()-t,1),flush=True)
r=roda(d,Cfg2(modo_defeito=False)); print(r)
