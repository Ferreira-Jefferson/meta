# Precursores de pernada (WIN, setembro/2026): estudo de evento e deteccao cedo

Pernada = perna >=750 pts do zigzag sobre o caminho dentro da vela. Pivos obtidos com zigzag de 100 pts (pivo = extremo local confirmado por recuo de 100); "chega a 750" = o movimento desse pivo ao proximo pivo de 100 foi >=750. Features calculadas SO com velas anteriores a vela do pivo (ou anteriores a vela em que o preco cruzou X). Sinal ajustado: valor positivo = a favor da nova pernada (para pernada de baixa, invertido). Janela de medicao: somente setembro/2026; agosto so como aquecimento dos indicadores e do volume relativo ao horario.

## M5

Pivos T=100: 2782; pernada >=750: 172 (8.2/pregao); respiros 250-750 (controle A): 1399; <250 (controle B): 1204; censurados (ultimo pivo aberto): 22

### Taxa-base de deteccao cedo: P(chegar a 750 | ja andou X do ultimo extremo)

| X (pts) | n eventos | chegaram a 750 | taxa | taxa sem censurados |
|---|---|---|---|---|
| 150 | 2316 | 172 | 7.4% | 172/2302 = 7.5% |
| 250 | 1578 | 172 | 10.9% | 172/1571 = 10.9% |
| 375 | 922 | 172 | 18.7% | 172/921 = 18.7% |
| 500 | 518 | 172 | 33.2% | 172/518 = 33.2% |

### Evento 1: pivo de pernada 750+ vs respiro 250-750 (o controle que importa)

| feature | n pernada | n respiro | mediana pernada | mediana respiro | dp pernada | dp respiro | AUC | z |
|---|---|---|---|---|---|---|---|---|
| atr5_50 | 172 | 1399 | 1.54 | 1.07 | 0.683 | 0.659 | 0.66 | +6.7 |
| atr14_50 | 172 | 1399 | 1.32 | 1.12 | 0.25 | 0.264 | 0.64 | +5.8 |
| lastrng_atr | 172 | 1399 | 1.16 | 0.933 | 1.08 | 0.659 | 0.63 | +5.5 |
| rng6_atr50 | 172 | 1399 | 3.43 | 2.66 | 2.86 | 2.15 | 0.63 | +5.4 |
| nr_rank | 172 | 1399 | 0.35 | 0.5 | 0.283 | 0.298 | 0.38 | -5.1 |
| m1_rv30_vs_rv300 | 160 | 1382 | 1.6 | 1.13 | 0.701 | 0.686 | 0.62 | +4.8 |
| rng12_atr50 | 172 | 1399 | 5.26 | 3.9 | 3.18 | 2.63 | 0.60 | +4.3 |
| min_since_open | 172 | 1399 | 92.5 | 165 | 184 | 143 | 0.40 | -4.3 |
| volrel3 | 172 | 1399 | 1.19 | 1.31 | 0.327 | 0.379 | 0.40 | -4.2 |
| hour | 172 | 1399 | 10 | 11 | 3.08 | 2.37 | 0.41 | -4.0 |
| m1_absret30_vs_atr | 160 | 1382 | 0.227 | 0.205 | 0.0723 | 0.0707 | 0.59 | +3.7 |
| volmax6 | 172 | 1399 | 1.61 | 1.73 | 0.502 | 0.646 | 0.42 | -3.2 |

### Evento 2: pivo de pernada 750+ vs oscilacao pequena (<250)

| feature | n pernada | n pequeno | mediana pernada | mediana pequeno | dp pernada | dp pequeno | AUC | z |
|---|---|---|---|---|---|---|---|---|
| atr5_50 | 172 | 1204 | 1.54 | 0.762 | 0.683 | 0.449 | 0.82 | +13.8 |
| atr14_50 | 172 | 1204 | 1.32 | 0.885 | 0.25 | 0.203 | 0.81 | +13.1 |
| rng6_atr50 | 172 | 1204 | 3.43 | 1.85 | 2.86 | 1.53 | 0.78 | +12.0 |
| m1_rv30_vs_rv300 | 160 | 1199 | 1.6 | 0.725 | 0.701 | 0.509 | 0.79 | +12.0 |
| rng12_atr50 | 172 | 1204 | 5.26 | 2.77 | 3.18 | 2.01 | 0.75 | +10.8 |
| hour | 172 | 1204 | 10 | 14 | 3.08 | 2.45 | 0.25 | -10.6 |
| min_since_open | 172 | 1204 | 92.5 | 338 | 184 | 146 | 0.25 | -10.6 |
| lastrng_atr | 172 | 1204 | 1.16 | 0.813 | 1.08 | 0.448 | 0.72 | +9.2 |

### Deteccao cedo X=150: quando o preco ja andou 150 pts, quem chega a 750 vs quem nao

