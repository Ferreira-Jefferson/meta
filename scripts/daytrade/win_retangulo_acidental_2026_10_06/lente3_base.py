import inspect, sys
sys.path.insert(0, '.')
import numpy as np, pandas as pd
import sim
from sim import Cfg
src = inspect.getsource(sim.simula_dia)
src = src.replace('pend = dict(lado=lado, lim=lim, stop=stop, alvo=alvo, esp=0)', 'pend = dict(lado=lado, lim=lim, stop=stop, alvo=alvo, esp=0, larg=larg, meio=meio)')
src = src.replace('t_ent=ts[b])\n                pend = None', 't_ent=ts[b], larg=pend["larg"], meio=pend["meio"])\n                pend = None')
src = src.replace('ent=pos["ent"], sai=preco, saida=tipo, pts=pts))', 'ent=pos["ent"], sai=preco, saida=tipo, pts=pts, larg=pos["larg"], meio=pos["meio"]))')
ns = dict(sim.__dict__); exec(src, ns); simula_dia = ns['simula_dia']
D = sim.carregar('WINV26', '2026-08-12', '2026-10-02')
CUSTO = 2.0
def run(cfg):
    ops = []
    for _, g in D.groupby(D.index.date):
        ops += simula_dia(g, cfg)
    t = pd.DataFrame(ops)
    t['rs'] = t.pts * 0.2 - CUSTO
    t['mes'] = pd.to_datetime(t.dia).dt.month
    return t
