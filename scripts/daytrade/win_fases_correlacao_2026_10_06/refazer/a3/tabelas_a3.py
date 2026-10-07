"""Monta as tabelas antes x depois do A3 a partir de resultado_variantes.jsonl e resultado_candidatas.jsonl (CSV em tabelas/)."""
import json
from pathlib import Path
import pandas as pd
AQUI = Path(__file__).resolve().parent
OUT = AQUI / "tabelas"; OUT.mkdir(exist_ok=True)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
v = pd.DataFrame([json.loads(l) for l in open(AQUI / "resultado_variantes.jsonl", encoding="utf-8")])
liq = v.pivot_table(index=["variante", "ano"], columns="cfg", values="liquido")
liq["D-A"] = liq.D - liq.A; liq["C-B"] = liq.C - liq.B
# soma 2022-24
s = liq.reset_index(); s24 = s[s.ano.isin([2022, 2023, 2024])].groupby("variante")[["A", "B", "C", "D"]].sum()
s24["D-A"] = s24.D - s24.A; s24["C-B"] = s24.C - s24.B
print("== liquido por variante/ano"); print(liq.round(0)); print("\n== soma 2022-24"); print(s24.round(0))
liq.to_csv(OUT / "variantes_liquido.csv"); s24.to_csv(OUT / "variantes_soma_2022_24.csv")
# saidas no call
pc = v.pivot_table(index=["variante", "ano"], columns="cfg", values="pct_zera_fim")
pn = v.pivot_table(index=["variante", "ano"], columns="cfg", values="pnl_zera_fim")
nt = v.pivot_table(index=["variante", "ano"], columns="cfg", values="trades")
call = pd.DataFrame({"trades_antes(A)": nt.A, "trades_depois(D)": nt.D, "%call_antes(A)": pc.L, "%call_depois(D)": 0.0,
                     "%zera_fim_depois(continuo)": pc.D, "pnl_zera_antes": pn.L, "pnl_zera_depois(D)": pn.D})
print("\n== saidas por zeragem de fim de pregao"); print(call)
call.to_csv(OUT / "variantes_saidas_call.csv")
px = v[(v.cfg == "C") & (v.variante == "v2.03")].set_index("ano")[["dias", "dias_proxy"]]; px["pct_proxy"] = (100 * px.dias_proxy / px.dias).round(0)
print("\n== dias com ultima barra proxy (sem tick)"); print(px); px.to_csv(OUT / "proxy_dias.csv")
# incrementos (adocoes)
rows = []
for cfg in "ABCD":
    p = v[v.cfg == cfg].pivot_table(index="ano", columns="variante", values="liquido")
    inc = pd.DataFrame({"v2.01-v2.00 (volume)": p["v2.01"] - p["v2.00"], "v2.02-v2.01 (aperta)": p["v2.02"] - p["v2.01"], "v2.03-v2.02 (ST H1)": p["v2.03"] - p["v2.02"]})
    inc.loc["2022-24"] = inc.loc[[2022, 2023, 2024]].sum()
    inc["cfg"] = cfg; rows.append(inc.reset_index())
inc = pd.concat(rows); print("\n== incrementos por adocao"); print(inc.pivot_table(index=["cfg", "ano"], values=inc.columns[1:4].tolist(), aggfunc="first", sort=False).round(0) if False else inc.round(0).to_string(index=False))
inc.to_csv(OUT / "adocoes_incrementos.csv", index=False)
c = pd.DataFrame([json.loads(l) for l in open(AQUI / "resultado_candidatas.jsonl", encoding="utf-8")]); c["ano"] = c.ano.astype(int)
cl = c.pivot_table(index=["familia", "cand", "ano"], columns="cfg", values="liquido", aggfunc="first")[["A", "D", "B", "C"]]
cl["D-A"] = cl.D - cl.A; cl["C-B"] = cl.C - cl.B
cl.to_csv(OUT / "candidatas_liquido.csv"); print("\n== candidatas"); print(cl.round(0).to_string())
