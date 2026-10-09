import sys; sys.path.insert(0,'ciclo3'); sys.path.insert(0,'.')
import ag2_lib as L, numpy as np
vb=L.base70(); v0=L.vec(vb)
ids=[('NG_0.25_1030',),('G1_0.3_0.3_2.0',),('NG_0.25_1030','G1_0.3_0.3_2.0'),('OPV',),('A2F',),('E1',),('E1s',),('CFc',)]
res=L.avalia(ids)
print('base: total',round(v0.sum(),2),'rep',round(L.repond(v0),2),'nd/dia',round(v0[L.EST=='nd'].mean(),2),'dir/dia',round(v0[L.EST=='dir'].mean(),2),'c3',round(v0[L.M3].sum(),2))
for k in ids:
    v=L.vec(res[k]); d=v-v0
    print('==',k,'rep',round(L.repond(v),2),'total',round(v.sum(),1),'06-20',round(v[L.DIAS.index('2025-06-20')],2),'07-11',round(v[L.DIAS.index('2025-07-11')],2))
    for i in np.where(abs(d)>0.5)[0]:
        print('   ',L.DIAS[i],L.CIC[i],L.EST[i],round(d[i],1))
