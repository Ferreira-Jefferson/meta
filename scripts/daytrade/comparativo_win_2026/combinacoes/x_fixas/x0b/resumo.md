# X0b

## Prova: dias com pregao >= 18:25 nao mudam
WinDeslocamentoMatinal: dias 958 (>=18:25: 631, <18:25: 327); dias com operacao diferente: 45; destes em dias >=18:25: 0 []; em dias <18:25: 45
  ops antes 183 depois 183; liquido antes 5,039 depois 5,214
WinCincoMedias: dias 958 (>=18:25: 631, <18:25: 327); dias com operacao diferente: 123; destes em dias >=18:25: 0 []; em dias <18:25: 123
  ops antes 1734 depois 1734; liquido antes 717 depois 3,162

## Tabela por ano (ops / liquido sem custo / liquido com R$2) antes -> depois
| ano | Win | Win_c1 | WinCincoMedias | WinDeslocamentoMatinal | WinRetanguloEma34 |
|---|---|---|---|---|---|
| 2022 | 245 / -227 / -717 | 256 / 333 / -179 | 486 / -962 / -1,934 -> 486 / 33 / -939 | 46 / 405 / 313 -> 46 / 327 / 235 | 327 / -2,257 / -2,911 |
| 2023 | 214 / -1,257 / -1,685 | 226 / -987 / -1,439 | 460 / 1,731 / 811 -> 460 / 3,181 / 2,261 | 39 / 1,229 / 1,151 -> 39 / 1,482 / 1,404 | 184 / -1,053 / -1,421 |
| 2024 | 248 / -870 / -1,366 | 256 / -643 / -1,155 | 482 / -978 / -1,942 -> 482 / -978 / -1,942 | 56 / 1,459 / 1,347 -> 56 / 1,459 / 1,347 | 53 / -150 / -256 |
| 2025 | 179 / -918 / -1,276 | 186 / -57 / -429 | 306 / 926 / 314 -> 306 / 926 / 314 | 42 / 1,946 / 1,862 -> 42 / 1,946 / 1,862 | 124 / -608 / -856 |
| total | 886 / -3,272 / -5,044 | 924 / -1,354 / -3,202 | 1734 / 717 / -2,751 -> 1734 / 3,162 / -306 | 183 / 5,039 / 4,673 -> 183 / 5,214 / 4,848 | 688 / -4,068 / -5,444 |

## Motivos de saida depois da correcao (overnight / de outro dia)
Win: overnight=0, de outro dia=0; antes: overnight=0, de outro dia=0
Win_c1: overnight=0, de outro dia=0; antes: overnight=0, de outro dia=0
WinCincoMedias: overnight=0, de outro dia=0; antes: overnight=0, de outro dia=123
WinDeslocamentoMatinal: overnight=0, de outro dia=0; antes: overnight=30, de outro dia=0
WinRetanguloEma34: overnight=0, de outro dia=0; antes: overnight=0, de outro dia=0
