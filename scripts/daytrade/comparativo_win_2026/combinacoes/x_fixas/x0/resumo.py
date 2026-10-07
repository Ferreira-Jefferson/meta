import pandas as pd
from pathlib import Path
A = Path(__file__).resolve().parent
N = ["Win", "Win_c1", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34"]
d = pd.concat([pd.read_csv(A / "resultados_2022_2025" / f"{n}.csv") for n in N])
d["ano"] = d.saida.str[:4]; d["rs2"] = d.rs - 2
out = ["# X0 — resumo por ano (só sanidade, nada é decidido)", "",
       "Período 2022-01-03 → 2025-09-30 (2022-23 = X0; 2024-25 = V0). R$1.000, 1 contrato, inputs padrão, ticks sintéticos 4/M1, WIN$N cru, WdoRetangulo neutro. "
       "Ano pela data de saída. 2025 vai só até setembro. Células: operações / líquido sem custo (R$) / líquido com R$2 por operação.", "",
       "| ano | " + " | ".join(N) + " |", "|---|" + "---|" * len(N)]
for a in ["2022", "2023", "2024", "2025"]:
    out.append(f"| {a} | " + " | ".join(f"{len(g)} / {g.rs.sum():,.0f} / {g.rs2.sum():,.0f}" for g in (d[(d.estrategia == n) & (d.ano == a)] for n in N)) + " |")
out.append("| **total** | " + " | ".join(f"**{len(g)} / {g.rs.sum():,.0f} / {g.rs2.sum():,.0f}**" for g in (d[d.estrategia == n] for n in N)) + " |")
mo = d[(d.estrategia == "WinDeslocamentoMatinal") & (d.motivo == "overnight")]
out += ["", "Notas:", f"- WinDeslocamentoMatinal: {len(mo)} das {int((d.estrategia == 'WinDeslocamentoMatinal').sum())} operações saíram por 'overnight' (líquido {mo.rs.sum():,.0f}); em 2022-23 há dias com sessão fechando 17:54 e o port zera só às 18:20, então a posição carrega até a abertura seguinte. Em 2024-25 não ocorre. Detalhe por ano abaixo.",
        "- WinRetanguloEma34: o port pararia ao equity <= 0 em 2022-06-15 (quebra); rodado sem parar, como pedido. O arquivo com a parada fica em logs/com_parada/.",
        "", "Overnight do Deslocamento por ano (ops / líquido): " + ", ".join(f"{a}: {len(g)} / {g.rs.sum():,.0f}" for a, g in mo.groupby("ano"))]
(A / "resumo.md").write_text("\n".join(out) + "\n", encoding="utf-8"); print("\n".join(out))
