# Frente E - Saida pela virada da outra familia (teste pareado)

Mesmas entradas (1.421 ops: Win 181, Cinco 308, Desloc 65, RetEma34 733, WdoRet 134; Win_c1 fora). Saida extra a MERCADO no `last` do 1o tick da M1 t+1 quando o voto vira contra numa M1 fechada t; vale so' se antes da saida original (stop/alvo originais intocados; a mercado e' aceitavel por ser saida condicional tipo stop). Familias: tendencia {Win, Cinco, Desloc}, retangulo {RetEma34, WdoRet}. V1 = outra familia INTEIRA contra; V2 = QUALQUER da outra contra; V3 = qualquer outra da PROPRIA familia (sem a propria) contra; a = sem, b = exigindo posicao no lucro no close da M1 t. **Celulas olhadas: 6 variantes pre-registradas x (5 estrategias + soma) = 36 celulas pareadas, mais 2 custos; nenhuma outra variante foi rodada.** Limitacao: as entradas seguintes da mesma estrategia no dia nao sao recalculadas.

## Soma das 5 (1 contrato cada, caixa R$1.000 corrido por ordem de saida), por mes da saida

### sem custo

| variante | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | caixa min | MaxDD | quebra |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| original | 3.606 | 2.066 | 2.492 | 2.483 | 1.879 | -12 | 1.360 | 2.286 | 4.748 | -689 | **20.219** | 558 | 1.603 | nao |
| V1a | 2.274 | 2.595 | 2.388 | 908 | 1.614 | -48 | 349 | 2.164 | 5.436 | -840 | **16.840** | 553 | 1.541 | nao |
| V1b | 2.278 | 2.150 | 2.415 | 406 | 2.244 | 33 | 558 | 2.016 | 5.019 | -843 | **16.276** | 544 | 1.710 | nao |
| V2a | 1.910 | 1.636 | 1.500 | 756 | 2.199 | -534 | 1.097 | 1.073 | 3.224 | 49 | **12.910** | 837 | 1.181 | nao |
| V2b | 2.020 | 1.358 | 1.166 | 969 | 1.500 | -92 | 636 | 910 | 3.800 | -635 | **11.632** | 670 | 1.877 | nao |
| V3a | 2.711 | 1.797 | 1.662 | 2.758 | 1.150 | -203 | 1.494 | 1.077 | 3.815 | -20 | **16.241** | 483 | 1.489 | nao |
| V3b | 3.361 | 1.484 | 1.694 | 2.720 | 1.164 | 252 | 1.676 | 1.727 | 3.767 | -806 | **17.039** | 433 | 1.673 | nao |

### R$2/op

| variante | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | caixa min | MaxDD | quebra |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| original | 3.380 | 1.736 | 2.026 | 2.167 | 1.571 | -296 | 1.152 | 1.998 | 4.414 | -771 | **17.377** | 510 | 1.728 | nao |
| V1a | 2.048 | 2.265 | 1.922 | 592 | 1.306 | -332 | 141 | 1.876 | 5.102 | -922 | **13.998** | 427 | 1.693 | nao |
| V1b | 2.052 | 1.820 | 1.949 | 90 | 1.936 | -251 | 350 | 1.728 | 4.685 | -925 | **13.434** | 466 | 1.863 | nao |
| V2a | 1.684 | 1.306 | 1.034 | 440 | 1.891 | -818 | 889 | 785 | 2.890 | -33 | **10.068** | 779 | 1.343 | nao |
| V2b | 1.794 | 1.028 | 700 | 653 | 1.192 | -376 | 428 | 622 | 3.466 | -717 | **8.790** | 622 | 1.981 | nao |
| V3a | 2.485 | 1.467 | 1.196 | 2.442 | 842 | -487 | 1.286 | 789 | 3.481 | -102 | **13.399** | 399 | 1.610 | nao |
| V3b | 3.135 | 1.154 | 1.228 | 2.404 | 856 | -32 | 1.468 | 1.439 | 3.433 | -888 | **14.197** | 385 | 1.707 | nao |

## Por estrategia, total (R$): original -> variante

### sem custo

| estrategia | original | V1a | V1b | V2a | V2b | V3a | V3b |
|---|---|---|---|---|---|---|---|
| Win | 3.997 | 4.090 | 4.009 | 3.892 | 4.178 | 3.822 | 3.873 |
| WinCincoMedias | 8.859 | 5.944 | 5.478 | 3.243 | 4.094 | 8.924 | 9.046 |
| WinDeslocamentoMatinal | 2.219 | 1.480 | 1.532 | 1.511 | 880 | 2.307 | 2.263 |
| WinRetanguloEma34 | 2.307 | 2.122 | 2.134 | 1.379 | 863 | 1.495 | 1.057 |
| WdoRetangulo | 2.837 | 3.204 | 3.123 | 2.885 | 1.617 | -307 | 800 |
| soma | 20.219 | 16.840 | 16.276 | 12.910 | 11.632 | 16.241 | 17.039 |

