import json, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
sys.path.insert(0, ".")
import robo, robo_v2, base

SEED = 20261015


def um(args):
    dia, var = args
    fz1, nf1 = robo.carrega_regras()
    if var == "v1": tr, log, contra = robo.roda_robo(dia, fz1, nf1)
    else:
        fz, nf = robo_v2.monta_v2()
        tr, log, contra = robo_v2.roda_v2(dia, fz, nf, estrutural=(var == "v2e"))
    ok = [x for x in tr if x.t_ent]
    cf = []
    if var != "v1" or True:
        for c in contra:
            r = robo.simula_vetada(dia, c)
            cf.append(dict(regra=c["regra"], t=str(c["t"].time()), lado=c["s"]["lado"], vetos=c["vetos"], **r))
    return dia, var, dict(brl=round(sum(x.brl for x in ok), 2), ops=len(ok), trades=[robo.trade_dict(x) for x in ok],
                          vetadas=cf, vetos=sorted({v for c in cf for v in c["vetos"]}))


def main():
    du = json.load(open("dias_usados.json"))
    velhos = list(du["ciclo0"]["dias"]) + [x["dia"] for x in du["ciclo1"]["dias"]]
    tipo_velho = {x["dia"]: x["tipo"] for x in du["ciclo1"]["dias"]}
    # sorteio
    m1 = base.m1_tudo(); import pandas as pd
    dias = pd.Series(m1.index.normalize().unique()); dias = dias[(dias >= "2022-03-01") & (dias <= "2025-09-30")]
    efs = {}
    for d in dias:
        s = str(d.date())
        if s in velhos: continue
        if (m1.index.normalize() == d).sum() < 300: continue
        efs[s] = robo.eficiencia(s)
    lim = 0.25
    while sum(e >= lim for e in efs.values()) < 10: lim -= 0.01
    bons = sorted(d for d, e in efs.items() if e >= lim); ruins = sorted(d for d, e in efs.items() if e < 0.15)
    print("limiar bom", round(lim, 2), "pool bons", len(bons), "ruins", len(ruins), "| >=0.30:", sum(e >= .30 for e in efs.values()), "0.25-0.30:", sum(.25 <= e < .30 for e in efs.values()), flush=True)
    rng = np.random.default_rng(SEED)
    sb = sorted(rng.choice(bons, 10, replace=False).tolist()); sr = sorted(rng.choice(ruins, 10, replace=False).tolist())
    novos = [(d, "bom", round(efs[d], 3)) for d in sb] + [(d, "ruim", round(efs[d], 3)) for d in sr]
    du["ciclo2"] = dict(seed=SEED, limiar_bom=round(lim, 2), limiar_ruim=0.15, sobram_bons=len(bons) - 10, sobram_ruins=len(ruins) - 10,
                        dias=[dict(dia=d, tipo=t, ef=e) for d, t, e in novos])
    json.dump(du, open("dias_usados.json", "w"), indent=1)
    alvo = [(d, tipo_velho.get(d, "c0")) for d in velhos] + [(d, t) for d, t, _ in novos]
    res = {}
    with ProcessPoolExecutor(6) as ex:
        fut = [ex.submit(um, (d, v)) for d, _ in alvo for v in ("v1", "v2", "v2e")]
        for f in as_completed(fut):
            d, v, r = f.result(); res.setdefault(d, {})[v] = r
            print(d, v, r["brl"], r["ops"], flush=True)
    json.dump(dict(novos=novos, velhos=velhos, tipo_velho=tipo_velho, res=res), open("ciclo2_resultado.json", "w"), indent=1, default=str)

if __name__ == "__main__":
    main()
