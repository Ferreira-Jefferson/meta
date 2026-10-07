import pandas as pd
from pathlib import Path
A = Path(__file__).resolve().parent
N = ["Win", "Win_c1", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34"]
d = pd.concat([pd.read_csv(A / "resultados" / f"{n}.csv") for n in N])
d["mes"] = d.saida.str[:7]; d["rs2"] = d.rs - 2
def tab(sub, titulo):
    out = [f"## {titulo}", "", "Linhas: operações / líquido sem custo (R$) / líquido com R$2 por operação. Mês pela data de saída.", "",
           "| mês | " + " | ".join(N) + " |", "|---|" + "---|" * len(N)]
    for m in sorted(sub.mes.unique()):
        row = []
        for n in N:
            g = sub[(sub.estrategia == n) & (sub.mes == m)]
            row.append(f"{len(g)} / {g.rs.sum():,.0f} / {g.rs2.sum():,.0f}")
        out.append(f"| {m} | " + " | ".join(row) + " |")
    row = []
    for n in N:
        g = sub[sub.estrategia == n]; row.append(f"**{len(g)} / {g.rs.sum():,.0f} / {g.rs2.sum():,.0f}**")
    out.append("| **total** | " + " | ".join(row) + " |")
    return "\n".join(out) + "\n"
txt = ["# V0 — resumo descritivo (só sanidade, sem decidir nada)", "",
       "Robôs no período 2024-01-02 → 2025-09-30, R$1.000, inputs padrão, ticks sintéticos 4/M1, WIN$N cru. WdoRetangulo excluído. Win e Win_c1 não param por saldo (como no comparativo); a coluna de total mostra o acumulado, não a quebra.", "",
       tab(d[(d.saida >= "2024-07") & (d.saida < "2025-10")], "VAL 2024-07 → 2025-09"), tab(d[d.saida < "2024-07"], "Aquecimento/DEV 2024-01 → 2024-06")]
(A / "resumo.md").write_text("\n".join(txt), encoding="utf-8")
print("\n".join(txt))