| feature | n chega | n nao | mediana chega | mediana nao | dp chega | dp nao | AUC | z |
|---|---|---|---|---|---|---|---|---|
| atr5_50 | 172 | 2130 | 1.54 | 0.903 | 0.683 | 0.626 | 0.72 | +9.4 |
| atr14_50 | 172 | 2130 | 1.32 | 0.969 | 0.25 | 0.261 | 0.69 | +8.5 |
| rng6_atr50 | 172 | 2130 | 3.43 | 2.3 | 2.86 | 2.03 | 0.68 | +7.8 |
| lastrng_atr | 172 | 2130 | 1.16 | 0.855 | 1.09 | 0.613 | 0.67 | +7.5 |
| m1_rv30_vs_rv300 | 160 | 2109 | 1.6 | 0.899 | 0.703 | 0.665 | 0.67 | +7.3 |
| nr_rank | 172 | 2130 | 0.35 | 0.6 | 0.287 | 0.303 | 0.34 | -6.9 |
| rng12_atr50 | 172 | 2130 | 5.26 | 3.43 | 3.18 | 2.53 | 0.65 | +6.6 |
| min_since_open | 172 | 2130 | 92.5 | 215 | 185 | 154 | 0.35 | -6.4 |
| hour | 172 | 2130 | 10 | 12 | 3.08 | 2.56 | 0.36 | -6.3 |
| m1_absret30_vs_atr | 160 | 2109 | 0.227 | 0.195 | 0.0726 | 0.0682 | 0.63 | +5.5 |

### Deteccao cedo X=250: quando o preco ja andou 250 pts, quem chega a 750 vs quem nao

| feature | n chega | n nao | mediana chega | mediana nao | dp chega | dp nao | AUC | z |
|---|---|---|---|---|---|---|---|---|
| atr5_50 | 172 | 1399 | 1.54 | 1.06 | 0.685 | 0.658 | 0.66 | +6.9 |
| lastrng_atr | 172 | 1399 | 1.12 | 0.906 | 1.09 | 0.664 | 0.64 | +5.9 |
| atr14_50 | 172 | 1399 | 1.32 | 1.12 | 0.25 | 0.265 | 0.64 | +5.9 |
| rng6_atr50 | 172 | 1399 | 3.43 | 2.63 | 2.86 | 2.16 | 0.63 | +5.7 |
| nr_rank | 172 | 1399 | 0.35 | 0.5 | 0.284 | 0.302 | 0.37 | -5.5 |
| m1_rv30_vs_rv300 | 160 | 1382 | 1.6 | 1.13 | 0.703 | 0.686 | 0.62 | +4.9 |
| rng12_atr50 | 172 | 1399 | 5.26 | 3.89 | 3.18 | 2.64 | 0.60 | +4.3 |
| min_since_open | 172 | 1399 | 92.5 | 165 | 185 | 144 | 0.40 | -4.3 |
| hour | 172 | 1399 | 10 | 11 | 3.08 | 2.39 | 0.41 | -4.1 |
| volrel3 | 172 | 1399 | 1.18 | 1.3 | 0.327 | 0.373 | 0.41 | -3.8 |

### Deteccao cedo X=375: quando o preco ja andou 375 pts, quem chega a 750 vs quem nao

| feature | n chega | n nao | mediana chega | mediana nao | dp chega | dp nao | AUC | z |
|---|---|---|---|---|---|---|---|---|
| atr5_50 | 172 | 749 | 1.53 | 1.23 | 0.687 | 0.637 | 0.60 | +4.2 |
| volrel3 | 172 | 749 | 1.19 | 1.29 | 0.333 | 0.365 | 0.41 | -3.7 |
| rng6_atr50 | 172 | 749 | 3.39 | 2.91 | 2.86 | 2.18 | 0.59 | +3.5 |
| atr14_50 | 172 | 749 | 1.32 | 1.23 | 0.25 | 0.254 | 0.58 | +3.2 |
| volrel1 | 172 | 749 | 1.15 | 1.28 | 0.404 | 0.462 | 0.43 | -3.1 |
| lastrng_atr | 172 | 749 | 1.06 | 0.983 | 1.1 | 0.715 | 0.57 | +2.7 |
| volaccel | 172 | 749 | 0.969 | 1 | 0.176 | 0.184 | 0.44 | -2.7 |
| nr_rank | 172 | 749 | 0.35 | 0.45 | 0.296 | 0.29 | 0.44 | -2.6 |
| m1_rv30_vs_rv300 | 160 | 735 | 1.6 | 1.32 | 0.705 | 0.683 | 0.56 | +2.4 |
| rng12_atr50 | 172 | 749 | 5.09 | 4.27 | 3.19 | 2.65 | 0.56 | +2.3 |

### Historico (pivo: pernada vs respiro): perna anterior e contagem de pernadas na sessao

| medida | pernada mediana (n) | respiro mediana (n) | AUC | z |
|---|---|---|---|---|
| prev_e | 415 (151) | 320 (1398) | 0.62 | +5.0 |
| prev_bars | 1 (151) | 1 (1398) | 0.44 | -2.2 |
| nbig | 4 (172) | 5 (1399) | 0.35 | -6.5 |
| bar | 16 (172) | 34 (1399) | 0.26 | -10.5 |

### Hora do pivo (fracao dos pivos)

| hora | pernada | respiro |
|---|---|---|
| 9 | 36.0% | 15.9% |
| 10 | 37.8% | 19.1% |
| 11 | 12.8% | 17.4% |
| 12 | 4.1% | 12.4% |
| 13 | 2.9% | 9.8% |
| 14 | 2.9% | 8.5% |
| 15 | 2.9% | 6.9% |
| 16 | 0.6% | 5.9% |
| 17 | 0.0% | 3.1% |
| 18 | 0.0% | 1.1% |

### Taxa de sucesso (chegar a 750 | andou 250) por terco, 6 features de maior |z| (X=250)

