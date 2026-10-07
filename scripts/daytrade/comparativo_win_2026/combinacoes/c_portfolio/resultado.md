# Frente C: portfolio com teto de K contratos simultaneos

Base: resultados/*.csv, WIN 02/01-05/10/2026, 1 contrato por estrategia, conta R$1.000. **Celulas olhadas: 48** (4 conjuntos x K{1,2,3} x prioridade{chegada, ranking} x {independente, NETTING}), cada uma com custo 0 e R$2/op. A escolha walk-forward abaixo so recombina essas celulas.

**Premissas.** (1) A saida de cada estrategia e a gravada no CSV; uma entrada cortada some. (2) Teto: entrada so aceita se posicoes abertas (de qualquer estrategia) < K; saida no mesmo minuto libera a vaga. (3) NETTING: entrada contraria a posicao aberta de outra estrategia e BLOQUEADA (coluna bloq.), contada a parte do corte por teto; a ordem de checagem e netting primeiro, teto depois. (4) Prioridade so atua em empate de minuto de entrada; "chegada" = ordem estavel do CSV, "ranking" = R$/op dos meses anteriores (walk-forward; jan sem historico = ordem alfabetica). Como estrategias raramente entram no mesmo minuto, as duas prioridades diferem pouco. (5) Caixa corrido por ordem de saida, quebra = saldo <= 0 (portfolio para). A margem do WIN nao e checada (R$1.000 cobre 3 contratos). (6) Pior saldo intradia = saldo fechado + resultado final das operacoes abertas, no pior instante (aproximacao). (7) O teto de 10% do saldo do Deslocamento usa o saldo da propria estrategia, nao o caixa comum: desvio declarado, nao recalculado. (8) Bases escolhidas olhando 2026: o walk-forward protege so a camada de combinacao.

## Referencias

| item | liquido s/custo | liquido R$2/op |
|---|---|---|
| WdoRetangulo isolada | 2.837 | 2.569 |
| Win isolada | 3.997 | 3.635 |
| WinCincoMedias isolada | 8.859 | 8.243 |
| WinDeslocamentoMatinal isolada | 2.219 | 2.089 |
| WinRetanguloEma34 isolada | 2.307 | 841 |
| Win_c1 isolada | 3.799 | 3.425 |
| soma sem teto: 5 sem Win_c1 (1421 ops) | 20.219 (DD 1.603) | 17.377 (DD 1.728) |
| soma sem teto: 5 sem Win (1427 ops) | 20.021 (DD 1.659) | 17.167 (DD 1.715) |
| soma sem teto: 4 sem WdoRet (Win) (1287 ops) | 17.382 (DD 1.316) | 14.808 (DD 1.424) |
| soma sem teto: 4 sem WdoRet (Win_c1) (1293 ops) | 17.184 (DD 1.527) | 14.598 (DD 1.635) |

Melhor isolada: WinCincoMedias.

## Resumo das celulas (total jan-out)

`pct liq` = percentil do liquido da celula entre 200 sorteios que removem ao acaso a mesma quantidade de entradas (cortes + bloqueios); `pct DD` = % dos sorteios com maior queda que a celula (alto = celula protege mais que o acaso).

| conjunto | K | prio | visao | custo | ops | acerto% | liquido | maxDD | lucro/DD | menor saldo | pior intradia | quebrou | cortes teto | bloq netting | pct liq | pct DD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 sem Win_c1 | 1 | chegada | independente | 0 | 897 | 40,6 | 7.913 | 1.952 | 4,05 | 507 | 507 | nao | 524 | 0 | 1,0 | 15,0 |
| 5 sem Win_c1 | 1 | chegada | independente | 2 | 897 | 40,5 | 6.119 | 2.006 | 3,05 | 467 | 467 | nao | 524 | 0 | 2,0 | 27,0 |
| 5 sem Win_c1 | 1 | chegada | NETTING | 0 | 897 | 40,6 | 7.913 | 1.952 | 4,05 | 507 | 507 | nao | 338 | 186 | 2,0 | 20,0 |
| 5 sem Win_c1 | 1 | chegada | NETTING | 2 | 897 | 40,5 | 6.119 | 2.006 | 3,05 | 467 | 467 | nao | 338 | 186 | 3,5 | 27,0 |
| 5 sem Win_c1 | 1 | ranking | independente | 0 | 892 | 39,6 | 6.778 | 1.952 | 3,47 | 507 | 507 | nao | 529 | 0 | 0,0 | 17,0 |
| 5 sem Win_c1 | 1 | ranking | independente | 2 | 892 | 39,5 | 4.994 | 2.006 | 2,49 | 467 | 467 | nao | 529 | 0 | 0,5 | 23,0 |
| 5 sem Win_c1 | 1 | ranking | NETTING | 0 | 892 | 39,6 | 6.778 | 1.952 | 3,47 | 507 | 507 | nao | 344 | 185 | 0,5 | 22,5 |
| 5 sem Win_c1 | 1 | ranking | NETTING | 2 | 892 | 39,5 | 4.994 | 2.006 | 2,49 | 467 | 467 | nao | 344 | 185 | 0,5 | 25,0 |
| 5 sem Win_c1 | 2 | chegada | independente | 0 | 1301 | 42,3 | 17.248 | 1.585 | 10,88 | 631 | 631 | nao | 120 | 0 | 20,5 | 69,0 |
| 5 sem Win_c1 | 2 | chegada | independente | 2 | 1301 | 42,1 | 14.646 | 1.676 | 8,74 | 587 | 587 | nao | 120 | 0 | 14,5 | 76,5 |
| 5 sem Win_c1 | 2 | chegada | NETTING | 0 | 1123 | 41,5 | 15.468 | 1.768 | 8,75 | 619 | 619 | nao | 65 | 233 | 34,0 | 32,5 |
| 5 sem Win_c1 | 2 | chegada | NETTING | 2 | 1123 | 41,3 | 13.222 | 1.862 | 7,10 | 577 | 577 | nao | 65 | 233 | 39,5 | 44,5 |
| 5 sem Win_c1 | 2 | ranking | independente | 0 | 1298 | 42,1 | 17.205 | 1.585 | 10,85 | 631 | 631 | nao | 123 | 0 | 14,0 | 71,0 |
| 5 sem Win_c1 | 2 | ranking | independente | 2 | 1298 | 42,0 | 14.609 | 1.676 | 8,72 | 587 | 587 | nao | 123 | 0 | 21,0 | 78,0 |
| 5 sem Win_c1 | 2 | ranking | NETTING | 0 | 1122 | 41,3 | 15.304 | 1.768 | 8,66 | 619 | 619 | nao | 66 | 233 | 39,5 | 28,0 |
| 5 sem Win_c1 | 2 | ranking | NETTING | 2 | 1122 | 41,1 | 13.060 | 1.862 | 7,01 | 577 | 577 | nao | 66 | 233 | 35,0 | 41,5 |
| 5 sem Win_c1 | 3 | chegada | independente | 0 | 1408 | 43,0 | 20.649 | 1.562 | 13,22 | 558 | 558 | nao | 13 | 0 | 93,0 | 98,5 |
| 5 sem Win_c1 | 3 | chegada | independente | 2 | 1408 | 42,8 | 17.833 | 1.692 | 10,54 | 510 | 510 | nao | 13 | 0 | 90,0 | 81,0 |
| 5 sem Win_c1 | 3 | chegada | NETTING | 0 | 1182 | 41,7 | 16.925 | 1.788 | 9,47 | 588 | 588 | nao | 4 | 235 | 55,5 | 32,0 |
| 5 sem Win_c1 | 3 | chegada | NETTING | 2 | 1182 | 41,5 | 14.561 | 1.828 | 7,97 | 544 | 544 | nao | 4 | 235 | 45,0 | 46,0 |
| 5 sem Win_c1 | 3 | ranking | independente | 0 | 1409 | 42,9 | 20.569 | 1.562 | 13,17 | 558 | 558 | nao | 12 | 0 | 88,5 | 99,5 |
| 5 sem Win_c1 | 3 | ranking | independente | 2 | 1409 | 42,8 | 17.751 | 1.692 | 10,49 | 510 | 510 | nao | 12 | 0 | 88,0 | 82,0 |
| 5 sem Win_c1 | 3 | ranking | NETTING | 0 | 1182 | 41,7 | 16.925 | 1.788 | 9,47 | 588 | 588 | nao | 4 | 235 | 54,0 | 30,0 |
| 5 sem Win_c1 | 3 | ranking | NETTING | 2 | 1182 | 41,5 | 14.561 | 1.828 | 7,97 | 544 | 544 | nao | 4 | 235 | 50,5 | 52,5 |
| 5 sem Win | 1 | chegada | independente | 0 | 904 | 39,6 | 7.590 | 1.952 | 3,89 | 496 | 496 | nao | 523 | 0 | 3,0 | 22,5 |
| 5 sem Win | 1 | chegada | independente | 2 | 904 | 39,3 | 5.782 | 2.006 | 2,88 | 456 | 456 | nao | 523 | 0 | 3,0 | 29,0 |
| 5 sem Win | 1 | chegada | NETTING | 0 | 904 | 39,6 | 7.590 | 1.952 | 3,89 | 496 | 496 | nao | 336 | 187 | 3,5 | 18,0 |
| 5 sem Win | 1 | chegada | NETTING | 2 | 904 | 39,3 | 5.782 | 2.006 | 2,88 | 456 | 456 | nao | 336 | 187 | 2,0 | 22,0 |
| 5 sem Win | 1 | ranking | independente | 0 | 898 | 38,9 | 6.642 | 1.952 | 3,40 | 496 | 496 | nao | 529 | 0 | 1,0 | 16,5 |
| 5 sem Win | 1 | ranking | independente | 2 | 898 | 38,5 | 4.846 | 2.006 | 2,42 | 456 | 456 | nao | 529 | 0 | 0,5 | 22,0 |
| 5 sem Win | 1 | ranking | NETTING | 0 | 898 | 38,9 | 6.642 | 1.952 | 3,40 | 496 | 496 | nao | 343 | 186 | 1,0 | 21,0 |
| 5 sem Win | 1 | ranking | NETTING | 2 | 898 | 38,5 | 4.846 | 2.006 | 2,42 | 456 | 456 | nao | 343 | 186 | 1,5 | 23,0 |
| 5 sem Win | 2 | chegada | independente | 0 | 1307 | 41,9 | 17.154 | 1.573 | 10,91 | 620 | 620 | nao | 120 | 0 | 23,5 | 86,5 |
| 5 sem Win | 2 | chegada | independente | 2 | 1307 | 41,5 | 14.540 | 1.658 | 8,77 | 576 | 576 | nao | 120 | 0 | 23,0 | 88,5 |
| 5 sem Win | 2 | chegada | NETTING | 0 | 1128 | 41,0 | 15.249 | 1.824 | 8,36 | 623 | 623 | nao | 65 | 234 | 40,0 | 36,5 |
| 5 sem Win | 2 | chegada | NETTING | 2 | 1128 | 40,4 | 12.993 | 1.918 | 6,77 | 581 | 581 | nao | 65 | 234 | 37,5 | 33,0 |
| 5 sem Win | 2 | ranking | independente | 0 | 1304 | 41,9 | 17.119 | 1.573 | 10,88 | 620 | 620 | nao | 123 | 0 | 25,5 | 86,5 |
| 5 sem Win | 2 | ranking | independente | 2 | 1304 | 41,4 | 14.511 | 1.658 | 8,75 | 576 | 576 | nao | 123 | 0 | 19,0 | 88,5 |
| 5 sem Win | 2 | ranking | NETTING | 0 | 1127 | 40,8 | 15.093 | 1.824 | 8,27 | 623 | 623 | nao | 66 | 234 | 39,5 | 28,0 |
| 5 sem Win | 2 | ranking | NETTING | 2 | 1127 | 40,3 | 12.839 | 1.918 | 6,69 | 581 | 581 | nao | 66 | 234 | 37,5 | 34,0 |
| 5 sem Win | 3 | chegada | independente | 0 | 1415 | 42,5 | 20.365 | 1.659 | 12,28 | 547 | 547 | nao | 12 | 0 | 89,0 | 80,5 |
| 5 sem Win | 3 | chegada | independente | 2 | 1415 | 42,0 | 17.535 | 1.715 | 10,22 | 499 | 499 | nao | 12 | 0 | 87,5 | 84,0 |
| 5 sem Win | 3 | chegada | NETTING | 0 | 1187 | 41,2 | 16.710 | 1.788 | 9,35 | 592 | 592 | nao | 4 | 236 | 52,0 | 30,0 |
| 5 sem Win | 3 | chegada | NETTING | 2 | 1187 | 40,7 | 14.336 | 1.860 | 7,71 | 548 | 548 | nao | 4 | 236 | 52,0 | 45,0 |
| 5 sem Win | 3 | ranking | independente | 0 | 1416 | 42,4 | 20.285 | 1.659 | 12,23 | 547 | 547 | nao | 11 | 0 | 87,5 | 88,0 |
| 5 sem Win | 3 | ranking | independente | 2 | 1416 | 42,0 | 17.453 | 1.715 | 10,18 | 499 | 499 | nao | 11 | 0 | 83,5 | 85,5 |
| 5 sem Win | 3 | ranking | NETTING | 0 | 1187 | 41,2 | 16.710 | 1.788 | 9,35 | 592 | 592 | nao | 4 | 236 | 53,0 | 31,0 |
| 5 sem Win | 3 | ranking | NETTING | 2 | 1187 | 40,7 | 14.336 | 1.860 | 7,71 | 548 | 548 | nao | 4 | 236 | 48,0 | 41,5 |
| 4 sem WdoRet (Win) | 1 | chegada | independente | 0 | 943 | 41,3 | 9.473 | 1.188 | 7,97 | 445 | 445 | nao | 344 | 0 | 2,5 | 60,5 |
| 4 sem WdoRet (Win) | 1 | chegada | independente | 2 | 943 | 41,1 | 7.587 | 1.244 | 6,10 | 409 | 409 | nao | 344 | 0 | 5,0 | 78,0 |
| 4 sem WdoRet (Win) | 1 | chegada | NETTING | 0 | 943 | 41,3 | 9.473 | 1.188 | 7,97 | 445 | 445 | nao | 251 | 93 | 6,0 | 65,0 |
| 4 sem WdoRet (Win) | 1 | chegada | NETTING | 2 | 943 | 41,1 | 7.587 | 1.244 | 6,10 | 409 | 409 | nao | 251 | 93 | 6,0 | 78,0 |
| 4 sem WdoRet (Win) | 1 | ranking | independente | 0 | 938 | 40,3 | 8.594 | 1.188 | 7,23 | 445 | 445 | nao | 349 | 0 | 3,0 | 62,5 |
| 4 sem WdoRet (Win) | 1 | ranking | independente | 2 | 938 | 40,2 | 6.718 | 1.244 | 5,40 | 409 | 409 | nao | 349 | 0 | 1,0 | 76,5 |
| 4 sem WdoRet (Win) | 1 | ranking | NETTING | 0 | 938 | 40,3 | 8.594 | 1.188 | 7,23 | 445 | 445 | nao | 255 | 94 | 2,5 | 66,5 |
| 4 sem WdoRet (Win) | 1 | ranking | NETTING | 2 | 938 | 40,2 | 6.718 | 1.244 | 5,40 | 409 | 409 | nao | 255 | 94 | 2,0 | 77,0 |
| 4 sem WdoRet (Win) | 2 | chegada | independente | 0 | 1234 | 41,5 | 15.922 | 1.282 | 12,42 | 537 | 537 | nao | 53 | 0 | 20,0 | 55,5 |
| 4 sem WdoRet (Win) | 2 | chegada | independente | 2 | 1234 | 41,4 | 13.454 | 1.388 | 9,69 | 491 | 491 | nao | 53 | 0 | 26,0 | 59,0 |
| 4 sem WdoRet (Win) | 2 | chegada | NETTING | 0 | 1135 | 41,1 | 15.993 | 1.307 | 12,24 | 557 | 557 | nao | 38 | 114 | 68,0 | 44,5 |
| 4 sem WdoRet (Win) | 2 | chegada | NETTING | 2 | 1135 | 41,1 | 13.723 | 1.469 | 9,34 | 519 | 519 | nao | 38 | 114 | 65,0 | 38,0 |
| 4 sem WdoRet (Win) | 2 | ranking | independente | 0 | 1234 | 41,5 | 15.975 | 1.282 | 12,46 | 537 | 537 | nao | 53 | 0 | 27,0 | 61,0 |
| 4 sem WdoRet (Win) | 2 | ranking | independente | 2 | 1234 | 41,4 | 13.507 | 1.388 | 9,73 | 491 | 491 | nao | 53 | 0 | 17,0 | 55,5 |
| 4 sem WdoRet (Win) | 2 | ranking | NETTING | 0 | 1135 | 41,1 | 16.046 | 1.307 | 12,28 | 557 | 557 | nao | 38 | 114 | 70,0 | 45,5 |
| 4 sem WdoRet (Win) | 2 | ranking | NETTING | 2 | 1135 | 41,1 | 13.776 | 1.469 | 9,38 | 519 | 519 | nao | 38 | 114 | 68,0 | 39,5 |
| 4 sem WdoRet (Win) | 3 | chegada | independente | 0 | 1282 | 42,0 | 17.553 | 1.282 | 13,69 | 464 | 464 | nao | 5 | 0 | 85,0 | 90,5 |
| 4 sem WdoRet (Win) | 3 | chegada | independente | 2 | 1282 | 41,9 | 14.989 | 1.388 | 10,80 | 414 | 414 | nao | 5 | 0 | 86,5 | 93,0 |
| 4 sem WdoRet (Win) | 3 | chegada | NETTING | 0 | 1170 | 41,4 | 17.120 | 1.307 | 13,10 | 526 | 526 | nao | 3 | 114 | 88,0 | 42,5 |
| 4 sem WdoRet (Win) | 3 | chegada | NETTING | 2 | 1170 | 41,3 | 14.780 | 1.473 | 10,03 | 486 | 486 | nao | 3 | 114 | 85,5 | 37,5 |
| 4 sem WdoRet (Win) | 3 | ranking | independente | 0 | 1282 | 42,0 | 17.553 | 1.282 | 13,69 | 464 | 464 | nao | 5 | 0 | 85,5 | 89,5 |
| 4 sem WdoRet (Win) | 3 | ranking | independente | 2 | 1282 | 41,9 | 14.989 | 1.388 | 10,80 | 414 | 414 | nao | 5 | 0 | 79,0 | 95,0 |
| 4 sem WdoRet (Win) | 3 | ranking | NETTING | 0 | 1170 | 41,4 | 17.120 | 1.307 | 13,10 | 526 | 526 | nao | 3 | 114 | 82,5 | 40,0 |
| 4 sem WdoRet (Win) | 3 | ranking | NETTING | 2 | 1170 | 41,3 | 14.780 | 1.473 | 10,03 | 486 | 486 | nao | 3 | 114 | 82,5 | 34,0 |
| 4 sem WdoRet (Win_c1) | 1 | chegada | independente | 0 | 949 | 40,6 | 9.901 | 1.193 | 8,30 | 434 | 434 | nao | 344 | 0 | 7,5 | 77,5 |
| 4 sem WdoRet (Win_c1) | 1 | chegada | independente | 2 | 949 | 40,1 | 8.003 | 1.277 | 6,27 | 398 | 398 | nao | 344 | 0 | 8,0 | 84,5 |
| 4 sem WdoRet (Win_c1) | 1 | chegada | NETTING | 0 | 949 | 40,6 | 9.901 | 1.193 | 8,30 | 434 | 434 | nao | 251 | 93 | 5,5 | 75,0 |
| 4 sem WdoRet (Win_c1) | 1 | chegada | NETTING | 2 | 949 | 40,1 | 8.003 | 1.277 | 6,27 | 398 | 398 | nao | 251 | 93 | 8,5 | 77,5 |
| 4 sem WdoRet (Win_c1) | 1 | ranking | independente | 0 | 943 | 39,9 | 9.209 | 1.193 | 7,72 | 434 | 434 | nao | 350 | 0 | 5,5 | 75,0 |
| 4 sem WdoRet (Win_c1) | 1 | ranking | independente | 2 | 943 | 39,4 | 7.323 | 1.277 | 5,73 | 398 | 398 | nao | 350 | 0 | 3,5 | 75,0 |
| 4 sem WdoRet (Win_c1) | 1 | ranking | NETTING | 0 | 943 | 39,9 | 9.209 | 1.193 | 7,72 | 434 | 434 | nao | 256 | 94 | 6,0 | 82,5 |
| 4 sem WdoRet (Win_c1) | 1 | ranking | NETTING | 2 | 943 | 39,4 | 7.323 | 1.277 | 5,73 | 398 | 398 | nao | 256 | 94 | 7,5 | 79,5 |
| 4 sem WdoRet (Win_c1) | 2 | chegada | independente | 0 | 1241 | 41,0 | 15.792 | 1.493 | 10,58 | 541 | 541 | nao | 52 | 0 | 12,5 | 51,5 |
| 4 sem WdoRet (Win_c1) | 2 | chegada | independente | 2 | 1241 | 40,6 | 13.310 | 1.599 | 8,32 | 495 | 495 | nao | 52 | 0 | 16,5 | 41,0 |
| 4 sem WdoRet (Win_c1) | 2 | chegada | NETTING | 0 | 1141 | 40,6 | 15.795 | 1.518 | 10,41 | 561 | 561 | nao | 38 | 114 | 61,0 | 25,0 |
| 4 sem WdoRet (Win_c1) | 2 | chegada | NETTING | 2 | 1141 | 40,1 | 13.513 | 1.620 | 8,34 | 523 | 523 | nao | 38 | 114 | 65,0 | 32,5 |
| 4 sem WdoRet (Win_c1) | 2 | ranking | independente | 0 | 1241 | 41,0 | 15.845 | 1.493 | 10,61 | 541 | 541 | nao | 52 | 0 | 19,5 | 37,5 |
| 4 sem WdoRet (Win_c1) | 2 | ranking | independente | 2 | 1241 | 40,6 | 13.363 | 1.599 | 8,36 | 495 | 495 | nao | 52 | 0 | 20,5 | 44,0 |
| 4 sem WdoRet (Win_c1) | 2 | ranking | NETTING | 0 | 1141 | 40,6 | 15.848 | 1.518 | 10,44 | 561 | 561 | nao | 38 | 114 | 56,5 | 26,5 |
| 4 sem WdoRet (Win_c1) | 2 | ranking | NETTING | 2 | 1141 | 40,1 | 13.566 | 1.620 | 8,37 | 523 | 523 | nao | 38 | 114 | 69,0 | 31,5 |
| 4 sem WdoRet (Win_c1) | 3 | chegada | independente | 0 | 1288 | 41,5 | 17.355 | 1.493 | 11,62 | 468 | 468 | nao | 5 | 0 | 85,5 | 92,5 |
| 4 sem WdoRet (Win_c1) | 3 | chegada | independente | 2 | 1288 | 41,1 | 14.779 | 1.599 | 9,24 | 418 | 418 | nao | 5 | 0 | 78,5 | 90,0 |
| 4 sem WdoRet (Win_c1) | 3 | chegada | NETTING | 0 | 1176 | 40,8 | 16.922 | 1.518 | 11,15 | 530 | 530 | nao | 3 | 114 | 86,0 | 28,0 |
| 4 sem WdoRet (Win_c1) | 3 | chegada | NETTING | 2 | 1176 | 40,4 | 14.570 | 1.620 | 8,99 | 490 | 490 | nao | 3 | 114 | 87,5 | 33,5 |
| 4 sem WdoRet (Win_c1) | 3 | ranking | independente | 0 | 1288 | 41,5 | 17.355 | 1.493 | 11,62 | 468 | 468 | nao | 5 | 0 | 85,0 | 92,0 |
| 4 sem WdoRet (Win_c1) | 3 | ranking | independente | 2 | 1288 | 41,1 | 14.779 | 1.599 | 9,24 | 418 | 418 | nao | 5 | 0 | 86,5 | 91,0 |
| 4 sem WdoRet (Win_c1) | 3 | ranking | NETTING | 0 | 1176 | 40,8 | 16.922 | 1.518 | 11,15 | 530 | 530 | nao | 3 | 114 | 85,5 | 34,5 |
| 4 sem WdoRet (Win_c1) | 3 | ranking | NETTING | 2 | 1176 | 40,4 | 14.570 | 1.620 | 8,99 | 490 | 490 | nao | 3 | 114 | 87,5 | 33,5 |

## Escolha walk-forward da celula (K, prioridade) so com meses anteriores

Em cada mes vale a celula (K x prioridade, dentro do conjunto/visao) com maior liquido acumulado / pior queda mensal dos meses anteriores; jan = K2 chegada. c = chegada, r = ranking.

| conjunto | visao | custo | liquido walk-forward | escolhas jan..out |
|---|---|---|---|---|
| 5 sem Win_c1 | independente | 0 | 20.345 | K2c K3c K3c K3c K3c K3c K3c K3c K3c K3c |
| 5 sem Win_c1 | independente | 2 | 17.549 | K2c K3c K3c K3c K3c K3c K3c K3c K3c K3c |
| 5 sem Win_c1 | NETTING | 0 | 15.722 | K2c K3c K3c K1c K3c K3c K3c K3c K3c K3c |
| 5 sem Win_c1 | NETTING | 2 | 13.918 | K2c K3c K1c K1c K3c K3c K3c K3c K3c K3c |
| 5 sem Win | independente | 0 | 20.057 | K2c K3c K3c K3c K3c K3c K3c K3c K3c K3c |
| 5 sem Win | independente | 2 | 17.247 | K2c K3c K3c K3c K3c K3c K3c K3c K3c K3c |
| 5 sem Win | NETTING | 0 | 16.674 | K2c K3c K3c K3c K3c K3c K3c K3c K3c K3c |
| 5 sem Win | NETTING | 2 | 14.312 | K2c K3c K3c K3c K3c K3c K3c K3c K3c K3c |
| 4 sem WdoRet (Win) | independente | 0 | 17.055 | K2c K2c K3c K3c K3c K2r K2r K2r K3c K3c |
| 4 sem WdoRet (Win) | independente | 2 | 14.527 | K2c K2c K3c K3c K3c K2r K2r K2r K3c K3c |
| 4 sem WdoRet (Win) | NETTING | 0 | 16.811 | K2c K2c K2r K3c K3c K2r K2r K2r K3c K3c |
| 4 sem WdoRet (Win) | NETTING | 2 | 14.641 | K2c K2c K3c K3c K3c K2r K2r K2r K3c K3c |
| 4 sem WdoRet (Win_c1) | independente | 0 | 16.857 | K2c K2c K3c K3c K3c K2r K2r K2r K3c K3c |
| 4 sem WdoRet (Win_c1) | independente | 2 | 14.317 | K2c K2c K3c K3c K3c K2r K2r K2r K3c K3c |
| 4 sem WdoRet (Win_c1) | NETTING | 0 | 16.613 | K2c K2c K2r K3c K3c K2r K2r K2r K3c K3c |
| 4 sem WdoRet (Win_c1) | NETTING | 2 | 14.397 | K2c K2c K3c K3c K3c K2r K3c K2r K3c K3c |

## Tabelas mensais por celula


### 5 sem Win_c1 | K=1 | chegada | independente (cortes teto 524, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 78 | 42,3 | 1.644 | 493 | 507 | 1.488 | 533 | 467 |
| fev | 99 | 39,4 | 1.800 | 731 | 2.572 | 1.602 | 791 | 2.414 |
| mar | 164 | 43,3 | 654 | 1.384 | 4.165 | 326 | 1.432 | 3.529 |
| abr | 91 | 41,8 | 1.521 | 493 | 4.966 | 1.339 | 543 | 4.248 |
| mai | 96 | 35,4 | 417 | 643 | 5.976 | 225 | 715 | 5.072 |
| jun | 79 | 39,2 | 296 | 789 | 6.952 | 138 | 871 | 5.890 |
| jul | 72 | 38,9 | -291 | 1.298 | 7.019 | -435 | 1.316 | 5.663 |
| ago | 93 | 37,6 | 1.084 | 1.080 | 6.708 | 898 | 1.148 | 5.344 |
| set | 94 | 47,9 | 2.732 | 649 | 8.084 | 2.544 | 689 | 6.538 |
| out | 31 | 32,3 | -1.944 | 1.952 | 8.913 | -2.006 | 2.006 | 7.119 |
| total | 897 | 40,6 | 7.913 | 1.952 | 507 | 6.119 | 2.006 | 467 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win_c1 | K=1 | chegada | NETTING (cortes teto 338, bloq netting 186)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 78 | 42,3 | 1.644 | 493 | 507 | 1.488 | 533 | 467 |
| fev | 99 | 39,4 | 1.800 | 731 | 2.572 | 1.602 | 791 | 2.414 |
| mar | 164 | 43,3 | 654 | 1.384 | 4.165 | 326 | 1.432 | 3.529 |
| abr | 91 | 41,8 | 1.521 | 493 | 4.966 | 1.339 | 543 | 4.248 |
| mai | 96 | 35,4 | 417 | 643 | 5.976 | 225 | 715 | 5.072 |
| jun | 79 | 39,2 | 296 | 789 | 6.952 | 138 | 871 | 5.890 |
| jul | 72 | 38,9 | -291 | 1.298 | 7.019 | -435 | 1.316 | 5.663 |
| ago | 93 | 37,6 | 1.084 | 1.080 | 6.708 | 898 | 1.148 | 5.344 |
| set | 94 | 47,9 | 2.732 | 649 | 8.084 | 2.544 | 689 | 6.538 |
| out | 31 | 32,3 | -1.944 | 1.952 | 8.913 | -2.006 | 2.006 | 7.119 |
| total | 897 | 40,6 | 7.913 | 1.952 | 507 | 6.119 | 2.006 | 467 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win_c1 | K=1 | ranking | independente (cortes teto 529, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 78 | 42,3 | 1.644 | 493 | 507 | 1.488 | 533 | 467 |
| fev | 98 | 39,8 | 1.758 | 731 | 2.572 | 1.562 | 791 | 2.414 |
| mar | 165 | 42,4 | 447 | 1.560 | 3.947 | 117 | 1.618 | 3.303 |
| abr | 90 | 40,0 | 1.417 | 493 | 4.717 | 1.237 | 543 | 3.999 |
| mai | 95 | 32,6 | 191 | 654 | 5.623 | 1 | 746 | 4.721 |
| jun | 79 | 38,0 | 256 | 789 | 6.373 | 98 | 871 | 5.315 |
| jul | 72 | 38,9 | -291 | 1.298 | 6.400 | -435 | 1.316 | 5.048 |
| ago | 90 | 34,4 | 568 | 1.093 | 6.089 | 388 | 1.215 | 4.729 |
| set | 94 | 47,9 | 2.732 | 649 | 6.949 | 2.544 | 689 | 5.413 |
| out | 31 | 32,3 | -1.944 | 1.952 | 7.778 | -2.006 | 2.006 | 5.994 |
| total | 892 | 39,6 | 6.778 | 1.952 | 507 | 4.994 | 2.006 | 467 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win_c1 | K=1 | ranking | NETTING (cortes teto 344, bloq netting 185)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 78 | 42,3 | 1.644 | 493 | 507 | 1.488 | 533 | 467 |
| fev | 98 | 39,8 | 1.758 | 731 | 2.572 | 1.562 | 791 | 2.414 |
| mar | 165 | 42,4 | 447 | 1.560 | 3.947 | 117 | 1.618 | 3.303 |
| abr | 90 | 40,0 | 1.417 | 493 | 4.717 | 1.237 | 543 | 3.999 |
| mai | 95 | 32,6 | 191 | 654 | 5.623 | 1 | 746 | 4.721 |
| jun | 79 | 38,0 | 256 | 789 | 6.373 | 98 | 871 | 5.315 |
| jul | 72 | 38,9 | -291 | 1.298 | 6.400 | -435 | 1.316 | 5.048 |
| ago | 90 | 34,4 | 568 | 1.093 | 6.089 | 388 | 1.215 | 4.729 |
| set | 94 | 47,9 | 2.732 | 649 | 6.949 | 2.544 | 689 | 5.413 |
| out | 31 | 32,3 | -1.944 | 1.952 | 7.778 | -2.006 | 2.006 | 5.994 |
| total | 892 | 39,6 | 6.778 | 1.952 | 507 | 4.994 | 2.006 | 467 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win_c1 | K=2 | chegada | independente (cortes teto 120, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 103 | 44,7 | 3.302 | 506 | 631 | 3.096 | 534 | 587 |
| fev | 147 | 40,8 | 1.485 | 996 | 4.147 | 1.191 | 1.046 | 3.931 |
| mar | 226 | 45,1 | 2.164 | 1.585 | 5.696 | 1.712 | 1.637 | 5.052 |
| abr | 144 | 39,6 | 1.904 | 657 | 7.378 | 1.616 | 703 | 6.376 |
| mai | 133 | 36,8 | 1.792 | 950 | 9.235 | 1.526 | 1.080 | 7.951 |
| jun | 126 | 39,7 | 191 | 1.253 | 11.495 | -61 | 1.399 | 9.983 |
| jul | 99 | 41,4 | 1.348 | 1.355 | 11.510 | 1.150 | 1.375 | 9.714 |
| ago | 139 | 41,0 | 2.344 | 1.298 | 12.958 | 2.066 | 1.404 | 10.996 |
| set | 145 | 50,3 | 3.529 | 845 | 15.489 | 3.239 | 905 | 13.253 |
| out | 39 | 38,5 | -811 | 1.562 | 18.248 | -889 | 1.600 | 15.646 |
| total | 1301 | 42,3 | 17.248 | 1.585 | 631 | 14.646 | 1.676 | 587 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win_c1 | K=2 | chegada | NETTING (cortes teto 65, bloq netting 233)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 88 | 44,3 | 3.763 | 511 | 619 | 3.587 | 539 | 577 |
| fev | 124 | 37,9 | 522 | 1.075 | 4.343 | 274 | 1.219 | 3.993 |
| mar | 180 | 42,2 | 88 | 1.768 | 4.366 | -272 | 1.862 | 3.624 |
| abr | 125 | 40,0 | 2.612 | 762 | 4.695 | 2.362 | 804 | 3.865 |
| mai | 120 | 35,0 | 1.422 | 993 | 7.365 | 1.182 | 1.111 | 6.287 |
| jun | 110 | 41,8 | 717 | 1.048 | 9.315 | 497 | 1.164 | 8.033 |
| jul | 87 | 40,2 | 871 | 1.416 | 9.707 | 697 | 1.444 | 8.177 |
| ago | 129 | 39,5 | 1.687 | 1.326 | 10.633 | 1.429 | 1.425 | 8.957 |
| set | 125 | 50,4 | 3.051 | 720 | 12.641 | 2.801 | 772 | 10.713 |
| out | 35 | 48,6 | 735 | 435 | 15.298 | 665 | 447 | 13.110 |
| total | 1123 | 41,5 | 15.468 | 1.768 | 619 | 13.222 | 1.862 | 577 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win_c1 | K=2 | ranking | independente (cortes teto 123, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 103 | 44,7 | 3.302 | 506 | 631 | 3.096 | 534 | 587 |
| fev | 145 | 40,7 | 1.522 | 996 | 4.147 | 1.232 | 1.046 | 3.931 |
| mar | 226 | 45,1 | 2.164 | 1.585 | 5.733 | 1.712 | 1.637 | 5.093 |
| abr | 144 | 39,6 | 1.904 | 657 | 7.415 | 1.616 | 703 | 6.417 |
| mai | 132 | 36,4 | 1.752 | 950 | 9.272 | 1.488 | 1.080 | 7.992 |
| jun | 126 | 38,9 | 151 | 1.253 | 11.492 | -101 | 1.399 | 9.954 |
| jul | 99 | 41,4 | 1.348 | 1.355 | 11.467 | 1.150 | 1.375 | 9.677 |
| ago | 139 | 41,0 | 2.344 | 1.298 | 12.915 | 2.066 | 1.404 | 10.959 |
| set | 145 | 50,3 | 3.529 | 845 | 15.446 | 3.239 | 905 | 13.216 |
| out | 39 | 38,5 | -811 | 1.562 | 18.205 | -889 | 1.600 | 15.609 |
| total | 1298 | 42,1 | 17.205 | 1.585 | 631 | 14.609 | 1.676 | 587 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win_c1 | K=2 | ranking | NETTING (cortes teto 66, bloq netting 233)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 88 | 44,3 | 3.763 | 511 | 619 | 3.587 | 539 | 577 |
| fev | 122 | 37,7 | 559 | 1.038 | 4.380 | 315 | 1.178 | 4.034 |
| mar | 180 | 42,2 | 88 | 1.768 | 4.403 | -272 | 1.862 | 3.665 |
| abr | 125 | 40,0 | 2.612 | 762 | 4.732 | 2.362 | 804 | 3.906 |
| mai | 120 | 34,2 | 1.341 | 993 | 7.402 | 1.101 | 1.111 | 6.328 |
| jun | 110 | 40,9 | 677 | 1.048 | 9.271 | 457 | 1.164 | 7.993 |
| jul | 87 | 40,2 | 871 | 1.416 | 9.623 | 697 | 1.444 | 8.097 |
| ago | 130 | 39,2 | 1.607 | 1.326 | 10.549 | 1.347 | 1.425 | 8.877 |
| set | 125 | 50,4 | 3.051 | 720 | 12.477 | 2.801 | 772 | 10.551 |
| out | 35 | 48,6 | 735 | 435 | 15.134 | 665 | 447 | 12.948 |
| total | 1122 | 41,3 | 15.304 | 1.768 | 619 | 13.060 | 1.862 | 577 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win_c1 | K=3 | chegada | independente (cortes teto 13, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 113 | 45,1 | 3.606 | 506 | 558 | 3.380 | 534 | 510 |
| fev | 165 | 41,2 | 2.066 | 996 | 4.416 | 1.736 | 1.046 | 4.178 |
| mar | 232 | 46,6 | 2.578 | 1.517 | 6.581 | 2.114 | 1.571 | 5.881 |
| abr | 157 | 39,5 | 2.537 | 779 | 8.555 | 2.223 | 829 | 7.481 |
| mai | 153 | 37,3 | 1.933 | 1.374 | 11.167 | 1.627 | 1.512 | 9.789 |
| jun | 139 | 41,0 | 4 | 1.282 | 13.568 | -274 | 1.415 | 11.717 |
| jul | 104 | 41,3 | 1.360 | 1.355 | 13.396 | 1.152 | 1.375 | 11.440 |
| ago | 142 | 41,5 | 2.335 | 1.298 | 14.882 | 2.051 | 1.404 | 12.748 |
| set | 162 | 51,2 | 4.919 | 630 | 17.378 | 4.595 | 640 | 14.966 |
| out | 41 | 41,5 | -689 | 1.562 | 21.649 | -771 | 1.600 | 18.833 |
| total | 1408 | 43,0 | 20.649 | 1.562 | 558 | 17.833 | 1.692 | 510 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win_c1 | K=3 | chegada | NETTING (cortes teto 4, bloq netting 235)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 94 | 44,7 | 3.795 | 511 | 588 | 3.607 | 539 | 544 |
| fev | 131 | 38,2 | 848 | 951 | 4.464 | 586 | 1.097 | 4.098 |
| mar | 182 | 42,9 | 236 | 1.708 | 4.872 | -128 | 1.804 | 4.100 |
| abr | 138 | 38,4 | 2.692 | 914 | 5.049 | 2.416 | 976 | 4.169 |
| mai | 129 | 36,4 | 1.710 | 1.210 | 7.951 | 1.452 | 1.332 | 6.817 |
| jun | 115 | 41,7 | 522 | 1.279 | 10.189 | 292 | 1.401 | 8.833 |
| jul | 89 | 40,4 | 881 | 1.448 | 10.386 | 703 | 1.478 | 8.772 |
| ago | 130 | 39,2 | 1.567 | 1.326 | 11.322 | 1.307 | 1.425 | 9.558 |
| set | 139 | 51,1 | 3.939 | 672 | 13.210 | 3.661 | 758 | 11.192 |
| out | 35 | 48,6 | 735 | 435 | 16.755 | 665 | 447 | 14.449 |
| total | 1182 | 41,7 | 16.925 | 1.788 | 588 | 14.561 | 1.828 | 544 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win_c1 | K=3 | ranking | independente (cortes teto 12, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 113 | 45,1 | 3.606 | 506 | 558 | 3.380 | 534 | 510 |
| fev | 165 | 41,2 | 2.066 | 996 | 4.416 | 1.736 | 1.046 | 4.178 |
| mar | 232 | 46,6 | 2.578 | 1.517 | 6.581 | 2.114 | 1.571 | 5.881 |
| abr | 157 | 39,5 | 2.537 | 779 | 8.555 | 2.223 | 829 | 7.481 |
| mai | 153 | 37,3 | 1.933 | 1.374 | 11.167 | 1.627 | 1.512 | 9.789 |
| jun | 139 | 41,0 | 4 | 1.282 | 13.568 | -274 | 1.415 | 11.717 |
| jul | 104 | 41,3 | 1.360 | 1.355 | 13.396 | 1.152 | 1.375 | 11.440 |
| ago | 143 | 41,3 | 2.255 | 1.298 | 14.882 | 1.969 | 1.404 | 12.748 |
| set | 162 | 51,2 | 4.919 | 630 | 17.298 | 4.595 | 640 | 14.884 |
| out | 41 | 41,5 | -689 | 1.562 | 21.569 | -771 | 1.600 | 18.751 |
| total | 1409 | 42,9 | 20.569 | 1.562 | 558 | 17.751 | 1.692 | 510 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win_c1 | K=3 | ranking | NETTING (cortes teto 4, bloq netting 235)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 94 | 44,7 | 3.795 | 511 | 588 | 3.607 | 539 | 544 |
| fev | 131 | 38,2 | 848 | 951 | 4.464 | 586 | 1.097 | 4.098 |
| mar | 182 | 42,9 | 236 | 1.708 | 4.872 | -128 | 1.804 | 4.100 |
| abr | 138 | 38,4 | 2.692 | 914 | 5.049 | 2.416 | 976 | 4.169 |
| mai | 129 | 36,4 | 1.710 | 1.210 | 7.951 | 1.452 | 1.332 | 6.817 |
| jun | 115 | 41,7 | 522 | 1.279 | 10.189 | 292 | 1.401 | 8.833 |
| jul | 89 | 40,4 | 881 | 1.448 | 10.386 | 703 | 1.478 | 8.772 |
| ago | 130 | 39,2 | 1.567 | 1.326 | 11.322 | 1.307 | 1.425 | 9.558 |
| set | 139 | 51,1 | 3.939 | 672 | 13.210 | 3.661 | 758 | 11.192 |
| out | 35 | 48,6 | 735 | 435 | 16.755 | 665 | 447 | 14.449 |
| total | 1182 | 41,7 | 16.925 | 1.788 | 588 | 14.561 | 1.828 | 544 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win | K=1 | chegada | independente (cortes teto 523, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 79 | 40,5 | 1.567 | 504 | 496 | 1.409 | 544 | 456 |
| fev | 99 | 39,4 | 1.800 | 731 | 2.495 | 1.602 | 791 | 2.335 |
| mar | 165 | 42,4 | 491 | 1.541 | 3.956 | 161 | 1.599 | 3.308 |
| abr | 94 | 41,5 | 2.074 | 535 | 4.573 | 1.886 | 589 | 3.847 |
| mai | 96 | 35,4 | 477 | 627 | 6.349 | 285 | 715 | 5.435 |
| jun | 80 | 37,5 | 111 | 954 | 7.325 | -49 | 1.042 | 6.184 |
| jul | 73 | 38,4 | -246 | 1.298 | 7.252 | -392 | 1.316 | 5.882 |
| ago | 93 | 35,5 | 868 | 1.152 | 6.941 | 682 | 1.234 | 5.563 |
| set | 94 | 45,7 | 2.392 | 649 | 8.101 | 2.204 | 689 | 6.541 |
| out | 31 | 32,3 | -1.944 | 1.952 | 8.590 | -2.006 | 2.006 | 6.782 |
| total | 904 | 39,6 | 7.590 | 1.952 | 496 | 5.782 | 2.006 | 456 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win | K=1 | chegada | NETTING (cortes teto 336, bloq netting 187)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 79 | 40,5 | 1.567 | 504 | 496 | 1.409 | 544 | 456 |
| fev | 99 | 39,4 | 1.800 | 731 | 2.495 | 1.602 | 791 | 2.335 |
| mar | 165 | 42,4 | 491 | 1.541 | 3.956 | 161 | 1.599 | 3.308 |
| abr | 94 | 41,5 | 2.074 | 535 | 4.573 | 1.886 | 589 | 3.847 |
| mai | 96 | 35,4 | 477 | 627 | 6.349 | 285 | 715 | 5.435 |
| jun | 80 | 37,5 | 111 | 954 | 7.325 | -49 | 1.042 | 6.184 |
| jul | 73 | 38,4 | -246 | 1.298 | 7.252 | -392 | 1.316 | 5.882 |
| ago | 93 | 35,5 | 868 | 1.152 | 6.941 | 682 | 1.234 | 5.563 |
| set | 94 | 45,7 | 2.392 | 649 | 8.101 | 2.204 | 689 | 6.541 |
| out | 31 | 32,3 | -1.944 | 1.952 | 8.590 | -2.006 | 2.006 | 6.782 |
| total | 904 | 39,6 | 7.590 | 1.952 | 496 | 5.782 | 2.006 | 456 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win | K=1 | ranking | independente (cortes teto 529, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 79 | 40,5 | 1.558 | 504 | 496 | 1.400 | 544 | 456 |
| fev | 98 | 39,8 | 1.758 | 731 | 2.486 | 1.562 | 791 | 2.326 |
| mar | 165 | 42,4 | 472 | 1.560 | 3.886 | 142 | 1.618 | 3.240 |
| abr | 93 | 39,8 | 1.970 | 535 | 4.503 | 1.784 | 589 | 3.779 |
| mai | 95 | 32,6 | 251 | 654 | 6.175 | 61 | 746 | 5.265 |
| jun | 80 | 37,5 | 79 | 954 | 6.925 | -81 | 1.042 | 5.758 |
| jul | 73 | 38,4 | -246 | 1.298 | 6.820 | -392 | 1.316 | 5.456 |
| ago | 90 | 32,2 | 352 | 1.165 | 6.509 | 172 | 1.301 | 5.137 |
| set | 94 | 45,7 | 2.392 | 649 | 7.153 | 2.204 | 689 | 5.605 |
| out | 31 | 32,3 | -1.944 | 1.952 | 7.642 | -2.006 | 2.006 | 5.846 |
| total | 898 | 38,9 | 6.642 | 1.952 | 496 | 4.846 | 2.006 | 456 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win | K=1 | ranking | NETTING (cortes teto 343, bloq netting 186)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 79 | 40,5 | 1.558 | 504 | 496 | 1.400 | 544 | 456 |
| fev | 98 | 39,8 | 1.758 | 731 | 2.486 | 1.562 | 791 | 2.326 |
| mar | 165 | 42,4 | 472 | 1.560 | 3.886 | 142 | 1.618 | 3.240 |
| abr | 93 | 39,8 | 1.970 | 535 | 4.503 | 1.784 | 589 | 3.779 |
| mai | 95 | 32,6 | 251 | 654 | 6.175 | 61 | 746 | 5.265 |
| jun | 80 | 37,5 | 79 | 954 | 6.925 | -81 | 1.042 | 5.758 |
| jul | 73 | 38,4 | -246 | 1.298 | 6.820 | -392 | 1.316 | 5.456 |
| ago | 90 | 32,2 | 352 | 1.165 | 6.509 | 172 | 1.301 | 5.137 |
| set | 94 | 45,7 | 2.392 | 649 | 7.153 | 2.204 | 689 | 5.605 |
| out | 31 | 32,3 | -1.944 | 1.952 | 7.642 | -2.006 | 2.006 | 5.846 |
| total | 898 | 38,9 | 6.642 | 1.952 | 496 | 4.846 | 2.006 | 456 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win | K=2 | chegada | independente (cortes teto 120, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 103 | 43,7 | 3.284 | 506 | 620 | 3.078 | 534 | 576 |
| fev | 147 | 40,8 | 1.485 | 996 | 4.129 | 1.191 | 1.046 | 3.913 |
| mar | 227 | 44,9 | 2.201 | 1.573 | 5.678 | 1.747 | 1.627 | 5.034 |
| abr | 148 | 40,5 | 2.048 | 582 | 7.460 | 1.752 | 630 | 6.452 |
| mai | 133 | 36,8 | 1.934 | 925 | 9.458 | 1.668 | 1.055 | 8.164 |
| jun | 126 | 38,9 | 221 | 1.236 | 11.800 | -31 | 1.382 | 10.278 |
| jul | 100 | 41,0 | 1.393 | 1.355 | 11.906 | 1.193 | 1.375 | 10.100 |
| ago | 139 | 39,6 | 2.128 | 1.509 | 13.338 | 1.850 | 1.615 | 11.364 |
| set | 145 | 49,7 | 3.271 | 845 | 15.653 | 2.981 | 905 | 13.405 |
| out | 39 | 38,5 | -811 | 1.562 | 18.154 | -889 | 1.600 | 15.540 |
| total | 1307 | 41,9 | 17.154 | 1.573 | 620 | 14.540 | 1.658 | 576 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win | K=2 | chegada | NETTING (cortes teto 65, bloq netting 234)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 88 | 43,2 | 3.745 | 511 | 623 | 3.569 | 539 | 581 |
| fev | 124 | 37,9 | 522 | 1.075 | 4.325 | 274 | 1.219 | 3.975 |
| mar | 180 | 41,7 | 57 | 1.824 | 4.317 | -303 | 1.918 | 3.575 |
| abr | 129 | 41,1 | 2.756 | 687 | 4.709 | 2.498 | 731 | 3.875 |
| mai | 120 | 35,0 | 1.564 | 968 | 7.520 | 1.324 | 1.086 | 6.434 |
| jun | 110 | 40,0 | 690 | 1.031 | 9.552 | 470 | 1.147 | 8.266 |
| jul | 88 | 39,8 | 916 | 1.416 | 9.978 | 740 | 1.444 | 8.440 |
| ago | 129 | 38,0 | 1.471 | 1.534 | 10.888 | 1.213 | 1.636 | 9.202 |
| set | 125 | 49,6 | 2.793 | 720 | 12.680 | 2.543 | 772 | 10.742 |
| out | 35 | 48,6 | 735 | 435 | 15.079 | 665 | 447 | 12.881 |
| total | 1128 | 41,0 | 15.249 | 1.824 | 623 | 12.993 | 1.918 | 581 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win | K=2 | ranking | independente (cortes teto 123, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 103 | 43,7 | 3.284 | 506 | 620 | 3.078 | 534 | 576 |
| fev | 145 | 40,7 | 1.522 | 996 | 4.129 | 1.232 | 1.046 | 3.913 |
| mar | 227 | 44,9 | 2.201 | 1.573 | 5.715 | 1.747 | 1.627 | 5.075 |
| abr | 148 | 40,5 | 2.048 | 582 | 7.497 | 1.752 | 630 | 6.493 |
| mai | 132 | 36,4 | 1.894 | 925 | 9.495 | 1.630 | 1.055 | 8.205 |
| jun | 126 | 38,9 | 189 | 1.236 | 11.797 | -63 | 1.382 | 10.281 |
| jul | 100 | 41,0 | 1.393 | 1.355 | 11.871 | 1.193 | 1.375 | 10.071 |
| ago | 139 | 39,6 | 2.128 | 1.509 | 13.303 | 1.850 | 1.615 | 11.335 |
| set | 145 | 49,7 | 3.271 | 845 | 15.618 | 2.981 | 905 | 13.376 |
| out | 39 | 38,5 | -811 | 1.562 | 18.119 | -889 | 1.600 | 15.511 |
| total | 1304 | 41,9 | 17.119 | 1.573 | 620 | 14.511 | 1.658 | 576 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win | K=2 | ranking | NETTING (cortes teto 66, bloq netting 234)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 88 | 43,2 | 3.745 | 511 | 623 | 3.569 | 539 | 581 |
| fev | 122 | 37,7 | 559 | 1.038 | 4.362 | 315 | 1.178 | 4.016 |
| mar | 180 | 41,7 | 57 | 1.824 | 4.354 | -303 | 1.918 | 3.616 |
| abr | 129 | 41,1 | 2.756 | 687 | 4.746 | 2.498 | 731 | 3.916 |
| mai | 120 | 34,2 | 1.483 | 968 | 7.557 | 1.243 | 1.086 | 6.475 |
| jun | 110 | 40,0 | 658 | 1.031 | 9.508 | 438 | 1.147 | 8.226 |
| jul | 88 | 39,8 | 916 | 1.416 | 9.902 | 740 | 1.444 | 8.368 |
| ago | 130 | 37,7 | 1.391 | 1.534 | 10.812 | 1.131 | 1.636 | 9.130 |
| set | 125 | 49,6 | 2.793 | 720 | 12.524 | 2.543 | 772 | 10.588 |
| out | 35 | 48,6 | 735 | 435 | 14.923 | 665 | 447 | 12.727 |
| total | 1127 | 40,8 | 15.093 | 1.824 | 623 | 12.839 | 1.918 | 581 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win | K=3 | chegada | independente (cortes teto 12, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 113 | 44,2 | 3.592 | 506 | 547 | 3.366 | 534 | 499 |
| fev | 165 | 41,2 | 2.066 | 996 | 4.402 | 1.736 | 1.046 | 4.164 |
| mar | 233 | 45,9 | 2.461 | 1.659 | 6.567 | 1.995 | 1.715 | 5.867 |
| abr | 161 | 40,4 | 2.681 | 704 | 8.487 | 2.359 | 756 | 7.407 |
| mai | 153 | 37,3 | 2.075 | 1.349 | 11.240 | 1.769 | 1.487 | 9.852 |
| jun | 140 | 39,3 | -6 | 1.280 | 13.723 | -286 | 1.398 | 11.850 |
| jul | 105 | 41,0 | 1.405 | 1.355 | 13.602 | 1.195 | 1.375 | 11.634 |
| ago | 142 | 40,1 | 2.119 | 1.509 | 15.072 | 1.835 | 1.615 | 12.924 |
| set | 162 | 50,6 | 4.661 | 630 | 17.352 | 4.337 | 640 | 14.926 |
| out | 41 | 41,5 | -689 | 1.562 | 21.365 | -771 | 1.600 | 18.535 |
| total | 1415 | 42,5 | 20.365 | 1.659 | 547 | 17.535 | 1.715 | 499 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win | K=3 | chegada | NETTING (cortes teto 4, bloq netting 236)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 94 | 43,6 | 3.781 | 511 | 592 | 3.593 | 539 | 548 |
| fev | 131 | 38,2 | 848 | 951 | 4.450 | 586 | 1.097 | 4.084 |
| mar | 182 | 42,3 | 205 | 1.764 | 4.827 | -159 | 1.860 | 4.055 |
| abr | 142 | 39,4 | 2.836 | 839 | 5.067 | 2.552 | 903 | 4.183 |
| mai | 129 | 36,4 | 1.852 | 1.185 | 8.110 | 1.594 | 1.307 | 6.968 |
| jun | 115 | 40,0 | 495 | 1.262 | 10.430 | 265 | 1.384 | 9.070 |
| jul | 90 | 40,0 | 926 | 1.448 | 10.661 | 746 | 1.478 | 9.039 |
| ago | 130 | 37,7 | 1.351 | 1.534 | 11.581 | 1.091 | 1.636 | 9.807 |
| set | 139 | 50,4 | 3.681 | 672 | 13.253 | 3.403 | 758 | 11.225 |
| out | 35 | 48,6 | 735 | 435 | 16.540 | 665 | 447 | 14.224 |
| total | 1187 | 41,2 | 16.710 | 1.788 | 592 | 14.336 | 1.860 | 548 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win | K=3 | ranking | independente (cortes teto 11, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 113 | 44,2 | 3.592 | 506 | 547 | 3.366 | 534 | 499 |
| fev | 165 | 41,2 | 2.066 | 996 | 4.402 | 1.736 | 1.046 | 4.164 |
| mar | 233 | 45,9 | 2.461 | 1.659 | 6.567 | 1.995 | 1.715 | 5.867 |
| abr | 161 | 40,4 | 2.681 | 704 | 8.487 | 2.359 | 756 | 7.407 |
| mai | 153 | 37,3 | 2.075 | 1.349 | 11.240 | 1.769 | 1.487 | 9.852 |
| jun | 140 | 39,3 | -6 | 1.280 | 13.723 | -286 | 1.398 | 11.850 |
| jul | 105 | 41,0 | 1.405 | 1.355 | 13.602 | 1.195 | 1.375 | 11.634 |
| ago | 143 | 39,9 | 2.039 | 1.509 | 15.072 | 1.753 | 1.615 | 12.924 |
| set | 162 | 50,6 | 4.661 | 630 | 17.272 | 4.337 | 640 | 14.844 |
| out | 41 | 41,5 | -689 | 1.562 | 21.285 | -771 | 1.600 | 18.453 |
| total | 1416 | 42,4 | 20.285 | 1.659 | 547 | 17.453 | 1.715 | 499 |

Quebrou: s/custo nao; R$2 nao.

### 5 sem Win | K=3 | ranking | NETTING (cortes teto 4, bloq netting 236)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 94 | 43,6 | 3.781 | 511 | 592 | 3.593 | 539 | 548 |
| fev | 131 | 38,2 | 848 | 951 | 4.450 | 586 | 1.097 | 4.084 |
| mar | 182 | 42,3 | 205 | 1.764 | 4.827 | -159 | 1.860 | 4.055 |
| abr | 142 | 39,4 | 2.836 | 839 | 5.067 | 2.552 | 903 | 4.183 |
| mai | 129 | 36,4 | 1.852 | 1.185 | 8.110 | 1.594 | 1.307 | 6.968 |
| jun | 115 | 40,0 | 495 | 1.262 | 10.430 | 265 | 1.384 | 9.070 |
| jul | 90 | 40,0 | 926 | 1.448 | 10.661 | 746 | 1.478 | 9.039 |
| ago | 130 | 37,7 | 1.351 | 1.534 | 11.581 | 1.091 | 1.636 | 9.807 |
| set | 139 | 50,4 | 3.681 | 672 | 13.253 | 3.403 | 758 | 11.225 |
| out | 35 | 48,6 | 735 | 435 | 16.540 | 665 | 447 | 14.224 |
| total | 1187 | 41,2 | 16.710 | 1.788 | 592 | 14.336 | 1.860 | 548 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win) | K=1 | chegada | independente (cortes teto 344, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 74 | 44,6 | 1.898 | 555 | 445 | 1.750 | 591 | 409 |
| fev | 108 | 37,0 | 567 | 938 | 2.826 | 351 | 1.062 | 2.676 |
| mar | 181 | 44,8 | 1.927 | 507 | 3.481 | 1.565 | 577 | 3.001 |
| abr | 96 | 41,7 | 1.826 | 389 | 5.383 | 1.634 | 411 | 4.655 |
| mai | 102 | 35,3 | 479 | 711 | 6.507 | 275 | 753 | 5.547 |
| jun | 87 | 40,2 | -181 | 818 | 7.393 | -355 | 936 | 6.111 |
| jul | 72 | 40,3 | 856 | 527 | 7.220 | 712 | 535 | 5.892 |
| ago | 89 | 37,1 | 851 | 1.080 | 7.981 | 673 | 1.148 | 6.533 |
| set | 102 | 49,0 | 2.430 | 668 | 9.182 | 2.226 | 708 | 7.562 |
| out | 32 | 37,5 | -1.180 | 1.188 | 10.473 | -1.244 | 1.244 | 8.587 |
| total | 943 | 41,3 | 9.473 | 1.188 | 445 | 7.587 | 1.244 | 409 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win) | K=1 | chegada | NETTING (cortes teto 251, bloq netting 93)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 74 | 44,6 | 1.898 | 555 | 445 | 1.750 | 591 | 409 |
| fev | 108 | 37,0 | 567 | 938 | 2.826 | 351 | 1.062 | 2.676 |
| mar | 181 | 44,8 | 1.927 | 507 | 3.481 | 1.565 | 577 | 3.001 |
| abr | 96 | 41,7 | 1.826 | 389 | 5.383 | 1.634 | 411 | 4.655 |
| mai | 102 | 35,3 | 479 | 711 | 6.507 | 275 | 753 | 5.547 |
| jun | 87 | 40,2 | -181 | 818 | 7.393 | -355 | 936 | 6.111 |
| jul | 72 | 40,3 | 856 | 527 | 7.220 | 712 | 535 | 5.892 |
| ago | 89 | 37,1 | 851 | 1.080 | 7.981 | 673 | 1.148 | 6.533 |
| set | 102 | 49,0 | 2.430 | 668 | 9.182 | 2.226 | 708 | 7.562 |
| out | 32 | 37,5 | -1.180 | 1.188 | 10.473 | -1.244 | 1.244 | 8.587 |
| total | 943 | 41,3 | 9.473 | 1.188 | 445 | 7.587 | 1.244 | 409 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win) | K=1 | ranking | independente (cortes teto 349, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 74 | 44,6 | 1.898 | 555 | 445 | 1.750 | 591 | 409 |
| fev | 107 | 37,4 | 525 | 884 | 2.826 | 311 | 1.008 | 2.676 |
| mar | 182 | 44,0 | 1.720 | 555 | 3.439 | 1.356 | 599 | 2.961 |
| abr | 95 | 40,0 | 1.722 | 389 | 5.134 | 1.532 | 411 | 4.406 |
| mai | 101 | 32,7 | 253 | 711 | 6.154 | 51 | 753 | 5.196 |
| jun | 87 | 39,1 | -221 | 818 | 6.774 | -395 | 936 | 5.496 |
| jul | 72 | 40,3 | 856 | 527 | 6.601 | 712 | 535 | 5.277 |
| ago | 86 | 33,7 | 591 | 1.080 | 7.362 | 419 | 1.148 | 5.918 |
| set | 102 | 49,0 | 2.430 | 668 | 8.303 | 2.226 | 708 | 6.693 |
| out | 32 | 37,5 | -1.180 | 1.188 | 9.594 | -1.244 | 1.244 | 7.718 |
| total | 938 | 40,3 | 8.594 | 1.188 | 445 | 6.718 | 1.244 | 409 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win) | K=1 | ranking | NETTING (cortes teto 255, bloq netting 94)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 74 | 44,6 | 1.898 | 555 | 445 | 1.750 | 591 | 409 |
| fev | 107 | 37,4 | 525 | 884 | 2.826 | 311 | 1.008 | 2.676 |
| mar | 182 | 44,0 | 1.720 | 555 | 3.439 | 1.356 | 599 | 2.961 |
| abr | 95 | 40,0 | 1.722 | 389 | 5.134 | 1.532 | 411 | 4.406 |
| mai | 101 | 32,7 | 253 | 711 | 6.154 | 51 | 753 | 5.196 |
| jun | 87 | 39,1 | -221 | 818 | 6.774 | -395 | 936 | 5.496 |
| jul | 72 | 40,3 | 856 | 527 | 6.601 | 712 | 535 | 5.277 |
| ago | 86 | 33,7 | 591 | 1.080 | 7.362 | 419 | 1.148 | 5.918 |
| set | 102 | 49,0 | 2.430 | 668 | 8.303 | 2.226 | 708 | 6.693 |
| out | 32 | 37,5 | -1.180 | 1.188 | 9.594 | -1.244 | 1.244 | 7.718 |
| total | 938 | 40,3 | 8.594 | 1.188 | 445 | 6.718 | 1.244 | 409 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win) | K=2 | chegada | independente (cortes teto 53, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 98 | 43,9 | 2.304 | 463 | 537 | 2.108 | 509 | 491 |
| fev | 143 | 38,5 | 891 | 894 | 3.140 | 605 | 1.046 | 2.936 |
| mar | 208 | 44,7 | 2.413 | 575 | 4.272 | 1.997 | 653 | 3.746 |
| abr | 137 | 39,4 | 2.561 | 581 | 6.513 | 2.287 | 659 | 5.567 |
| mai | 134 | 35,1 | 1.298 | 855 | 8.458 | 1.030 | 898 | 7.244 |
| jun | 120 | 40,0 | 25 | 833 | 10.315 | -215 | 1.001 | 8.762 |
| jul | 86 | 40,7 | 1.798 | 620 | 10.118 | 1.626 | 632 | 8.402 |
| ago | 132 | 40,9 | 1.920 | 1.241 | 11.896 | 1.656 | 1.345 | 10.032 |
| set | 137 | 48,9 | 2.873 | 831 | 14.169 | 2.599 | 929 | 12.051 |
| out | 39 | 41,0 | -161 | 920 | 16.648 | -239 | 956 | 14.246 |
| total | 1234 | 41,5 | 15.922 | 1.282 | 537 | 13.454 | 1.388 | 491 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win) | K=2 | chegada | NETTING (cortes teto 38, bloq netting 114)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 84 | 41,7 | 2.177 | 443 | 557 | 2.009 | 481 | 519 |
| fev | 135 | 37,8 | 827 | 796 | 2.938 | 557 | 940 | 2.764 |
| mar | 197 | 44,2 | 2.096 | 502 | 3.981 | 1.702 | 569 | 3.417 |
| abr | 126 | 39,7 | 2.608 | 614 | 6.005 | 2.356 | 680 | 5.125 |
| mai | 122 | 35,2 | 1.381 | 846 | 7.997 | 1.137 | 870 | 6.871 |
| jun | 108 | 39,8 | -18 | 880 | 9.990 | -234 | 1.037 | 8.462 |
| jul | 82 | 40,2 | 1.707 | 626 | 9.608 | 1.543 | 652 | 8.030 |
| ago | 122 | 39,3 | 1.713 | 1.269 | 11.358 | 1.469 | 1.366 | 9.640 |
| set | 125 | 48,8 | 2.881 | 668 | 13.450 | 2.631 | 714 | 11.496 |
| out | 34 | 47,1 | 621 | 435 | 15.937 | 553 | 447 | 13.723 |
| total | 1135 | 41,1 | 15.993 | 1.307 | 557 | 13.723 | 1.469 | 519 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win) | K=2 | ranking | independente (cortes teto 53, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 98 | 43,9 | 2.304 | 463 | 537 | 2.108 | 509 | 491 |
| fev | 142 | 38,7 | 1.024 | 894 | 3.140 | 740 | 1.046 | 2.936 |
| mar | 208 | 44,7 | 2.413 | 575 | 4.405 | 1.997 | 653 | 3.881 |
| abr | 137 | 39,4 | 2.561 | 581 | 6.646 | 2.287 | 659 | 5.702 |
| mai | 134 | 35,1 | 1.298 | 855 | 8.591 | 1.030 | 898 | 7.379 |
| jun | 120 | 40,0 | 25 | 833 | 10.448 | -215 | 1.001 | 8.897 |
| jul | 86 | 40,7 | 1.798 | 620 | 10.251 | 1.626 | 632 | 8.537 |
| ago | 133 | 40,6 | 1.840 | 1.241 | 12.029 | 1.574 | 1.345 | 10.167 |
| set | 137 | 48,9 | 2.873 | 831 | 14.222 | 2.599 | 929 | 12.104 |
| out | 39 | 41,0 | -161 | 920 | 16.701 | -239 | 956 | 14.299 |
| total | 1234 | 41,5 | 15.975 | 1.282 | 537 | 13.507 | 1.388 | 491 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win) | K=2 | ranking | NETTING (cortes teto 38, bloq netting 114)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 84 | 41,7 | 2.177 | 443 | 557 | 2.009 | 481 | 519 |
| fev | 134 | 38,1 | 960 | 796 | 2.938 | 692 | 940 | 2.764 |
| mar | 197 | 44,2 | 2.096 | 502 | 4.114 | 1.702 | 569 | 3.552 |
| abr | 126 | 39,7 | 2.608 | 614 | 6.138 | 2.356 | 680 | 5.260 |
| mai | 122 | 35,2 | 1.381 | 846 | 8.130 | 1.137 | 870 | 7.006 |
| jun | 108 | 39,8 | -18 | 880 | 10.123 | -234 | 1.037 | 8.597 |
| jul | 82 | 40,2 | 1.707 | 626 | 9.741 | 1.543 | 652 | 8.165 |
| ago | 123 | 39,0 | 1.633 | 1.269 | 11.491 | 1.387 | 1.366 | 9.775 |
| set | 125 | 48,8 | 2.881 | 668 | 13.503 | 2.631 | 714 | 11.549 |
| out | 34 | 47,1 | 621 | 435 | 15.990 | 553 | 447 | 13.776 |
| total | 1135 | 41,1 | 16.046 | 1.307 | 557 | 13.776 | 1.469 | 519 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win) | K=3 | chegada | independente (cortes teto 5, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 101 | 43,6 | 2.353 | 536 | 464 | 2.151 | 586 | 414 |
| fev | 148 | 39,9 | 1.102 | 852 | 3.154 | 806 | 990 | 2.942 |
| mar | 213 | 46,0 | 2.752 | 575 | 4.532 | 2.326 | 653 | 3.990 |
| abr | 145 | 39,3 | 2.980 | 767 | 7.033 | 2.690 | 849 | 6.043 |
| mai | 141 | 35,5 | 1.045 | 1.040 | 9.476 | 763 | 1.166 | 8.220 |
| jun | 128 | 41,4 | 264 | 770 | 11.080 | 8 | 873 | 9.578 |
| jul | 87 | 40,2 | 1.766 | 620 | 11.122 | 1.592 | 632 | 9.334 |
| ago | 134 | 41,0 | 1.871 | 1.241 | 12.868 | 1.603 | 1.345 | 10.930 |
| set | 146 | 48,6 | 3.581 | 842 | 15.092 | 3.289 | 948 | 12.896 |
| out | 39 | 41,0 | -161 | 920 | 18.279 | -239 | 956 | 15.781 |
| total | 1282 | 42,0 | 17.553 | 1.282 | 464 | 14.989 | 1.388 | 414 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win) | K=3 | chegada | NETTING (cortes teto 3, bloq netting 114)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 87 | 42,5 | 2.245 | 474 | 526 | 2.071 | 514 | 486 |
| fev | 137 | 38,0 | 850 | 796 | 2.971 | 576 | 884 | 2.789 |
| mar | 199 | 44,7 | 2.244 | 502 | 4.072 | 1.846 | 569 | 3.498 |
| abr | 134 | 39,6 | 3.027 | 800 | 6.165 | 2.759 | 870 | 5.253 |
| mai | 127 | 35,4 | 1.099 | 998 | 8.655 | 845 | 1.122 | 7.499 |
| jun | 112 | 40,2 | 53 | 878 | 10.373 | -171 | 1.041 | 8.861 |
| jul | 83 | 39,8 | 1.675 | 626 | 10.055 | 1.509 | 652 | 8.429 |
| ago | 124 | 39,5 | 1.664 | 1.269 | 11.773 | 1.416 | 1.366 | 10.005 |
| set | 133 | 48,9 | 3.642 | 668 | 13.816 | 3.376 | 732 | 11.808 |
| out | 34 | 47,1 | 621 | 435 | 17.064 | 553 | 447 | 14.780 |
| total | 1170 | 41,4 | 17.120 | 1.307 | 526 | 14.780 | 1.473 | 486 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win) | K=3 | ranking | independente (cortes teto 5, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 101 | 43,6 | 2.353 | 536 | 464 | 2.151 | 586 | 414 |
| fev | 148 | 39,9 | 1.102 | 852 | 3.154 | 806 | 990 | 2.942 |
| mar | 213 | 46,0 | 2.752 | 575 | 4.532 | 2.326 | 653 | 3.990 |
| abr | 145 | 39,3 | 2.980 | 767 | 7.033 | 2.690 | 849 | 6.043 |
| mai | 141 | 35,5 | 1.045 | 1.040 | 9.476 | 763 | 1.166 | 8.220 |
| jun | 128 | 41,4 | 264 | 770 | 11.080 | 8 | 873 | 9.578 |
| jul | 87 | 40,2 | 1.766 | 620 | 11.122 | 1.592 | 632 | 9.334 |
| ago | 134 | 41,0 | 1.871 | 1.241 | 12.868 | 1.603 | 1.345 | 10.930 |
| set | 146 | 48,6 | 3.581 | 842 | 15.092 | 3.289 | 948 | 12.896 |
| out | 39 | 41,0 | -161 | 920 | 18.279 | -239 | 956 | 15.781 |
| total | 1282 | 42,0 | 17.553 | 1.282 | 464 | 14.989 | 1.388 | 414 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win) | K=3 | ranking | NETTING (cortes teto 3, bloq netting 114)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 87 | 42,5 | 2.245 | 474 | 526 | 2.071 | 514 | 486 |
| fev | 137 | 38,0 | 850 | 796 | 2.971 | 576 | 884 | 2.789 |
| mar | 199 | 44,7 | 2.244 | 502 | 4.072 | 1.846 | 569 | 3.498 |
| abr | 134 | 39,6 | 3.027 | 800 | 6.165 | 2.759 | 870 | 5.253 |
| mai | 127 | 35,4 | 1.099 | 998 | 8.655 | 845 | 1.122 | 7.499 |
| jun | 112 | 40,2 | 53 | 878 | 10.373 | -171 | 1.041 | 8.861 |
| jul | 83 | 39,8 | 1.675 | 626 | 10.055 | 1.509 | 652 | 8.429 |
| ago | 124 | 39,5 | 1.664 | 1.269 | 11.773 | 1.416 | 1.366 | 10.005 |
| set | 133 | 48,9 | 3.642 | 668 | 13.816 | 3.376 | 732 | 11.808 |
| out | 34 | 47,1 | 621 | 435 | 17.064 | 553 | 447 | 14.780 |
| total | 1170 | 41,4 | 17.120 | 1.307 | 526 | 14.780 | 1.473 | 486 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win_c1) | K=1 | chegada | independente (cortes teto 344, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 75 | 42,7 | 1.821 | 566 | 434 | 1.671 | 602 | 398 |
| fev | 108 | 37,0 | 567 | 938 | 2.749 | 351 | 1.062 | 2.597 |
| mar | 182 | 44,0 | 1.764 | 536 | 3.423 | 1.400 | 580 | 2.947 |
| abr | 99 | 42,4 | 2.595 | 389 | 5.131 | 2.397 | 411 | 4.397 |
| mai | 102 | 35,3 | 539 | 651 | 7.096 | 335 | 693 | 6.126 |
| jun | 87 | 39,1 | -174 | 803 | 7.989 | -348 | 921 | 6.697 |
| jul | 73 | 39,7 | 901 | 527 | 7.827 | 755 | 535 | 6.497 |
| ago | 89 | 34,8 | 635 | 1.152 | 8.622 | 457 | 1.234 | 7.162 |
| set | 102 | 48,0 | 2.433 | 668 | 9.607 | 2.229 | 708 | 7.975 |
| out | 32 | 37,5 | -1.180 | 1.188 | 10.901 | -1.244 | 1.244 | 9.003 |
| total | 949 | 40,6 | 9.901 | 1.193 | 434 | 8.003 | 1.277 | 398 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win_c1) | K=1 | chegada | NETTING (cortes teto 251, bloq netting 93)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 75 | 42,7 | 1.821 | 566 | 434 | 1.671 | 602 | 398 |
| fev | 108 | 37,0 | 567 | 938 | 2.749 | 351 | 1.062 | 2.597 |
| mar | 182 | 44,0 | 1.764 | 536 | 3.423 | 1.400 | 580 | 2.947 |
| abr | 99 | 42,4 | 2.595 | 389 | 5.131 | 2.397 | 411 | 4.397 |
| mai | 102 | 35,3 | 539 | 651 | 7.096 | 335 | 693 | 6.126 |
| jun | 87 | 39,1 | -174 | 803 | 7.989 | -348 | 921 | 6.697 |
| jul | 73 | 39,7 | 901 | 527 | 7.827 | 755 | 535 | 6.497 |
| ago | 89 | 34,8 | 635 | 1.152 | 8.622 | 457 | 1.234 | 7.162 |
| set | 102 | 48,0 | 2.433 | 668 | 9.607 | 2.229 | 708 | 7.975 |
| out | 32 | 37,5 | -1.180 | 1.188 | 10.901 | -1.244 | 1.244 | 9.003 |
| total | 949 | 40,6 | 9.901 | 1.193 | 434 | 8.003 | 1.277 | 398 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win_c1) | K=1 | ranking | independente (cortes teto 350, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 75 | 42,7 | 1.812 | 566 | 434 | 1.662 | 602 | 398 |
| fev | 107 | 37,4 | 525 | 884 | 2.740 | 311 | 1.008 | 2.588 |
| mar | 182 | 44,0 | 1.745 | 555 | 3.372 | 1.381 | 599 | 2.898 |
| abr | 98 | 40,8 | 2.491 | 389 | 5.061 | 2.295 | 411 | 4.329 |
| mai | 101 | 32,7 | 313 | 651 | 6.922 | 111 | 693 | 5.956 |
| jun | 87 | 39,1 | -206 | 803 | 7.557 | -380 | 921 | 6.271 |
| jul | 73 | 39,7 | 901 | 527 | 7.395 | 755 | 535 | 6.071 |
| ago | 86 | 31,4 | 375 | 1.152 | 8.190 | 203 | 1.234 | 6.736 |
| set | 102 | 48,0 | 2.433 | 668 | 8.915 | 2.229 | 708 | 7.295 |
| out | 32 | 37,5 | -1.180 | 1.188 | 10.209 | -1.244 | 1.244 | 8.323 |
| total | 943 | 39,9 | 9.209 | 1.193 | 434 | 7.323 | 1.277 | 398 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win_c1) | K=1 | ranking | NETTING (cortes teto 256, bloq netting 94)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 75 | 42,7 | 1.812 | 566 | 434 | 1.662 | 602 | 398 |
| fev | 107 | 37,4 | 525 | 884 | 2.740 | 311 | 1.008 | 2.588 |
| mar | 182 | 44,0 | 1.745 | 555 | 3.372 | 1.381 | 599 | 2.898 |
| abr | 98 | 40,8 | 2.491 | 389 | 5.061 | 2.295 | 411 | 4.329 |
| mai | 101 | 32,7 | 313 | 651 | 6.922 | 111 | 693 | 5.956 |
| jun | 87 | 39,1 | -206 | 803 | 7.557 | -380 | 921 | 6.271 |
| jul | 73 | 39,7 | 901 | 527 | 7.395 | 755 | 535 | 6.071 |
| ago | 86 | 31,4 | 375 | 1.152 | 8.190 | 203 | 1.234 | 6.736 |
| set | 102 | 48,0 | 2.433 | 668 | 8.915 | 2.229 | 708 | 7.295 |
| out | 32 | 37,5 | -1.180 | 1.188 | 10.209 | -1.244 | 1.244 | 8.323 |
| total | 943 | 39,9 | 9.209 | 1.193 | 434 | 7.323 | 1.277 | 398 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win_c1) | K=2 | chegada | independente (cortes teto 52, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 98 | 42,9 | 2.290 | 459 | 541 | 2.094 | 505 | 495 |
| fev | 143 | 38,5 | 891 | 894 | 3.126 | 605 | 1.046 | 2.922 |
| mar | 209 | 44,5 | 2.450 | 550 | 4.258 | 2.032 | 628 | 3.757 |
| abr | 141 | 40,4 | 2.705 | 548 | 6.599 | 2.423 | 617 | 5.647 |
| mai | 134 | 35,1 | 1.440 | 830 | 8.685 | 1.172 | 873 | 7.461 |
| jun | 121 | 38,0 | 15 | 799 | 10.624 | -227 | 988 | 9.049 |
| jul | 87 | 40,2 | 1.843 | 620 | 10.478 | 1.669 | 632 | 8.750 |
| ago | 132 | 39,4 | 1.704 | 1.452 | 12.240 | 1.440 | 1.556 | 10.362 |
| set | 137 | 48,2 | 2.615 | 831 | 14.297 | 2.341 | 929 | 12.165 |
| out | 39 | 41,0 | -161 | 920 | 16.518 | -239 | 956 | 14.102 |
| total | 1241 | 41,0 | 15.792 | 1.493 | 541 | 13.310 | 1.599 | 495 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win_c1) | K=2 | chegada | NETTING (cortes teto 38, bloq netting 114)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 84 | 40,5 | 2.163 | 439 | 561 | 1.995 | 477 | 523 |
| fev | 135 | 37,8 | 827 | 796 | 2.924 | 557 | 940 | 2.750 |
| mar | 197 | 43,7 | 2.065 | 558 | 3.974 | 1.671 | 604 | 3.428 |
| abr | 130 | 40,8 | 2.752 | 568 | 6.023 | 2.492 | 638 | 5.139 |
| mai | 122 | 35,2 | 1.523 | 821 | 8.156 | 1.279 | 845 | 7.022 |
| jun | 109 | 37,6 | -28 | 894 | 10.221 | -246 | 1.062 | 8.683 |
| jul | 83 | 39,8 | 1.752 | 620 | 9.900 | 1.586 | 632 | 8.312 |
| ago | 122 | 37,7 | 1.497 | 1.477 | 11.634 | 1.253 | 1.577 | 9.904 |
| set | 125 | 48,0 | 2.623 | 668 | 13.510 | 2.373 | 714 | 11.544 |
| out | 34 | 47,1 | 621 | 435 | 15.739 | 553 | 447 | 13.513 |
| total | 1141 | 40,6 | 15.795 | 1.518 | 561 | 13.513 | 1.620 | 523 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win_c1) | K=2 | ranking | independente (cortes teto 52, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 98 | 42,9 | 2.290 | 459 | 541 | 2.094 | 505 | 495 |
| fev | 142 | 38,7 | 1.024 | 894 | 3.126 | 740 | 1.046 | 2.922 |
| mar | 209 | 44,5 | 2.450 | 550 | 4.391 | 2.032 | 628 | 3.892 |
| abr | 141 | 40,4 | 2.705 | 548 | 6.732 | 2.423 | 617 | 5.782 |
| mai | 134 | 35,1 | 1.440 | 830 | 8.818 | 1.172 | 873 | 7.596 |
| jun | 121 | 38,0 | 15 | 799 | 10.757 | -227 | 988 | 9.184 |
| jul | 87 | 40,2 | 1.843 | 620 | 10.611 | 1.669 | 632 | 8.885 |
| ago | 133 | 39,1 | 1.624 | 1.452 | 12.373 | 1.358 | 1.556 | 10.497 |
| set | 137 | 48,2 | 2.615 | 831 | 14.350 | 2.341 | 929 | 12.218 |
| out | 39 | 41,0 | -161 | 920 | 16.571 | -239 | 956 | 14.155 |
| total | 1241 | 41,0 | 15.845 | 1.493 | 541 | 13.363 | 1.599 | 495 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win_c1) | K=2 | ranking | NETTING (cortes teto 38, bloq netting 114)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 84 | 40,5 | 2.163 | 439 | 561 | 1.995 | 477 | 523 |
| fev | 134 | 38,1 | 960 | 796 | 2.924 | 692 | 940 | 2.750 |
| mar | 197 | 43,7 | 2.065 | 558 | 4.107 | 1.671 | 604 | 3.563 |
| abr | 130 | 40,8 | 2.752 | 568 | 6.156 | 2.492 | 638 | 5.274 |
| mai | 122 | 35,2 | 1.523 | 821 | 8.289 | 1.279 | 845 | 7.157 |
| jun | 109 | 37,6 | -28 | 894 | 10.354 | -246 | 1.062 | 8.818 |
| jul | 83 | 39,8 | 1.752 | 620 | 10.033 | 1.586 | 632 | 8.447 |
| ago | 123 | 37,4 | 1.417 | 1.477 | 11.767 | 1.171 | 1.577 | 10.039 |
| set | 125 | 48,0 | 2.623 | 668 | 13.563 | 2.373 | 714 | 11.597 |
| out | 34 | 47,1 | 621 | 435 | 15.792 | 553 | 447 | 13.566 |
| total | 1141 | 40,6 | 15.848 | 1.518 | 561 | 13.566 | 1.620 | 523 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win_c1) | K=3 | chegada | independente (cortes teto 5, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 101 | 42,6 | 2.339 | 532 | 468 | 2.137 | 582 | 418 |
| fev | 148 | 39,9 | 1.102 | 852 | 3.140 | 806 | 990 | 2.928 |
| mar | 213 | 45,5 | 2.721 | 550 | 4.518 | 2.295 | 628 | 4.001 |
| abr | 149 | 40,3 | 3.124 | 721 | 7.051 | 2.826 | 807 | 6.057 |
| mai | 141 | 35,5 | 1.187 | 1.015 | 9.635 | 905 | 1.141 | 8.371 |
| jun | 129 | 39,5 | 254 | 768 | 11.321 | -4 | 871 | 9.811 |
| jul | 88 | 39,8 | 1.811 | 620 | 11.414 | 1.635 | 632 | 9.616 |
| ago | 134 | 39,6 | 1.655 | 1.452 | 13.144 | 1.387 | 1.556 | 11.194 |
| set | 146 | 47,9 | 3.323 | 842 | 15.152 | 3.031 | 948 | 12.944 |
| out | 39 | 41,0 | -161 | 920 | 18.081 | -239 | 956 | 15.571 |
| total | 1288 | 41,5 | 17.355 | 1.493 | 468 | 14.779 | 1.599 | 418 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win_c1) | K=3 | chegada | NETTING (cortes teto 3, bloq netting 114)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 87 | 41,4 | 2.231 | 470 | 530 | 2.057 | 510 | 490 |
| fev | 137 | 38,0 | 850 | 796 | 2.957 | 576 | 884 | 2.775 |
| mar | 199 | 44,2 | 2.213 | 558 | 4.065 | 1.815 | 604 | 3.509 |
| abr | 138 | 40,6 | 3.171 | 754 | 6.183 | 2.895 | 828 | 5.267 |
| mai | 127 | 35,4 | 1.241 | 973 | 8.814 | 987 | 1.097 | 7.650 |
| jun | 113 | 38,1 | 43 | 892 | 10.614 | -183 | 1.066 | 9.082 |
| jul | 84 | 39,3 | 1.720 | 620 | 10.347 | 1.552 | 632 | 8.711 |
| ago | 124 | 37,9 | 1.448 | 1.477 | 12.049 | 1.200 | 1.577 | 10.269 |
| set | 133 | 48,1 | 3.384 | 668 | 13.876 | 3.118 | 732 | 11.856 |
| out | 34 | 47,1 | 621 | 435 | 16.866 | 553 | 447 | 14.570 |
| total | 1176 | 40,8 | 16.922 | 1.518 | 530 | 14.570 | 1.620 | 490 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win_c1) | K=3 | ranking | independente (cortes teto 5, bloq netting 0)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 101 | 42,6 | 2.339 | 532 | 468 | 2.137 | 582 | 418 |
| fev | 148 | 39,9 | 1.102 | 852 | 3.140 | 806 | 990 | 2.928 |
| mar | 213 | 45,5 | 2.721 | 550 | 4.518 | 2.295 | 628 | 4.001 |
| abr | 149 | 40,3 | 3.124 | 721 | 7.051 | 2.826 | 807 | 6.057 |
| mai | 141 | 35,5 | 1.187 | 1.015 | 9.635 | 905 | 1.141 | 8.371 |
| jun | 129 | 39,5 | 254 | 768 | 11.321 | -4 | 871 | 9.811 |
| jul | 88 | 39,8 | 1.811 | 620 | 11.414 | 1.635 | 632 | 9.616 |
| ago | 134 | 39,6 | 1.655 | 1.452 | 13.144 | 1.387 | 1.556 | 11.194 |
| set | 146 | 47,9 | 3.323 | 842 | 15.152 | 3.031 | 948 | 12.944 |
| out | 39 | 41,0 | -161 | 920 | 18.081 | -239 | 956 | 15.571 |
| total | 1288 | 41,5 | 17.355 | 1.493 | 468 | 14.779 | 1.599 | 418 |

Quebrou: s/custo nao; R$2 nao.

### 4 sem WdoRet (Win_c1) | K=3 | ranking | NETTING (cortes teto 3, bloq netting 114)

| mes | ops | acerto% | liq s/custo | maxDD | menor saldo | liq R$2 | maxDD R$2 | menor saldo R$2 |
|---|---|---|---|---|---|---|---|---|
| jan | 87 | 41,4 | 2.231 | 470 | 530 | 2.057 | 510 | 490 |
| fev | 137 | 38,0 | 850 | 796 | 2.957 | 576 | 884 | 2.775 |
| mar | 199 | 44,2 | 2.213 | 558 | 4.065 | 1.815 | 604 | 3.509 |
| abr | 138 | 40,6 | 3.171 | 754 | 6.183 | 2.895 | 828 | 5.267 |
| mai | 127 | 35,4 | 1.241 | 973 | 8.814 | 987 | 1.097 | 7.650 |
| jun | 113 | 38,1 | 43 | 892 | 10.614 | -183 | 1.066 | 9.082 |
| jul | 84 | 39,3 | 1.720 | 620 | 10.347 | 1.552 | 632 | 8.711 |
| ago | 124 | 37,9 | 1.448 | 1.477 | 12.049 | 1.200 | 1.577 | 10.269 |
| set | 133 | 48,1 | 3.384 | 668 | 13.876 | 3.118 | 732 | 11.856 |
| out | 34 | 47,1 | 621 | 435 | 16.866 | 553 | 447 | 14.570 |
| total | 1176 | 40,8 | 16.922 | 1.518 | 530 | 14.570 | 1.620 | 490 |

Quebrou: s/custo nao; R$2 nao.
