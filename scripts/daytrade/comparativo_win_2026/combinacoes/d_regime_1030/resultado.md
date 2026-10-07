# Frente D: estado das 10:30 do Deslocamento como regime diario

Base: resultados/*.csv, WIN 02/01-05/10/2026, 5 estrategias (sem Win_c1; Win_c1 ~ Win), 1 contrato, R$1.000 corrido, quebra = saldo <= 0. **Celulas olhadas: 4** (d1-d4), cada uma com custo 0 e R$2/op.

**Sem parametros, sem walk-forward:** as regras foram escritas no TODO antes de rodar e nao ha nada a ajustar. Isto NAO e validacao fora da amostra: as 5 estrategias base foram escolhidas olhando 2026.

Regime = voto do WinDeslocamentoMatinal na barra da decisao (1a M1 do dia + 89 min, ~10:29-10:33 conforme a abertura, vale 1 min depois; "depois das 10:30" = entrada >= essa hora de decisao do dia). Dias: 29 compra, 37 venda, 124 sem sinal. Entradas antes das 10:30 nao sao afetadas. O Deslocamento fica isento (e a fonte do regime). Operacoes removidas, saidas das demais inalteradas (aproximacao: nao refaz a trajetoria da estrategia sem a entrada).

d1: tendencia (Win, Cinco) pos-10:30 so a favor do sinal, sem sinal vale tudo. d2: igual, mas sem sinal a tendencia nao opera. d3: retangulo (RetEma34, WdoRet) pos-10:30 so em dia sem sinal. d4 = d1 + d3.

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

`pct_sorteio_dias` = percentil do liquido contra 200 sorteios de DIAS que removem o mesmo numero de entradas pos-10:30 das mesmas estrategias; `pct_placebo_lado` = contra 200 sorteios com o lado do sinal de cada dia trocado ao acaso (d3 nao usa lado); `pct_perm_dias` = contra 200 permutacoes do estado (compra/venda/sem sinal) entre os dias. Percentil alto = a regra faz melhor que o acaso.

| celula | custo | ops | removidas | liquido | maxDD | lucro_DD | menor_saldo | quebrou | delta_vs_soma | pct_sorteio_dias | pct_placebo_lado | pct_perm_dias |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| d1 | 0.0 | 1408 | 13 | 20074 | 1603 | 12.52 | 558 | nao | -145 | 59.0 | 100.0 | 83.0 |
| d1 | 2.0 | 1408 | 13 | 17258 | 1804 | 9.57 | 510 | nao | -119 | 59.0 | 100.0 | 80.0 |
| d2 | 0.0 | 1179 | 242 | 18212 | 1658 | 10.98 | 601 | nao | -2007 | 99.5 | 99.5 | 100.0 |
| d2 | 2.0 | 1179 | 242 | 15854 | 1721 | 9.21 | 561 | nao | -1523 | 99.5 | 99.5 | 100.0 |
| d3 | 0.0 | 1162 | 259 | 19332 | 1524 | 12.69 | 661 | nao | -887 | 64.0 | - | 61.5 |
| d3 | 2.0 | 1162 | 259 | 17008 | 1570 | 10.83 | 589 | nao | -369 | 64.5 | - | 62.5 |
| d4 | 0.0 | 1149 | 272 | 19187 | 1550 | 12.38 | 661 | nao | -1032 | 84.5 | 100.0 | 80.5 |
| d4 | 2.0 | 1149 | 272 | 16889 | 1594 | 10.6 | 589 | nao | -488 | 84.5 | 100.0 | 79.0 |

## Contexto: R$/op das entradas pos-10:30 por estado (so descritivo, nao escolheu nada)

| estrategia | estado | n | R$/op | R$ total |
|---|---|---|---|---|
| WdoRetangulo | a favor | 18 | -43,61 | -785 |
| WdoRetangulo | contra | 21 | 0,76 | 16 |
| WdoRetangulo | sem sinal | 86 | 30,29 | 2.605 |
| Win | a favor | 20 | 46,15 | 923 |
| Win | contra | 1 | 114,00 | 114 |
| Win | sem sinal | 64 | 15,91 | 1.018 |
| WinCincoMedias | a favor | 50 | 59,68 | 2.984 |
| WinCincoMedias | contra | 12 | 2,58 | 31 |
| WinCincoMedias | sem sinal | 165 | 5,12 | 844 |
| WinDeslocamentoMatinal | a favor | 65 | 34,14 | 2.219 |
| WinRetanguloEma34 | a favor | 108 | 0,74 | 80 |
| WinRetanguloEma34 | contra | 112 | 14,07 | 1.576 |
| WinRetanguloEma34 | sem sinal | 407 | -0,02 | -7 |

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

### d1 - sem custo (quebra: nao; menor saldo R$ 558)

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -136 | 738 | 161 | -505 | 36 | -41 | 280 | 930 | 2.370 | 50 | 3.883 | 180 |
| WinCincoMedias | 2.758 | 723 | 489 | 1.665 | 1.071 | -169 | 261 | 248 | 934 | 848 | 8.828 | 296 |
| WinDeslocamentoMatinal | -415 | -32 | 59 | 1.329 | 570 | -96 | 643 | 400 | 412 | -651 | 2.219 | 65 |
| WinRetanguloEma34 | 146 | -533 | 2.043 | 491 | -570 | 488 | 582 | 243 | -292 | -291 | 2.307 | 733 |
| WdoRetangulo | 1.253 | 964 | -260 | -497 | 834 | -276 | -406 | 415 | 1.338 | -528 | 2.837 | 134 |
| SOMA | 3.606 | 1.860 | 2.492 | 2.483 | 1.941 | -94 | 1.360 | 2.236 | 4.762 | -572 | 20.074 | 1.408 |

### d1 - R$2/op (quebra: nao; menor saldo R$ 510)

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -168 | 702 | 135 | -569 | -10 | -67 | 250 | 884 | 2.330 | 36 | 3.523 | 180 |
| WinCincoMedias | 2.696 | 671 | 449 | 1.581 | 1.005 | -247 | 205 | 162 | 876 | 838 | 8.236 | 296 |
| WinDeslocamentoMatinal | -429 | -46 | 45 | 1.317 | 556 | -106 | 625 | 386 | 396 | -655 | 2.089 | 65 |
| WinRetanguloEma34 | 52 | -719 | 1.697 | 361 | -722 | 352 | 512 | 125 | -478 | -339 | 841 | 733 |
| WdoRetangulo | 1.229 | 930 | -300 | -523 | 808 | -304 | -440 | 395 | 1.306 | -532 | 2.569 | 134 |
| SOMA | 3.380 | 1.538 | 2.026 | 2.167 | 1.637 | -372 | 1.152 | 1.952 | 4.430 | -652 | 17.258 | 1.408 |

### d2 - sem custo (quebra: nao; menor saldo R$ 601)

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -124 | 492 | 85 | -175 | -53 | -83 | 311 | 318 | 2.044 | 50 | 2.865 | 116 |
| WinCincoMedias | 2.250 | 257 | -147 | 1.913 | 1.008 | 175 | 339 | 584 | 827 | 778 | 7.984 | 131 |
| WinDeslocamentoMatinal | -415 | -32 | 59 | 1.329 | 570 | -96 | 643 | 400 | 412 | -651 | 2.219 | 65 |
| WinRetanguloEma34 | 146 | -533 | 2.043 | 491 | -570 | 488 | 582 | 243 | -292 | -291 | 2.307 | 733 |
| WdoRetangulo | 1.253 | 964 | -260 | -497 | 834 | -276 | -406 | 415 | 1.338 | -528 | 2.837 | 134 |
| SOMA | 3.110 | 1.148 | 1.780 | 3.061 | 1.789 | 208 | 1.469 | 1.960 | 4.329 | -642 | 18.212 | 1.179 |

### d2 - R$2/op (quebra: nao; menor saldo R$ 561)

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -150 | 476 | 75 | -217 | -87 | -93 | 295 | 282 | 2.016 | 36 | 2.633 | 116 |
| WinCincoMedias | 2.214 | 237 | -161 | 1.873 | 978 | 155 | 315 | 540 | 801 | 770 | 7.722 | 131 |
| WinDeslocamentoMatinal | -429 | -46 | 45 | 1.317 | 556 | -106 | 625 | 386 | 396 | -655 | 2.089 | 65 |
| WinRetanguloEma34 | 52 | -719 | 1.697 | 361 | -722 | 352 | 512 | 125 | -478 | -339 | 841 | 733 |
| WdoRetangulo | 1.229 | 930 | -300 | -523 | 808 | -304 | -440 | 395 | 1.306 | -532 | 2.569 | 134 |
| SOMA | 2.916 | 878 | 1.356 | 2.811 | 1.533 | 4 | 1.307 | 1.728 | 4.041 | -720 | 15.854 | 1.179 |

### d3 - sem custo (quebra: nao; menor saldo R$ 661)

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -136 | 852 | 161 | -505 | 36 | -41 | 280 | 930 | 2.370 | 50 | 3.997 | 181 |
| WinCincoMedias | 2.758 | 815 | 489 | 1.665 | 1.009 | -87 | 261 | 298 | 920 | 731 | 8.859 | 308 |
| WinDeslocamentoMatinal | -415 | -32 | 59 | 1.329 | 570 | -96 | 643 | 400 | 412 | -651 | 2.219 | 65 |
| WinRetanguloEma34 | 157 | -766 | 859 | 429 | -569 | 277 | 548 | 45 | -327 | -2 | 651 | 513 |
| WdoRetangulo | 1.264 | 320 | 998 | -453 | 907 | 419 | -557 | -188 | 782 | 114 | 3.606 | 95 |
| SOMA | 3.628 | 1.189 | 2.566 | 2.465 | 1.953 | 472 | 1.175 | 1.485 | 4.157 | 242 | 19.332 | 1.162 |

### d3 - R$2/op (quebra: nao; menor saldo R$ 589)

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -168 | 814 | 135 | -569 | -10 | -67 | 250 | 884 | 2.330 | 36 | 3.635 | 181 |
| WinCincoMedias | 2.696 | 757 | 449 | 1.581 | 939 | -171 | 205 | 208 | 860 | 719 | 8.243 | 308 |
| WinDeslocamentoMatinal | -429 | -46 | 45 | 1.317 | 556 | -106 | 625 | 386 | 396 | -655 | 2.089 | 65 |
| WinRetanguloEma34 | 89 | -886 | 637 | 327 | -693 | 179 | 488 | -55 | -445 | -16 | -375 | 513 |
| WdoRetangulo | 1.248 | 298 | 968 | -477 | 891 | 401 | -583 | -202 | 760 | 112 | 3.416 | 95 |
| SOMA | 3.436 | 937 | 2.234 | 2.179 | 1.683 | 236 | 985 | 1.221 | 3.901 | 196 | 17.008 | 1.162 |

### d4 - sem custo (quebra: nao; menor saldo R$ 661)

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -136 | 738 | 161 | -505 | 36 | -41 | 280 | 930 | 2.370 | 50 | 3.883 | 180 |
| WinCincoMedias | 2.758 | 723 | 489 | 1.665 | 1.071 | -169 | 261 | 248 | 934 | 848 | 8.828 | 296 |
| WinDeslocamentoMatinal | -415 | -32 | 59 | 1.329 | 570 | -96 | 643 | 400 | 412 | -651 | 2.219 | 65 |
| WinRetanguloEma34 | 157 | -766 | 859 | 429 | -569 | 277 | 548 | 45 | -327 | -2 | 651 | 513 |
| WdoRetangulo | 1.264 | 320 | 998 | -453 | 907 | 419 | -557 | -188 | 782 | 114 | 3.606 | 95 |
| SOMA | 3.628 | 983 | 2.566 | 2.465 | 2.015 | 390 | 1.175 | 1.435 | 4.171 | 359 | 19.187 | 1.149 |

### d4 - R$2/op (quebra: nao; menor saldo R$ 589)

| estrategia | jan | fev | mar | abr | mai | jun | jul | ago | set | out | total | ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Win | -168 | 702 | 135 | -569 | -10 | -67 | 250 | 884 | 2.330 | 36 | 3.523 | 180 |
| WinCincoMedias | 2.696 | 671 | 449 | 1.581 | 1.005 | -247 | 205 | 162 | 876 | 838 | 8.236 | 296 |
| WinDeslocamentoMatinal | -429 | -46 | 45 | 1.317 | 556 | -106 | 625 | 386 | 396 | -655 | 2.089 | 65 |
| WinRetanguloEma34 | 89 | -886 | 637 | 327 | -693 | 179 | 488 | -55 | -445 | -16 | -375 | 513 |
| WdoRetangulo | 1.248 | 298 | 968 | -477 | 891 | 401 | -583 | -202 | 760 | 112 | 3.416 | 95 |
| SOMA | 3.436 | 739 | 2.234 | 2.179 | 1.749 | 160 | 985 | 1.175 | 3.917 | 315 | 16.889 | 1.149 |
