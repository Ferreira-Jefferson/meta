import json, sys
import numpy as np, pandas as pd
R = json.load(open("coleta.json"))
print("total robo v2:", round(sum(r["brl"] for r in R), 2), "ops", sum(r["ops"] for r in R))
for c in (0, 1, 2):
    print(" ciclo", c, round(sum(r["brl"] for r in R if r["ciclo"] == c), 2))
rows = []
for r in R:
    for c in r["cands"]: c["ciclo"] = r["ciclo"]; c["tipo"] = r["tipo"]; rows.append(c)
df = pd.DataFrame(rows)
df["t"] = pd.to_datetime(df["t"])
# dedupe: regra+lado+janela 45 min
df = df.sort_values(["dia", "regra", "lado", "t"]).reset_index(drop=True)
gid = []; g = -1; last = None
for _, x in df.iterrows():
    k = (x.dia, x.regra, x.lado)
    if last is None or k != last[0] or (x.t - last[1]) > pd.Timedelta(minutes=45):
        g += 1; last = [k, x.t]
    gid.append(g)
df["g"] = gid
# grupo exclui se robo entrou com mesma regra+lado na janela
ent = []
for r in R:
    for t in r["trades"]:
        ent.append((r["dia"], t["fonte"], t["lado"], pd.Timestamp(t["t_sinal"])))
def entrou(gr):
    f = gr.iloc[0]
    return any(e[0] == f.dia and e[1] == f.regra and e[2] == f.lado and abs((e[3] - f.t)) <= pd.Timedelta(minutes=45) for e in ent)
first = df.groupby("g").head(1).copy()
first["entrou_mesma"] = first["g"].map(lambda i: entrou(df[df.g == i]))
ops = first[~first.entrou_mesma].copy()
print("candidatas brutas", len(df), "| grupos dedupe", len(first), "| excluidos (robo entrou)", int(first.entrou_mesma.sum()), "| oportunidades", len(ops))
ops.to_json("oportunidades.json", orient="records", date_format="iso")
def tab(d, by):
    t = d.groupby(by).agg(n=("brl", "size"), enchem=("motivo", lambda s: (s != "nao_encheu").sum()),
                          ganh=("brl", lambda s: (s > 0).sum()), perd=("brl", lambda s: (s < 0).sum()),
                          na_mesa=("brl", lambda s: s[s > 0].sum()), evitou=("brl", lambda s: s[s < 0].sum()), liquido=("brl", "sum"))
    return t.round(0)
print(tab(ops, "causa"))
print("TOTAL", round(ops.brl.sum(), 0))
for c in (0, 1, 2):
    print("ciclo", c, round(ops[ops.ciclo == c].brl.sum(), 0), "veto:", round(ops[(ops.ciclo == c) & (ops.causa == "veto")].brl.sum(), 0))
print(tab(ops[ops.causa == "veto"].explode("vetos"), "vetos").sort_values("liquido", ascending=False).head(12))
print(tab(ops, "regra").sort_values("liquido", ascending=False).head(10))
print(tab(ops, ["causa", "lado"]))
# teto por dia
print("\nTETO")
T = pd.DataFrame([dict(dia=r["dia"], tipo=r["tipo"], ciclo=r["ciclo"], robo=r["brl"], ops=r["ops"], teto1=r["teto1"], teto3=r["teto3"], teto_inf=r["teto_inf"],
                        ef=round(r["ef"], 2), rng=round(r["rng_pts"]), n_or=r["n_oracle"],
                        mesa_op=ops[ops.dia == r["dia"]].query("brl>0").brl.sum() if len(ops[ops.dia == r["dia"]]) else 0,
                        melhor=r["melhor"][0] if r["melhor"] else None) for r in R])
T["falta3"] = T.teto3 - T.robo
T["captura3"] = T.robo / T.teto3
print(T.sort_values("falta3", ascending=False).round(2).to_string())
print("soma robo", T.robo.sum().round(0), "teto1", T.teto1.sum().round(0), "teto3", T.teto3.sum().round(0), "inf", T.teto_inf.sum().round(0), "captura3", round(T.robo.sum() / T.teto3.sum(), 3))
print(T.groupby("tipo")[["robo", "teto3"]].sum().round(0))
T.to_json("teto_dias.json", orient="records")
