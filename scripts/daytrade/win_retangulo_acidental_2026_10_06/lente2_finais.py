"""Finalistas congeladas: set + ago (1 vez), toque/atravessa, nulo invertido."""
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd
from lente2_sim import *
import sim
CF={
 "DEFEITO(rodou)": Cfg2(modo_defeito=True),
 "reg0 s4.5L a4.5L (tick certo)": Cfg2(),
 "reg0 sem/sem": Cfg2(stop_frac=None,alvo_frac=None),
 "reg13 sem/sem": Cfg2(stop_frac=None,alvo_frac=None,primeira_entrada=780),
 "F1 reg0 s1.5L a2L": Cfg2(stop_frac=1.5,alvo_frac=2.0),
 "F2 reg0 s3L a2L": Cfg2(stop_frac=3.0,alvo_frac=2.0),
 "F3 reg13 s4.5L a2L": Cfg2(stop_frac=4.5,alvo_frac=2.0,primeira_entrada=780),
 "F4 reg13 s3L a2L": Cfg2(stop_frac=3.0,alvo_frac=2.0,primeira_entrada=780),
}
from dataclasses import replace
def work(a):
    nome,per,var=a
    d=carregar("WINV26",*(SET if per=="set" else AGO)); cf=CF[nome]
    if var=="atravessa": cf=replace(cf,fill="atravessa")
    if var=="nulo": cf=replace(cf,inverte=True)
    t=simula2(d,cf); r=resumo(t,CUSTO)
    return dict(cfg=nome,per=per,var=var,**r)
if __name__=="__main__":
    cells=[(n,p,v) for n in CF for p in ("set","ago") for v in ("toque","atravessa","nulo")]
    print(len(cells),flush=True); rows=[]
    with ProcessPoolExecutor(4) as ex:
        for f in as_completed([ex.submit(work,c) for c in cells]): rows.append(f.result())
    D=pd.DataFrame(rows); D.to_csv("lente2_finais.csv",index=False)
    pd.set_option("display.width",250)
    for v in ("toque","atravessa","nulo"):
        x=D[D["var"]==v]; print("\n",v)
        print(x.pivot(index="cfg",columns="per",values="rs").round(0).reindex(list(CF)).to_string())
    x=D[D["var"]=="toque"].set_index(["cfg","per"])[["trades","win","pf","pior_dia","dd"]].round(1)
    print(x.reindex(pd.MultiIndex.from_product([list(CF),["set","ago"]])).to_string())
