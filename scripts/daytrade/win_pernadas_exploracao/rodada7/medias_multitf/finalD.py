import pickle, sys, math, numpy as np, pandas as pd
sys.path.insert(0, "C:/Users/Jeffe/Documents/study/meta/scripts/daytrade/win_pernadas_exploracao/rodada4/decisao")
import motor, core
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 500)
A = pickle.load(open('finalA.pkl', 'rb')); X = pickle.load(open('aux.pkl', 'rb'))
rows = []
for rid in ('R1', 'R2', 'R3', 'R6', 'R7', 'R10'):
    for jan, ws in (('desc', (1,)), ('conf+set', (2, 3))):
        rr = np.vstack([A['rows'][(rid, w)] for w in ws])
        if len(rr) == 0: continue
        i = rr[:, 1].astype(int); t = rr[:, -1]
        m = X['m'][i]
        hr = np.where(m < 660, '<11h', np.where(m < 780, '11-13h', '>13h'))
        v2 = X['v2x'][i]; zz = X['zz'][i] * t
        for nm, lab in (('hora', hr), ('v2x', np.where(v2, 'v2x', 'sem v2x')),
                        ('pernada750', np.where(zz > 0, 'a favor', np.where(zz < 0, 'contra', 'sem')))):
            for g in np.unique(lab):
                sub = rr[lab == g]
                s = core.stats_from(sub)
                rows.append(dict(regra=rid, janela=jan, filtro=nm, grupo=g, n=s['n'], acerto=round(s['win'], 3) if s['n'] else np.nan,
                                 be=round(s['be'], 3) if s['n'] else np.nan, esp=round(s['mean'], 1) if s['n'] else np.nan))
F = pd.DataFrame(rows); F.to_pickle('filtros.pkl'); print(F.to_string(index=False))
# ruina / mao a partir de R$250
print('\nRUINA/MAO R$250')
out = []
for rid in [f"R{i}" for i in range(1, 11)]:
    for jan, ws in (('desc', (1,)), ('conf+set', (2, 3))):
        rr = np.vstack([A['rows'][(rid, w)] for w in ws]); p = rr[:, 2]
        res = p * motor.VALOR_PONTO
        S = rr[:, 4].mean(); T = rr[:, 5].mean()
        win = (p > 0).mean(); gw = p[p > 0].mean(); gl = -p[p <= 0].mean()
        be = gl / (gw + gl)
        # mao: p encolhido para a base (BE) com n0=100
        pe = motor.p_encolhido(int((p > 0).sum()), len(p), be)
        mao = motor.tamanho(pe, gw, gl, 250.0)
        mc = motor.ruina_mc(res, None, 250.0, 215, 3000) if p.mean() > 0 else dict(p_ruina=1.0, t_mediano=float('nan'))
        out.append(dict(regra=rid, janela=jan, n=len(p), esp_pts=round(p.mean(), 1), esp_R=round(p.mean() * 0.2, 2), S_med=round(S), perda_R=round(gl * 0.2, 1),
                        p_encolhido=round(pe, 3), mao=mao, ruina_215ops=round(mc['p_ruina'], 3), seq_perdas=core.stats_from(rr)['maxloss']))
O = pd.DataFrame(out); print(O.to_string(index=False)); O.to_pickle('ruina.pkl')
