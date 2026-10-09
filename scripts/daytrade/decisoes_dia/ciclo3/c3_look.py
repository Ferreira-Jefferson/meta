import sys; sys.path.insert(0,'ciclo3'); sys.path.insert(0,'.')
import cfg3, base, robo_v3, pandas as pd
for dia in sys.argv[1:]:
    cfg=robo_v3.monta_v3()
    tr,log=cfg3.roda(dia,cfg)
    print("=====",dia)
    for x in tr:
        if x.t_ent is not None: print(x.fonte[:50],x.lado,x.t_sinal.time(),x.t_ent.time(),x.t_sai.time(),x.preco,x.stop_ini,x.alvo,x.preco_sai,x.motivo,round(x.brl,2))
    for l in log: print(l)
    m1=base.carrega(dia,0); m1=m1[m1.index.normalize()==pd.Timestamp(dia)]
    m=base._m15(m1)
    print(m[['open','high','low','close','vol']].astype(int).to_string())
