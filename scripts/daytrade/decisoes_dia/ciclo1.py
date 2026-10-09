import json, sys
from collections import defaultdict
sys.path.insert(0, ".")
import robo, base

fz, nf = robo.carrega_regras()
print(len(fz), "FAZER", len(nf), "NAO_FAZER")
dias0 = json.load(open("dias.json"))["dias"]
res0 = {}
for d in dias0:
    tr, log, _ = robo.roda_robo(d, fz, nf)
    ok = [x for x in tr if x.t_ent]
    res0[d] = dict(brl=round(sum(x.brl for x in ok), 2), ops=len(ok), ef=round(robo.eficiencia(d), 2),
                   trades=[robo.trade_dict(x) for x in ok], log=log)
    print("C0", d, "ef", res0[d]["ef"], "R$", res0[d]["brl"], "ops", len(ok), [x.fonte[:40] + ":" + x.motivo for x in ok], flush=True)
json.dump(res0, open("ciclo0_robo.json", "w"), indent=1, default=str)

sb, sr, efs, nb, nr = robo.sorteia_ciclo1()
print("pool bons", nb, "ruins", nr)
json.dump({"ciclo0": {"dias": dias0, "seed": 20261009}, "ciclo1": {"seed": 20261014,
  "dias": [{"dia": d, "tipo": "bom", "ef": round(efs[d], 3)} for d in sb] + [{"dia": d, "tipo": "ruim", "ef": round(efs[d], 3)} for d in sr]}},
  open("dias_usados.json", "w"), indent=1)
res = {}
fazer_stat = defaultdict(lambda: [0, 0.0, 0]); veto_stat = defaultdict(lambda: dict(agiu=0, bloq=0, brl=0.0, perderia=0, ganharia=0))
for tipo, lst in (("bom", sb), ("ruim", sr)):
    for d in lst:
        tr, log, contra = robo.roda_robo(d, fz, nf)
        ok = [x for x in tr if x.t_ent]
        for x in ok:
            f = fazer_stat[x.fonte]; f[0] += 1; f[1] += x.brl; f[2] += x.brl > 0
        vet_dia = sorted({v for l in log for vs in l["vetos"].values() for v in vs})
        cf = []
        for c in contra:
            r = robo.simula_vetada(d, c)
            cf.append(dict(regra=c["regra"], t=str(c["t"].time()), vetos=c["vetos"], **r))
            for v in c["vetos"]:
                s = veto_stat[v]; s["bloq"] += 1; s["brl"] += r["brl"]
                if r["ops"]: s["perderia" if r["brl"] < 0 else "ganharia"] += 1
        for l in log:
            for vs in l["vetos"].values():
                for v in vs: veto_stat[v]["agiu"] += 1
        res[d] = dict(tipo=tipo, ef=round(efs[d], 3), brl=round(sum(x.brl for x in ok), 2), ops=len(ok),
                      trades=[robo.trade_dict(x) for x in ok], log=log, vetadas=cf, vetos_agiram=vet_dia)
        print(tipo, d, round(efs[d], 2), "R$", res[d]["brl"], "ops", len(ok), "vetadas", len(cf), flush=True)
json.dump(res, open("ciclo1_resultado.json", "w"), indent=1, default=str)
json.dump(dict(fazer={k: v for k, v in fazer_stat.items()}, vetos=dict(veto_stat)), open("ciclo1_stats.json", "w"), indent=1)
neg = {d: dict(brl=r["brl"], tipo=r["tipo"], ef=r["ef"], ops=r["ops"],
               trades=[(t["fonte"], t["lado"], t["motivo"], t["brl"]) for t in r["trades"]], vetos=r["vetos_agiram"]) for d, r in res.items() if r["brl"] < 0}
json.dump(neg, open("ciclo1_negativos.json", "w"), indent=1)
print("NEGATIVOS", list(neg))
