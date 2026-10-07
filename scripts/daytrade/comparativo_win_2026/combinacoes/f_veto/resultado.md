# Frente F: veto cruzado por posicao real contraria

Base: resultados/*.csv, WIN 02/01-05/10/2026, 5 estrategias (sem Win_c1; Win_c1 ~ Win), 1 contrato, R$1.000 corrido, quebra = saldo <= 0. **Celulas olhadas: 3** (f1, f2, f3), cada uma com custo 0 e R$2/op.

Regra: uma entrada de X e bloqueada se, na ultima M1 fechada antes dela, outra estrategia tem posicao REAL aberta do lado contrario (entrada < linha+1min <= saida; confere com `.posicao` da F0: 0 divergencias). f1: so a outra familia (tendencia = Win, Cinco, Desloc; retangulo = RetEma34, WdoRet). f2: qualquer outra (NETTING). f3: como f2, mas so se a contraria esta no lucro pelo close da ultima M1 fechada.

**Sem parametros, sem walk-forward** (as 3 celulas foram escritas antes). NAO e validacao fora da amostra: as bases foram escolhidas olhando 2026. As posicoes vetadoras vem do replay original (uma entrada vetada continua contando como posicao para vetar as outras: aproximacao); as saidas das demais ficam inalteradas.

## Referencias

| item | liquido s/custo | liquido R$2/op |
|---|---|---|
| Win isolada | 3.997 | 3.635 |
| WinCincoMedias isolada | 8.859 | 8.243 |
| WinDeslocamentoMatinal isolada | 2.219 | 2.089 |
| WinRetanguloEma34 isolada | 2.307 | 841 |
| WdoRetangulo isolada | 2.837 | 2.569 |
| **soma sem filtro (5 sem Win_c1, 1421 ops)** | 20.219 (DD 1.603) | 17.377 (DD 1.728) |
| melhor isolada: WinCincoMedias | 8.859 | 8.243 |

## Resumo (total jan-out)

`liq_vetadas` = o que as entradas vetadas teriam rendido (negativo = o veto acertou). `pct_sorteio` = percentil do liquido contra 200 sorteios que descartam ao acaso o mesmo numero de entradas por estrategia. `pct_placebo_lado` = contra 200 sorteios em que o lado de cada posicao vetadora e trocado ao acaso (`vetadas_no_placebo` = media de vetos desse placebo, ~metade das reais para f2 se os lados fossem independentes). Percentil alto = o veto faz melhor que o acaso.

| celula | custo | ops | vetadas | liquido | maxDD | lucro_DD | menor_saldo | quebrou | delta_vs_soma | liq_vetadas | pct_sorteio | pct_placebo_lado | vetadas_no_placebo |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| f1 | 0.0 | 1228 | 193 | 17010 | 1762 | 9.65 | 620 | nao | -3209 | 3209 | 33.5 | 80.5 | 224 |
| f1 | 2.0 | 1228 | 193 | 14554 | 1847 | 7.88 | 582 | nao | -2823 | 2823 | 33.5 | 80.0 | 224 |
| f2 | 0.0 | 1131 | 290 | 16175 | 1788 | 9.05 | 588 | nao | -4044 | 4044 | 27.8 | 96.5 | 387 |
| f2 | 2.0 | 1131 | 290 | 13913 | 1951 | 7.13 | 544 | nao | -3464 | 3464 | 27.8 | 94.0 | 387 |
| f3 | 0.0 | 1298 | 123 | 18736 | 1792 | 10.46 | 565 | nao | -1483 | 1483 | 33.0 | 78.0 | 117 |
| f3 | 2.0 | 1298 | 123 | 16140 | 1992 | 8.1 | 525 | nao | -1237 | 1237 | 33.0 | 78.5 | 117 |

## Estabilidade entre metades (delta do veto sem custo contra a soma sem filtro)

| celula | jan-mai | jun-out |
|---|---|---|
| f1 | -2613 | -596 |
| f2 | -3831 | -213 |
| f3 | -1006 | -477 |

## Vetadas por estrategia

| celula | Win | WinCincoMedias | WinDeslocamentoMatinal | WinRetanguloEma34 | WdoRetangulo |
|---|---|---|---|---|---|
| f1 | 12 | 45 | 2 | 105 | 29 |
| f2 | 12 | 48 | 3 | 188 | 39 |
| f3 | 3 | 9 | 1 | 88 | 22 |

## Tabelas mensais (liquido R$; por data de saida)

### Soma sem filtro

**sem custo**

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -136 | 852 | 161 | -505 | 36 | -41 | 280 | 930 | 2.370 | 50 | 3.997 | 181 |
| WinCincoMedias | 2.758 | 815 | 489 | 1.665 | 1.009 | -87 | 261 | 298 | 920 | 731 | 8.859 | 308 |
| WinDeslocamentoMatinal | -415 | -32 | 59 | 1.329 | 570 | -96 | 643 | 400 | 412 | -651 | 2.219 | 65 |
| WinRetanguloEma34 | 146 | -533 | 2.043 | 491 | -570 | 488 | 582 | 243 | -292 | -291 | 2.307 | 733 |
| WdoRetangulo | 1.253 | 964 | -260 | -497 | 834 | -276 | -406 | 415 | 1.338 | -528 | 2.837 | 134 |
| SOMA | 3.606 | 2.066 | 2.492 | 2.483 | 1.879 | -12 | 1.360 | 2.286 | 4.748 | -689 | 20.219 | 1.421 |

**R$2/op**

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -168 | 814 | 135 | -569 | -10 | -67 | 250 | 884 | 2.330 | 36 | 3.635 | 181 |
| WinCincoMedias | 2.696 | 757 | 449 | 1.581 | 939 | -171 | 205 | 208 | 860 | 719 | 8.243 | 308 |
| WinDeslocamentoMatinal | -429 | -46 | 45 | 1.317 | 556 | -106 | 625 | 386 | 396 | -655 | 2.089 | 65 |
| WinRetanguloEma34 | 52 | -719 | 1.697 | 361 | -722 | 352 | 512 | 125 | -478 | -339 | 841 | 733 |
| WdoRetangulo | 1.229 | 930 | -300 | -523 | 808 | -304 | -440 | 395 | 1.306 | -532 | 2.569 | 134 |
| SOMA | 3.380 | 1.736 | 2.026 | 2.167 | 1.571 | -296 | 1.152 | 1.998 | 4.414 | -771 | 17.377 | 1.421 |

### f1 - sem custo (quebra: nao; menor saldo R$ 620)

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -136 | 717 | 266 | -505 | 89 | -65 | 146 | 899 | 2.294 | 50 | 3.755 | 169 |
| WinCincoMedias | 2.305 | 497 | 366 | 1.456 | 1.091 | -50 | 120 | 347 | 974 | 731 | 7.837 | 263 |
| WinDeslocamentoMatinal | -537 | -32 | 59 | 924 | 570 | -96 | 643 | 400 | 412 | -651 | 1.692 | 63 |
| WinRetanguloEma34 | -17 | -785 | 1.535 | 440 | -538 | 326 | 491 | 62 | -163 | 134 | 1.485 | 628 |
| WdoRetangulo | 1.664 | 440 | -757 | 104 | 697 | 200 | -469 | -92 | 340 | 114 | 2.241 | 105 |
| SOMA | 3.279 | 837 | 1.469 | 2.419 | 1.909 | 315 | 931 | 1.616 | 3.857 | 378 | 17.010 | 1.228 |

### f1 - R$2/op (quebra: nao; menor saldo R$ 582)

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -168 | 685 | 244 | -569 | 47 | -87 | 118 | 855 | 2.256 | 36 | 3.417 | 169 |
| WinCincoMedias | 2.249 | 455 | 330 | 1.382 | 1.039 | -114 | 74 | 261 | 916 | 719 | 7.311 | 263 |
| WinDeslocamentoMatinal | -549 | -46 | 45 | 914 | 556 | -106 | 625 | 386 | 396 | -655 | 1.566 | 63 |
| WinRetanguloEma34 | -85 | -949 | 1.217 | 326 | -664 | 218 | 429 | -38 | -319 | 94 | 229 | 628 |
| WdoRetangulo | 1.642 | 414 | -793 | 88 | 677 | 180 | -499 | -108 | 318 | 112 | 2.031 | 105 |
| SOMA | 3.089 | 559 | 1.043 | 2.141 | 1.655 | 91 | 747 | 1.356 | 3.567 | 306 | 14.554 | 1.228 |

### f2 - sem custo (quebra: nao; menor saldo R$ 588)

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -136 | 717 | 266 | -505 | 89 | -65 | 146 | 899 | 2.294 | 50 | 3.755 | 169 |
| WinCincoMedias | 2.305 | 497 | 366 | 1.456 | 1.112 | -36 | 120 | 321 | 974 | 731 | 7.846 | 260 |
| WinDeslocamentoMatinal | -537 | -32 | 59 | 924 | 570 | -96 | 643 | 400 | 412 | -294 | 2.049 | 62 |
| WinRetanguloEma34 | 93 | -763 | 783 | 502 | -570 | 298 | 441 | 57 | 80 | 12 | 933 | 545 |
| WdoRetangulo | 1.405 | 654 | -1.325 | 44 | 721 | 200 | -469 | -92 | 340 | 114 | 1.592 | 95 |
| SOMA | 3.130 | 1.073 | 149 | 2.421 | 1.922 | 301 | 881 | 1.585 | 4.100 | 613 | 16.175 | 1.131 |

### f2 - R$2/op (quebra: nao; menor saldo R$ 544)

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -168 | 685 | 244 | -569 | 47 | -87 | 118 | 855 | 2.256 | 36 | 3.417 | 169 |
| WinCincoMedias | 2.249 | 455 | 330 | 1.382 | 1.062 | -98 | 74 | 237 | 916 | 719 | 7.326 | 260 |
| WinDeslocamentoMatinal | -549 | -46 | 45 | 914 | 556 | -106 | 625 | 386 | 396 | -296 | 1.925 | 62 |
| WinRetanguloEma34 | 29 | -891 | 533 | 400 | -684 | 194 | 385 | -39 | -60 | -24 | -157 | 545 |
| WdoRetangulo | 1.387 | 634 | -1.355 | 30 | 703 | 180 | -499 | -108 | 318 | 112 | 1.402 | 95 |
| SOMA | 2.948 | 837 | -203 | 2.157 | 1.684 | 83 | 703 | 1.331 | 3.826 | 547 | 13.913 | 1.131 |

### f3 - sem custo (quebra: nao; menor saldo R$ 565)

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -136 | 852 | 161 | -505 | 36 | -91 | 146 | 930 | 2.294 | 50 | 3.737 | 178 |
| WinCincoMedias | 2.758 | 917 | 366 | 1.678 | 1.119 | -150 | 261 | 298 | 974 | 731 | 8.952 | 299 |
| WinDeslocamentoMatinal | -537 | -32 | 59 | 1.329 | 570 | -96 | 643 | 400 | 412 | -651 | 2.097 | 64 |
| WinRetanguloEma34 | 90 | -941 | 1.343 | 508 | -712 | 178 | 375 | 85 | -98 | -50 | 778 | 645 |
| WdoRetangulo | 1.664 | 894 | -714 | 37 | 716 | 49 | -469 | -92 | 973 | 114 | 3.172 | 112 |
| SOMA | 3.839 | 1.690 | 1.215 | 3.047 | 1.729 | -110 | 956 | 1.621 | 4.555 | 194 | 18.736 | 1.298 |

### f3 - R$2/op (quebra: nao; menor saldo R$ 525)

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -168 | 814 | 135 | -569 | -10 | -115 | 118 | 884 | 2.256 | 36 | 3.381 | 178 |
| WinCincoMedias | 2.696 | 861 | 330 | 1.596 | 1.055 | -232 | 205 | 208 | 916 | 719 | 8.354 | 299 |
| WinDeslocamentoMatinal | -549 | -46 | 45 | 1.317 | 556 | -106 | 625 | 386 | 396 | -655 | 1.969 | 64 |
| WinRetanguloEma34 | 22 | -1.101 | 1.025 | 384 | -846 | 58 | 315 | -25 | -250 | -94 | -512 | 645 |
| WdoRetangulo | 1.642 | 866 | -748 | 17 | 694 | 27 | -499 | -108 | 945 | 112 | 2.948 | 112 |
| SOMA | 3.643 | 1.394 | 787 | 2.745 | 1.449 | -368 | 764 | 1.345 | 4.263 | 118 | 16.140 | 1.298 |
