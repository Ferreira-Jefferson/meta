import pickle, json, os, numpy as np
import detail as D
from detail import *
HERE = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, "C:/Users/Jeffe/Documents/study/meta/scripts/daytrade/win_pernadas_exploracao/rodada4/decisao")
import motor
fr = json.load(open(os.path.join(HERE, "congelado_ANTES_da_confirmacao.json")))["celulas"]
R = pickle.load(open(os.path.join(HERE, "avalia.pkl"), "rb"))
def streak_p95(p_loss, n, sims=2000, seed=3):
    rng = np.random.default_rng(seed); out = []
    for _ in range(sims):
        l = rng.random(n) < p_loss; mx = cur = 0
        for x in l:
            cur = cur + 1 if x else 0; mx = max(mx, cur)
        out.append(mx)
    return int(np.percentile(out, 95))
caps = [250, 500, 1000, 2000, 3000, 5000, 7500, 10000, 15000, 20000, 30000, 50000, 100000]
print("| # | celula | esperanca conf (pts/op) | contratos a R$250 | p_est (encolhido) | ruina R$250 (1 ano) | p95 seq perdas | capital p/ ruina<=5% | R$/op (1 ctr) |")
print("|" + "---|" * 9)
for i, c in enumerate(fr):
    s, tr = R[("conf", i, 0)]
    pn = tr["pnl"]; n = len(pn)
    res = pn * 0.2
    k = int((pn > 0).sum()); p0 = s["p0"]
    pe = motor.p_encolhido(k, n, p0)
    gm = pn[pn > 0].mean() if k else 0; lm = -pn[pn < 0].mean()
    nc = motor.tamanho(pe, gm, lm, 250.0) if s["mean"] > 0 else 0
    nops = max(int(s["opd"] * 250), 20)
    r250 = motor.ruina_mc(res, None, 250.0, nops, n_caminhos=3000, seed=1)["p_ruina"]
    sp = streak_p95(1 - k / n, nops)
    cap = "-"
    if s["mean"] > 0:
        ok = [x for x in caps if motor.ruina_mc(res, None, x, nops, n_caminhos=2000, seed=2)["p_ruina"] <= 0.05]
        cap = str(ok[0]) if ok else ">100000"
    print(f"| {i+1} | T{c['T']} {c['geom']} / {c['filtro']} | {s['mean']:.1f} | {nc} | {pe*100:.1f}% | {r250*100:.0f}% | {sp} | {cap} | {res.mean():.2f} |".replace(".", ","), flush=True)
