# Z9-T6 EA maestro (posicao liquida = soma dos sinais)

Premissas: cada sub-ordem executa ao preco_entrada/preco_saida do robo (bruto = soma isolada, conferido: diferenca 0 em todos os anos);
custo R$1 por contrato de variacao da posicao liquida (eventos simultaneos sao netados); cada ano parte de R$1.000;
saldo minimo marcado a mercado nos instantes de evento com preco(t) (nao ve picos entre eventos). Tetos: o teto vale na ENTRADA
(sinal que estouraria e' ignorado); a saida de uma perna oposta pode empurrar |pos| acima do teto (ex.: cap2 chegou a 3 em 2024).

| ano | variante | liquido c/ custo | bruto | custo | ops/contratos | maior queda | saldo min realizado | saldo min a mercado | max contratos | margem (R$100/ct) | quebra |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2022 | isolada(5 contas) | 5,026 | - | 946 | 473/473 | 2,315 | - | - | - | - | nao |
| 2022 | T6 | 5,028 | 5,972 | 944 | 473/946 | 2,537 | 994 | 985 | 4 | 400 | nao |
| 2022 | T6-cap2 | 4,903 | 5,787 | 884 | 443/886 | 2,445 | 998 | 985 | 2 | 200 | nao |
| 2022 | T6-cap1 | 5,462 | 6,146 | 684 | 342/684 | 1,785 | 999 | 985 | 2 | 200 | nao |
| 2023 | isolada(5 contas) | 4,512 | - | 910 | 455/455 | 2,108 | - | - | - | - | nao |
| 2023 | T6 | 4,514 | 5,422 | 908 | 455/910 | 2,170 | 998 | 989 | 4 | 400 | nao |
| 2023 | T6-cap2 | 4,610 | 5,456 | 846 | 424/848 | 1,891 | 998 | 989 | 2 | 200 | nao |
| 2023 | T6-cap1 | 3,755 | 4,367 | 612 | 307/614 | 1,341 | 999 | 989 | 2 | 200 | nao |
| 2024 | isolada(5 contas) | 4,720 | - | 954 | 477/477 | 1,883 | - | - | - | - | nao |
| 2024 | T6 | 4,726 | 5,674 | 948 | 477/954 | 2,031 | 867 | 866 | 4 | 400 | nao |
| 2024 | T6-cap2 | 4,422 | 5,304 | 882 | 444/888 | 2,105 | 650 | 524 | 3 | 300 | nao |
| 2024 | T6-cap1 | 3,270 | 3,920 | 650 | 328/656 | 1,923 | 829 | 817 | 2 | 200 | nao |
| 2025 | isolada(5 contas) | 5,208 | - | 688 | 344/344 | 3,112 | - | - | - | - | nao |
| 2025 | T6 | 5,212 | 5,896 | 684 | 344/688 | 3,163 | 982 | 910 | 4 | 400 | nao |
| 2025 | T6-cap2 | 3,541 | 4,163 | 622 | 313/626 | 3,448 | 982 | 910 | 2 | 200 | nao |
| 2025 | T6-cap1 | 2,619 | 3,059 | 440 | 222/444 | 2,375 | 999 | 999 | 2 | 200 | nao |
| 2026 | isolada(5 contas) | 14,079 | - | 722 | 361/361 | 3,335 | - | - | - | - | nao |
| 2026 | T6 | 14,087 | 14,801 | 714 | 361/722 | 3,350 | 622 | 700 | 4 | 400 | nao |
| 2026 | T6-cap2 | 13,103 | 13,769 | 666 | 337/674 | 3,308 | 745 | 745 | 2 | 200 | nao |
| 2026 | T6-cap1 | 6,769 | 7,253 | 484 | 245/490 | 2,248 | 745 | 745 | 2 | 200 | nao |

Custo da isolada = R$2/op. Maior queda do maestro e' a mercado nos eventos; da isolada, por saidas.

## Horas por |posicao| (T6, intervalos dentro do mesmo dia entre eventos; 0 = flat entre eventos)

| ano | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| 2022 | 261 | 1013 | 209 | 56 | 3 |
| 2023 | 147 | 979 | 292 | 54 | 4 |
| 2024 | 170 | 1061 | 326 | 63 | 2 |
| 2025 | 102 | 749 | 262 | 59 | 9 |
| 2026 | 115 | 694 | 280 | 65 | 2 |

T6 liquido 5 anos = 33,567; isolada = 33,545.