| feature | terco baixo | terco medio | terco alto |
|---|---|---|---|
| atr5_50 | 29/525 = 6% | 46/522 = 9% | 97/524 = 19% |
| lastrng_atr | 32/524 = 6% | 55/523 = 11% | 85/524 = 16% |
| atr14_50 | 34/524 = 6% | 47/523 = 9% | 91/524 = 17% |
| rng6_atr50 | 36/525 = 7% | 53/522 = 10% | 83/524 = 16% |
| nr_rank | 93/588 = 16% | 48/478 = 10% | 31/505 = 6% |
| m1_rv30_vs_rv300 | 31/514 = 6% | 44/514 = 9% | 85/514 = 17% |

## M15

Pivos T=100: 1094; pernada >=750: 226 (10.8/pregao); respiros 250-750 (controle A): 599; <250 (controle B): 259; censurados (ultimo pivo aberto): 22

### Taxa-base de deteccao cedo: P(chegar a 750 | ja andou X do ultimo extremo)

| X (pts) | n eventos | chegaram a 750 | taxa | taxa sem censurados |
|---|---|---|---|---|
| 150 | 1023 | 226 | 22.1% | 226/1002 = 22.6% |
| 250 | 835 | 226 | 27.1% | 226/825 = 27.4% |
| 375 | 605 | 226 | 37.4% | 226/601 = 37.6% |
| 500 | 438 | 226 | 51.6% | 226/437 = 51.7% |

### Evento 1: pivo de pernada 750+ vs respiro 250-750 (o controle que importa)

| feature | n pernada | n respiro | mediana pernada | mediana respiro | dp pernada | dp respiro | AUC | z |
|---|---|---|---|---|---|---|---|---|
| m1_rv30_vs_rv300 | 216 | 578 | 1.42 | 0.83 | 0.707 | 0.636 | 0.68 | +7.9 |
| nr_rank | 226 | 599 | 0.25 | 0.6 | 0.297 | 0.306 | 0.33 | -7.7 |
| atr5_50 | 226 | 599 | 1.33 | 0.942 | 0.526 | 0.4 | 0.67 | +7.4 |
| hour | 226 | 599 | 10 | 13 | 2.99 | 2.47 | 0.34 | -7.0 |
| min_since_open | 226 | 599 | 105 | 255 | 178 | 149 | 0.34 | -7.0 |
| lastrng_atr | 226 | 599 | 1.18 | 0.83 | 0.715 | 0.637 | 0.65 | +6.7 |
| m1_absret30_vs_atr | 216 | 578 | 0.149 | 0.102 | 0.0633 | 0.0566 | 0.65 | +6.7 |
| rng6_atr50 | 226 | 599 | 3.22 | 2.49 | 1.87 | 1.39 | 0.64 | +6.3 |
| dayrange_pts | 226 | 599 | 2.46e+03 | 2.85e+03 | 1.18e+03 | 1.19e+03 | 0.41 | -4.0 |
| rng12_atr50 | 226 | 599 | 4.42 | 3.71 | 2.01 | 1.64 | 0.58 | +3.5 |
| volrel1 | 226 | 599 | 1.17 | 1.27 | 0.28 | 0.384 | 0.43 | -3.1 |
| volmax6 | 226 | 599 | 1.57 | 1.58 | 0.33 | 0.463 | 0.43 | -3.0 |

### Evento 2: pivo de pernada 750+ vs oscilacao pequena (<250)

| feature | n pernada | n pequeno | mediana pernada | mediana pequeno | dp pernada | dp pequeno | AUC | z |
|---|---|---|---|---|---|---|---|---|
| nr_rank | 226 | 259 | 0.25 | 0.75 | 0.297 | 0.264 | 0.22 | -10.8 |
| m1_rv30_vs_rv300 | 216 | 259 | 1.42 | 0.706 | 0.707 | 0.448 | 0.79 | +10.8 |
| hour | 226 | 259 | 10 | 15 | 2.99 | 2.28 | 0.23 | -10.4 |
| min_since_open | 226 | 259 | 105 | 360 | 178 | 136 | 0.23 | -10.4 |
| atr5_50 | 226 | 259 | 1.33 | 0.723 | 0.526 | 0.319 | 0.77 | +10.3 |
| lastrng_atr | 226 | 259 | 1.18 | 0.691 | 0.715 | 0.405 | 0.77 | +10.3 |
| m1_absret30_vs_atr | 216 | 259 | 0.149 | 0.0897 | 0.0633 | 0.0415 | 0.76 | +9.8 |
| rng6_atr50 | 226 | 259 | 3.22 | 1.79 | 1.87 | 1.14 | 0.75 | +9.5 |

### Deteccao cedo X=150: quando o preco ja andou 150 pts, quem chega a 750 vs quem nao

