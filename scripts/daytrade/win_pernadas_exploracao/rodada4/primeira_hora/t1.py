import time,numpy as np
from core_ph import *
dias=carrega();ld=sorted(k for k in dias if '2026-01'<=k<'2026-07')
print(len(ld))
t0=time.time()
pd_=config_run(dias,ld,('0900',150,10,0,5,150,250))
print(time.time()-t0,resume(pd_,0,np.random.default_rng(1)),resume(pd_,1))
