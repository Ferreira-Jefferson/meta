"""Extras: v4 por estrato separando dias de escolha (c0-c2, 50) e aleatorios (c3+c4, 40); hora dos trades; perda por hora em rotacao; fontes nos 40 aleatorios."""
import sys, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import *
res = json.load(open(ER / "v4_90.json"))
v = np.array([res[d]["brl"] for d in DIAS])
print("grupo | estrato | dias | R$/dia | negativos | total")
for g, m in (("50 escolha", ~M40), ("40 aleatorios", M40)):
    for e in ("rot", "int", "dir"):
        k = m & (EST3 == e)
        if k.any(): print(f"{g} | {e} | {k.sum()} | {v[k].mean():+.1f} | {(v[k]<0).sum()} | {v[k].sum():+.0f}")
print("\ntrades em dia rotacao, por hora do sinal (tudo 90 | so 40 aleatorios): n, R$, R$/trade")
rows = []
for d, e, m in zip(DIAS, EST3, M40):
    for t in res[d]["trades"]: rows.append(dict(d=d, est=e, m40=m, h=int(t["sinal"][:2]), brl=t["brl"], fonte=t["fonte"], mot=t["motivo"], lado=t["lado"]))
df = pd.DataFrame(rows)
for nome, sub in (("90", df[df.est == "rot"]), ("40", df[(df.est == "rot") & df.m40])):
    g = sub.groupby("h").brl.agg(["count", "sum", "mean"]); print(nome); print(g.round(1).to_string())
print("\nrotacao, motivo de saida (90):"); print(df[df.est == "rot"].groupby("mot").brl.agg(["count", "sum", "mean"]).round(1).to_string())
print("\nrot nos 40 aleatorios por fonte:"); print(df[(df.est == "rot") & df.m40].groupby("fonte").brl.agg(["count", "sum", "mean"]).round(1).to_string())
print("\nfora de rot nos 40 aleatorios por fonte:"); print(df[(df.est != "rot") & df.m40].groupby("fonte").brl.agg(["count", "sum", "mean"]).round(1).to_string())
print("\ncontratos usados:", pd.Series([t["contratos"] for d in DIAS for t in res[d]["trades"]]).value_counts().to_dict())