| feature | n chega | n nao | mediana chega | mediana nao | dp chega | dp nao | AUC | z |
|---|---|---|---|---|---|---|---|---|
| m1_rv30_vs_rv300 | 216 | 755 | 1.42 | 0.8 | 0.707 | 0.604 | 0.71 | +9.3 |
| nr_rank | 226 | 776 | 0.25 | 0.6 | 0.297 | 0.302 | 0.30 | -9.1 |
| atr5_50 | 226 | 776 | 1.33 | 0.879 | 0.526 | 0.392 | 0.69 | +8.7 |
| min_since_open | 226 | 776 | 105 | 285 | 178 | 150 | 0.32 | -8.4 |
| hour | 226 | 776 | 10 | 13 | 2.99 | 2.48 | 0.32 | -8.4 |
| lastrng_atr | 226 | 776 | 1.18 | 0.795 | 0.715 | 0.605 | 0.68 | +8.1 |
| m1_absret30_vs_atr | 216 | 755 | 0.149 | 0.0987 | 0.0633 | 0.054 | 0.68 | +8.0 |
| rng6_atr50 | 226 | 776 | 3.22 | 2.31 | 1.87 | 1.36 | 0.67 | +7.6 |
| dayrange_pts | 226 | 776 | 2.46e+03 | 2.86e+03 | 1.18e+03 | 1.17e+03 | 0.39 | -5.0 |
| rng12_atr50 | 226 | 776 | 4.42 | 3.6 | 2.01 | 1.61 | 0.60 | +4.7 |

### Deteccao cedo X=250: quando o preco ja andou 250 pts, quem chega a 750 vs quem nao

| feature | n chega | n nao | mediana chega | mediana nao | dp chega | dp nao | AUC | z |
|---|---|---|---|---|---|---|---|---|
| nr_rank | 226 | 599 | 0.25 | 0.6 | 0.3 | 0.312 | 0.32 | -8.0 |
| m1_rv30_vs_rv300 | 216 | 578 | 1.42 | 0.829 | 0.707 | 0.637 | 0.68 | +8.0 |
| atr5_50 | 226 | 599 | 1.33 | 0.935 | 0.526 | 0.403 | 0.67 | +7.5 |
| lastrng_atr | 226 | 599 | 1.18 | 0.812 | 0.716 | 0.644 | 0.66 | +7.0 |
| min_since_open | 226 | 599 | 105 | 255 | 178 | 150 | 0.34 | -7.0 |
| hour | 226 | 599 | 10 | 13 | 3 | 2.48 | 0.34 | -6.9 |
| m1_absret30_vs_atr | 216 | 578 | 0.149 | 0.102 | 0.0632 | 0.0567 | 0.66 | +6.8 |
| rng6_atr50 | 226 | 599 | 3.22 | 2.47 | 1.87 | 1.4 | 0.64 | +6.4 |
| dayrange_pts | 226 | 599 | 2.46e+03 | 2.85e+03 | 1.18e+03 | 1.19e+03 | 0.41 | -4.0 |
| rng12_atr50 | 226 | 599 | 4.42 | 3.71 | 2.01 | 1.64 | 0.58 | +3.5 |

### Deteccao cedo X=375: quando o preco ja andou 375 pts, quem chega a 750 vs quem nao

| feature | n chega | n nao | mediana chega | mediana nao | dp chega | dp nao | AUC | z |
|---|---|---|---|---|---|---|---|---|
| m1_rv30_vs_rv300 | 216 | 359 | 1.42 | 0.867 | 0.708 | 0.689 | 0.65 | +6.1 |
| nr_rank | 226 | 375 | 0.25 | 0.55 | 0.301 | 0.301 | 0.35 | -6.0 |
| atr5_50 | 226 | 375 | 1.33 | 0.989 | 0.527 | 0.421 | 0.64 | +5.7 |
| lastrng_atr | 226 | 375 | 1.17 | 0.842 | 0.719 | 0.654 | 0.63 | +5.3 |
| min_since_open | 226 | 375 | 105 | 210 | 178 | 146 | 0.37 | -5.2 |
| hour | 226 | 375 | 10 | 12 | 3.01 | 2.43 | 0.38 | -5.1 |
| m1_absret30_vs_atr | 216 | 359 | 0.149 | 0.108 | 0.0635 | 0.0606 | 0.62 | +5.0 |
| rng6_atr50 | 226 | 375 | 3.22 | 2.6 | 1.87 | 1.48 | 0.61 | +4.5 |
| bbwidth20 | 226 | 375 | 4.07 | 4.67 | 2.26 | 2.06 | 0.42 | -3.4 |
| dayrange_pts | 226 | 375 | 2.46e+03 | 2.82e+03 | 1.18e+03 | 1.18e+03 | 0.43 | -3.0 |

### Historico (pivo: pernada vs respiro): perna anterior e contagem de pernadas na sessao

| medida | pernada mediana (n) | respiro mediana (n) | AUC | z |
|---|---|---|---|---|
| prev_e | 670 (204) | 420 (599) | 0.67 | +7.5 |
| prev_bars | 1 (204) | 1 (599) | 0.52 | +0.9 |
| nbig | 5 (226) | 9 (599) | 0.29 | -9.5 |
| bar | 6 (226) | 17 (599) | 0.22 | -12.6 |

### Hora do pivo (fracao dos pivos)

| hora | pernada | respiro |
|---|---|---|
| 9 | 27.0% | 10.7% |
| 10 | 33.2% | 8.8% |
| 11 | 18.1% | 12.4% |
| 12 | 8.4% | 12.5% |
| 13 | 3.5% | 12.7% |
| 14 | 5.3% | 11.7% |
| 15 | 2.7% | 11.7% |
| 16 | 1.8% | 11.2% |
| 17 | 0.0% | 6.7% |
| 18 | 0.0% | 1.7% |

### Taxa de sucesso (chegar a 750 | andou 250) por terco, 6 features de maior |z| (X=250)

