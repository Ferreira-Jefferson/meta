import time,pandas as pd
from eventos import *
c=pd.read_pickle("candles.pkl"); days=prep_days(c)
print(len(days)); d=[x for x in days if "2026.04.01"<=x["date"]<="2026.04.30"]
t=time.time(); e=events_table(d); print(time.time()-t,len(e)); print(e.describe().T.round(3).to_string())
t=time.time(); e2=events_table(d,seed=1); print(time.time()-t,len(e2))
