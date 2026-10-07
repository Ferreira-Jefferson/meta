import pickle,json,numpy as np
from core_ph import grade
D=pickle.load(open('res_desc.pkl','rb'))[-1];C=pickle.load(open('res_conf.pkl','rb'))[-1];S=pickle.load(open('res_set.pkl','rb'))[-1]
fz=[tuple(x) for x in json.load(open('congeladas.json'))]
def f(r): return 'n %d fill %.2f ac %.3f be %.3f ev %.1f [%.1f,%.1f] dias+ %.2f pior %d atr %.1fmin'%(r['n'],r['fill'],r['acerto'],r['be'],r['ev'],r['lo'],r['hi'],r['dias_pos'],r['worst'],r['atraso']) if r else 'sem trades'
for c in fz:
    print(c)
    for nm,R in (('desc',D),('CONF',C),('set',S)):
        print(' ',nm,'cons',f(R[c][0])); print(' ',nm,'otim ev %.1f ac %.3f n %d'%(R[c][1]['ev'],R[c][1]['acerto'],R[c][1]['n']))
G=grade()
for nm,R in (('desc',D),('conf',C),('set',S)):
    e=[R[c][0]['ev'] for c in G if R[c][0] and R[c][0]['n']>=40]
    eo=[R[c][1]['ev'] for c in G if R[c][1] and R[c][1]['n']>=40]
    print(nm,'grade: n cfg',len(e),'EV medio cons %.1f otim %.1f frac>0 cons %.3f otim %.3f'%(np.mean(e),np.mean(eo),np.mean(np.array(e)>0),np.mean(np.array(eo)>0)))
# tabela d x alvo x stop para janela 0930 M250 K10 prazo5, desc cons e conf
for nm,R in (('desc',D),('conf',C)):
    print('MAPA',nm,'0930 M250 K10 p5 EV cons (linhas d/alvo, colunas stop 150/250/400)')
    for d in (0,50,100):
        for a in (100,150,200,300):
            print(d,a,[round(R[('0930',250,10,d,5,a,s)][0]['ev'],1) if R[('0930',250,10,d,5,a,s)][0] else None for s in (150,250,400)])
# melhores por janela (desc) e como foram na conf
for W in ('0900','0930','1000','NY'):
    cs=[c for c in G if c[0]==W and D[c][0] and D[c][0]['n']>=150]
    cs.sort(key=lambda c:-D[c][0]['ev'])
    print(W,'EV medio desc %.1f conf %.1f'%(np.mean([D[c][0]['ev'] for c in cs]),np.nanmean([C[c][0]['ev'] for c in cs if C[c][0]])),'topo',cs[0],round(D[cs[0]][0]['ev'],1),'->',C[cs[0]][0] and round(C[cs[0]][0]['ev'],1))
# correlacao desc x conf
x=[(D[c][0]['ev'],C[c][0]['ev']) for c in G if D[c][0] and C[c][0] and D[c][0]['n']>=150 and C[c][0]['n']>=40]
x=np.array(x);print('corr desc x conf',np.corrcoef(x.T)[0,1],len(x))