| feature | terco baixo | terco medio | terco alto |
|---|---|---|---|
| nr_rank | 128/290 = 44% | 64/293 = 22% | 34/242 = 14% |
| m1_rv30_vs_rv300 | 38/265 = 14% | 53/264 = 20% | 125/265 = 47% |
| atr5_50 | 47/275 = 17% | 52/275 = 19% | 127/275 = 46% |
| lastrng_atr | 42/275 = 15% | 67/275 = 24% | 117/275 = 43% |
| min_since_open | 139/299 = 46% | 44/264 = 17% | 43/262 = 16% |
| hour | 151/355 = 43% | 35/249 = 14% | 40/221 = 18% |

## H1

Pivos T=100: 320; pernada >=750: 157 (7.5/pregao); respiros 250-750 (controle A): 122; <250 (controle B): 22; censurados (ultimo pivo aberto): 22

### Taxa-base de deteccao cedo: P(chegar a 750 | ja andou X do ultimo extremo)

| X (pts) | n eventos | chegaram a 750 | taxa | taxa sem censurados |
|---|---|---|---|---|
| 150 | 316 | 157 | 49.7% | 157/294 = 53.4% |
| 250 | 298 | 157 | 52.7% | 157/279 = 56.3% |
| 375 | 259 | 157 | 60.6% | 157/247 = 63.6% |
| 500 | 221 | 157 | 71.0% | 157/217 = 72.4% |

### Evento 1: pivo de pernada 750+ vs respiro 250-750 (o controle que importa)

| feature | n pernada | n respiro | mediana pernada | mediana respiro | dp pernada | dp respiro | AUC | z |
|---|---|---|---|---|---|---|---|---|
| volaccel | 157 | 122 | 0.971 | 1.01 | 0.111 | 0.116 | 0.39 | -3.2 |
| volrel3 | 157 | 122 | 1.18 | 1.26 | 0.178 | 0.187 | 0.39 | -3.2 |
| rng6_atr50 | 157 | 122 | 2.51 | 2.77 | 1.27 | 1.05 | 0.41 | -2.6 |
| ret3_atr | 157 | 122 | -0.0494 | 0.206 | 1.32 | 0.99 | 0.41 | -2.6 |
| atr5_50 | 157 | 122 | 0.964 | 1.09 | 0.406 | 0.297 | 0.42 | -2.4 |
| min_since_open | 157 | 122 | 180 | 300 | 193 | 134 | 0.42 | -2.2 |
| hour | 157 | 122 | 12 | 14 | 3.22 | 2.24 | 0.42 | -2.2 |
| ret12_atr | 157 | 122 | -0.359 | 0.314 | 2.27 | 2.01 | 0.43 | -2.1 |
| dSMA50_atr | 157 | 122 | -0.245 | 0.298 | 2.68 | 2.67 | 0.43 | -2.0 |
| vol_per_pt | 157 | 122 | 0.987 | 1.06 | 0.508 | 0.368 | 0.43 | -1.9 |
| dSMA9_atr | 157 | 122 | -0.0343 | 0.116 | 1.09 | 0.852 | 0.43 | -1.9 |
| dSMA21_atr | 157 | 122 | -0.0815 | 0.212 | 1.65 | 1.42 | 0.43 | -1.9 |

### Evento 2: pivo de pernada 750+ vs oscilacao pequena (<250)

| feature | n pernada | n pequeno | mediana pernada | mediana pequeno | dp pernada | dp pequeno | AUC | z |
|---|---|---|---|---|---|---|---|---|
| dist_prevclose_pts | 157 | 22 | -165 | 662 | 1.85e+03 | 1.62e+03 | 0.37 | -2.0 |
| ret12_atr | 157 | 22 | -0.359 | 0.325 | 2.27 | 2.1 | 0.37 | -2.0 |
| compress_9_21_50 | 157 | 22 | 1.21 | 2.16 | 1.38 | 1.45 | 0.38 | -1.9 |
| macdhist_atr | 157 | 22 | -0.0105 | 0.0633 | 0.193 | 0.187 | 0.38 | -1.9 |
| slope9_atr | 157 | 22 | -0.108 | 0.249 | 0.884 | 0.764 | 0.38 | -1.8 |
| dSMA9_atr | 157 | 22 | -0.0343 | 0.164 | 1.09 | 0.984 | 0.38 | -1.8 |
| ret6_atr | 157 | 22 | -0.0926 | 0.829 | 1.56 | 1.43 | 0.38 | -1.8 |
| dSMA21_atr | 157 | 22 | -0.0815 | 0.336 | 1.65 | 1.54 | 0.39 | -1.7 |

### Deteccao cedo X=150: quando o preco ja andou 150 pts, quem chega a 750 vs quem nao

