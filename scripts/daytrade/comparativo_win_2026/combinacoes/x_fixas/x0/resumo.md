# X0 — resumo por ano (só sanidade, nada é decidido)

> **Corrigido 2026-10-06 (X0b):** as colunas WinCincoMedias e WinDeslocamentoMatinal abaixo estão pós-correção da zeragem no fim real do pregão (`x0b/resumo.md`). Valores originais do X0: Cinco 2022 -962/-1,934, 2023 1,731/811, total 1734 / 717 / -2,751; Desloc 2022 405/313, 2023 1,229/1,151, 2024 1,378/1,266, total 183 / 4,958 / 4,592. Em 2024 o Desloc também passa de 1,378 para 1,459 porque o X0 original usava a emenda com a V0 (saldo reinicia em R$1.000) e o x0b roda contínuo. Win, Win_c1 e RetEma34 não mudaram.


Período 2022-01-03 → 2025-09-30 (2022-23 = X0; 2024-25 = V0). R$1.000, 1 contrato, inputs padrão, ticks sintéticos 4/M1, WIN$N cru, WdoRetangulo neutro. Ano pela data de saída. 2025 vai só até setembro. Células: operações / líquido sem custo (R$) / líquido com R$2 por operação.

| ano | Win | Win_c1 | WinCincoMedias | WinDeslocamentoMatinal | WinRetanguloEma34 |
|---|---|---|---|---|---|
| 2022 | 245 / -227 / -717 | 256 / 333 / -179 | 486 / 33 / -939 | 46 / 327 / 235 | 327 / -2,257 / -2,911 |
| 2023 | 214 / -1,257 / -1,685 | 226 / -987 / -1,439 | 460 / 3,181 / 2,261 | 39 / 1,482 / 1,404 | 184 / -1,053 / -1,421 |
| 2024 | 248 / -870 / -1,366 | 256 / -643 / -1,155 | 482 / -978 / -1,942 | 56 / 1,459 / 1,347 | 53 / -150 / -256 |
| 2025 | 179 / -918 / -1,276 | 186 / -57 / -429 | 306 / 926 / 314 | 42 / 1,946 / 1,862 | 124 / -608 / -856 |
| **total** | **886 / -3,272 / -5,044** | **924 / -1,354 / -3,202** | **1734 / 3,162 / -306** | **183 / 5,214 / 4,848** | **688 / -4,068 / -5,444** |

Notas:
- [corrigido 2026-10-06] WinDeslocamentoMatinal: no X0 original 30 das 183 operações saíam por 'overnight' (líquido 5,288), porque em 2022-23 há dias com sessão fechando 17:54 e o port zerava só às 18:20. Pós-X0b: 0 overnight (zeragem em fim do pregão − 5 min).
- WinRetanguloEma34: o port pararia ao equity <= 0 em 2022-06-15 (quebra); rodado sem parar, como pedido. O arquivo com a parada fica em logs/com_parada/.

[corrigido 2026-10-06] Overnight do Deslocamento no X0 original (ops / líquido): 2022: 10 / 2,707, 2023: 20 / 2,581. Pós-X0b: 0 em todos os anos.
