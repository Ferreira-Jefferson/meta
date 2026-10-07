import pandas as pd, numpy as np, core
raw=core.load_raw()
for day in ['2026.03.02','2026.05.12','2026.06.30']:
    tk=pd.read_pickle(f"C:/Users/Jeffe/Documents/study/meta/data/cache_win_ticks/WIN@D/{day.replace('.','-')}.pkl")
    tk=tk[tk['last']>0]
    t=pd.to_datetime(tk.time_msc,unit='ms')
    print(day,len(tk),t.iloc[0],t.iloc[-1])
    for off in (0,3):
        tm=t-pd.Timedelta(hours=off)
        mn=(tm.dt.hour*60+tm.dt.minute).values
        g=tk.groupby(mn)['last'].agg(['first','max','min','last'])
        r=raw[raw.DATE==day].set_index('m')
        j=g.join(r,how='inner')
        print(' off',off,len(j),'close diff',(j['last']-j.CLOSE).describe()[['mean','std','min','max']].round(1).tolist(),'high diff',(j['max']-j.HIGH).abs().mean().round(1))