| feature | n chega | n nao | mediana chega | mediana nao | dp chega | dp nao | AUC | z |
|---|---|---|---|---|---|---|---|---|
| volaccel | 157 | 137 | 0.971 | 1.01 | 0.111 | 0.115 | 0.39 | -3.4 |
| volrel3 | 157 | 137 | 1.18 | 1.26 | 0.178 | 0.185 | 0.39 | -3.2 |
| ret3_atr | 157 | 137 | -0.0494 | 0.22 | 1.32 | 1.06 | 0.40 | -2.9 |
| rng6_atr50 | 157 | 137 | 2.51 | 2.77 | 1.27 | 1.06 | 0.40 | -2.8 |
| atr5_50 | 157 | 137 | 0.964 | 1.09 | 0.406 | 0.298 | 0.41 | -2.6 |
| ret12_atr | 157 | 137 | -0.359 | 0.323 | 2.27 | 2.07 | 0.42 | -2.4 |
| dSMA21_atr | 157 | 137 | -0.0815 | 0.295 | 1.65 | 1.48 | 0.42 | -2.3 |
| dSMA9_atr | 157 | 137 | -0.0343 | 0.119 | 1.09 | 0.89 | 0.43 | -2.2 |
| rsi14 | 157 | 137 | -0.83 | 2.61 | 12.8 | 11.9 | 0.43 | -2.2 |
| dSMA50_atr | 157 | 137 | -0.245 | 0.315 | 2.68 | 2.75 | 0.43 | -2.2 |

### Deteccao cedo X=250: quando o preco ja andou 250 pts, quem chega a 750 vs quem nao

| feature | n chega | n nao | mediana chega | mediana nao | dp chega | dp nao | AUC | z |
|---|---|---|---|---|---|---|---|---|
| volaccel | 157 | 122 | 0.971 | 1.01 | 0.111 | 0.116 | 0.39 | -3.2 |
| volrel3 | 157 | 122 | 1.18 | 1.26 | 0.178 | 0.187 | 0.39 | -3.2 |
| rng6_atr50 | 157 | 122 | 2.51 | 2.77 | 1.27 | 1.05 | 0.41 | -2.6 |
| ret3_atr | 157 | 122 | -0.0494 | 0.206 | 1.32 | 0.99 | 0.41 | -2.6 |
| atr5_50 | 157 | 122 | 0.964 | 1.09 | 0.406 | 0.297 | 0.42 | -2.4 |
| min_since_open | 157 | 122 | 180 | 300 | 193 | 134 | 0.42 | -2.2 |
| hour | 157 | 122 | 12 | 14 | 3.22 | 2.24 | 0.42 | -2.2 |
| ret12_atr | 157 | 122 | -0.359 | 0.314 | 2.27 | 2.01 | 0.43 | -2.1 |
| dSMA50_atr | 157 | 122 | -0.245 | 0.298 | 2.68 | 2.67 | 0.43 | -2.0 |
| vol_per_pt | 157 | 122 | 0.987 | 1.06 | 0.508 | 0.368 | 0.43 | -1.9 |

### Deteccao cedo X=375: quando o preco ja andou 375 pts, quem chega a 750 vs quem nao

| feature | n chega | n nao | mediana chega | mediana nao | dp chega | dp nao | AUC | z |
|---|---|---|---|---|---|---|---|---|
| rng6_atr50 | 157 | 90 | 2.51 | 2.78 | 1.27 | 0.964 | 0.39 | -2.8 |
| ret12_atr | 157 | 90 | -0.359 | 0.445 | 2.27 | 2 | 0.40 | -2.6 |
| atr5_50 | 157 | 90 | 0.964 | 1.09 | 0.406 | 0.273 | 0.40 | -2.5 |
| volrel3 | 157 | 90 | 1.18 | 1.25 | 0.178 | 0.172 | 0.41 | -2.4 |
| dist_prevday_ext_pts | 157 | 90 | 1.49e+03 | 2.15e+03 | 2.32e+03 | 2.3e+03 | 0.41 | -2.4 |
| dSMA50_atr | 157 | 90 | -0.245 | 0.377 | 2.68 | 2.65 | 0.41 | -2.4 |
| dSMA21_atr | 157 | 90 | -0.0815 | 0.368 | 1.65 | 1.42 | 0.41 | -2.3 |
| volaccel | 157 | 90 | 0.971 | 1.01 | 0.111 | 0.1 | 0.41 | -2.3 |
| rsi14 | 157 | 90 | -0.83 | 3.23 | 12.8 | 11.5 | 0.41 | -2.3 |
| vol_per_pt | 157 | 90 | 0.987 | 1.1 | 0.508 | 0.371 | 0.42 | -2.1 |

### Historico (pivo: pernada vs respiro): perna anterior e contagem de pernadas na sessao

| medida | pernada mediana (n) | respiro mediana (n) | AUC | z |
|---|---|---|---|---|
| prev_e | 1.08e+03 (135) | 668 (122) | 0.66 | +4.4 |
| prev_bars | 1 (135) | 1 (122) | 0.57 | +2.0 |
| nbig | 3 (157) | 6 (122) | 0.23 | -7.8 |
| bar | 2 (157) | 5.5 (122) | 0.23 | -7.7 |

### Hora do pivo (fracao dos pivos)

| hora | pernada | respiro |
|---|---|---|
| 9 | 22.3% | 3.3% |
| 10 | 15.9% | 4.1% |
| 11 | 13.4% | 10.7% |
| 12 | 13.4% | 9.8% |
| 13 | 11.5% | 9.8% |
| 14 | 11.5% | 12.3% |
| 15 | 5.7% | 16.4% |
| 16 | 4.5% | 19.7% |
| 17 | 1.9% | 13.9% |

### Taxa de sucesso (chegar a 750 | andou 250) por terco, 6 features de maior |z| (X=250)

