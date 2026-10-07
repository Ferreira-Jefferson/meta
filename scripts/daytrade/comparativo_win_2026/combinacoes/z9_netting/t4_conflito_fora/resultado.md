# Z9-T4 conflito = fora

Regra: quem abre primeiro fica; mesmo lado ignorado; lado contrario zera a mercado (preco(t), t = entrada do causador) e ninguem entra; depois a conta fica livre. T4b: fora pelo resto do pregao apos conflito. T4c: nao zera, bloqueia como T0 (so registra conflitos). Liquido com custo R$2/op, 1 contrato, R$1.000 por ano. Aproximacao: robo bloqueado/interrompido nao muda as operacoes seguintes dele.

## Por ano (liquido R$ / ops / acerto % / maior queda R$ / quebra)

| ano | soma isolada | T4 | T4b | T4c (=T0) |
|---|---|---|---|---|
| 2022 | 5.026 / 473 / 42.9 / 2.315 / - | 4.913 / 295 / 44.4 / 1.543 / - | 6.143 / 260 / 47.7 / 1.348 / - | 4.740 / 270 / 47.8 / 1.922 / - |
| 2023 | 4.512 / 455 / 45.1 / 2.108 / - | 3.936 / 281 / 50.2 / 1.443 / - | 3.531 / 252 / 50.4 / 1.398 / - | 3.908 / 257 / 50.6 / 1.299 / - |
| 2024 | 4.720 / 477 / 44.9 / 1.883 / - | 3.895 / 294 / 49.7 / 1.631 / - | 4.577 / 266 / 51.1 / 1.323 / - | 5.173 / 267 / 51.7 / 1.473 / - |
| 2025 | 5.208 / 344 / 43.3 / 3.112 / - | 2.338 / 203 / 45.3 / 1.997 / - | 2.420 / 191 / 46.1 / 2.233 / - | 3.123 / 192 / 47.9 / 2.981 / - |
| 2026 | 14.079 / 361 / 45.2 / 3.335 / - | 6.526 / 216 / 44.4 / 1.953 / - | 6.717 / 201 / 44.8 / 2.034 / - | 5.131 / 207 / 43.5 / 2.515 / - |

## Por robo dono (liquido R$ c/ custo (ops))

| robo | variante | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| WinGapBarra1 | T4 | 2.300 (126) | 1.243 (114) | 1.757 (109) | 934 (91) | 7.029 (90) |
| WinCincoMedias | T4 | 2.215 (110) | -73 (100) | 1.987 (119) | 679 (65) | 151 (75) |
| WinDeslocamentoMatinal | T4 | 670 (12) | 1.661 (17) | 315 (21) | 711 (18) | -1.120 (19) |
| WinRetanguloEma34 | T4 | -163 (34) | 641 (39) | -19 (34) | -135 (23) | 176 (20) |
| Win_c1 | T4 | -109 (13) | 464 (11) | -145 (11) | 149 (6) | 290 (12) |
| WinGapBarra1 | T4b | 2.300 (126) | 1.243 (114) | 1.757 (109) | 934 (91) | 7.029 (90) |
| WinCincoMedias | T4b | 2.588 (99) | -133 (88) | 2.011 (103) | 487 (60) | 137 (69) |
| WinDeslocamentoMatinal | T4b | 839 (10) | 1.256 (15) | 622 (19) | 883 (17) | -949 (17) |
| WinRetanguloEma34 | T4b | 520 (18) | 617 (28) | 263 (28) | -35 (18) | 270 (16) |
| Win_c1 | T4b | -104 (7) | 548 (7) | -76 (7) | 151 (5) | 230 (9) |
| WinGapBarra1 | T4c | 1.214 (126) | 1.291 (114) | 2.287 (109) | 1.567 (91) | 5.740 (90) |
| WinCincoMedias | T4c | 2.669 (100) | 68 (89) | 2.020 (103) | 487 (60) | -173 (73) |
| WinDeslocamentoMatinal | T4c | 839 (10) | 1.223 (15) | 622 (19) | 938 (17) | -774 (17) |
| WinRetanguloEma34 | T4c | 220 (22) | 818 (31) | 320 (29) | -18 (18) | 129 (17) |
| Win_c1 | T4c | -202 (12) | 508 (8) | -76 (7) | 149 (6) | 209 (10) |

## O conflito e' informativo? Posicao aberta no 1o conflito: R$ bruto (1 contrato, sem custo) ate' a saida natural vs zerando no conflito

| ano | conflitos | natural R$ | zerando R$ | zerar - natural | % perda se natural | % perda se zerar | R$ medio por op (nao-conflito) |
|---|---|---|---|---|---|---|---|
| 2022 | 60 | -2.153 | -1.241 | 912 | 58 | 67 | media geral T4c 19.6; media nas posicoes com conflito -35.9 |
| 2023 | 40 | -594 | -719 | -125 | 57 | 57 | media geral T4c 17.2; media nas posicoes com conflito -14.8 |
| 2024 | 40 | -355 | -945 | -590 | 60 | 65 | media geral T4c 21.4; media nas posicoes com conflito -8.9 |
| 2025 | 24 | 232 | -473 | -705 | 50 | 62 | media geral T4c 18.3; media nas posicoes com conflito 9.7 |
| 2026 | 29 | -2.225 | -656 | 1.569 | 76 | 69 | media geral T4c 26.8; media nas posicoes com conflito -76.7 |
| 2022-25 | 164 | -2.870 | -3.378 | -508 | 57 | 63 | media geral T4c 19.2; media nas posicoes com conflito -17.5 |
