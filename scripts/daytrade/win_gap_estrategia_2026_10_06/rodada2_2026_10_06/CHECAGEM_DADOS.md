# CHECAGEM DOS DADOS — rodada 2 (WIN gap, 2026-04-06 a 2026-10-05)

Tudo abaixo e' MEDIDO por `checagem.py` (reexecutavel). Fontes: `data/win_fases_pregao_6m.csv` (fases por tick), `data/b3_grade_horaria_win.csv`, `data/comparativo_win_2026/ticks/*.npz` (WIN$N), `data/win_sem_leiloes/m5_WIN$N.parquet`.

Pregoes na janela: 127 (CSV) / 127 (tabela de dias). Usados nas medicoes: **120**. Excluidos: 7.

## 1. Gap = preco do leilao de D − preco do call de D−1

- Gap usado (`dias_WIN$N.csv`) contra o recalculado no CSV de fases (`pre_preco_inicio[D] − pos_preco_fechamento[D−1]`): 125/125 dias comparaveis iguais (07-31 sem gap); maior diferenca 0.0 pts. Com `pre_preco_fechamento` (preco unico do leilao): 125/125 iguais.
- `pre_preco_inicio == pre_preco_fechamento` (leilao de preco unico) em 126/127 dias.
- O gap do 1o dia da janela (2026-04-06) usa o call de 2026-04-02 (fora da janela); e' 1 numero lido, nenhuma barra/tick anterior a 04-06 e' lido.

## 2. Fase continua: comeca depois do leilao e termina em `negociacao_fim` da grade

