import pandas as pd, numpy as np
from pathlib import Path
A = Path(__file__).resolve().parent
CUSTO = 2.0
ANOS = (2022, 2023, 2024, 2025, 2026)
def metr(rs):
    n = len(rs)
    if n == 0: return dict(ops=0, liquido=0.0, acerto=np.nan, pf=np.nan, maior_queda=0.0)
    r = rs - CUSTO
    eq = np.cumsum(np.r_[0.0, r.to_numpy()]); dd = (np.maximum.accumulate(eq) - eq).max()
    g, p = r[r > 0].sum(), -r[r < 0].sum()
    return dict(ops=n, liquido=round(r.sum(), 2), acerto=round(100*(r > 0).mean(), 1),
                pf=round(g/p, 2) if p > 0 else np.nan, maior_queda=round(dd, 2))
def saldo_min(df):
    """recomeca com R$1.000 a cada ano; saldo minimo (ao longo das operacoes, com custo) entre os anos"""
    mins = []
    for ano in ANOS:
        r = (df[df.ano == ano].rs - CUSTO).to_numpy()
        eq = 1000 + np.cumsum(r) if len(r) else np.array([1000.0])
        mins.append(float(min(1000.0, eq.min())))
    return round(min(mins), 2), [round(m, 2) for m in mins]
linhas, cands = [], []
tfs = [("M30", A/"resultado.csv")]
# M30 da Y1 (reaproveita)
y1 = pd.read_csv(A/"resultado.csv")
y1 = y1[y1.tf == "M30"].copy(); y1["tf"] = "M30"
nomes = {60: "H1", 120: "H2", 180: "H3", 240: "H4"}
rows = [r for r in y1.to_dict("records")]
for robo in ("Win", "Win_c1"):
    for tf in (60, 120, 180, 240):
        fs = [A/"trades"/f"{robo}_M{tf}_{p}.csv" for p in ("2225", "2026")]
        if not all(f.exists() for f in fs): continue
        df = pd.concat([pd.read_csv(f) for f in fs]); df["ano"] = df.saida.str[:4].astype(int)
        pos = 0
        for ano in ANOS:
            m = metr(df[df.ano == ano].rs); pos += m["liquido"] > 0
            rows.append(dict(robo=robo, tf=nomes[tf], ano=ano, **m))
        m = metr(df.rs); rows.append(dict(robo=robo, tf=nomes[tf], ano="total", **m, anos_pos=pos))
        if all(metr(df[df.ano == a].rs)["liquido"] > 0 for a in ANOS):
            cands.append((robo, nomes[tf], saldo_min(df)))
t = pd.DataFrame(rows); t.to_csv(A/"resultado_maiores.csv", index=False)
md = ["# Y1b -- Win e Win_c1 em tempos maiores (H1-H4) + M30 da Y1", "",
      "Liquido com custo R$2/op, R$1.000, 1 contrato, sem parar por saldo. 2022-01-03..2025-09-30 (shim x0) + 2026-01-02..10-05 (dados.py). Ano = ano da saida.",
      "Filtro superior: H1->H3, H2->H6, H3->H12, H4->H12 (M30->H2 na Y1). Barras alinhadas a meia-noite do servidor.", "",
      "## Liquido com custo por ano (ops entre parenteses)", "",
      "| robo | tf | 2022 | 2023 | 2024 | 2025 | 2026 | total | anos + | candidato |", "|---|---|---|---|---|---|---|---|---|---|"]
for (robo, tf), g in t.groupby(["robo", "tf"], sort=False):
    v = {str(r.ano): r for r in g.itertuples()}
    cand = "SIM" if all(v[str(a)].liquido > 0 for a in ANOS) else "nao"
    cel = " | ".join(f"{v[str(a)].liquido:.0f} ({int(v[str(a)].ops)})" for a in ANOS)
    md.append(f"| {robo} | {tf} | {cel} | {v['total'].liquido:.0f} ({int(v['total'].ops)}) | {int(v['total'].anos_pos)}/5 | {cand} |")
md += ["", "## Candidatos (positivo com custo nos 5 anos) e saldo minimo recomecando com R$1.000 a cada ano", ""]
if cands:
    for robo, tf, (m, por) in cands: md.append(f"- {robo} {tf}: saldo minimo R$ {m} (por ano {por})")
else: md.append("Nenhum.")
md += ["", "## Detalhe (ops / liquido / acerto% / PF / maior queda)", "", "| robo | tf | ano | ops | liquido | acerto% | PF | maior queda |", "|---|---|---|---|---|---|---|---|"]
for r in t.itertuples():
    md.append(f"| {r.robo} | {r.tf} | {r.ano} | {r.ops} | {r.liquido:.2f} | {r.acerto} | {r.pf} | {r.maior_queda:.2f} |")
(A/"resultado_maiores.md").write_text("\n".join(md), encoding="utf-8")
print("\n".join(md[:22]), flush=True)
