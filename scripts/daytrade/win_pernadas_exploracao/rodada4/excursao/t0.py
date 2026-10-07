import time, exc
t=time.time(); s,w,df,R=exc.run_task((1,1,-1,0)); print(time.time()-t, len(df), R.shape)
print(df.head()); import numpy as np
print(np.nanmean(R[:,:exc.NG],axis=0).round(1)); print((~np.isnan(R[:,:exc.NG])).mean(0).round(2)[:4], (~np.isnan(R[:,2*exc.NG:3*exc.NG])).mean(0).round(2)[:4])
t=time.time(); s,w,df,R=exc.run_task((1,1,0,0)); print(time.time()-t, len(df))
