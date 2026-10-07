import pandas as pd, numpy as np
from pathlib import Path
A = Path(__file__).resolve().parent
Y4 = A.parent / "trades"
CUSTO = 2.0
anos = ["2022", "2023", "2024", "2025", "2026"]
TFS = [(1,"M1"),(2,"M2"),(3,"M3"),(5,"M5"),(10,"M10"),(15,"M15"),(20,"M20"),(30,"M30"),(60,"H1"),(120,"H2"),(180,"H3"),(240,"H4")]
def carrega(pref, tf, base):
    ps = []
    for p in ("2022_2025", "2026"):
        f = base / f"{pref}_M{tf}_{p}.csv"
        if not f.exists(): return None
        ps.append(pd.read_csv(f))
    df = pd.concat(ps)
    if df.empty: df = pd.DataFrame(columns=["entrada","saida","rs"]).astype({"saida": str, "rs": float})
    df["ano"] = df.saida.str[:4]; df["liq"] = df.rs - CUSTO
    return df.sort_values("saida")
rows = []
for versao, pref, base, lim in (("ORIGINAL", "ret", Y4, 5), ("RetTF", "rettf", A / "trades", 999)):
    for tf, nome in TFS:
        if tf > lim: continue
        df = carrega(pref, tf, base)
        if df is None: continue
        pos = 0; sub = []
        for a in anos + ["total"]:
            g = df if a == "total" else df[df.ano == a]
            n = len(g); liq = g.liq.sum()
            w = (g.liq > 0).mean() * 100 if n else np.nan
            gp, gl = g.liq[g.liq > 0].sum(), -g.liq[g.liq < 0].sum()
            pf = gp / gl if gl > 0 else np.nan
            eq = g.liq.cumsum(); dd = (eq.cummax().clip(lower=0) - eq).max() if n else 0
            if a == "total":
                # menor saldo recomeçando com 1000 a cada ano = min por ano
                menor = min([1000 + (df[df.ano == y].liq.cumsum().min() if (df.ano == y).any() else 0) for y in anos] + [1000])
                menor = min(1000 + min(0, df[df.ano == y].liq.cumsum().min()) if (df.ano == y).any() else 1000 for y in anos)
            else:
                menor = 1000 + min(0, eq.min()) if n else 1000
            if a != "total" and liq > 0: pos += 1
            sub.append(dict(versao=versao, tf=nome, ano=a, ops=n, liquido_com_custo=round(liq, 2), acerto_pct=round(w, 1),
                            fator_lucro=round(pf, 2), maior_queda=round(dd, 2), menor_saldo=round(menor, 2)))
        for r in sub: r["anos_positivos"] = f"{pos}/5"
        rows += sub
t = pd.DataFrame(rows); t.to_csv(A / "resultado.csv", index=False)
md = ["# Y4b - WinRetanguloEma34: ORIGINAL (Y4) x RetTF (ajustes A, B, C), por tempo gráfico",
      "R$2/op, 1 contrato, R$1.000 por ano, sem parar por saldo. 'menor saldo' = 1.000 + pior ponto do líquido acumulado dentro do ano (recomeça em R$1.000 a cada ano; no total = o menor entre os anos). 2025 = jan-set; 2026 = 02/01-05/10. Acerto = ops com líquido (após R$2) > 0. Maior queda = pico a vale do líquido acumulado.",
      "ORIGINAL só existe do M1 ao M5 (Y4; M10/M15 = 0 operações). Candidato = positivo com custo nos 5 anos.\n",
      "## Resumo: líquido c/ custo por ano (ops entre parênteses)\n",
      "| versão | tempo | 2022 | 2023 | 2024 | 2025 | 2026 | total | anos + | menor saldo |", "|---|---|---|---|---|---|---|---|---|---|"]
for (v, tfn), g in t.groupby(["versao", "tf"], sort=False):
    c = {r.ano: r for r in g.itertuples()}
    cel = lambda a: f"{c[a].liquido_com_custo:,.0f} ({c[a].ops})"
    md.append(f"| {v} | {tfn} | " + " | ".join(cel(a) for a in anos + ["total"]) + f" | {c['total'].anos_positivos} | {c['total'].menor_saldo:,.0f} |")
md.append("")
for (v, tfn), g in t.groupby(["versao", "tf"], sort=False):
    md.append(f"## {v} {tfn} (anos +: {g.anos_positivos.iloc[0]})\n")
    md.append("| ano | ops | líquido c/ custo | acerto % | fator lucro | maior queda | menor saldo |\n|---|---|---|---|---|---|---|")
    for r in g.itertuples():
        md.append(f"| {r.ano} | {r.ops} | {r.liquido_com_custo:,.2f} | {r.acerto_pct} | {r.fator_lucro} | {r.maior_queda:,.2f} | {r.menor_saldo:,.0f} |")
    md.append("")
cand = [f"{v} {tfn}" for (v, tfn), g in t.groupby(["versao", "tf"]) if (g[g.ano != "total"].liquido_com_custo > 0).all()]
md.append(f"**Candidatos: {', '.join(cand) if cand else 'nenhum'}**")
(A / "resultado.md").write_text("\n".join(md), encoding="utf-8")
print("\n".join(md[:30]))
