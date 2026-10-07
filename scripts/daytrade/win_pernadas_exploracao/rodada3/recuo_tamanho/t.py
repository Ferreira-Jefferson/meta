import time;from lib import *
d=load_days(1,1);print(len(d))
t0=time.time();e=events_all(d);print(time.time()-t0,len(e));print(e.groupby("lv")[["NH","P15","P20"]].mean());print(e.groupby("lv").size())
e=events_all(d,np.random.default_rng(1));print(e.groupby("lv")[["NH","P15","P20"]].mean())
