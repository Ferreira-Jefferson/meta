import pickle, numpy as np, an, sys
cfg,res=pickle.load(open("desc.pkl","rb"))
rows=an.summarize(res["obs"],res["shift"],res["shuf"])
# base global: eventos de queda sem barreira = media do nulo shift
import itertools
print("n configs", len(rows))
rows=[r for r in rows if r["n"]>=60]
rows.sort(key=lambda r:-abs(r["z"][1]))
print("fam N D n | B250 obs nulo_shift nulo_shuf | z_shift z_shuf | meia1 meia2 | B150 B400 PL obs/nulo | z(B150,B400,PL)")
for r in rows[:40]:
    f,N,D=r["key"]
    print(f"{f:12s} {N} {D} {r['n']:4d} | {r['ro'][1]:.3f} {r['mu'][1]:.3f} {r['mus'][1]:.3f} | {r['z'][1]:+.1f} {r['zs'][1]:+.1f} | {r['halves'][0]:+.3f} {r['halves'][1]:+.3f} | {r['ro'][0]:.3f}/{r['mu'][0]:.3f} {r['ro'][2]:.3f}/{r['mu'][2]:.3f} {r['ro'][6]:.3f}/{r['mu'][6]:.3f} | {r['z'][0]:+.1f} {r['z'][2]:+.1f} {r['z'][6]:+.1f}")
import collections
zs=np.array([r["z"][1] for r in rows]); print("N>=60 configs",len(zs),"|z|>2:",(abs(zs)>2).sum(),"|z|>3:",(abs(zs)>3).sum(), "esperado |z|>2 por acaso ~",round(.0455*len(zs),1))
print("base (media do nulo shift, B250):", np.mean([r["mu"][1] for r in rows]).round(3))
