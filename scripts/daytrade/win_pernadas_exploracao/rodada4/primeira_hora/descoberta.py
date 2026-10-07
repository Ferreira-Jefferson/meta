import sys,pickle,numpy as np
from concurrent.futures import ProcessPoolExecutor,as_completed
from core_ph import *
DIAS=None
def init():
    global DIAS;DIAS=carrega()
def job(args):
    seed,ini,fim=args  # seed -1 = real
    dias=DIAS;ld=sorted(k for k in dias if ini<=k<fim)
    if seed>=0: dias=embaralha({k:dias[k] for k in ld},np.random.default_rng(seed))
    rng=np.random.default_rng(7);out={}
    for cfg in grade():
        pdia=config_run(dias,ld,cfg)
        out[cfg]=(resume(pdia,0,rng if seed<0 else None,400 if seed<0 else 0),resume(pdia,1))
    return seed,ini,out
if __name__=='__main__':
    ini,fim,tag=sys.argv[1],sys.argv[2],sys.argv[3]
    seeds=[int(s) for s in sys.argv[4].split(',')]
    res={}
    with ProcessPoolExecutor(4,initializer=init) as ex:
        fs=[ex.submit(job,(s,ini,fim)) for s in seeds]
        for f in as_completed(fs):
            s,_,o=f.result();res[s]=o;print('pronto seed',s,flush=True)
    pickle.dump(res,open(f'res_{tag}.pkl','wb'))
