import pickle,numpy as np,sys
real,nulls=pickle.load(open("res.pkl","rb"))
pat=sys.argv[1]
for k,(v,n) in real.items():
    if not all(s in k for s in pat.split("&")): continue
    xs=np.array([nl[k][0] for nl in nulls if k in nl and not np.isnan(nl[k][0])])
    ns=np.mean([nl[k][1] for nl in nulls if k in nl])
    if len(xs)==0: continue
    z=(v-xs.mean())/(xs.std()+1e-9); pc=(xs>=v).mean()
    print(f"{k:75s} real={v:8.3f} n={n:4d} | nulo={xs.mean():8.3f} [{np.percentile(xs,5):7.3f},{np.percentile(xs,95):7.3f}] n={ns:5.0f} z={z:5.1f} P(nulo>=real)={pc:.2f}")
