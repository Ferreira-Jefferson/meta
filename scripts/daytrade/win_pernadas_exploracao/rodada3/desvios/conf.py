from lib import *
fz=pd.read_csv("congelada.csv"); volmed={int(k):v for k,v in json.load(open("volmed.json")).items()}
days=load("2026.07.01","2026.08.31")
ev=events(days,volmed); print("eventos",len(ev),"dias",ev.dia.nunique())
ev.to_pickle("ev_conf.pkl")
base=basecols(ev); dayidx=pd.factorize(ev.dia)[0]; nd=dayidx.max()+1
rng=np.random.default_rng(2); W=np.stack([np.bincount(rng.integers(0,nd,nd),minlength=nd) for _ in range(2000)]).astype(float)
rows=[]
for _,f in fz.iterrows():
    m=np.ones(len(ev),bool)
    for part in f.cell.split(" & "):
        d,v=part.split("=",1); m&=(ev[d]==v).values
    y=ev[f.out].values; b=base[f.out].values; ok=m&~np.isnan(y); n=int(ok.sum())
    if n<30: rows.append(dict(cell=f.cell,out=f.out,n=n)); continue
    dx=np.bincount(dayidx[ok],weights=y[ok],minlength=nd); db=np.bincount(dayidx[ok],weights=b[ok],minlength=nd); dn=np.bincount(dayidx[ok],minlength=nd)
    dd=(W@dx-W@db)/(W@dn)
    rows.append(dict(cell=f.cell,out=f.out,n_desc=f.n,desc_p=f.p,desc_base=f.base,n=n,dias=int((dn>0).sum()),conf_p=y[ok].mean(),conf_base=b[ok].mean(),diff=y[ok].mean()-b[ok].mean(),lo=np.nanpercentile(dd,2.5),hi=np.nanpercentile(dd,97.5),desc_diff=f["diff"]))
r=pd.DataFrame(rows)
r["confirma"]=(np.sign(r["diff"])==np.sign(r.desc_diff))&(r.lo*r.hi>0)&(r["diff"].abs()>=0.05)
r.to_csv("confirmacao.csv",index=False)
print(r.round(3).to_string())
