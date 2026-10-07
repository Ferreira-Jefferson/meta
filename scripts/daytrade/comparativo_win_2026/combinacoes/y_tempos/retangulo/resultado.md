# Y4 - WinRetanguloEma34 por tempo gráfico (R$2/op, 1 contrato, R$1.000, sem parar por saldo)

Prova: M1 reproduz byte a byte `resultados/WinRetanguloEma34.csv` (2026) e `x0b/resultados_2022_2025/WinRetanguloEma34.csv`.
Acerto = operações com líquido (após R$2) > 0. Maior queda = pico a vale do líquido acumulado (começa em 0, sem o capital). 2025 = jan-set. 2026 = 02/01-05/10.
Candidato = positivo com custo nos 5 anos.

## M1  (anos +: 1/5)

| ano | ops | líquido c/ custo | acerto % | fator lucro | maior queda |
|---|---|---|---|---|---|
| 2022 | 327 | -2,911.00 | 36.7 | 0.71 | 3,078.00 |
| 2023 | 184 | -1,421.00 | 37.0 | 0.71 | 1,709.00 |
| 2024 | 53 | -256.00 | 41.5 | 0.81 | 348.00 |
| 2025 | 124 | -856.00 | 41.9 | 0.77 | 1,239.00 |
| 2026 | 733 | 841.00 | 42.2 | 1.04 | 1,187.00 |
| total | 1421 | -4,603.00 | 40.2 | 0.88 | 6,119.00 |

## M2  (anos +: 1/5)

| ano | ops | líquido c/ custo | acerto % | fator lucro | maior queda |
|---|---|---|---|---|---|
| 2022 | 432 | -3,547.00 | 36.8 | 0.73 | 3,569.00 |
| 2023 | 269 | -2,574.00 | 35.7 | 0.66 | 2,645.00 |
| 2024 | 128 | -191.00 | 43.0 | 0.93 | 778.00 |
| 2025 | 155 | -1,708.00 | 36.8 | 0.64 | 1,728.00 |
| 2026 | 445 | 478.00 | 42.0 | 1.04 | 754.00 |
| total | 1429 | -7,542.00 | 38.8 | 0.82 | 8,295.00 |

## M3  (anos +: 2/5)

| ano | ops | líquido c/ custo | acerto % | fator lucro | maior queda |
|---|---|---|---|---|---|
| 2022 | 329 | -728.00 | 42.2 | 0.92 | 1,717.00 |
| 2023 | 205 | -880.00 | 40.5 | 0.84 | 1,241.00 |
| 2024 | 89 | -131.00 | 42.7 | 0.93 | 448.00 |
| 2025 | 83 | 552.00 | 53.0 | 1.28 | 465.00 |
| 2026 | 287 | 1,648.00 | 46.0 | 1.21 | 856.00 |
| total | 993 | 461.00 | 43.9 | 1.02 | 2,582.00 |

## M5  (anos +: 2/5)

| ano | ops | líquido c/ custo | acerto % | fator lucro | maior queda |
|---|---|---|---|---|---|
| 2022 | 139 | -973.00 | 37.4 | 0.77 | 1,270.00 |
| 2023 | 72 | 100.00 | 45.8 | 1.06 | 325.00 |
| 2024 | 44 | -354.00 | 36.4 | 0.7 | 451.00 |
| 2025 | 40 | -181.00 | 42.5 | 0.85 | 620.00 |
| 2026 | 132 | 90.00 | 39.4 | 1.02 | 779.00 |
| total | 427 | -1,318.00 | 39.8 | 0.89 | 2,057.00 |

## M10  (anos +: 0/5)

| ano | ops | líquido c/ custo | acerto % | fator lucro | maior queda |
|---|---|---|---|---|---|
| 2022 | 0 | 0.00 | nan | nan | 0.00 |
| 2023 | 0 | 0.00 | nan | nan | 0.00 |
| 2024 | 0 | 0.00 | nan | nan | 0.00 |
| 2025 | 0 | 0.00 | nan | nan | 0.00 |
| 2026 | 0 | 0.00 | nan | nan | 0.00 |
| total | 0 | 0.00 | nan | nan | 0.00 |

## M15  (anos +: 0/5)

| ano | ops | líquido c/ custo | acerto % | fator lucro | maior queda |
|---|---|---|---|---|---|
| 2022 | 0 | 0.00 | nan | nan | 0.00 |
| 2023 | 0 | 0.00 | nan | nan | 0.00 |
| 2024 | 0 | 0.00 | nan | nan | 0.00 |
| 2025 | 0 | 0.00 | nan | nan | 0.00 |
| 2026 | 0 | 0.00 | nan | nan | 0.00 |
| total | 0 | 0.00 | nan | nan | 0.00 |

**Candidatos: nenhum**