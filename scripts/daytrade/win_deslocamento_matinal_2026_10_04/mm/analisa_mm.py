import json, sys
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import comum as c
modo = sys.argv[1]
rs = json.loads((HERE / f"saida_{modo}.json").read_text())
L = []
for r in rs:
    tr = [SimpleNamespace(entry_ts=pd.Timestamp(t["entry_ts"]), pnl_brl=t["pnl"]) for t in r["trades"]]
    st = c.estatisticas(tr); an = c.por_ano(tr)
    L.append(dict(id=r["cid"], prem=r["premissa"], n=st["n"], liq=st["liquido"], media=st["media"], lo=st["ic_lo"], hi=st["ic_hi"],
                  win=st["win"], be=st["be"], anos="/".join(f"{an.get(y,(0,0))[1]:+.0f}" for y in (2022,2023,2024)) if modo=="IS" else "",
                  anos_pos=sum(an.get(y,(0,0))[1] > 0 for y in (2022,2023,2024)) if modo=="IS" else ""))
d = pd.DataFrame(L)
order = ["BASE","A_e10","A_e20","A_e50","A_s10d","A_s20d","S30","S15","E15","E25","P30","P60"]
d["o"] = d["id"].map(order.index); d = d.sort_values(["o","prem"]).drop(columns="o")
d.to_csv(HERE / f"tabela_{modo}.csv", index=False, sep=";", decimal=",")
pd.set_option("display.width", 250)
print(d.round(1).to_string(index=False))
if modo == "IS":
    p = d[d.prem=="P2"].set_index("id"); b = p.loc["BASE"]
    viz = {"A_e10":["A_e20"],"A_e20":["A_e10","A_e50"],"A_e50":["A_e20"],"A_s10d":["A_s20d"],"A_s20d":["A_s10d"],"S30":["S15"],"S15":["S30"],"E15":["E25"],"E25":["E15"],"P30":["P60"],"P60":["P30"]}
    for i, v in viz.items():
        r = p.loc[i]
        a = r.media > b.media; bb = r.liq >= 0.9*b.liq; cc = r.anos_pos == 3; dd = any(p.loc[x].media > b.media for x in v)
        print(i, "a",a,"b",bb,"c",cc,"d",dd, "=> PASSA" if a and bb and cc and dd else "")