### R$2/op

| estrategia | original | V1a | V1b | V2a | V2b | V3a | V3b |
|---|---|---|---|---|---|---|---|
| Win | 3.635 | 3.728 | 3.647 | 3.530 | 3.816 | 3.460 | 3.511 |
| WinCincoMedias | 8.243 | 5.328 | 4.862 | 2.627 | 3.478 | 8.308 | 8.430 |
| WinDeslocamentoMatinal | 2.089 | 1.350 | 1.402 | 1.381 | 750 | 2.177 | 2.133 |
| WinRetanguloEma34 | 841 | 656 | 668 | -87 | -603 | 29 | -409 |
| WdoRetangulo | 2.569 | 2.936 | 2.855 | 2.617 | 1.349 | -575 | 532 |
| soma | 17.377 | 13.998 | 13.434 | 10.068 | 8.790 | 13.399 | 14.197 |

Nenhuma celula quebrou o caixa de R$1.000 (todas com caixa minimo > 0; ver colunas acima).

## Pareado: R$ da saida nova - R$ da original, por operacao (IC 95% bootstrap por dia, 2000 reamostras)

| variante | escopo | ops | afetadas | delta total R$ | media/op [IC] | media/afetada [IC] |
|---|---|---|---|---|---|---|
| V1a | soma | 1421 | 298 | -3.379 | -2.38 [-6.13; 1.14] | -11.34 [-29.12; 5.52] |
| V1a | Win | 181 | 24 | 93 | 0.51 [-1.13; 2.08] | 3.88 [-8.50; 15.71] |
| V1a | WinCincoMedias | 308 | 203 | -2.915 | -9.46 [-22.68; 1.48] | -14.36 [-34.09; 2.26] |
| V1a | WinDeslocamentoMatinal | 65 | 49 | -739 | -11.37 [-64.29; 39.30] | -15.08 [-85.60; 54.12] |
| V1a | WinRetanguloEma34 | 733 | 11 | -185 | -0.25 [-1.01; 0.38] | -16.82 [-52.67; 33.57] |
| V1a | WdoRetangulo | 134 | 11 | 367 | 2.74 [-6.14; 12.27] | 33.36 [-81.29; 151.02] |
| V1b | soma | 1421 | 182 | -3.943 | -2.77 [-6.38; 0.41] | -21.66 [-48.12; 3.30] |
| V1b | Win | 181 | 14 | 12 | 0.07 [-1.34; 1.46] | 0.86 [-19.00; 18.91] |
| V1b | WinCincoMedias | 308 | 119 | -3.381 | -10.98 [-22.84; -0.58] | -28.41 [-57.72; -1.47] |
| V1b | WinDeslocamentoMatinal | 65 | 37 | -687 | -10.57 [-53.29; 30.88] | -18.57 [-91.80; 54.59] |
| V1b | WinRetanguloEma34 | 733 | 8 | -173 | -0.24 [-0.85; 0.23] | -21.62 [-56.40; 40.00] |
| V1b | WdoRetangulo | 134 | 4 | 286 | 2.13 [-1.25; 7.23] | 71.50 [-72.00; 302.00] |
| V2a | soma | 1421 | 623 | -7.309 | -5.14 [-10.39; -0.01] | -11.73 [-23.64; -0.02] |
| V2a | Win | 181 | 70 | -105 | -0.58 [-6.12; 4.21] | -1.50 [-15.36; 10.93] |
| V2a | WinCincoMedias | 308 | 293 | -5.616 | -18.23 [-35.52; -1.66] | -19.17 [-37.44; -1.78] |
| V2a | WinDeslocamentoMatinal | 65 | 59 | -708 | -10.89 [-66.75; 42.23] | -12.00 [-72.46; 47.09] |
| V2a | WinRetanguloEma34 | 733 | 142 | -928 | -1.27 [-3.35; 0.75] | -6.54 [-16.86; 4.10] |
| V2a | WdoRetangulo | 134 | 59 | 48 | 0.36 [-24.37; 26.74] | 0.81 [-56.49; 61.21] |
| V2b | soma | 1421 | 416 | -8.587 | -6.04 [-10.53; -1.83] | -20.64 [-35.93; -6.39] |
| V2b | Win | 181 | 40 | 181 | 1.00 [-1.20; 3.16] | 4.53 [-5.50; 14.34] |
| V2b | WinCincoMedias | 308 | 179 | -4.765 | -15.47 [-33.19; -0.91] | -26.62 [-55.93; -1.48] |
| V2b | WinDeslocamentoMatinal | 65 | 45 | -1.339 | -20.60 [-71.86; 24.56] | -29.76 [-106.40; 36.18] |
| V2b | WinRetanguloEma34 | 733 | 112 | -1.444 | -1.97 [-3.74; -0.20] | -12.89 [-23.63; -1.45] |
| V2b | WdoRetangulo | 134 | 40 | -1.220 | -9.10 [-30.31; 10.96] | -30.50 [-97.74; 37.65] |
| V3a | soma | 1421 | 592 | -3.978 | -2.80 [-6.81; 1.41] | -6.72 [-16.41; 3.35] |
| V3a | Win | 181 | 2 | -175 | -0.97 [-3.28; 0.05] | -87.50 [-178.00; 3.00] |
| V3a | WinCincoMedias | 308 | 9 | 65 | 0.21 [-0.24; 0.77] | 7.22 [-13.21; 24.33] |
| V3a | WinDeslocamentoMatinal | 65 | 8 | 88 | 1.35 [-8.35; 10.52] | 11.00 [-70.92; 87.02] |
| V3a | WinRetanguloEma34 | 733 | 442 | -812 | -1.11 [-4.22; 1.75] | -1.84 [-6.96; 2.94] |
| V3a | WdoRetangulo | 134 | 131 | -3.144 | -23.46 [-61.58; 15.39] | -24.00 [-62.59; 16.04] |
| V3b | soma | 1421 | 256 | -3.180 | -2.24 [-5.15; 0.67] | -12.42 [-28.37; 3.54] |
| V3b | Win | 181 | 1 | -124 | -0.69 [-2.27; 0.00] | -124.00 [-124.00; -124.00] |
| V3b | WinCincoMedias | 308 | 5 | 187 | 0.61 [-0.04; 1.68] | 37.40 [-13.00; 62.50] |
| V3b | WinDeslocamentoMatinal | 65 | 2 | 44 | 0.68 [-0.93; 3.14] | 22.00 [-22.00; 66.00] |
| V3b | WinRetanguloEma34 | 733 | 145 | -1.250 | -1.71 [-3.68; 0.11] | -8.62 [-17.31; 0.61] |
| V3b | WdoRetangulo | 134 | 103 | -2.037 | -15.20 [-43.66; 12.66] | -19.78 [-56.89; 16.12] |

