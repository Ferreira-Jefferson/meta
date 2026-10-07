import pickle, numpy as np
B=pickle.load(open('finalB.pkl','rb'))
tot=diff=0; tn=0
for k,v in B.items():
    if k[3]!='m1': continue
    t=B[(k[0],k[1],k[2],'tk')]
    tn+=len(v)
    if len(v)==len(t):
        d=(np.abs(v[:,2]-t[:,2])>1e-9).sum(); diff+=d; tot+=len(v)
    else: print('len diff',k,len(v),len(t))
print(tot,diff,tn)
