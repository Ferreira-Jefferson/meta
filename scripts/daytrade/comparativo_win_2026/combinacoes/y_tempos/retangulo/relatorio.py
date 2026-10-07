import pandas as pd, numpy as np
from pathlib import Path
A = Path(__file__).resolve().parent
CUSTO = 2.0
anos = ["2022", "2023", "2024", "2025", "2026"]
rows = []
for tf in [1, 2, 3, 5, 10, 15]:
    from pandas.errors import EmptyDataError
    df = pd.concat([pd.read_csv(A / "trades" / f"ret_M{tf}_{p}.csv") for p in ("2022_2025", "2026")])
    if df.empty: df = pd.DataFrame(columns=["saida", "rs"]).astype({"saida": str, "rs": float})
    df["ano"] = df.saida.str[:4]
    df["liq"] = df.rs - CUSTO
    pos = 0
    for a in anos + ["total"]:
        g = df if a == "total" else df[df.ano == a]
        g = g.sort_values("saida")
        n = len(g)
        liq = g.liq.sum()
        w = (g.liq > 0).mean() * 100 if n else np.nan
        gp, gl = g.liq[g.liq > 0].sum(), -g.liq[g.liq < 0].sum()
        pf = gp / gl if gl > 0 else np.nan
        eq = g.liq.cumsum(); dd = (eq.cummax().clip(lower=0) - eq).max() if n else 0
        if a != "total" and liq > 0: pos += 1
        rows.append(dict(tf=f"M{tf}", ano=a, ops=n, liquido_com_custo=round(liq, 2), acerto_pct=round(w, 1),
                         fator_lucro=round(pf, 2), maior_queda=round(dd, 2), anos_positivos=None))
    for r in rows[-6:]: r["anos_positivos"] = f"{pos}/5"
t = pd.DataFrame(rows)
t.to_csv(A / "resultado.csv", index=False)
md = ["# Y4 - WinRetanguloEma34 por tempo gráfico (R$2/op, 1 contrato, R$1.000, sem parar por saldo)\n",
      "Prova: M1 reproduz byte a byte `resultados/WinRetanguloEma34.csv` (2026) e `x0b/resultados_2022_2025/WinRetanguloEma34.csv`.",
      "Acerto = operações com líquido (após R$2) > 0. Maior queda = pico a vale do líquido acumulado (começa em 0, sem o capital). 2025 = jan-set. 2026 = 02/01-05/10.",
      "Candidato = positivo com custo nos 5 anos.\n"]
for tf, g in t.groupby("tf", sort=False):
    md.append(f"## {tf}  (anos +: {g.anos_positivos.iloc[0]})\n")
    md.append("| ano | ops | líquido c/ custo | acerto % | fator lucro | maior queda |\n|---|---|---|---|---|---|")
    for _, r in g.iterrows():
        md.append(f"| {r.ano} | {r.ops} | {r.liquido_com_custo:,.2f} | {r.acerto_pct} | {r.fator_lucro} | {r.maior_queda:,.2f} |")
    md.append("")
cand = [tf for tf, g in t.groupby("tf") if (g[g.ano != "total"].liquido_com_custo > 0).all()]
md.append(f"**Candidatos: {', '.join(cand) if cand else 'nenhum'}**")
(A / "resultado.md").write_text("\n".join(md), encoding="utf-8")
print("\n".join(md))
