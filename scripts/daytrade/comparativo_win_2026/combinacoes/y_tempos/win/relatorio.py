import pandas as pd, numpy as np
from pathlib import Path
A = Path(__file__).resolve().parent
CUSTO = 2.0
def metr(rs):
    n = len(rs)
    if n == 0: return dict(ops=0, liquido=0.0, acerto=np.nan, pf=np.nan, maior_queda=0.0)
    r = rs - CUSTO
    eq = np.cumsum(np.r_[0.0, r.to_numpy()]); dd = (np.maximum.accumulate(eq) - eq).max()
    g, p = r[r > 0].sum(), -r[r < 0].sum()
    return dict(ops=n, liquido=round(r.sum(), 2), acerto=round(100*(r > 0).mean(), 1),
                pf=round(g/p, 2) if p > 0 else np.nan, maior_queda=round(dd, 2))
linhas = []
for robo in ("Win", "Win_c1"):
    for tf in (1, 2, 3, 5, 10, 15, 30):
        fs = [A/"trades"/f"{robo}_M{tf}_{p}.csv" for p in ("2225", "2026")]
        if not all(f.exists() for f in fs): continue
        df = pd.concat([pd.read_csv(f) for f in fs]); df["ano"] = df.saida.str[:4].astype(int)
        pos = 0
        for ano in (2022, 2023, 2024, 2025, 2026):
            m = metr(df[df.ano == ano].rs); pos += m["liquido"] > 0
            linhas.append(dict(robo=robo, tf=f"M{tf}", ano=ano, **m))
        m = metr(df.rs); linhas.append(dict(robo=robo, tf=f"M{tf}", ano="total", **m, anos_pos=pos))
t = pd.DataFrame(linhas); t.to_csv(A/"resultado.csv", index=False)
md = ["# Y1 -- Win e Win_c1 em outros tempos graficos", "",
      "Liquido com custo R$2/op, R$1.000, 1 contrato, sem parar por saldo. 2022-01-03..2025-09-30 (shim x0, ticks sinteticos 4/M1) + 2026-01-02..10-05 (dados.py). Ano = ano da saida. Acerto e PF ja com custo. Maior queda = por ano (curva de operacoes), 'total' = periodo todo. Prova M5 byte a byte: Win/Win_c1 em 2026 e 2022-25.",
      "Filtro superior: M1->M3, M2->M6, M3->M10, M5->M15, M10->M30, M15->H1, M30->H2.", "",
      "## Liquido com custo por ano", "", "| robo | tf | 2022 | 2023 | 2024 | 2025 | 2026 | total | anos + | candidato |", "|---|---|---|---|---|---|---|---|---|---|"]
for (robo, tf), g in t.groupby(["robo", "tf"], sort=False):
    v = {str(r.ano): r for r in g.itertuples()}
    cand = "SIM" if all(v[str(a)].liquido > 0 for a in (2022, 2023, 2024, 2025, 2026)) else "nao"
    md.append(f"| {robo} | {tf} | " + " | ".join(f"{v[k].liquido:.0f}" for k in ("2022","2023","2024","2025","2026","total")) + f" | {int(v['total'].anos_pos)}/5 | {cand} |")
md += ["", "## Detalhe (ops / liquido / acerto% / PF / maior queda)", "", "| robo | tf | ano | ops | liquido | acerto% | PF | maior queda |", "|---|---|---|---|---|---|---|---|"]
for r in t.itertuples():
    md.append(f"| {r.robo} | {r.tf} | {r.ano} | {r.ops} | {r.liquido:.2f} | {r.acerto} | {r.pf} | {r.maior_queda:.2f} |")
(A/"resultado.md").write_text("\n".join(md), encoding="utf-8")
print("\n".join(md[:30]))
