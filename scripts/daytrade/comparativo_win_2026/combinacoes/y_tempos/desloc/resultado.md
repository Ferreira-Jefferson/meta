# Y3 - WinDeslocamentoMatinal em outros tempos gráficos (R$2/op; R$1.000 corrido; ops por ano de entrada)

Líquido, acerto, FP e maior queda COM custo de R$2/op. 2022-01-03..2025-09-30 contínuo (shim x0b, zeragem corrigida) + 2026-01-02..10-05 (dados.py).

| tempo | ano | ops | líquido R$ | acerto % | FP | maior queda R$ | anos + |
|---|---|---|---|---|---|---|---|
| M1 | 2022 | 46 | 235 | 26.1 | 1.09 | 799 | 5 |
| M1 | 2023 | 39 | 1404 | 59.0 | 1.59 | 822 | 5 |
| M1 | 2024 | 56 | 1347 | 51.8 | 1.43 | 955 | 5 |
| M1 | 2025 | 42 | 1862 | 52.4 | 1.84 | 758 | 5 |
| M1 | 2026 | 65 | 2089 | 38.5 | 1.36 | 1172 | 5 |
| M1 | total | 248 | 6937 | 44.8 | 1.43 | 1172 | 5 |
| M2 | 2022 | 50 | 41 | 24.0 | 1.02 | 833 | 5 |
| M2 | 2023 | 43 | 1552 | 58.1 | 1.58 | 1152 | 5 |
| M2 | 2024 | 57 | 1336 | 52.6 | 1.42 | 955 | 5 |
| M2 | 2025 | 48 | 1447 | 52.1 | 1.52 | 965 | 5 |
| M2 | 2026 | 67 | 1912 | 38.8 | 1.31 | 1278 | 5 |
| M2 | total | 265 | 6288 | 44.5 | 1.36 | 1278 | 5 |
| M3 | 2022 | 52 | -214 | 21.2 | 0.92 | 820 | 4 |
| M3 | 2023 | 47 | 1029 | 51.1 | 1.32 | 1536 | 4 |
| M3 | 2024 | 62 | 838 | 50.0 | 1.22 | 911 | 4 |
| M3 | 2025 | 51 | 2065 | 54.9 | 1.74 | 883 | 4 |
| M3 | 2026 | 70 | 1637 | 34.3 | 1.26 | 1436 | 4 |
| M3 | total | 282 | 5355 | 41.8 | 1.29 | 1536 | 4 |
| M5 | 2022 | 51 | -257 | 21.6 | 0.9 | 818 | 4 |
| M5 | 2023 | 51 | 705 | 39.2 | 1.22 | 1155 | 4 |
| M5 | 2024 | 64 | 568 | 48.4 | 1.14 | 1257 | 4 |
| M5 | 2025 | 53 | 2367 | 56.6 | 1.85 | 754 | 4 |
| M5 | 2026 | 74 | 1134 | 45.9 | 1.13 | 2081 | 4 |
| M5 | total | 293 | 4517 | 43.0 | 1.21 | 2081 | 4 |
| M10 | 2022 | 54 | -956 | 14.8 | 0.58 | 956 | 1 |
| M10 | 2023 | 18 | -190 | 5.6 | 0.53 | 403 | 1 |
| M10 | 2024 | 0 | 0 | - | - | 0 | 1 |
| M10 | 2025 | 0 | 0 | - | - | 0 | 1 |
| M10 | 2026 | 36 | 449 | 38.9 | 1.11 | 1946 | 1 |
| M10 | total | 108 | -697 | 21.3 | 0.9 | 1946 | 1 |
| M15 | 2022 | 56 | -978 | 14.3 | 0.58 | 978 | 1 |
| M15 | 2023 | 36 | -215 | 11.1 | 0.82 | 671 | 1 |
| M15 | 2024 | 0 | 0 | - | - | 0 | 1 |
| M15 | 2025 | 0 | 0 | - | - | 0 | 1 |
| M15 | 2026 | 36 | 449 | 38.9 | 1.11 | 1946 | 1 |
| M15 | total | 128 | -744 | 20.3 | 0.9 | 1946 | 1 |
| M30 | 2022 | 59 | -1042 | 13.6 | 0.56 | 1042 | 1 |
| M30 | 2023 | 8 | -101 | 0.0 | 0.0 | 101 | 1 |
| M30 | 2024 | 0 | 0 | - | - | 0 | 1 |
| M30 | 2025 | 0 | 0 | - | - | 0 | 1 |
| M30 | 2026 | 38 | 326 | 36.8 | 1.08 | 2114 | 1 |
| M30 | total | 105 | -817 | 21.0 | 0.88 | 2114 | 1 |

Candidatos (positivo com custo nos 5 anos): M1, M2
Notas:
- Prova: com M1 a cópia reproduz byte a byte resultados/WinDeslocamentoMatinal.csv (2026) e x_fixas/x0b/resultados_2022_2025/WinDeslocamentoMatinal.csv.
- QUEBRA (saldo <= 0, para de operar; por isso M10/M15/M30 ficam com 0 ops em 2024-25): M10 em 2023-05-16, M15 em 2023-07-31, M30 em 2023-02-22. M1, M2, M3, M5 não quebram.
- Dias em branco por regra: em dias cuja 1a barra é 09:02-09:04 a 1a vela de M10/M15/M30 com abertura >= 1a barra+90 min abre mais de 5 min depois (a janela de 5 min não muda): 18 dias atrasados em 2022-25 por tf (2022-23 só o início da série quebrou) e 104 em 2026. Isso é consequência declarada da regra pré-registrada, não bug.
- M15 e M10 coincidem em 2026 (mesmos 36 trades).
- Alinhamento das velas: baldes à meia-noite (floor(ms/tf)); Y3 em desloc/: port_desloc_tf.py, run_y3.py, tabela.py, trades/M<tf>_<2225|2026>.csv, prova/.