| feature | terco baixo | terco medio | terco alto |
|---|---|---|---|
| volaccel | 60/93 = 65% | 49/93 = 53% | 48/93 = 52% |
| volrel3 | 59/94 = 63% | 59/92 = 64% | 39/93 = 42% |
| rng6_atr50 | 65/93 = 70% | 46/93 = 49% | 46/93 = 49% |
| ret3_atr | 62/93 = 67% | 50/93 = 54% | 45/93 = 48% |
| atr5_50 | 66/93 = 71% | 40/94 = 43% | 51/92 = 55% |
| min_since_open | 67/97 = 69% | 45/92 = 49% | 45/90 = 50% |


Total de comparacoes (features x tipo de teste x timeframe): 747. Com |z|>3 esperam-se ~2.0 por acaso; com |z|>2, ~34.

# Complemento: controle por horario e deteccao cedo condicionada

## M5: P(chegar a 750 | andou 250) por bloco de horario x tercil de volatilidade curta (atr5_50) e de m1_rv30_vs_rv300

**atr5_50** (tercis calculados dentro de cada bloco)

| bloco | baixo | medio | alto | n bloco | taxa bloco |
|---|---|---|---|---|---|
| 09-10:59 | 51/206 = 25% | 37/205 = 18% | 39/205 = 19% | 616 | 21% |
| 11-13:59 | 6/196 = 3% | 10/196 = 5% | 18/196 = 9% | 588 | 6% |
| 14+ | 4/123 = 3% | 3/122 = 2% | 4/122 = 3% | 367 | 3% |

**m1_rv30_vs_rv300** (tercis calculados dentro de cada bloco)

| bloco | baixo | medio | alto | n bloco | taxa bloco |
|---|---|---|---|---|---|
| 09-10:59 | 48/196 = 24% | 37/195 = 19% | 30/196 = 15% | 616 | 21% |
| 11-13:59 | 6/196 = 3% | 10/196 = 5% | 18/196 = 9% | 588 | 6% |
| 14+ | 4/123 = 3% | 3/122 = 2% | 4/122 = 3% | 367 | 3% |

**nr_rank** (tercis calculados dentro de cada bloco)

| bloco | baixo | medio | alto | n bloco | taxa bloco |
|---|---|---|---|---|---|
| 09-10:59 | 49/235 = 21% | 41/216 = 19% | 37/165 = 22% | 616 | 21% |
| 11-13:59 | 13/211 = 6% | 12/216 = 6% | 9/161 = 6% | 588 | 6% |
| 14+ | 4/124 = 3% | 4/129 = 3% | 3/114 = 3% | 367 | 3% |

### M5: Evento 1 so com pivos apos 11:00 (remove o efeito abertura)

| feature | n pernada | n respiro | mediana pernada | mediana respiro | AUC | z |
|---|---|---|---|---|---|---|
| atr14_pts | 45 | 910 | 421 | 340 | 0.67 | +3.8 |
| m1_rv30_vs_rv300 | 45 | 910 | 1.14 | 0.816 | 0.66 | +3.7 |
| hour | 45 | 910 | 11 | 13 | 0.34 | -3.6 |
| min_since_open | 45 | 910 | 175 | 250 | 0.34 | -3.6 |
| atr14_50 | 45 | 910 | 1.13 | 0.913 | 0.66 | +3.6 |
| atr5_50 | 45 | 910 | 1.03 | 0.807 | 0.64 | +3.2 |
| m1_absret30_vs_atr | 45 | 910 | 0.202 | 0.185 | 0.61 | +2.4 |
| rng12_atr50 | 45 | 910 | 3.45 | 3.12 | 0.61 | +2.4 |
| rng6_atr50 | 45 | 910 | 2.36 | 2.04 | 0.60 | +2.3 |
| dist_prevday_ext_pts | 45 | 910 | 885 | 1.66e+03 | 0.40 | -2.2 |

### M5: deteccao X=250 so apos 11:00 (n chega=45, n nao=910, taxa=4.7%)

| feature | mediana chega | mediana nao | AUC | z |
|---|---|---|---|---|
| atr14_pts | 421 | 337 | 0.67 | +3.9 |
| m1_rv30_vs_rv300 | 1.13 | 0.814 | 0.67 | +3.8 |
| min_since_open | 175 | 250 | 0.34 | -3.6 |
| hour | 11 | 13 | 0.34 | -3.6 |
| atr14_50 | 1.13 | 0.906 | 0.66 | +3.6 |
| atr5_50 | 1.02 | 0.785 | 0.65 | +3.3 |
| rng6_atr50 | 2.36 | 1.97 | 0.62 | +2.7 |
| rng12_atr50 | 3.45 | 3.04 | 0.61 | +2.5 |

### M5: taxa por direcao e por ordem do pivo na sessao (X=250)

- alta: 89/796 = 11.2%
- baixa: 83/775 = 10.7%

### M5: taxa (X=250) por tamanho da perna imediatamente anterior (prev_e, pts)

| faixa | n | chegou a 750 |
|---|---|---|
| 0-300 | 690 | 7% |
| 300-500 | 481 | 10% |
| 500-750 | 239 | 11% |
| 750-1100 | 100 | 18% |
| 1100-9999 | 39 | 33% |

### M5: taxa (X=250) por numero de pernadas 750+ ja ocorridas na sessao

| nbig | n | chegou a 750 |
|---|---|---|
| 0-0 | 23 | 96% |
| 1-2 | 317 | 14% |
| 3-5 | 499 | 11% |
| 6-9 | 496 | 8% |
| 10-98 | 236 | 5% |

