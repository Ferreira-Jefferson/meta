import sys; sys.path.insert(0,'ciclo3'); sys.path.insert(0,'.')
import ag2_lib as L, robo, base, pandas as pd
def simula_sinal(dia, t_alvo, s, g):
    usada=[]
    def decide(ctx):
        if ctx.t==t_alvo and not usada:
            usada.append(1); return s, dict(entrou='x'), g
        return None,None,None
    tr,_=robo._roda(dia,decide,max_ops=1)
    ok=[x for x in tr if x.t_ent is not None]
    return (round(ok[0].brl,1),ok[0].motivo,str(ok[0].t_sai.time())) if ok else (0,'nao_encheu','')
for dia in sys.argv[1:]:
    cfg=L.base_v3()
    print('=====',dia)
    for t,ctx in base.contextos(dia):
        sins=[]
        for n,r,g in cfg.fz+cfg.prio:
            s=robo._chama(r,ctx)
            if s and 'erro' not in s: sins.append((n,s,g))
        if not sins: continue
        vet={'compra':[],'venda':[]}
        for n,r,g in cfg.nf:
            s=robo._chama(r,ctx)
            if s and 'erro' not in s and s.get('lado') in vet: vet[s['lado']].append(n)
        for n,s,g in sins:
            if robo._agressiva(s,ctx): res='agressiva'
            else: res=simula_sinal(dia,ctx.t,s,g)
            print(t.time(),n[:55],s['lado'],'| vetos:',[v[:40] for v in vet[s['lado']]],'| isolada:',res)
