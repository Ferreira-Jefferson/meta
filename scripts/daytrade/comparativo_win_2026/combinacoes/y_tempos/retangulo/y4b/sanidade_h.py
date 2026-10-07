import sys
from pathlib import Path
AQUI=Path(__file__).resolve().parent; BASE=AQUI.parents[3]
sys.path.insert(0,str(BASE)); sys.path.insert(0,str(AQUI))
import port_ret_tf_v2 as P, dados
tf=int(sys.argv[1])
c=dict(chamadas=0, ret=0)
orig=P.Ea._detecta
def d(self):
    c['chamadas']+=1; a=self.tem_ret; orig(self); c['ret']+= (self.tem_ret and not a)
P.Ea._detecta=d
ea=P.roda(verbose=False,tf=tf,limite_equity=-1e18,ajustes=True)
print(tf,"2026 chamadas detector",c['chamadas'],"retangulos formados",c['ret'],"ops",len(ea.trades),ea.stats,flush=True)
