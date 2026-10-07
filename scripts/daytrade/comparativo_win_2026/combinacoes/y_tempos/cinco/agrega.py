"""Y2 -- tabela tempo grafico x ano, com custo R$2/op. Maior queda = pico-a-vale da curva acumulada (por saida) dentro do ano, R$ com custo."""
from pathlib import Path
import pandas as pd, numpy as np
AQUI = Path(__file__).resolve().parent
CUSTO = 2.0
ANOS = ["2022", "2023", "2024", "2025", "2026"]
linhas = []
for tf in (5, 10, 15, 20, 30, 60, 120):
    nome = f"M{tf}" if tf < 60 else f"H{tf//60}"
    dfs = [pd.read_csv(AQUI / "trades" / f"cinco_M{tf}_{p}.csv") for p in ("2022_2025", "2026")]
    d = pd.concat(dfs, ignore_index=True)
    d["ano"] = d["saida"].str[:4]
    d["l"] = d["rs"] - CUSTO
    pos = 0
    for a in ANOS:
        g = d[d.ano == a].sort_values("saida")
        if g.empty:
            linhas.append(dict(tf=nome, ano=a, ops=0, liquido=0.0, acerto=np.nan, fp=np.nan, maior_queda=0.0)); continue
        x = g.l.to_numpy(); cum = np.cumsum(x); pico = np.maximum.accumulate(np.r_[0, cum])[1:]
        w, ls = x[x > 0].sum(), -x[x < 0].sum()
        linhas.append(dict(tf=nome, ano=a, ops=len(g), liquido=round(x.sum(), 2), acerto=round((x > 0).mean() * 100, 1),
                           fp=round(w / ls, 2) if ls > 0 else np.inf, maior_queda=round((pico - cum).max(), 2)))
R = pd.DataFrame(linhas)
anos_pos = R.assign(p=R.liquido > 0).groupby("tf", sort=False).p.sum()
R["anos_pos"] = R.tf.map(anos_pos)
R.to_csv(AQUI / "resultado.csv", index=False)
out = ["# Y2 -- WinCincoMedias em outros tempos graficos (R$2/op, R$1.000, 1 contrato)", "",
       "Prova: M30 byte-igual a resultados/WinCincoMedias.csv (2026) e x0b/resultados_2022_2025/WinCincoMedias.csv. Ano = ano da saida; 2025 ate set; 2026 ate 05/10. Supertrend no proximo TF >= 2x a base. Maior queda em R$ dentro do ano (com custo). Candidato = positivo com custo nos 5 anos.", "",
       "| TF | ano | ops | liquido c/ custo | acerto % | fator lucro | maior queda | anos + (de 5) |", "|---|---|---|---|---|---|---|---|"]
f = lambda v: str(v).replace(".", ",")
for _, r in R.iterrows():
    out.append(f"| {r.tf} | {r.ano} | {r.ops} | {f(r.liquido)} | {f(r.acerto)} | {f(r.fp)} | {f(r.maior_queda)} | {int(r.anos_pos)} |")
cand = [t for t, n in anos_pos.items() if n == 5]
out += ["", "Candidatos: " + (", ".join(cand) if cand else "nenhum")]
(AQUI / "resultado.md").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
