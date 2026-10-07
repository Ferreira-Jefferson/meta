# N2 — RDT: resultado (DEV + VAL única)

Script: `n2_rdt.py` (SHA-256 `ed31fee66739a54ebea4884bafc25abe645071825040b7ed07700f0e1ae1fd36`, gravado em PREREGISTRO.md antes do VAL). Execução do Testador, ticks sintéticos 4/M1, R$1.000 corrido, R$2/op, 1 contrato.

## DEV (2022-01-03 → 2024-06-28), 12 células (R$, custo R$2/op)
| f | até | k | ops | sem custo | com custo | PF | DD | caixa mín | meses+ (c/ op) | tri+ /10 | sem 2 melhores |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0,25 | 12:00 | 0,3 | 26 | 936 | 884 | 1,85 | 568 | 744 | 7/30 (7/19) | 4 | -245 |
| 0,50 | 12:00 | 0,3 | 40 | 2.249 | 2.169 | 2,30 | 412 | 1.000 | 13/30 (13/23) | 5 | 1.194 |
| 0,75 | 12:00 | 0,3 | 76 | 1.451 | 1.299 | 1,30 | 1.521 | -71 (quebra) | 16/30 (16/27) | 5 | 458 |
| 0,25 | 14:00 | 0,3 | 40 | 1.246 | 1.166 | 1,71 | 752 | 1.000 | 9/30 (9/23) | 4 | 37 |
| 0,50 | 14:00 | 0,3 | 58 | 1.586 | 1.470 | 1,51 | 629 | 1.000 | 13/30 (13/27) | 5 | 495 |
| 0,75 | 14:00 | 0,3 | 83 | 693 | 527 | 1,10 | 1.698 | -248 (quebra) | 14/30 (14/28) | 5 | -314 |
| 0,25 | 12:00 | 0,4 | 13 | 523 | 497 | 1,93 | 355 | 921 | 4/30 (4/11) | 4 | -329 |
| **0,50** | **12:00** | **0,4** | 21 | 1.615 | 1.573 | 2,77 | 272 | 1.000 | 9/30 (9/15) | 4 | 618 |
| 0,75 | 12:00 | 0,4 | 49 | 1.755 | 1.657 | 1,60 | 1.145 | 211 | 14/30 (14/23) | 6 | 816 |
| 0,25 | 14:00 | 0,4 | 21 | 1.012 | 970 | 2,17 | 425 | 1.000 | 6/30 (6/14) | 4 | -140 |
| 0,50 | 14:00 | 0,4 | 34 | 1.389 | 1.321 | 1,80 | 419 | 1.000 | 11/30 (11/20) | 5 | 366 |
| 0,75 | 14:00 | 0,4 | 55 | 1.135 | 1.025 | 1,30 | 1.322 | 34 | 14/30 (14/24) | 6 | 184 |

Anos (com custo) em `n2_dev_grade.csv`. A célula f 0,5 / até 12:00 / k 0,3 reproduz a olhada do N1: 40 operações, +R$2.169, PF 2,30, DD R$412, caixa mínimo R$1.210 no N1 contra R$1.000 aqui (aqui o caixa mínimo é truncado em R$1.000; nunca caiu abaixo).

Regra de escolha: células com líquido > 0, vizinhos em f e em ate (mesmo k) > 0 e caixa mínimo ≥ R$500; maior lucro/DD. As 3 com f 0,75 e as de caixa < 500 saem; vence **f 0,5 / até 12:00 / k 0,4** (lucro/DD 5,78; stop mediano R$106). Controle aleatório DEV (200): percentil 97,5, p95 = R$1.263. Sem as 2 melhores: +R$618.

## VAL (2024-07-01 → 2025-09-30), célula congelada, uma vez
12 operações (50 sinais), sem custo +R$239, **com custo +R$215**, PF 1,55, DD R$266, caixa mínimo R$734, sem quebra. Sem as 2 melhores: -R$241.

| mês | R$ | mês | R$ | mês | R$ |
|---|---|---|---|---|---|
| 2024-07 | -86 | 2024-12 | — | 2025-07 | — |
| 2024-08 | -97 | 2025-01 | — | 2025-08 | 47 |
| 2024-09 | -9 | 2025-02 | 8 | 2025-09 | 104 |
| 2024-10 | -74 | 2025-03 | — | | |
| 2024-11 | 325 | 2025-04/05 | — | | |
| | | 2025-06 | -3 | | |

Meses positivos: 4/15 (leitura do TODO), 4/9 contando só meses com operação (informativo).

| trimestre | R$ |
|---|---|
| 2024 T3 | -192 |
| 2024 T4 | +251 |
| 2025 T1 | +8 |
| 2025 T2 | -3 |
| 2025 T3 | +151 |

3 de 5 positivos.

Controle aleatório VAL (200 sorteios, mesma contagem por mês, mesmo horário, mesma geometria em ATR): média -R$237, p50 -R$250, **p95 R$574**. RDT +R$215 → percentil 82,0.

## Critérios (com a decisão do orquestrador)
| critério | resultado |
|---|---|
| líquido com custo > 0 | PASSA (+R$215) |
| ≥ 3 de 5 trimestres positivos | PASSA (3/5) |
| PF ≥ 1,2 | PASSA (1,55) |
| não quebrar | PASSA (caixa mín R$734) |
| acima do p95 do controle aleatório | **FALHA** (percentil 82, p95 R$574) |

## Veredito: REFUTADA
Falhou no critério que mais pesa, o controle aleatório (+R$215 contra p95 de R$574). Os outros quatro passam, mas a amostra é de 12 operações, e sem as 2 melhores o líquido é -R$241. Não vai ao holdout (N3). No DEV passava o controle (percentil 97,5), o que sugere que parte do resultado do DEV vinha de seleção da célula sobre 622 pregões.
