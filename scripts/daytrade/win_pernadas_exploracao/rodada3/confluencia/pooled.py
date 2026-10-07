import pickle, numpy as np, an
cfg,res=pickle.load(open("desc.pkl","rb"))
def pool(group, N, D, periods=(0,1)):
    keys=[k for k in res["obs"] if k[1]==N and k[2]==D and (group is None or k[0] in group)]
    def tot(x):  # soma sobre familias
        return sum(x[k][list(periods)].sum(0) for k in keys)
    So=tot(res["obs"]); n=So[:,0]
    ro=So[:,1:].sum(0)/n.sum()
    sh=an.reweighted([tot(x) for x in res["shift"]], n); su=an.reweighted([tot(x) for x in res["shuf"]], n)
    mu,sd=np.nanmean(sh,0),np.nanstd(sh,0); ms,ss=np.nanmean(su,0),np.nanstd(su,0)
    return int(n.sum()), ro, mu, (ro-mu)/sd, (ro-ms)/ss
for N in (100,200):
  for D in (300,600):
    for p in ((0,),(1,),(0,1)):
        n,ro,mu,z,zs=pool(None,N,D,p)
        print(f"todas N{N} D{D} per{p} nEv={n} B250 {ro[1]:.3f} nulo {mu[1]:.3f} z {z[1]:+.1f} zshuf {zs[1]:+.1f} | S250 {ro[4]:.3f}/{mu[4]:.3f} | PL {ro[6]:.3f}/{mu[6]:.3f} z{z[6]:+.1f}")
