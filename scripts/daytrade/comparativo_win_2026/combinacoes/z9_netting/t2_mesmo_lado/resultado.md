# Z9-T2 -- mesmo lado mantem, lado oposto inverte (WIN, conta NETTING, 1 contrato, R$1.000/ano, custo R$2/op)

Regras: T2 = sinal do mesmo lado ignorado (dono segue ate' a saida dele); T2b = saida passa a ser a mais tardia entre os que concordam; T2c = saida passa a ser a mais cedo. Sinal contrario: encerra a mercado a preco(t) (t = entrada do causador) e o novo robo assume a preco_entrada. Saida natural a preco_saida. Empate de segundo: ordem de ROBOS; saida natural em t <= entrada do sinal e' processada antes.
Aproximacao: robo interrompido/bloqueado/ignorado nao muda as operacoes seguintes dele; sinal so existe no instante da entrada.

## Por ano (liquido R$ c/ custo | ops | acerto % | maior queda R$ | quebra)

| ano | soma isolada | T2 liq | ops | acerto | queda | quebra | T2b liq | ops | acerto | queda | quebra | T2c liq | ops | acerto | queda | quebra |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2022 | +5.026 (473 ops) | +6.255 | 342 | 45.3 | 2188 | - | +6.204 | 340 | 45.6 | 2201 | - | +4.867 | 356 | 44.1 | 1955 | - |
| 2023 | +4.512 (455 ops) | +3.757 | 315 | 49.8 | 1656 | - | +3.673 | 315 | 50.2 | 1683 | - | +1.873 | 337 | 45.4 | 1615 | - |
| 2024 | +4.720 (477 ops) | +2.860 | 329 | 47.7 | 1756 | - | +2.930 | 324 | 48.8 | 1722 | - | +1.717 | 356 | 42.7 | 1850 | - |
| 2025 | +5.208 (344 ops) | +1.757 | 225 | 44.0 | 1522 | - | +1.836 | 224 | 44.2 | 1536 | - | +2.085 | 247 | 42.1 | 1228 | - |
| 2026 | +14.079 (361 ops) | +8.389 | 239 | 46.0 | 1661 | - | +8.286 | 236 | 46.6 | 1790 | - | +7.229 | 256 | 43.8 | 1460 | - |


## Por robo

### T2

| ano | robo | sinais | assumiram | ignorados (concordancia) | inverteram | foram invertidos | liquido R$ (atribuido ao dono) |
|---|---|---|---|---|---|---|---|
| 2022 | WinGapBarra1 | 126 | 126 | 0 | 0 | 51 | +2.300 |
| 2022 | WinCincoMedias | 195 | 149 | 46 | 43 | 7 | +3.096 |
| 2022 | WinDeslocamentoMatinal | 45 | 12 | 33 | 2 | 0 | +615 |
| 2022 | WinRetanguloEma34 | 75 | 46 | 29 | 16 | 5 | +377 |
| 2022 | Win_c1 | 32 | 9 | 23 | 2 | 0 | -133 |
| 2023 | WinGapBarra1 | 114 | 114 | 0 | 0 | 34 | +1.243 |
| 2023 | WinCincoMedias | 169 | 118 | 51 | 21 | 5 | +199 |
| 2023 | WinDeslocamentoMatinal | 39 | 16 | 23 | 1 | 1 | +1.764 |
| 2023 | WinRetanguloEma34 | 88 | 58 | 30 | 22 | 5 | +35 |
| 2023 | Win_c1 | 45 | 9 | 36 | 1 | 0 | +516 |
| 2024 | WinGapBarra1 | 109 | 109 | 0 | 0 | 36 | +1.757 |
| 2024 | WinCincoMedias | 192 | 140 | 52 | 25 | 4 | +669 |
| 2024 | WinDeslocamentoMatinal | 56 | 20 | 36 | 1 | 0 | +444 |
| 2024 | WinRetanguloEma34 | 79 | 49 | 30 | 17 | 4 | +184 |
| 2024 | Win_c1 | 41 | 11 | 30 | 1 | 0 | -194 |
| 2025 | WinGapBarra1 | 91 | 91 | 0 | 0 | 22 | +934 |
| 2025 | WinCincoMedias | 129 | 82 | 47 | 18 | 1 | -26 |
| 2025 | WinDeslocamentoMatinal | 41 | 18 | 23 | 1 | 1 | +711 |
| 2025 | WinRetanguloEma34 | 54 | 29 | 25 | 7 | 2 | -13 |
| 2025 | Win_c1 | 29 | 5 | 24 | 0 | 0 | +151 |
| 2026 | WinGapBarra1 | 90 | 90 | 0 | 0 | 21 | +7.029 |
| 2026 | WinCincoMedias | 130 | 95 | 35 | 21 | 4 | +1.305 |
| 2026 | WinDeslocamentoMatinal | 63 | 19 | 44 | 2 | 5 | -1.120 |
| 2026 | WinRetanguloEma34 | 47 | 25 | 22 | 8 | 2 | +963 |
| 2026 | Win_c1 | 31 | 10 | 21 | 1 | 0 | +212 |

### T2b

| ano | robo | sinais | assumiram | ignorados (concordancia) | inverteram | foram invertidos | liquido R$ (atribuido ao dono) |
|---|---|---|---|---|---|---|---|
| 2022 | WinGapBarra1 | 126 | 126 | 0 | 0 | 51 | +2.468 |
| 2022 | WinCincoMedias | 195 | 149 | 46 | 43 | 7 | +3.101 |
| 2022 | WinDeslocamentoMatinal | 45 | 12 | 33 | 2 | 0 | +621 |
| 2022 | WinRetanguloEma34 | 75 | 46 | 29 | 16 | 5 | +289 |
| 2022 | Win_c1 | 32 | 7 | 25 | 2 | 0 | -275 |
| 2023 | WinGapBarra1 | 114 | 114 | 0 | 0 | 34 | +1.211 |
| 2023 | WinCincoMedias | 169 | 118 | 51 | 21 | 5 | +244 |
| 2023 | WinDeslocamentoMatinal | 39 | 16 | 23 | 1 | 1 | +1.742 |
| 2023 | WinRetanguloEma34 | 88 | 58 | 30 | 23 | 5 | +1 |
| 2023 | Win_c1 | 45 | 9 | 36 | 1 | 1 | +475 |
| 2024 | WinGapBarra1 | 109 | 109 | 0 | 0 | 36 | +1.672 |
| 2024 | WinCincoMedias | 192 | 139 | 53 | 25 | 5 | +896 |
| 2024 | WinDeslocamentoMatinal | 56 | 20 | 36 | 1 | 0 | +446 |
| 2024 | WinRetanguloEma34 | 79 | 47 | 32 | 18 | 4 | +45 |
| 2024 | Win_c1 | 41 | 9 | 32 | 1 | 0 | -129 |
| 2025 | WinGapBarra1 | 91 | 91 | 0 | 0 | 22 | +893 |
| 2025 | WinCincoMedias | 129 | 82 | 47 | 18 | 1 | -26 |
| 2025 | WinDeslocamentoMatinal | 41 | 18 | 23 | 1 | 1 | +720 |
| 2025 | WinRetanguloEma34 | 54 | 28 | 26 | 7 | 2 | -10 |
| 2025 | Win_c1 | 29 | 5 | 24 | 0 | 0 | +259 |
| 2026 | WinGapBarra1 | 90 | 90 | 0 | 0 | 21 | +7.242 |
| 2026 | WinCincoMedias | 130 | 95 | 35 | 21 | 4 | +1.244 |
| 2026 | WinDeslocamentoMatinal | 63 | 19 | 44 | 2 | 5 | -1.121 |
| 2026 | WinRetanguloEma34 | 47 | 25 | 22 | 8 | 2 | +816 |
| 2026 | Win_c1 | 31 | 7 | 24 | 1 | 0 | +105 |

### T2c

| ano | robo | sinais | assumiram | ignorados (concordancia) | inverteram | foram invertidos | liquido R$ (atribuido ao dono) |
|---|---|---|---|---|---|---|---|
| 2022 | WinGapBarra1 | 126 | 126 | 0 | 0 | 41 | +820 |
| 2022 | WinCincoMedias | 195 | 154 | 41 | 40 | 7 | +3.094 |
| 2022 | WinDeslocamentoMatinal | 45 | 13 | 32 | 2 | 0 | +704 |
| 2022 | WinRetanguloEma34 | 75 | 48 | 27 | 10 | 5 | +560 |
| 2022 | Win_c1 | 32 | 15 | 17 | 1 | 0 | -311 |
| 2023 | WinGapBarra1 | 114 | 114 | 0 | 0 | 27 | +99 |
| 2023 | WinCincoMedias | 169 | 122 | 47 | 21 | 5 | -505 |
| 2023 | WinDeslocamentoMatinal | 39 | 17 | 22 | 0 | 1 | +1.719 |
| 2023 | WinRetanguloEma34 | 88 | 60 | 28 | 16 | 5 | -12 |
| 2023 | Win_c1 | 45 | 24 | 21 | 1 | 0 | +572 |
| 2024 | WinGapBarra1 | 109 | 109 | 0 | 0 | 27 | +926 |
| 2024 | WinCincoMedias | 192 | 151 | 41 | 23 | 3 | +1.022 |
| 2024 | WinDeslocamentoMatinal | 56 | 21 | 35 | 1 | 0 | +125 |
| 2024 | WinRetanguloEma34 | 79 | 53 | 26 | 9 | 4 | -53 |
| 2024 | Win_c1 | 41 | 22 | 19 | 1 | 0 | -303 |
| 2025 | WinGapBarra1 | 91 | 91 | 0 | 0 | 19 | +1.614 |
| 2025 | WinCincoMedias | 129 | 89 | 40 | 17 | 1 | -463 |
| 2025 | WinDeslocamentoMatinal | 41 | 19 | 22 | 1 | 1 | +825 |
| 2025 | WinRetanguloEma34 | 54 | 33 | 21 | 5 | 2 | +107 |
| 2025 | Win_c1 | 29 | 15 | 14 | 0 | 0 | +2 |
| 2026 | WinGapBarra1 | 90 | 90 | 0 | 0 | 19 | +6.805 |
| 2026 | WinCincoMedias | 130 | 100 | 30 | 20 | 4 | +193 |
| 2026 | WinDeslocamentoMatinal | 63 | 21 | 42 | 2 | 5 | -1.081 |
| 2026 | WinRetanguloEma34 | 47 | 29 | 18 | 7 | 2 | +855 |
| 2026 | Win_c1 | 31 | 16 | 15 | 1 | 0 | +457 |

## Inversoes por ano (T2)

| ano | inversoes |
|---|---|
| 2022 | 63 |
| 2023 | 45 |
| 2024 | 44 |
| 2025 | 26 |
| 2026 | 32 |
