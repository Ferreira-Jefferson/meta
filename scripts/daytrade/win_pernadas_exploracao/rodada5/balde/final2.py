import sys, json, pickle; sys.path.insert(0,'.')
from agg import *
from balde_core import PARES,TRIGS,DIRS
r=carrega(); names=r['names']; months=r['months']
F=r[False]['F']; Fo=r[True]['F']
W={w:wmask(months,w) for w in ('desc','conf','ref')}
nu=pickle.load(open('nulo_res.pkl','rb'))['res']
fr=json.load(open('congelado_ANTES_da_confirmacao.json'))['cells']
key2i={(str(n[0]),n[1],n[2]):i for i,n in enumerate(names)}
nF=696
rows=[]
for c in fr:
    i=key2i[(c['key'],c['trig'],c['dir'])]
    row=dict(cel=f"{c['key']} {c['trig']} {c['dir']}")
    for w in ('desc','conf','ref'):
        m=metricas(F,W[w]); mo=metricas(Fo,W[w])
        ci=boot_ci(F,months,w,i)
        mp,nm=meses_pos(F,months,w,i)
        pl=1-m['win'][i]
        sp=streak_p95(pl,max(m['nf'][i],1)) if m['nf'][i]>0 else np.nan
        z=np.nan
        if i<nF:
            x=nu[w]['mean'][:,i]; z=(m['mean'][i]-np.nanmean(x))/np.nanstd(x,ddof=1)
        row[w]=dict(n=int(m['nf'][i]),ops_dia=m['opsdia'][i],win=m['win'][i],be=m['be'][i],mean=m['mean'][i],lo=ci[0],hi=ci[1],t=m['t'][i],
                    streak=m['streak'][i],streak_p95=sp,mp=mp,nmes=nm,mean_otim=mo['mean'][i],win_otim=mo['win'][i],z_nulo=z,sumpts=m['sumpts'][i])
    rows.append(row)
pickle.dump(rows,open('conf_rows.pkl','wb'))
for row in rows:
    print(row['cel'])
    for w in ('desc','conf','ref'):
        d=row[w]; print('  ',w,{k:(round(v,3) if isinstance(v,float) else v) for k,v in d.items()})
