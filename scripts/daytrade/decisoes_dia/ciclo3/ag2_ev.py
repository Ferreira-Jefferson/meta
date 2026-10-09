import sys; sys.path.insert(0,'ciclo3'); sys.path.insert(0,'.')
import ag2_lib as L, base, numpy as np
res=L.avalia([('E1',),('E1s',),('G1',),('CFc',)])
vb=L.base70()
for key,tag in (('E1','c3:E1'),('G1','G1'),('CFc','')):
    print('==',key)
    for d in L.DIAS:
        r=res[(key,)][d]; b=vb[d]
        if abs(r['brl']-b['brl'])>0.5:
            print(d, L.EF[d].__round__(2), L.EST[L.DIAS.index(d)], 'base',b['brl'],'->',r['brl'], [(t['fonte'][:30],t['lado'],t['sinal'],t['motivo'],t['brl']) for t in r['trades']])
