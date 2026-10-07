"""Fase 1: stop x alvo x regime de entrada, SO setembro (selecao)."""
import itertools, csv, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from lente2_sim import *
STOPS=[("sem",None,None)]+[(f"{x}L",x,None) for x in (0.5,1,1.5,2,3,4.5,6)]+[(f"{p}p",None,p) for p in (200,400,700,1000,1500)]
ALVOS=[("sem",None,None)]+[(f"{x}L",x,None) for x in (0.5,1,2,3,4.5,6,8)]+[(f"{p}p",None,p) for p in (200,400,700,1000,1500)]
REG=[0,13*60,14*60,15*60]
_d=None
def work(a):
    global _d
    if _d is None: _d=carregar("WINV26",*SET)
    (sn,sf,sp),(an,af,ap),pe=a
    cf=Cfg2(stop_frac=sf,stop_pts=sp,alvo_frac=af,alvo_pts=ap,primeira_entrada=pe)
    r=roda(_d,cf); return dict(reg=pe//60,stop=sn,alvo=an,**r)
if __name__=="__main__":
    cells=list(itertools.product(STOPS,ALVOS,REG)); print(len(cells),"celulas",flush=True)
    rows=[]
    with ProcessPoolExecutor(4) as ex:
        fs=[ex.submit(work,c) for c in cells]
        for i,f in enumerate(as_completed(fs)):
            rows.append(f.result())
            if i%50==0: print(i,rows[-1],flush=True)
    with open("lente2_fase1.csv","w",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    print("ok",flush=True)
