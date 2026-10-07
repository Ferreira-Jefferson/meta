from base import *
import pickle
res={}
for name,rule in [("M5","5min"),("M15","15min"),("H1","60min")]:
    r=rs(win,rule); L=[]
    for d in days:
        b=r[r.d==d]
        for k,l in enumerate(zigzag(b)):
            l["d"]=d;l["k"]=k;L.append(l)
    res[name]=pd.DataFrame(L)
    x=res[name]; x["size"]=(x.p1-x.p0).abs()
    print(name,len(x),(x.dir==1).sum(),(x.dir==-1).sum())
    print(" 1a perna dir:",x[x.k==0].dir.value_counts().to_dict())
pickle.dump(res,open("legs.pkl","wb"))
