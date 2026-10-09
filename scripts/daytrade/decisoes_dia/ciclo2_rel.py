import json
J = json.load(open("ciclo2_resultado.json")); R = J["res"]
def tot(dias, v): return round(sum(R[d][v]["brl"] for d in dias), 2)
def stats(dias, v):
    t = [x for d in dias for x in R[d][v]["trades"]]
    g = sum(x["brl"] for x in t if x["brl"] > 0); p = -sum(x["brl"] for x in t if x["brl"] < 0)
    return dict(brl=tot(dias, v), ops=len(t), acerto=f'{sum(x["brl"]>0 for x in t)}/{len(t)}', fp=round(g/p, 2) if p else "inf",
                pior=min(R[d][v]["brl"] for d in dias), neg=sum(R[d][v]["brl"] < 0 for d in dias))
print("== 30 dias usados ==")
vel = J["velhos"]
for d in vel: print(d, J["tipo_velho"].get(d, "c0"), *[f'{R[d][v]["brl"]:9.2f}({R[d][v]["ops"]})' for v in ("v1","v2","v2e")])
for v in ("v1","v2","v2e"): print(v, stats(vel, v))
print("== 20 novos ==")
nov = [d for d,_,_ in J["novos"]]
for d,t,e in J["novos"]:
    r = R[d]; print(d, t, e, *[f'{r[v]["brl"]:9.2f}({r[v]["ops"]})' for v in ("v1","v2","v2e")],
      "| v2 regras:", [x["fonte"].split(":",1)[1][:28]+("/"+x["lado"][0]+"/"+x["motivo"]+"/"+str(x["brl"])) for x in r["v2"]["trades"]], "| vetos:", [v.split(":",1)[1][:30] for v in r["v2"]["vetos"]])
for tp in ("bom","ruim",None):
    ds = [d for d,t,_ in J["novos"] if tp is None or t==tp]
    for v in ("v1","v2","v2e"): print(tp or "todos", v, stats(ds, v))
print("== vetadas v2 nos 20 novos ==")
for v in ("v2","v2e"):
    cf = [c for d in nov for c in R[d][v]["vetadas"]]; en = [c for c in cf if c["ops"]]
    print(v, "vetadas", len(cf), "enchidas", len(en), "soma R$", round(sum(c["brl"] for c in cf),2), "perderiam", sum(c["brl"]<0 for c in en), "ganhariam", sum(c["brl"]>0 for c in en))
print("== negativos v2 ==")
for d in nov+vel:
    if R[d]["v2"]["brl"] < 0: print(d, "novo" if d in nov else "usado", R[d]["v2"]["brl"], [(x["fonte"][:40],x["lado"],x["motivo"],x["brl"]) for x in R[d]["v2"]["trades"]], R[d]["v2"]["vetos"])
