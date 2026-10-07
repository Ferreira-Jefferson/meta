# Placar forward -- win_deslocamento_matinal (WIN@D)

Janela: 2026-10-01 a 2026-10-06 (4 pregões completos). Regras em `CONGELADO_FORWARD.md`. Placar mensal só informativo; decisão formal com BASE ≥ 40 operações.

## Total

|variante|trades|líquido R$|R$/op|acerto|stops|ganho médio|perda média|MaxDD R$|fator recup.|
|---|---|---|---|---|---|---|---|---|---|
|BASE|2|-285,0|-142,5|50,0%|1|11,5|-296,5|296,5|-0,96|
|E100|1|-296,5|-296,5|0,0%|1|0,0|-296,5|296,5|-1,00|
|P_10_100|0|0,0|0,0|0,0%|0|0,0|0,0|0,0|—|
|BASE_R10_cap1000|2|-264,0|-132,0|0,0%|2|0,0|-132,0|264,0|-1,00|
|R10_volM30_cap1000|2|-264,0|-132,0|0,0%|2|0,0|-132,0|264,0|-1,00|

## Por mês


**2026-10**

|variante|trades|líquido R$|R$/op|acerto|stops|ganho médio|perda média|MaxDD R$|fator recup.|
|---|---|---|---|---|---|---|---|---|---|
|BASE|2|-285,0|-142,5|50,0%|1|11,5|-296,5|296,5|-0,96|
|E100|1|-296,5|-296,5|0,0%|1|0,0|-296,5|296,5|-1,00|
|P_10_100|0|0,0|0,0|0,0%|0|0,0|0,0|0,0|—|
|BASE_R10_cap1000|2|-264,0|-132,0|0,0%|2|0,0|-132,0|264,0|-1,00|
|R10_volM30_cap1000|2|-264,0|-132,0|0,0%|2|0,0|-132,0|264,0|-1,00|

## Operações por dia

|data|variante|lado|entrada|saída|motivo|R$|
|---|---|---|---|---|---|---|
|2026-10-02|BASE|long|13:33 @ 189115|13:54 @ 187635|STOP|-296,5|
|2026-10-02|BASE_R10_cap1000|long|13:33 @ 189115|13:35 @ 188610|STOP|-101,5|
|2026-10-02|E100|long|13:33 @ 189115|13:54 @ 187635|STOP|-296,5|
|2026-10-02|R10_volM30_cap1000|long|13:33 @ 189115|13:35 @ 188610|STOP|-101,5|
|2026-10-05|BASE|short|13:34 @ 208115|21:20 @ 208055|FORCED_FLATTEN|11,5|
|2026-10-05|BASE_R10_cap1000|short|13:34 @ 208115|13:35 @ 208925|STOP|-162,5|
|2026-10-05|R10_volM30_cap1000|short|13:34 @ 208115|13:35 @ 208925|STOP|-162,5|

*Horários em UTC ingênuo (BRT + 3h), como no motor.*

## Log de execução

- rodou em 2026-10-06 19:19:18; último pregão coberto: 2026-10-06; 4 pregões; M1 em `m1_win_forward.csv`
- ATENCAO conferencia vs CSV de pesquisa: 12313 barras sobrepostas, 83 campos diferentes
