# RESUMO MM - media movel sobre win_deslocamento_matinal (WIN@, capital reposto, fila P2; P0 em tabela_*.csv)
Pre-registro: PRE_REGISTRO_MM.md. Baseline reproduz exato (IS 143 tr, +4.144,50). Codigo: run_mm.py, analisa_mm.py; logs is_stdout.log/oos_stdout.log.

## IS 2021-10..2024-12 (P2)
| celula | trades | liquido | R$/op | IC95% | win% | BE | 22/23/24 | passa |
|---|---|---|---|---|---|---|---|---|
| BASE | 143 | +4.144,5 | +29,0 | [-1,9;+60,4] | 53,8 | 44,5 | +750/+1958/+1293 | - |
| A_e10 | 129 | +4.258,5 | +33,0 | [-0,6;+66,5] | 54,3 | 43,8 | +1023/+2003/+852 | sim |
| A_e20 | 142 | +4.138,0 | +29,1 | [-2,4;+60,4] | 53,5 | 44,2 | idem base | sim (+0,1) |
| A_e50 | 142 | +4.285,0 | +30,2 | [-1,0;+61,7] | 54,2 | 44,5 | +891/+1958/+1293 | sim |
| A_s10d | 106 | +2.890,0 | +27,3 | [-7,7;+62,4] | 51,9 | 42,9 | +310/+1679/+880 | nao |
| A_s20d | 104 | +2.404,0 | +23,1 | [-13,0;+59,1] | 49,0 | 41,6 | +439/+1450/+512 | nao |
| S30 | 142 | +4.285,0 | +30,2 | [-1,0;+61,7] | 54,2 | 44,5 | +891/+1958/+1293 | sim |
| S15 | 140 | +4.350,0 | +31,1 | [-1,2;+64,0] | 54,3 | 44,4 | +891/+1958/+1358 | sim |
| E15 | 50 | -771,0 | -15,4 | [-59,5;+29,4] | 46,0 | 51,7 | -562/+284/-272 | nao |
| E25 | 107 | +994,5 | +9,3 | [-24,2;+44,2] | 49,5 | 46,4 | +411/+425/+16 | nao |
| P30 | 52 | -5,0 | -0,1 | [-42,7;+46,6] | 40,4 | 40,4 | -115/+426/+95 | nao |
| P60 | 64 | +3,0 | 0,0 | [-37,9;+39,9] | 42,2 | 42,2 | +109/+654/-428 | nao |

Escolhidas (2 de maior R$/op entre as que passam): A_e10, S15.

## OOS 2025-01..2026-09 (rodada UMA vez, P2)
| celula | trades | liquido | R$/op | IC95% | win% | BE |
|---|---|---|---|---|---|---|
| BASE | 113 | +4.897,5 | +43,3 | [-7,2;+92,9] | 52,2 | 42,4 |
| A_e10 | 99 | +4.647,5 | +46,9 | [-7,7;+103,5] | 53,5 | 43,0 |
| S15 | 104 | +4.558,0 | +43,8 | [-10,7;+99,1] | 53,8 | 44,1 |

## Veredito
MM nao ajuda de forma mensuravel. Filtros de alinhamento/inclinacao so' cortam 1-14 trades e mexem +1 a +4 R$/op, dentro do ruido (todos os ICs cruzam 0 e contem a baseline); na OOS o liquido cai nos dois (-250/-340) e o R$/op quase nao muda. Esticado (E15/E25), recuo na EMA (P30/P60) e SMA diaria destroem o edge (o recuo perde os dias que continuam sem voltar: 52-64 fills de 143).
