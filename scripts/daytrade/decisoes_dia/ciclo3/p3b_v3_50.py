import sys; sys.path.insert(0,'.')
import numpy as np
import av, cfg3, an
res = av.avalia([[],["C8","C7","C6","C4"]], an.DIAS)
vb = an.vec(res[()]); v = an.vec(res[("C4","C6","C7","C8")] if ("C4","C6","C7","C8") in res else res[tuple(sorted(["C8","C7","C6","C4"], key=cfg3.ORDEM.index))])
l = an.linha(v, vb)
print({k:(round(x,2) if not isinstance(x,(tuple,str,int)) else x) for k,x in l.items()})
print("rep v2", round(an.repond(vb),2), "v3", round(an.repond(v),2), "rep3 v2", round(an.repond3(vb),2), "v3", round(an.repond3(v),2))
for e in ("bom","int","ruim"):
    m = an.EST3==e; print(e, m.sum(), "v2", round(vb[m].mean(),2), "v3", round(v[m].mean(),2), "tot", round(vb[m].sum(),1), round(v[m].sum(),1))
for c in ("c0","c1","c2"):
    m = an.CIC==c; print(c, round(vb[m].sum(),1), round(v[m].sum(),1))
ds=[]
for i in range(50):
    m=np.ones(50,bool); m[i]=False; ds.append(an.repond(v,m)-an.repond(vb,m))
print("LODO d_rep min/max", round(min(ds),2), round(max(ds),2), "todos>0:", all(x>0 for x in ds))
dd = v-vb
idx = np.argsort(dd)
print("dias mais mudaram:", [(an.DIAS[i], round(dd[i],1)) for i in list(idx[:3])+list(idx[-6:])])
print("dias com mudanca:", int((np.abs(dd)>0.5).sum()))