- Primeiro tick continuo > hora do leilao: 126/127. Ultimo tick continuo < `negociacao_fim` da grade (18:25, ou 17:55 antes de 2024-03-11 em horario de verao dos EUA — nenhum dia da janela e' dessa fase): 127/127.
- Falhas:
| dia | leilao | primeiro_tick | ultimo_tick | fim_grade | ok_ini | ok_fim |
|---|---|---|---|---|---|---|
| 2026-07-31 | nan | 12:34:07.972 | 18:24:59.999 | 18:25:00.000 | False | True |

- `fim_continuo` da grade por dia na janela: {'18:25': 127}.

## 3. Nenhum leilao nem call nas barras usadas: 1a e ultima barra M5 de cada dia contra o CSV

- Abertura da 1a barra M5 == `pregao_preco_inicio` (1o negocio continuo): 120/120
- Fechamento da ultima barra M5 == `pregao_preco_fechamento` (ultimo negocio continuo): 120/120
- Maxima do dia nas barras == `pregao_maxima`: 117/120; minima == `pregao_minima`: 118/120
- Hora da ultima barra == `fim_continuo` − 5 min (18:20): 120/120; nenhuma barra com hora >= 18:25: True
- Divergencias (dia, barras x CSV):
| dia | open1 | csv_o | close_n | csv_c | hi | csv_h | lo | csv_l | fimN | ult_esp | fonte |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-04-10 | 195920.0 | 195920.0 | 198150.0 | 198150.0 | 198150.0 | 198165.0 | 195510.0 | 195510.0 | 2026-04-10 18:20:00 | 2026-04-10 18:20:00 | ticks |
| 2026-05-11 | 187390.0 | 187390.0 | 184870.0 | 184870.0 | 187390.0 | 187400.0 | 183940.0 | 183940.0 | 2026-05-11 18:20:00 | 2026-05-11 18:20:00 | ticks |
| 2026-05-14 | 179065.0 | 179065.0 | 180670.0 | 180670.0 | 181550.0 | 181550.0 | 179065.0 | 179060.0 | 2026-05-14 18:20:00 | 2026-05-14 18:20:00 | ticks |
| 2026-06-16 | 170970.0 | 170970.0 | 169360.0 | 169360.0 | 170970.0 | 170975.0 | 169075.0 | 169075.0 | 2026-06-16 18:20:00 | 2026-06-16 18:20:00 | ticks |
| 2026-07-10 | 175905.0 | 175905.0 | 180605.0 | 180605.0 | 180670.0 | 180670.0 | 175905.0 | 175900.0 | 2026-07-10 18:20:00 | 2026-07-10 18:20:00 | ticks |

### 3b. Barras M5 usadas x OHLC reconstruido dos ticks continuos (high, low, close de TODAS as barras; open da barra 1)

- 13560 barras comparadas: high diferente em 26, low diferente em 28, close diferente em 34; open da barra 1 diferente em 5/120. Barras M5 e ticks vem de fontes distintas (M1 do MT5 x ticks); diferencas, quando existem, sao de 5 a 15 pts nos extremos. Exemplos de high (dia, barra, M5, tick): [('2026-04-09', '18:20', 196000.0, 196045), ('2026-04-10', '18:20', 198150.0, 198165), ('2026-05-04', '16:50', 188585.0, 188580), ('2026-05-04', '18:20', 188570.0, 188575), ('2026-05-08', '12:10', 187500.0, 187495), ('2026-05-11', '09:00', 187390.0, 187400), ('2026-05-11', '12:25', 184765.0, 184760), ('2026-05-28', '17:35', 175890.0, 175885)]. A execucao usa os ticks; o sinal usa open/close da barra 1.

- Sinal da barra 1 (sinal de close-open) com OHLC dos ticks x das barras M5: diferente em 0/120 dias [].

## 4. Reconciliacao dos ticks continuos com o CSV (open/close/max/min do pregao)

- Ticks continuos (filtrados por `filtra_ticks_continuo`) == CSV, nos 120 dias usados: abertura 115/120, fechamento 120/120, maxima 120/120, minima 120/120.
- Divergencias:
| dia | tick_o | csv_o | tick_c | csv_c | tick_h | csv_h | tick_l | csv_l | o_ok | c_ok | h_ok | l_ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-04-13 | 196850 | 196855.0 | 197965 | 197965.0 | 198465 | 198465.0 | 196295 | 196295.0 | False | True | True | True |
| 2026-06-29 | 177205 | 177200.0 | 175800 | 175800.0 | 177205 | 177205.0 | 174980 | 174980.0 | False | True | True | True |
| 2026-07-13 | 179665 | 179670.0 | 177140 | 177140.0 | 180245 | 180245.0 | 176990 | 176990.0 | False | True | True | True |
| 2026-09-08 | 190475 | 190480.0 | 190060 | 190060.0 | 191930 | 191930.0 | 188735 | 188735.0 | False | True | True | True |
| 2026-09-14 | 186895 | 186900.0 | 187350 | 187350.0 | 188260 | 188260.0 | 185040 | 185040.0 | False | True | True | True |

- Mesma conta nos dias EXCLUIDOS (informativo):
| dia | tick_o | csv_o | tick_c | csv_c | tick_h | csv_h | tick_l | csv_l |
|---|---|---|---|---|---|---|---|---|
| 2026-04-15 | 202880 | 202880.0 | 201780 | 201780.0 | 203495 | 203495.0 | 201210 | 201210.0 |
| 2026-05-06 | 191435 | 191435.0 | 190010 | 190010.0 | 192560 | 192560.0 | 189635 | 189635.0 |
| 2026-06-17 | 172815 | 172815.0 | 171520 | 171520.0 | 175330 | 175330.0 | 171160 | 171160.0 |
| 2026-07-31 | 177465 | 177470.0 | 178615 | 178615.0 | 179495 | 179495.0 | 176985 | 176985.0 |
| 2026-08-10 | 173020 | 173025.0 | 172265 | 172265.0 | 173700 | 173700.0 | 171670 | 171670.0 |
| 2026-08-12 | 172215 | 172215.0 | 170330 | 170330.0 | 172230 | 172230.0 | 170225 | 170225.0 |
| 2026-09-24 | 185960 | 186575.0 | 184950 | 184950.0 | 187555 | 187555.0 | 184725 | 184725.0 |

## 5. Dias excluidos e decisoes

|gap| mediano dos dias usados: 500 pts.

| dia | motivo | gap | dia_seguinte | gap_seguinte |
|---|---|---|---|---|
| 2026-04-15 | rolagem | 4415.0 | 2026-04-16 | 345.0 |
| 2026-05-06 | ticks_faltando_09:16-09:23(janela de ordem) | 2040.0 | 2026-05-07 | 300.0 |
| 2026-06-17 | rolagem | 3350.0 | 2026-06-18 | 320.0 |
| 2026-07-31 | abertura_atrasada+sem_dia_anterior+pregao_parcial | nan | 2026-08-03 | 865.0 |
| 2026-08-10 | ticks_faltando_10:00-10:08(posicao aberta) | 355.0 | 2026-08-11 | 75.0 |
| 2026-08-12 | rolagem | 3960.0 | 2026-08-13 | 235.0 |
| 2026-09-24 | ticks_so_comecam_09:14(sem 1a barra nem janela de ordem) | -105.0 | 2026-09-25 | 340.0 |

**Rolagens (04-15, 06-17, 08-12).** O WIN$N troca de contrato no vencimento (quarta mais proxima do dia 15 dos meses pares). No dia D da troca, o call de D−1 e o leilao de D sao de contratos diferentes: degrau medido de 3.350 a 4.415 pts no gap contra |gap| mediano de 500. Por isso os 3 dias sao excluidos. No dia SEGUINTE o call de D (ja' no contrato novo) e o leilao de D+1 estao no mesmo contrato: o gap desses dias esta na coluna `gap_seguinte` acima e fica na faixa normal; os dias seguintes sao MANTIDOS. Prova adicional: o pregao de D continua intra-contrato (tabela `lente4/dias_flag.csv`: 'pregao D intra-contrato ok'), e so' o gap e' contaminado.

**07-31.** Primeiro negocio as 12:34:07 (abertura atrasada real; 351 min de pregao): sem 1a barra as 09:00, o sinal 'a 1a barra M5' nao existe nesse dia. Excluido.

**10-05 (gap +17.775 pts).** E' real (dia seguinte ao 1o turno da eleicao): leilao e call batem com os ticks e com o CSV (item 4). Mantido, e e' o dia de maior |gap| da janela.

**05-06, 08-10, 09-24 (fonte `ticks+M1`).** Medido em `ticks_resumo.csv`/CSV de fases: 05-06 sem ticks de 09:16 a 09:23 (maior buraco entre ticks 368 s, dentro da janela da ordem de entrada 09:05-09:35); 08-10 sem ticks de 10:00 a 10:08 (155 s; posicao potencialmente aberta); 09-24 ticks so' comecam as 09:14 (a 1a barra e o preco do 1o negocio continuo vem do M1, a janela inteira de entrada fica cega). Decisao: **excluir os tres**. O simulador resolve stop/alvo/limite por tick; num buraco ele nao ve se o nivel foi tocado, e o M1 nao devolve a sequencia. Custo: 3 de 123 pregoes.

## 6. Hora da 1a barra M5 e do sinal

- Pregoes cuja 1a barra M5 com negocio continuo NAO e' a das 09:00: 0 de 120.
_(nenhum)_

- Leilao de abertura DENTRO da barra 09:00-09:05 (o continuo comeca depois dele, no mesmo M5): 120/120 dias; o continuo comeca em mediana 09:02:52.292, p90 09:03:19.387. A barra 1 e' portanto parcial: so' os negocios continuos depois do leilao (o loader remove volume e preco do leilao; open = 1o negocio continuo, item 3). A decisao acontece no FECHO da barra (09:05); a ordem so' vale a partir de 09:05 (testado em `tests/test_win_gap_rodada2_lookahead.py`).
- Dias com o continuo comecando depois das 09:05: 0; antes das 09:00: 0.

## 7. Look-ahead

- ATR de dias anteriores (`ctx.calcula_atr_prev`): media da amplitude dos <= 10 pregoes validos ANTERIORES a D (exige >= 3), sem D; ele so' usa pregoes DENTRO da janela (nada antes de 04-06).
- Filtro de volume do call (V3): mediana movel de ate' 60 pregoes de `call_volume` com `shift(1)` (ate' D−1), so' valores do mesmo regime (medido), minimo 20 observacoes; no 1o pregao (cujo D−1 e' pre-janela) o filtro e' desligado. Pregoes sem historico suficiente contam como 'volume nao alto'.
- Contexto do dia (`ctx.constroi`) so' carrega: gap, vol_alto, call de D−1, ATR de D−1 para tras e a 1a barra (open/high/low/close).
- Testes pytest (`tests/test_win_gap_rodada2_lookahead.py`, tmp_path, paralelo-seguro): (1) ATR de D identico se D e o futuro mudam; (2) `vol_alto` identico para D <= k se `call_volume` de k em diante muda (e o teste enxerga mudanca depois); (3) decisao/niveis so' dependem da 1a barra e do contexto; (4) a ordem nao enche com ticks anteriores ao fecho da 1a barra; (5) stop/alvo ignoram ticks anteriores ao fill e nao mudam se so' o futuro muda.
