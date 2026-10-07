import warnings; warnings.filterwarnings("ignore")
import pandas as pd, grid, compare
pd.set_option('display.width',250)
D=grid.get_data()
for name,over in [("ref 9/21/50 M5/M15 fms",{}),("5/30 f",dict(ltf=5,htf=30,breach="f"))]:
    cfg=dict(grid.REF_CFG); cfg.update(over)
    t,p,k=compare.compare(D,cfg,grid.REF_GEOM,1,nrand=10)
    print(name,k); print(t.round(3).to_string(index=False)); print(p.round(3).to_string(index=False))