- M5, X=250, atr5_50>1.2 E m1_rv30/rv300>1.2: 100/636 = 16% (resto: 8%); dos que chegam a 750, essa regra pega 100/172
- M5, X=250, atr5_50>1.4 E m1_rv30/rv300>1.4: 82/493 = 17% (resto: 8%); dos que chegam a 750, essa regra pega 82/172

## M15: P(chegar a 750 | andou 250) por bloco de horario x tercil de volatilidade curta (atr5_50) e de m1_rv30_vs_rv300

**atr5_50** (tercis calculados dentro de cada bloco)

| bloco | baixo | medio | alto | n bloco | taxa bloco |
|---|---|---|---|---|---|
| 09-10:59 | 47/85 = 55% | 42/85 = 49% | 47/83 = 57% | 253 | 54% |
| 11-13:59 | 13/98 = 13% | 14/97 = 14% | 41/98 = 42% | 293 | 23% |
| 14+ | 5/93 = 5% | 4/93 = 4% | 13/93 = 14% | 279 | 8% |

**m1_rv30_vs_rv300** (tercis calculados dentro de cada bloco)

| bloco | baixo | medio | alto | n bloco | taxa bloco |
|---|---|---|---|---|---|
| 09-10:59 | 54/75 = 72% | 40/73 = 55% | 32/74 = 43% | 253 | 54% |
| 11-13:59 | 13/99 = 13% | 14/96 = 15% | 41/98 = 42% | 293 | 23% |
| 14+ | 4/93 = 4% | 8/93 = 9% | 10/93 = 11% | 279 | 8% |

**nr_rank** (tercis calculados dentro de cada bloco)

| bloco | baixo | medio | alto | n bloco | taxa bloco |
|---|---|---|---|---|---|
| 09-10:59 | 56/105 = 53% | 37/83 = 45% | 43/65 = 66% | 253 | 54% |
| 11-13:59 | 34/99 = 34% | 25/106 = 24% | 9/88 = 10% | 293 | 23% |
| 14+ | 9/102 = 9% | 6/113 = 5% | 7/64 = 11% | 279 | 8% |

### M15: Evento 1 so com pivos apos 11:00 (remove o efeito abertura)

| feature | n pernada | n respiro | mediana pernada | mediana respiro | AUC | z |
|---|---|---|---|---|---|---|
| min_since_open | 90 | 482 | 165 | 300 | 0.25 | -7.4 |
| atr5_50 | 90 | 482 | 1.24 | 0.874 | 0.74 | +7.3 |
| hour | 90 | 482 | 11 | 14 | 0.26 | -7.2 |
| m1_absret30_vs_atr | 90 | 482 | 0.138 | 0.0965 | 0.72 | +6.7 |
| m1_rv30_vs_rv300 | 90 | 482 | 1.25 | 0.757 | 0.72 | +6.6 |
| rng6_atr50 | 90 | 482 | 2.94 | 2.26 | 0.70 | +6.1 |
| atr14_pts | 90 | 482 | 635 | 539 | 0.69 | +5.8 |
| rng12_atr50 | 90 | 482 | 4.68 | 3.64 | 0.69 | +5.6 |
| atr14_50 | 90 | 482 | 1.1 | 1.02 | 0.68 | +5.4 |
| nr_rank | 90 | 482 | 0.45 | 0.7 | 0.33 | -5.2 |

### M15: deteccao X=250 so apos 11:00 (n chega=90, n nao=482, taxa=15.7%)

| feature | mediana chega | mediana nao | AUC | z |
|---|---|---|---|---|
| min_since_open | 165 | 300 | 0.25 | -7.4 |
| atr5_50 | 1.24 | 0.869 | 0.74 | +7.3 |
| hour | 11 | 14 | 0.26 | -7.2 |
| m1_absret30_vs_atr | 0.138 | 0.0963 | 0.73 | +6.8 |
| m1_rv30_vs_rv300 | 1.25 | 0.746 | 0.72 | +6.7 |
| rng6_atr50 | 2.94 | 2.23 | 0.70 | +6.2 |
| atr14_pts | 635 | 539 | 0.69 | +5.8 |
| rng12_atr50 | 4.68 | 3.63 | 0.69 | +5.6 |

### M15: taxa por direcao e por ordem do pivo na sessao (X=250)

- alta: 110/420 = 26.2%
- baixa: 116/405 = 28.6%

### M15: taxa (X=250) por tamanho da perna imediatamente anterior (prev_e, pts)

| faixa | n | chegou a 750 |
|---|---|---|
| 0-300 | 213 | 12% |
| 300-500 | 216 | 21% |
| 500-750 | 171 | 24% |
| 750-1100 | 112 | 46% |
| 1100-9999 | 91 | 44% |

### M15: taxa (X=250) por numero de pernadas 750+ ja ocorridas na sessao

| nbig | n | chegou a 750 |
|---|---|---|
| 0-0 | 22 | 100% |
| 1-2 | 107 | 41% |
| 3-5 | 147 | 44% |
| 6-9 | 274 | 24% |
| 10-98 | 275 | 11% |

- M15, X=250, atr5_50>1.2 E m1_rv30/rv300>1.2: 118/245 = 48% (resto: 19%); dos que chegam a 750, essa regra pega 118/226
- M15, X=250, atr5_50>1.4 E m1_rv30/rv300>1.4: 78/145 = 54% (resto: 22%); dos que chegam a 750, essa regra pega 78/226
