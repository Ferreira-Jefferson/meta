"""Fase 2: extensoes (BE, tempo, zerar antecipada) sobre bases do platô da fase 1. So setembro."""
import itertools, csv
from concurrent.futures import ProcessPoolExecutor, as_completed
from lente2_sim import *
BASES=[(1.5,2.0),(3.0,2.0),(4.5,2.0),(4.5,3.0)]
EXT=[("nenhuma",{})]+[(f"BE{p}p",dict(be_pts=p)) for p in (100,200,400)]+[(f"BE{x}L",dict(be_frac=x)) for x in (0.5,1.0,1.5)] \
   +[(f"tempo{m}",dict(tempo_min=m)) for m in (30,60,120,180)]+[("zera16h",dict(zerar=16*60)),("zera17h",dict(zerar=17*60))]
_d=None
def work(a):
    global _d
    if _d is None: _d=carregar("WINV26",*SET)
    (sf,af),(en,ek),pe=a
    r=roda(_d,Cfg2(stop_frac=sf,alvo_frac=af,primeira_entrada=pe,**ek)); return dict(reg=pe//60,stop=sf,alvo=af,ext=en,**r)
if __name__=="__main__":
    cells=list(itertools.product(BASES,EXT,[0,13*60])); print(len(cells),flush=True); rows=[]
    with ProcessPoolExecutor(4) as ex:
        for f in as_completed([ex.submit(work,c) for c in cells]): rows.append(f.result())
    import pandas as pd; pd.DataFrame(rows).to_csv("lente2_fase2.csv",index=False); print("ok",flush=True)