## Controles (200 sorteios): percentil do delta total real (maior = real melhor que o sorteio)

Sorteio de instante: os atrasos (M1 desde a entrada) das saidas disparadas sao permutados entre as mesmas operacoes (nas variantes b, exige lucro no instante sorteado). Placebo: voto da outra familia/propria trocado por lado sorteado, persistente em cada trecho continuo de voto.

| variante | escopo | disparadas | delta real | sorteio medio (p95) | pct sorteio | placebo medio (p95) | pct placebo |
|---|---|---|---|---|---|---|---|
| V1a | soma | 298 | -3.379 | -9.185 (-7.427) | 100.0 | -4.040 (-2.189) | 72.5 |
| V1a | Win | 24 | 93 | 76 (305) | 54.2 | 73 (285) | 56.7 |
| V1a | WinCincoMedias | 203 | -2.915 | -7.396 (-5.885) | 100.0 | -3.018 (-1.615) | 57.0 |
| V1a | WinDeslocamentoMatinal | 49 | -739 | -2.499 (-1.545) | 99.0 | -1.168 (-278) | 83.5 |
| V1a | WinRetanguloEma34 | 11 | -185 | -44 (88) | 5.0 | -43 (134) | 10.2 |
| V1a | WdoRetangulo | 11 | 367 | 679 (990) | 4.5 | 116 (602) | 79.0 |
| V1b | soma | 182 | -3.943 | -6.202 (-4.344) | 96.5 | -3.467 (-1.655) | 30.5 |
| V1b | Win | 14 | 12 | 42 (180) | 36.0 | 91 (295) | 24.0 |
| V1b | WinCincoMedias | 119 | -3.381 | -4.962 (-3.238) | 94.5 | -2.885 (-1.607) | 28.0 |
| V1b | WinDeslocamentoMatinal | 37 | -687 | -1.358 (-384) | 88.0 | -652 (183) | 48.0 |
| V1b | WinRetanguloEma34 | 8 | -173 | -9 (92) | 0.0 | -26 (134) | 5.5 |
| V1b | WdoRetangulo | 4 | 286 | 85 (357) | 88.0 | 6 (338) | 88.0 |
| V2a | soma | 623 | -7.309 | -7.313 (-5.461) | 51.2 | -13.507 (-10.078) | 100.0 |
| V2a | Win | 70 | -105 | -317 (357) | 71.0 | -2.111 (-963) | 99.5 |
| V2a | WinCincoMedias | 293 | -5.616 | -6.257 (-4.791) | 78.5 | -7.305 (-5.691) | 97.0 |
| V2a | WinDeslocamentoMatinal | 59 | -708 | -2.375 (-1.338) | 99.5 | -1.972 (-1.077) | 98.5 |
| V2a | WinRetanguloEma34 | 142 | -928 | -514 (54) | 10.5 | -376 (360) | 11.0 |
| V2a | WdoRetangulo | 59 | 48 | 2.149 (2.784) | 0.0 | -1.743 (-299) | 98.0 |
| V2b | soma | 416 | -8.587 | -8.980 (-6.471) | 60.0 | -13.698 (-10.717) | 99.5 |
| V2b | Win | 40 | 181 | -394 (101) | 97.5 | -1.652 (-613) | 100.0 |
| V2b | WinCincoMedias | 179 | -4.765 | -5.721 (-3.995) | 80.5 | -6.463 (-4.944) | 97.5 |
| V2b | WinDeslocamentoMatinal | 45 | -1.339 | -1.907 (-454) | 74.0 | -2.173 (-1.188) | 89.8 |
| V2b | WinRetanguloEma34 | 112 | -1.444 | -351 (134) | 0.0 | -807 (-84) | 7.0 |
| V2b | WdoRetangulo | 40 | -1.220 | -607 (354) | 16.5 | -2.602 (-1.256) | 95.7 |
| V3a | soma | 592 | -3.978 | -212 (685) | 0.0 | -14.168 (-11.385) | 100.0 |
| V3a | Win | 2 | -175 | -137 (3) | 49.0 | -1.994 (-1.035) | 100.0 |
| V3a | WinCincoMedias | 9 | 65 | 304 (417) | 0.0 | -5.321 (-3.369) | 100.0 |
| V3a | WinDeslocamentoMatinal | 8 | 88 | 504 (692) | 0.0 | -2.518 (-1.439) | 100.0 |
| V3a | WinRetanguloEma34 | 442 | -812 | 2.452 (3.156) | 0.0 | -1.308 (-207) | 79.5 |
| V3a | WdoRetangulo | 131 | -3.144 | -3.336 (-2.671) | 68.0 | -3.027 (-2.148) | 43.5 |
| V3b | soma | 256 | -3.180 | -2.728 (-981) | 32.5 | -14.127 (-11.312) | 100.0 |
| V3b | Win | 1 | -124 | -20 (26) | 2.5 | -1.835 (-998) | 100.0 |
| V3b | WinCincoMedias | 5 | 187 | 175 (293) | 51.7 | -5.181 (-3.364) | 100.0 |
| V3b | WinDeslocamentoMatinal | 2 | 44 | 88 (238) | 29.5 | -2.230 (-1.086) | 100.0 |
| V3b | WinRetanguloEma34 | 145 | -1.250 | -153 (392) | 0.0 | -1.533 (-588) | 66.5 |
| V3b | WdoRetangulo | 103 | -2.037 | -2.818 (-973) | 81.5 | -3.348 (-2.214) | 98.5 |

