"""v3 x v4 nos 70 dias (dias_usados.json) e caixa real (R$2.000; contratos=min(2, floor(caixa/1000)) fixos no dia; ordem cronologica; pára < R$1.000)."""
import sys, json
sys.path.insert(0, '.'); sys.path.insert(0, '../ciclo3')
import numpy as np
import ev4, cfg4
sys.path.insert(0, str(cfg4.RAIZ))
import robo_v4
from p4_validacao import caixa

if __name__ == "__main__":
    res = ev4.avalia([(), tuple(robo_v4.IDS)])
    R3, R4 = res[()], res[cfg4.chave(robo_v4.IDS)]
    v3, v4 = ev4.vec(R3), ev4.vec(R4)
    out = {}
    for nome, v in (("v3", v3), ("v4", v4)):
        tr = [t for d in ev4.DIAS for t in (R3 if nome == "v3" else R4)[d]["trades"]]
        out[nome] = dict(total=float(v.sum()), rep=float(ev4.repond(v)), dir_dia=float(v[ev4.EST == "dir"].mean()), nd_dia=float(v[ev4.EST == "nd"].mean()),
                         pior_dia=float(v.min()), pior_dia_data=ev4.DIAS[int(v.argmin())], c012=float(v[ev4.M012].sum()), c3=float(v[ev4.M3].sum()),
                         ops=len(tr), acerto=round(100 * sum(t["pts"] > 0 for t in tr) / len(tr), 1), dias_neg=int((v < 0).sum()), dias_pos=int((v > 0).sum()))
        c = caixa(R3 if nome == "v3" else R4, ev4.DIAS)
        out[nome]["caixa"] = {k: c[k] for k in ("final", "minimo", "parou")}
        # risco maximo do dia (% do caixa) = ultimo campo de hist
        out[nome]["risco_max_pct"] = max((h[4] for h in c["hist"] if len(h) > 4), default=None)
    out["delta"] = ev4.linha(v4, v3)
    out["delta"]["dias_piores"] = [(ev4.DIAS[i], round(float(v4[i] - v3[i]), 1)) for i in np.where(v4 - v3 < -0.5)[0]]
    out["delta"]["dias_melhores"] = [(ev4.DIAS[i], round(float(v4[i] - v3[i]), 1)) for i in np.where(v4 - v3 > 0.5)[0]]
    print(json.dumps(out, indent=1, default=str), flush=True)
    json.dump(out, open("p_v4_70.json", "w"), indent=1, default=str)
