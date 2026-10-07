# DADOS DO HOLDOUT (2025-12-19 a 2026-02-19)

## 0. Ticks

- MT5 (`copy_ticks_range`, dia inteiro 00:00-24:00) devolveu 0 ticks para WIN$N, WIN$, WIN@, WIN@D, WIN@N e WIN$D em 2025-12-22, 2026-01-15 e 2026-02-19, e 2.074.311 ticks em 2026-02-20 (primeiro dia com tick). Os contratos WINZ25 e WING26 nao existem no terminal (`Terminal: Not found`). Nao ha tick local anterior a 2026-02-20 (`data/raw_ticks`, `data/cache_win_ticks`, `data/comparativo_win_2026/ticks`).
- Portanto: execucao em barras M1 com a regra conservadora da barra do fill (CRITERIOS.md). Leilao e call sao **PROXY** (`proxy=True` em todos os dias): preco do leilao = open da barra M1 do leilao (nao corrigido); preco do call = close da ultima barra continua; volume do call estimado.

## 1. Gap: WIN$N (proxy) x serie ajustada WIN@D (independente)

- Dias comparaveis: 38. |gap$N − gapD|: mediana 178 pts, maxima 1150 pts; iguais em 6/38.
- Dias em que difere:
| data | gap | gap_D | dif |
|---|---|---|---|
| 2025-12-19 | -130.0 | -115.0 | -15.0 |
| 2025-12-22 | 585.0 | 455.0 | 130.0 |
| 2025-12-23 | 310.0 | 200.0 | 110.0 |
| 2025-12-26 | -665.0 | -465.0 | -200.0 |
| 2025-12-29 | -330.0 | -200.0 | -130.0 |
| 2025-12-30 | 150.0 | 440.0 | -290.0 |
| 2026-01-02 | 725.0 | 200.0 | 525.0 |
| 2026-01-08 | -210.0 | -200.0 | -10.0 |
| 2026-01-09 | 570.0 | 225.0 | 345.0 |
| 2026-01-12 | 300.0 | 280.0 | 20.0 |
| 2026-01-13 | 140.0 | 130.0 | 10.0 |
| 2026-01-19 | -615.0 | -740.0 | 125.0 |
| 2026-01-20 | -685.0 | -725.0 | 40.0 |
| 2026-01-21 | 225.0 | 100.0 | 125.0 |
| 2026-01-22 | -215.0 | 175.0 | -390.0 |
| 2026-01-23 | 900.0 | 1150.0 | -250.0 |
| 2026-01-26 | 1360.0 | 480.0 | 880.0 |
| 2026-01-27 | 2205.0 | 1610.0 | 595.0 |
| 2026-01-28 | 755.0 | 1290.0 | -535.0 |
| 2026-01-29 | 1615.0 | 1400.0 | 215.0 |
| 2026-01-30 | -885.0 | -1040.0 | 155.0 |
| 2026-02-02 | -1060.0 | -1875.0 | 815.0 |
| 2026-02-03 | 1105.0 | 845.0 | 260.0 |
| 2026-02-04 | 760.0 | 715.0 | 45.0 |
| 2026-02-05 | -325.0 | -15.0 | -310.0 |
| 2026-02-06 | 1090.0 | 880.0 | 210.0 |
| 2026-02-09 | 840.0 | 400.0 | 440.0 |
| 2026-02-10 | -350.0 | -830.0 | 480.0 |
| 2026-02-11 | 1835.0 | 685.0 | 1150.0 |
| 2026-02-12 | 1240.0 | 860.0 | 380.0 |
| 2026-02-13 | -765.0 | -705.0 | -60.0 |
| 2026-02-19 | -220.0 | 290.0 | -510.0 |

## 2. Rolagens (WINZ25→WING26 em 2025-12-17; WING26→WINJ26 em 2026-02-18), detectadas pelo tamanho do gap

- |gap| mediano dos dias da janela: 578 pts; maior |gap| nao-rolagem: 2205 pts.
- Dias com degrau entre as duas series (|gap$N| − |gapD| > 1.500) ou sem gap:
| data | gap | gap_D | |gap$N|−|gapD| |
|---|---|---|---|
| 2025-12-17 | 3600.0 | 335.0 | 3265.0 |
| 2026-02-18 | nan | 50.0 | nan |

- 2025-12-17 fica fora da janela (so' aquecimento do ATR, e excluido da media por ser rolagem); 2026-02-18 (rolagem + sessao parcial 13:00) esta na janela e e' EXCLUIDO; 2026-02-19, o dia seguinte, usa o call de 02-18 (ja' no contrato novo) e entra.

## 3. Sessoes: feriados, meio-pregao e fim do continuo

- Dias da janela excluidos:
| data | n_barras | primeira | motivo_excl |
|---|---|---|---|
| 2026-02-18 | 65 | 13:00:00 | rolagem+sem_dia_anterior+pregao_parcial |

- Dias uteis sem pregao na base (feriados: 24/12 e 31/12 sem dados, 01/01, 16-17/02 carnaval): [datetime.date(2025, 12, 24), datetime.date(2025, 12, 25), datetime.date(2025, 12, 31), datetime.date(2026, 1, 1), datetime.date(2026, 2, 16), datetime.date(2026, 2, 17)]
- Pregoes elegiveis: 38; todos com 113 barras M5 (09:00 a 18:20) e 1a barra as 09:00: True.
- `fim_continuo` (data/b3_grade_horaria_win.csv) por dia: {'18:25': 39}; maior hora de barra M5 na base: 18:20:00; barras com hora >= 18:25: 0.

## 4. Sem leilao nem call nas barras

- Ultima barra M1 de cada dia: hora ['18:24'] (18:24 = ultima do continuo; o call esta fora); flag `ultima_continua` em 39 barras (1 por dia). Barras com `hl_aprox`: 26 (maxima/minima do dia aproximadas so' quando o preco removido era o extremo); `flag_leilao`: 38 barras (a barra do leilao, com volume removido; open nao corrigido).
- Consistencia intradia WIN$N x WIN@D (close M1, desvio padrao da diferenca dentro do dia; 0 = mesma serie a menos de constante): mediana 2.9 pts, maxima 10.1 pts em 39 dias.

## 5. ATR (aquecimento)

- ATR dos pregoes anteriores a D: media da amplitude (max-min das barras M5) dos <= 10 pregoes validos anteriores. Para os primeiros dias da janela le so' precos de 2025-12-04 a 2025-12-18 (rolagem de 12-17 excluida da media); nenhum dia da IS.
