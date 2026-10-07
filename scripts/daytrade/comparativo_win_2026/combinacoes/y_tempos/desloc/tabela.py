import pandas as pd, numpy as np
from pathlib import Path
A = Path(__file__).resolve().parent
R = []
def met(d):
    r = d.rs.to_numpy() - 2.0
    if len(r) == 0: return dict(ops=0, liq=0.0, acerto=np.nan, fp=np.nan, dd=0.0)
    c = np.cumsum(r); dd = float((np.maximum.accumulate(np.r_[0, c])[1:] - c).max())
    g, p = r[r > 0].sum(), -r[r < 0].sum()
    return dict(ops=len(r), liq=round(float(r.sum()), 0), acerto=round(100 * (r > 0).mean(), 1), fp=round(g / p, 2) if p > 0 else np.inf, dd=round(dd, 0))
for tf in (1, 2, 3, 5, 10, 15, 30):
    d = pd.concat([pd.read_csv(A / "trades" / f"M{tf}_{per}.csv") for per in ("2225", "2026")] if tf > 1 else
                  [pd.read_csv(A / "prova" / "p2225.csv"), pd.read_csv(A / "prova" / "p2026.csv")])
    d["ano"] = d.entrada.str[:4].astype(int)
    pos = 0
    for ano in (2022, 2023, 2024, 2025, 2026):
        m = met(d[d.ano == ano]); pos += m["liq"] > 0
        R.append(dict(tf=f"M{tf}", ano=ano, **m))
    for x in R[-5:]: x["anos_pos"] = pos
    t = met(d); R.append(dict(tf=f"M{tf}", ano="total", **t, anos_pos=pos))
df = pd.DataFrame(R); df.to_csv(A / "resultado.csv", index=False)
cand = {t: g[g.ano != "total"].liq.gt(0).all() for t, g in df.groupby("tf", sort=False)}
L = ["# Y3 - WinDeslocamentoMatinal em outros tempos gráficos (R$2/op; R$1.000 corrido; ops por ano de entrada)\n",
     "Líquido, acerto, FP e maior queda COM custo de R$2/op. 2022-01-03..2025-09-30 contínuo (shim x0b, zeragem corrigida) + 2026-01-02..10-05 (dados.py).\n",
     "| tempo | ano | ops | líquido R$ | acerto % | FP | maior queda R$ | anos + |", "|---|---|---|---|---|---|---|---|"]
for _, r in df.iterrows():
    L.append(f"| {r.tf} | {r.ano} | {r.ops} | {r.liq:.0f} | {r.acerto} | {r.fp} | {r.dd:.0f} | {r.anos_pos:.0f} |".replace("nan", "-"))
L.append("\nCandidatos (positivo com custo nos 5 anos): " + (", ".join(t for t, v in cand.items() if v) or "nenhum"))
(A / "resultado.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
