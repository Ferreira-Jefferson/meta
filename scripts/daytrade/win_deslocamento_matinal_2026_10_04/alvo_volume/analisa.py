import json, sys
from pathlib import Path
import pandas as pd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_alvo_volume import metr

s = json.load(open(HERE / "saida_simples.json"))
j = json.load(open(HERE / "saida_juntas.json"))
esc = json.load(open(HERE / "escolhidas.json"))
allt = {**s, **j}
rows = []
for k, t in allt.items():
    cid, jan = k.split("|")
    ref = s[f"REF|{jan}"]
    m = metr(t, ref)
    m.update(cel=cid, jan=jan)
    rows.append(m)
df = pd.DataFrame(rows)
df.to_csv(HERE / "resultado.csv", index=False, sep=";", decimal=",")
cols = ["cel", "n", "liq", "cap_final", "r_op", "acerto", "ganho", "perda", "payoff", "stop", "alvo", "volume", "fim_dia",
        "maxdd", "maxdd_pct", "fr", "alt_n", "alt_rs"]
for jan in ("IS", "OOS"):
    d = df[df.jan == jan][cols]
    print(f"\n## {jan}\n|" + "|".join(cols) + "|")
    print("|" + "|".join("---" for _ in cols) + "|")
    for _, r in d.iterrows():
        print("|" + "|".join(r[c] if isinstance(r[c], str) else (f"{r[c]:.2f}" if c in ("payoff", "fr") else f"{r[c]:.0f}" if c not in ("r_op", "acerto", "maxdd_pct") else f"{r[c]:.1f}") for c in cols) + "|")
print("\n## por ano")
for cid in ["REF"] + esc["alvo"] + esc["volume"] + esc["comb"]:
    for jan in ("IS", "OOS"):
        print(cid, jan, df[(df.cel == cid) & (df.jan == jan)].anos.iloc[0])
print(esc)
