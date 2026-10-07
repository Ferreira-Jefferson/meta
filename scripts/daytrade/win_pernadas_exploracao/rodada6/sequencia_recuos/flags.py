"""flags.py <per> : cruza as celulas das 9 configs; lista as que destoam do nulo (|z|>=2,5 em alguma) e a consistencia entre escalas."""
import sys, glob, re
import numpy as np, pandas as pd

per = sys.argv[1]
fs = sorted(glob.glob(f"out_txt/cells_{per}_*.csv"))
dd = []
for f in fs:
    m = re.search(r"_(\d+)_(\d+)\.csv", f)
    d = pd.read_csv(f); d["T"] = int(m.group(1)); d["div"] = int(m.group(2)); dd.append(d)
d = pd.concat(dd)
d["cfg"] = "T" + d["T"].astype(str) + "/m" + (d["T"] / d["div"]).astype(int).astype(str)
d["id"] = d.tabela + " | " + d.chave.astype(str)
print("celulas totais (n>=minn):", len(d), " |z|>2:", int((d.z.abs() > 2).sum()), " |z|>3:", int((d.z.abs() > 3).sum()))
print("esperado por acaso (normal, independente): |z|>2:", round(len(d) * 0.0455), " |z|>3:", round(len(d) * 0.0027))
# por config
print(d.groupby("cfg").apply(lambda g: pd.Series({"cel": len(g), "z2": int((g.z.abs() > 2).sum()), "z3": int((g.z.abs() > 3).sum())})))
pv = d.pivot_table(index="id", columns="cfg", values="z")
pv["n_cfg"] = pv.notna().sum(axis=1)
pv["n_pos2"] = (pv.drop(columns="n_cfg") > 2).sum(axis=1)
pv["n_neg2"] = (pv.drop(columns="n_cfg") < -2).sum(axis=1)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500); pd.set_option("display.max_colwidth", 80)
sel = pv[(pv.n_pos2 >= 3) | (pv.n_neg2 >= 3)].sort_values("n_pos2", ascending=False)
print("\nCelulas com |z|>2 do MESMO sinal em >=3 configs:")
print(sel.round(1).to_string())
sel.round(2).to_csv(f"out_txt/flags_{per}.csv")