## Leitura
- Nenhuma variante melhora a soma: delta total entre -3.180 e -8.587 R$ (sem custo); IC 95% da media por operacao inclui zero em V1a, V1b, V3a, V3b e fica abaixo de zero so' em V2a/V2b (as mais agressivas, que disparam em 44% das ops). Sair pela virada devolve o alvo/ganho que a saida original ia colher.
- Contra o sorteio de instante: V1a (outra familia inteira) e' o melhor que o acaso (pct 100) e V1b 96,5, mas ainda negativo contra a original: a virada perde MENOS que sair cedo ao acaso, nao ganha. V2 (pct 51-60) e V3 (0-33) nao se distinguem do acaso ou ficam abaixo.
- Placebo: V2 e V3 sao MELHORES que o placebo (pct 99-100), mas o placebo dispara muito mais cedo e perde bem mais; contra o placebo V1 nao se destaca (30-72).
- Por estrategia: o dano vem do WinCincoMedias (-2,9 a -5,6 mil em V1/V2) e do RetEma34/WdoRet em V2/V3; ganhos pontuais em Win (V2b +181) e WdoRet (V1a +367, V1b +286, V2a +48) sao pequenos e com poucas ops. Com 36 celulas olhadas e correcao de Bonferroni (6 variantes) nada sobrevive.
