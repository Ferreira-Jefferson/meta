import sys; sys.path.insert(0,'ciclo3')
import av, cfg3, json
import numpy as np
ef = av.eficiencia_todos()
n=len(ef); print("dias IS elegiveis:", n)
for lb in (0.25,0.30):
    c={"bom":0,"int":0,"ruim":0}
    for d,e in ef.items(): c[av.estrato(e,lb)]+=1
    print("limiar bom",lb,{k:(v,round(v/n,4)) for k,v in c.items()})
d50=cfg3.dias50()
from collections import Counter
print(Counter((t,av.estrato(ef[d])) for d,t in d50))
print(Counter(av.estrato(ef[d]) for d,t in d50))
print("ef>=0.30 nos 50:", sum(ef[d]>=0.30 for d,t in d50))
