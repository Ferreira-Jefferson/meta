import pickle,numpy as np
real,nulls=pickle.load(open("res.pkl","rb"))
tot=0;hit=[]
for k,(v,n) in real.items():
    xs=np.array([nl[k][0] for nl in nulls if k in nl and not np.isnan(nl[k][0])])
    if n<20 or len(xs)<50 or xs.std()<1e-9: continue
    tot+=1; z=(v-xs.mean())/xs.std()
    if abs(z)>=2: hit.append((k,round(z,1)))
print(tot,len(hit))
for h in hit: print(h)
