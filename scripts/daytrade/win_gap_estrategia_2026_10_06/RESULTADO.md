# WIN — gap e 1ª barra M5: estratégia e medição (2026-10-06)

Estratégia: `win_gap.py::WinGapReversao` (lab; não registrada em `registry.py`). Dados: WIN$N M5 sem leilões (`data/win_sem_leiloes`), preço cru. Motor de produção intocado.
Reprodução: `dados.py` (base, gap, rolagem) → `sweep_is.py` → `resumo_is.py` (escolha) → `valida.py` → `gera_resultado.py`. Saídas em `out/`.

## 1. Como foi medido

- **Desenho de execução:** entrada `EnterLimit` com `ttl_bars=6` (6 barras M5 = 30 min, sem conversão tick→barra); alvo, quando existe, em ordem-limite real fatiada sem prazo (`exit_split_unit`, `exit_ttl_bars=10**9`); `anchor_exits_at_fill=True`; stop a mercado. Sem alvo, segura até o fim do CONTÍNUO. Entrada a mercado: nenhuma.
- **Fim do dia:** `session_end_time=18:20` passado no script (base em BRT). A última barra de cada dia é a última do contínuo (o loader descarta o call). Dias de pregão que acabam 17:55 caem no fallback "última barra".
- **Capital:** R$250 (margem R$100 × 2 × 1,25; 1 contrato; 1 ponto = R$0,20). Dois modos, porque com R$250 a conta morre no meio da janela e a janela passa a medir caixa:
  - **A, conta contínua:** R$250 no início da janela, caixa arrastado. Mostra a censura (ordens recusadas por capital, pregões sem trade, caixa mínimo marcado a mercado).
  - **B, R$250 por pregão:** cada pregão é uma run nova com R$250 (capital mínimo real em toda operação, sem arrasto). Mede o resultado por operação sem a morte de caixa. Capital NOCIONAL na tabela (retorno, MaxDD %, capital final em branco). Como os pregões são independentes, o nulo de direção aleatória é exato: cada dia de gatilho roda forçando +1 e forçando −1; o nulo sorteia entre os dois (10.000 sorteios; p = fração de sorteios com líquido ≥ o observado).
- **Premissa de preenchimento (coluna `fill`):** `toque` = entrada e alvo enchem quando a barra toca o nível, fila 0/0 (`limit_fill_capped_by_volume=True`). **O WIN não tem fila calibrada em `fidelidade.py`; a premissa é otimista e não foi medida.** `atrav+1t` = só enche se a barra atravessa o nível em ≥ 1 tick (5 pts). A coluna `p nulo` é do modo B. A etiqueta `desliz.alvo 1,0t` vem da config; o alvo fatiado não paga esse deslize (`machine._close_position`), stop e flatten pagam 1 tick.
- **Base `BE emp%`:** `perda média / (ganho médio + perda média)` sobre o P&L líquido por operação. `win% > BE emp%` e `líquido > 0` são a mesma afirmação.
- **Exclusões:** dias de rolagem do WIN$N (quarta mais próxima do dia 15 dos meses pares; gap bruto mediano 2.158 a 3.600 pts nesses dias contra 315 a 448 nos outros), 2026-07-31 (abertura às 12:34), pregões parciais (começam depois de 09:10 ou < 80 barras M5) e dias sem pregão anterior em até 5 dias.
- **Gap:** `leilao_preco[D] − call_preco[D−1]`. Contexto causal por dia: o volume do call de D−1 é "alto" se acima da mediana dos ≤ 60 pregões anteriores do mesmo regime (proxy × medido), com ≥ 20 observações.

## 2. Variantes e grade (IS)

- **V1** fade do gap: direção contra o gap, decidida no fecho da 1ª barra M5; limite no close da barra ± `recuo` na direção do gap.
- **V2** 1ª barra M5 fecha contra o gap (`close − open` de sinal oposto ao gap): entra na direção da barra, limite em `close − sinal × recuo` (recuo = pullback). Sem fechar contra o gap: sem trade.
- **V3** = V2 + volume do call D−1 alto: `skip` ou alvo menor (350 pts).
- Eixo opcional |gap| ≥ 400 pts (V2).
- 28 células: recuo {0, 150} × stop {350, 700} × alvo {nenhum, 700} para V1 e V2 (16); V3: recuo × stop × {skip, alvo 350}, alvo base 700 (8); V2 com |gap| ≥ 400 (4). Eixos conferidos (seção 4).

## 3. Critério de escolha (declarado antes de ver os números)

1. Eliminatório: conta contínua de R$250 sem ordem recusada por capital e com caixa mínimo ≥ R$100 (margem crua).
2. Se ninguém sobrevive ao 1, segue só com o modo B, dizendo isso na primeira linha.
3. Entre os elegíveis: n ≥ 30, líquido > 0, win% > BE emp; ordena por lucro/DD (modo B, `toque`). A primeira é congelada.

## 4. IS (2026-04-06 a 2026-10-05) — NÃO é evidência: os indícios nasceram aqui

123 pregões elegíveis (4 excluídos: 3 rolagens + 07-31).

### Modo A, conta contínua R$250, fill=toque (28 células)

```
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes       modo       fill     sinais  sem fill% atraso min    BE emp%     p nulo  caixa min  sem trade
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
V1 r0 s350 a-                    -82,8%      -207,00   -82,8%      207,00    -1,00   0,0%      2      -1,68     0,0          43,00     123      conta      toque        122        0,0        0,0        nan          —      43,00    121/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 120 ordens
V1 r0 s350 a700                  -82,8%      -207,00   -82,8%      207,00    -1,00   0,0%      2      -1,68     0,0          43,00     123      conta      toque        122        0,0        0,0        nan          —      43,00    121/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 120 ordens
V1 r0 s700 a-                    -75,4%      -188,50   -85,6%      364,50    -0,52  33,3%      3      -1,53     0,0          61,50     123      conta      toque        122        0,0        0,0       60,0          —      61,50    120/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 119 ordens
V1 r0 s700 a700                  -71,2%      -178,00   -92,8%      932,50    -0,19  45,8%     24      -1,45     0,2          72,00     123      conta      toque        122        0,0        0,0       48,4          —      72,00     99/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 98 ordens
V1 r150 s350 a-                  -70,8%      -177,00   -84,0%      383,00    -0,46   0,0%      2      -1,44     0,0          73,00     123      conta      toque        122       18,9        0,0        nan          —      73,00    121/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 97 ordens
V1 r150 s350 a700                -88,0%      -220,00   -93,5%      432,50    -0,51  25,0%     12      -1,79     0,1          30,00     123      conta      toque        122       18,9        0,0       33,0          —      30,00    111/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 87 ordens
V1 r150 s700 a-                1.137,4%     2.843,50   -58,4%    1.441,50     1,97  33,3%     99      23,12     0,8       3.093,50     123      conta      toque        122       18,9        0,0       27,6          —     218,00     24/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r150 s700 a700                -88,0%      -220,00   -96,0%      723,50    -0,30  41,7%     12      -1,79     0,1          30,00     123      conta      toque        122       18,9        0,0       47,9          —      30,00    111/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 87 ordens
V2 r0 s350 a-                  1.221,4%     3.053,50   -67,0%    1.111,00     2,75  23,8%     63      24,83     0,5       3.303,50     123      conta      toque         63        0,0        0,0       14,9          —      82,50     60/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s350 a700                  -77,8%      -194,50   -79,5%      215,00    -0,90  20,0%      5      -1,58     0,0          55,50     123      conta      toque         63        0,0        0,0       36,0          —      55,50    118/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 58 ordens
V2 r0 s700 a-                  2.350,6%     5.876,50   -69,4%    1.222,50     4,81  42,9%     63      47,78     0,5       6.126,50     123      conta      toque         63        0,0        0,0       25,6          —      76,50     60/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s700 a700                  866,6%     2.166,50   -70,1%      913,50     2,37  60,3%     63      17,61     0,5       2.416,50     123      conta      toque         63        0,0        0,0       49,0          —      76,50     60/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                1.513,6%     3.784,00   -43,0%      942,50     4,01  31,2%     48      30,76     0,4       4.034,00     123      conta      toque         63       23,8        0,0       15,7          —     142,50     75/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a700                -72,2%      -180,50   -75,5%      214,50    -0,84  20,0%      5      -1,47     0,0          69,50     123      conta      toque         63       23,8        0,0       36,4          —      69,50    118/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 43 ordens
V2 r150 s700 a-                1.522,0%     3.805,00   -57,4%    1.222,50     3,11  39,6%     48      30,93     0,4       4.055,00     123      conta      toque         63       23,8        0,0       25,0          —     106,50     75/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s700 a700               -105,6%      -264,00  -103,3%      438,50    -0,60  33,3%      6     -22,00     0,5         -14,00      12      conta      toque          7       14,3        0,0       48,4          —     -14,00       6/12  ZERADO desliz.alvo 1,0t fila NAO CALIBRADA
V3 r0 s350 a700 skip             -77,8%      -194,50   -79,5%      215,00    -0,90  20,0%      5      -1,58     0,0          55,50     123      conta      toque         45        0,0        0,0       36,0          —      55,50    118/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 40 ordens
V3 r0 s350 a700 a350             -77,8%      -194,50   -79,5%      215,00    -0,90  20,0%      5      -1,58     0,0          55,50     123      conta      toque         63        0,0        0,0       36,0          —      55,50    118/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 58 ordens
V3 r0 s700 a700 skip             693,4%     1.733,50   -70,1%      686,00     2,53  62,2%     45      14,09     0,4       1.983,50     123      conta      toque         45        0,0        0,0       49,6          —      76,50     78/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r0 s700 a700 a350             709,4%     1.773,50   -70,1%      701,50     2,53  61,9%     63      14,42     0,5       2.023,50     123      conta      toque         63        0,0        0,0       52,0          —      76,50     60/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r150 s350 a700 skip           -72,2%      -180,50   -75,5%      214,50    -0,84  20,0%      5      -1,47     0,0          69,50     123      conta      toque         45       31,1        0,0       36,4          —      69,50    118/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 26 ordens
V3 r150 s350 a700 a350           -72,2%      -180,50   -75,5%      214,50    -0,84  20,0%      5      -1,47     0,0          69,50     123      conta      toque         63       23,8        0,0       36,4          —      69,50    118/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 43 ordens
V3 r150 s700 a700 skip          -105,6%      -264,00  -103,3%      438,50    -0,60  33,3%      6     -22,00     0,5         -14,00      12      conta      toque          7       14,3        0,0       48,4          —     -14,00       6/12  ZERADO desliz.alvo 1,0t fila NAO CALIBRADA
V3 r150 s700 a700 a350          -105,6%      -264,00  -103,3%      438,50    -0,60  33,3%      6     -22,00     0,5         -14,00      12      conta      toque          7       14,3        0,0       48,4          —     -14,00       6/12  ZERADO desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s350 a700 g400             -82,8%      -207,00   -82,8%      207,00    -1,00   0,0%      2      -1,68     0,0          43,00     123      conta      toque         33        0,0        0,0        nan          —      43,00    121/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 31 ordens
V2 r0 s700 a700 g400             -56,6%      -141,50  -103,0%      257,50    -0,55   0,0%      1     -15,72     0,1         108,50       9      conta      toque          2       50,0        0,0        nan          —      -7,50        8/9  ZERADO desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a700 g400           -70,8%      -177,00   -70,8%      177,00    -1,00   0,0%      2      -1,44     0,0          73,00     123      conta      toque         33       24,2        0,0        nan          —      73,00    121/123  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 23 ordens
V2 r150 s700 a700 g400          -113,2%      -283,00  -113,2%      283,00    -1,00   0,0%      2     -31,44     0,2         -33,00       9      conta      toque          2        0,0        0,0        nan          —     -33,00        7/9  ZERADO desliz.alvo 1,0t fila NAO CALIBRADA
```

### Modo B, R$250 por pregão, fill=toque (28 células)

```
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes       modo       fill     sinais  sem fill% atraso min    BE emp%     p nulo  caixa min  sem trade
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
V1 r0 s350 a-                         —     2.200,50        —    1.204,00     1,83  19,0%    121      17,89     1,0              —     123     pregao      toque        122        0,8        0,0       15,4      0,163          —      2/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r0 s350 a700                       —       629,50        —    1.096,00     0,57  36,4%    121       5,12     1,0              —     123     pregao      toque        122        0,8        0,0       34,2      0,336          —      2/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r0 s700 a-                         —     3.589,50        —    1.687,00     2,13  33,1%    121      29,18     1,0              —     123     pregao      toque        122        0,8        0,0       27,2      0,035          —      2/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r0 s700 a700                       —       -72,50        —    1.977,00    -0,04  47,9%    121      -0,59     1,0              —     123     pregao      toque        122        0,8        0,0       48,1      0,487          —      2/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r150 s350 a-                       —     2.844,50        —      907,00     3,14  22,2%     99      23,13     0,8              —     123     pregao      toque        122       18,9        0,0       16,2      0,158          —     24/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r150 s350 a700                     —       631,50        —    1.213,00     0,52  35,4%     99       5,13     0,8              —     123     pregao      toque        122       18,9        0,0       32,7      0,380          —     24/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r150 s700 a-                       —     2.843,50        —    1.270,00     2,24  33,3%     99      23,12     0,8              —     123     pregao      toque        122       18,9        0,0       27,6      0,148          —     24/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r150 s700 a700                     —        33,50        —    1.423,00     0,02  47,5%     99       0,27     0,8              —     123     pregao      toque        122       18,9        0,0       47,4      0,646          —     24/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s350 a-                         —     3.326,00        —    1.026,50     3,24  24,2%     62      27,04     0,5              —     123     pregao      toque         63        1,6        0,0       14,3      0,007          —     61/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s350 a700                       —     1.717,00        —      572,00     3,00  45,2%     62      13,96     0,5              —     123     pregao      toque         63        1,6        0,0       33,5      0,024          —     61/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s700 a-                         —     6.149,00        —      892,50     6,89  43,5%     62      49,99     0,5              —     123     pregao      toque         63        1,6        0,0       25,0      0,001          —     61/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s700 a700                       —     2.439,00        —      709,50     3,44  61,3%     62      19,83     0,5              —     123     pregao      toque         63        1,6        0,0       48,1      0,010          —     61/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                       —     3.784,00        —      501,50     7,55  31,2%     48      30,76     0,4              —     123     pregao      toque         63       23,8        0,0       15,7      0,013          —     75/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a700                     —     1.389,00        —      512,00     2,71  45,8%     48      11,29     0,4              —     123     pregao      toque         63       23,8        0,0       34,0      0,015          —     75/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s700 a-                       —     3.805,00        —      675,50     5,63  39,6%     48      30,93     0,4              —     123     pregao      toque         63       23,8        0,0       25,0      0,041          —     75/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s700 a700                     —     1.499,00        —      646,50     2,32  58,3%     48      12,19     0,4              —     123     pregao      toque         63       23,8        0,0       48,1      0,054          —     75/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r0 s350 a700 skip                  —     1.635,00        —      286,00     5,72  50,0%     44      13,29     0,4              —     123     pregao      toque         45        2,2        0,0       34,4      0,020          —     79/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r0 s350 a700 a350                  —     1.529,00        —      449,00     3,41  46,8%     62      12,43     0,5              —     123     pregao      toque         63        1,6        0,0       35,7      0,036          —     61/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r0 s700 a700 skip                  —     2.006,00        —      566,00     3,54  63,6%     44      16,31     0,4              —     123     pregao      toque         45        2,2        0,0       48,3      0,015          —     79/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r0 s700 a700 a350                  —     2.046,00        —      543,50     3,76  62,9%     62      16,63     0,5              —     123     pregao      toque         63        1,6        0,0       51,1      0,013          —     61/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r150 s350 a700 skip                —     1.160,50        —      296,50     3,91  51,6%     31       9,43     0,3              —     123     pregao      toque         45       31,1        0,0       36,7      0,010          —     92/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r150 s350 a700 a350                —     1.144,00        —      512,00     2,23  45,8%     48       9,30     0,4              —     123     pregao      toque         63       23,8        0,0       35,6      0,036          —     75/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r150 s700 a700 skip                —       894,50        —      424,50     2,11  58,1%     31       7,27     0,3              —     123     pregao      toque         45       31,1        0,0       48,7      0,067          —     92/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r150 s700 a700 a350                —     1.403,00        —      435,50     3,22  62,5%     48      11,41     0,4              —     123     pregao      toque         63       23,8        0,0       52,2      0,078          —     75/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s350 a700 g400                  —       540,00        —      500,50     1,08  40,6%     32       4,39     0,3              —     123     pregao      toque         33        3,0        0,0       33,4      0,137          —     91/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s700 a700 g400                  —     1.047,00        —      568,00     1,84  59,4%     32       8,51     0,3              —     123     pregao      toque         33        3,0        0,0       48,2      0,048          —     91/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a700 g400                —       480,50        —      501,50     0,96  44,0%     25       3,91     0,2              —     123     pregao      toque         33       24,2        0,0       36,1      0,051          —     98/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s700 a700 g400                —       775,50        —      566,00     1,37  60,0%     25       6,30     0,2              —     123     pregao      toque         33       24,2        0,0       49,8      0,186          —     98/123  desliz.alvo 1,0t fila NAO CALIBRADA
```

### Modo B, fill=atrav+1t

```
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes       modo       fill     sinais  sem fill% atraso min    BE emp%     p nulo  caixa min  sem trade
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
V1 r0 s350 a-                         —     1.800,00        —    1.345,50     1,34  18,3%    120      14,63     1,0              —     123     pregao   atrav+1t        122        1,6        0,0       15,4      0,191          —      3/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r0 s350 a700                       —       240,00        —    1.096,00     0,22  35,0%    120       1,95     1,0              —     123     pregao   atrav+1t        122        1,6        0,0       34,1      0,362          —      3/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r0 s700 a-                         —     3.189,00        —    1.687,00     1,89  32,5%    120      25,93     1,0              —     123     pregao   atrav+1t        122        1,6        0,0       27,2      0,040          —      3/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r0 s700 a700                       —      -532,00        —    2.118,50    -0,25  46,7%    120      -4,33     1,0              —     123     pregao   atrav+1t        122        1,6        0,0       48,2      0,515          —      3/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r150 s350 a-                       —     2.655,00        —      907,00     2,93  21,4%     98      21,59     0,8              —     123     pregao   atrav+1t        122       19,7        0,0       15,8      0,171          —     25/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r150 s350 a700                     —       492,00        —    1.213,00     0,41  34,7%     98       4,00     0,8              —     123     pregao   atrav+1t        122       19,7        0,0       32,6      0,404          —     25/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r150 s700 a-                       —     2.654,00        —    1.270,00     2,09  32,7%     98      21,58     0,8              —     123     pregao   atrav+1t        122       19,7        0,0       27,3      0,159          —     25/123  desliz.alvo 1,0t fila NAO CALIBRADA
V1 r150 s700 a700                     —      -106,00        —    1.562,50    -0,07  46,9%     98      -0,86     0,8              —     123     pregao   atrav+1t        122       19,7        0,0       47,3      0,659          —     25/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s350 a-                         —     2.925,50        —    1.026,50     2,85  23,0%     61      23,78     0,5              —     123     pregao   atrav+1t         63        3,2        0,0       14,2      0,010          —     62/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s350 a700                       —     1.538,50        —      572,00     2,69  44,3%     61      12,51     0,5              —     123     pregao   atrav+1t         63        3,2        0,0       33,6      0,029          —     62/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s700 a-                         —     5.748,50        —      892,50     6,44  42,6%     61      46,74     0,5              —     123     pregao   atrav+1t         63        3,2        0,0       25,0      0,001          —     62/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s700 a700                       —     2.260,50        —      709,50     3,19  60,7%     61      18,38     0,5              —     123     pregao   atrav+1t         63        3,2        0,0       48,2      0,011          —     62/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                       —     3.594,50        —      501,50     7,17  29,8%     47      29,22     0,4              —     123     pregao   atrav+1t         63       25,4        0,0       15,2      0,016          —     76/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a700                     —     1.249,50        —      512,00     2,44  44,7%     47      10,16     0,4              —     123     pregao   atrav+1t         63       25,4        0,0       33,9      0,019          —     76/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s700 a-                       —     3.615,50        —      675,50     5,35  38,3%     47      29,39     0,4              —     123     pregao   atrav+1t         63       25,4        0,0       24,5      0,046          —     76/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s700 a700                     —     1.359,50        —      646,50     2,10  57,4%     47      11,05     0,4              —     123     pregao   atrav+1t         63       25,4        0,0       48,0      0,059          —     76/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r0 s350 a700 skip                  —     1.456,50        —      286,00     5,09  48,8%     43      11,84     0,3              —     123     pregao   atrav+1t         45        4,4        0,0       34,5      0,025          —     80/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r0 s350 a700 a350                  —     1.350,50        —      449,00     3,01  45,9%     61      10,98     0,5              —     123     pregao   atrav+1t         63        3,2        0,0       35,9      0,042          —     62/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r0 s700 a700 skip                  —     1.827,50        —      566,00     3,23  62,8%     43      14,86     0,3              —     123     pregao   atrav+1t         45        4,4        0,0       48,5      0,017          —     80/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r0 s700 a700 a350                  —     1.867,50        —      543,50     3,44  62,3%     61      15,18     0,5              —     123     pregao   atrav+1t         63        3,2        0,0       51,3      0,016          —     62/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r150 s350 a700 skip                —     1.021,00        —      296,50     3,44  50,0%     30       8,30     0,2              —     123     pregao   atrav+1t         45       33,3        0,0       36,5      0,013          —     93/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r150 s350 a700 a350                —     1.004,50        —      512,00     1,96  44,7%     47       8,17     0,4              —     123     pregao   atrav+1t         63       25,4        0,0       35,6      0,045          —     76/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r150 s700 a700 skip                —       755,00        —      428,50     1,76  56,7%     30       6,14     0,2              —     123     pregao   atrav+1t         45       33,3        0,0       48,5      0,080          —     93/123  desliz.alvo 1,0t fila NAO CALIBRADA
V3 r150 s700 a700 a350                —     1.263,50        —      435,50     2,90  61,7%     47      10,27     0,4              —     123     pregao   atrav+1t         63       25,4        0,0       52,2      0,090          —     76/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s350 a700 g400                  —       361,50        —      500,50     0,72  38,7%     31       2,94     0,3              —     123     pregao   atrav+1t         33        6,1        0,0       33,7      0,169          —     92/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r0 s700 a700 g400                  —       868,50        —      568,00     1,53  58,1%     31       7,06     0,3              —     123     pregao   atrav+1t         33        6,1        0,0       48,5      0,057          —     92/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a700 g400                —       341,00        —      501,50     0,68  41,7%     24       2,77     0,2              —     123     pregao   atrav+1t         33       27,3        0,0       35,9      0,065          —     99/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s700 a700 g400                —       636,00        —      566,00     1,12  58,3%     24       5,17     0,2              —     123     pregao   atrav+1t         33       27,3        0,0       49,7      0,197          —     99/123  desliz.alvo 1,0t fila NAO CALIBRADA
```

### Sobrevivência de caixa e eixos

```
Criterio 1 (conta continua R$250 nao censurada): 3/28 celulas sobrevivem
  V1 r0 s350 a-              trades=  2 recusadas=120 caixa_min=  43.00 sem_trade=121/123
  V1 r0 s350 a700            trades=  2 recusadas=120 caixa_min=  43.00 sem_trade=121/123
  V1 r0 s700 a-              trades=  3 recusadas=119 caixa_min=  61.50 sem_trade=120/123
  V1 r0 s700 a700            trades= 24 recusadas= 98 caixa_min=  72.00 sem_trade=99/123
  V1 r150 s350 a-            trades=  2 recusadas= 97 caixa_min=  73.00 sem_trade=121/123
  V1 r150 s350 a700          trades= 12 recusadas= 87 caixa_min=  30.00 sem_trade=111/123
  V1 r150 s700 a-            trades= 99 recusadas=  0 caixa_min= 218.00 sem_trade=24/123
  V1 r150 s700 a700          trades= 12 recusadas= 87 caixa_min=  30.00 sem_trade=111/123
  V2 r0 s350 a-              trades= 63 recusadas=  0 caixa_min=  82.50 sem_trade=60/123
  V2 r0 s350 a700            trades=  5 recusadas= 58 caixa_min=  55.50 sem_trade=118/123
  V2 r0 s700 a-              trades= 63 recusadas=  0 caixa_min=  76.50 sem_trade=60/123
  V2 r0 s700 a700            trades= 63 recusadas=  0 caixa_min=  76.50 sem_trade=60/123
  V2 r150 s350 a-            trades= 48 recusadas=  0 caixa_min= 142.50 sem_trade=75/123
  V2 r150 s350 a700          trades=  5 recusadas= 43 caixa_min=  69.50 sem_trade=118/123
  V2 r150 s700 a-            trades= 48 recusadas=  0 caixa_min= 106.50 sem_trade=75/123
  V2 r150 s700 a700          trades=  6 recusadas=  0 caixa_min= -14.00 sem_trade=6/12
  V3 r0 s350 a700 skip       trades=  5 recusadas= 40 caixa_min=  55.50 sem_trade=118/123
  V3 r0 s350 a700 a350       trades=  5 recusadas= 58 caixa_min=  55.50 sem_trade=118/123
  V3 r0 s700 a700 skip       trades= 45 recusadas=  0 caixa_min=  76.50 sem_trade=78/123
  V3 r0 s700 a700 a350       trades= 63 recusadas=  0 caixa_min=  76.50 sem_trade=60/123
  V3 r150 s350 a700 skip     trades=  5 recusadas= 26 caixa_min=  69.50 sem_trade=118/123
  V3 r150 s350 a700 a350     trades=  5 recusadas= 43 caixa_min=  69.50 sem_trade=118/123
  V3 r150 s700 a700 skip     trades=  6 recusadas=  0 caixa_min= -14.00 sem_trade=6/12
  V3 r150 s700 a700 a350     trades=  6 recusadas=  0 caixa_min= -14.00 sem_trade=6/12
  V2 r0 s350 a700 g400       trades=  2 recusadas= 31 caixa_min=  43.00 sem_trade=121/123
  V2 r0 s700 a700 g400       trades=  1 recusadas=  0 caixa_min=  -7.50 sem_trade=8/9
  V2 r150 s350 a700 g400     trades=  2 recusadas= 23 caixa_min=  73.00 sem_trade=121/123
  V2 r150 s700 a700 g400     trades=  2 recusadas=  0 caixa_min= -33.00 sem_trade=7/9

Elegiveis (modo B, n>=30, liquido>0, win%>BE emp), ordenadas por lucro/DD:
  V2 r150 s350 a-            lucro/DD=  7.55 liq=  3784.00 n= 48 win=31.2 BE=15.7 p_nulo=0.013
  V2 r150 s700 a-            lucro/DD=  5.63 liq=  3805.00 n= 48 win=39.6 BE=25.0 p_nulo=0.041
  V1 r150 s700 a-            lucro/DD=  2.24 liq=  2843.50 n= 99 win=33.3 BE=27.6 p_nulo=0.148

ESCOLHA CONGELADA: V2 r150 s350 a- {'variante': 'V2', 'recuo_pts': 150, 'stop_pts': 350, 'alvo_pts': None}
```

```
Eixos: celulas que diferem (liquido, n) ao trocar so' o eixo, modo B toque
  recuo_pts    grupos comparaveis=14 grupos em que o eixo mudou o resultado=14
  stop_pts     grupos comparaveis=14 grupos em que o eixo mudou o resultado=14
  alvo_pts     grupos comparaveis= 8 grupos em que o eixo mudou o resultado= 8
  vol_modo     grupos comparaveis= 4 grupos em que o eixo mudou o resultado= 4
  gap_min_pts  grupos comparaveis= 4 grupos em que o eixo mudou o resultado= 4
```

Escolha congelada: **V2, recuo 150 pts, stop 350 pts, sem alvo, ttl 6 barras (30 min), sem filtro de gap nem de volume**. Era uma das 3 células que sobreviveram ao critério 1 e a de maior lucro/DD entre elas (7,55; as outras: V2 r150 s700 sem alvo 5,63; V1 r150 s700 sem alvo 2,24). Sobreviver ao critério 1 depende do caminho (ordem das primeiras operações): em 25 das 28 células a conta de R$250 foi censurada.

## 5. Validação — rodada uma vez, célula congelada, sem reajuste

Gasta estas janelas para estas hipóteses: 2022-01 a 2025-09 (por ano) e 2026-02-20 a 2026-04-03. Preços de leilão e de call são PROXY nas duas (o open da barra do leilão não é corrigido; o volume do call é estimado). 2025-10 a 2026-02-19 ficou sem uso.
Em cada janela: A com R$250 novos; B por pregão. Por ano, A reinicia em R$250.

```

## IS 2026-04-06..10-05
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes       modo       fill     sinais  sem fill% atraso min    BE emp%     p nulo  caixa min  sem trade
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
V2 r150 s350 a-                1.513,6%     3.784,00   -43,0%      942,50     4,01  31,2%     48      30,76     0,4       4.034,00     123      conta      toque         63       23,8        0,0       15,7          —     142,50     75/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                       —     3.784,00        —      501,50     7,55  31,2%     48      30,76     0,4              —     123     pregao      toque         63       23,8        0,0       15,7      0,013          —     75/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                1.437,8%     3.594,50   -43,0%      942,50     3,81  29,8%     47      29,22     0,4       3.844,50     123      conta   atrav+1t         63       25,4        0,0       15,2          —     142,50     76/123  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                       —     3.594,50        —      501,50     7,17  29,8%     47      29,22     0,4              —     123     pregao   atrav+1t         63       25,4        0,0       15,2      0,016          —     76/123  desliz.alvo 1,0t fila NAO CALIBRADA
  B toque   : sinais=63 fills=48 sem_fill=15 (23.8%) atraso mediana/p90 (min)=0.0/5.0 win=31.2% BE emp=15.7% liquido=3784.00 nulo medio=979.2 [p5 -1095.1 ; p95 3083.0] p=0.013 saidas={'stop': 32, 'forced_flatten': 16} flatten=16 (no ultimo bar do continuo=16) saidas na barra do call=0 stop tocado na barra do fill=9 pior op=-242.50
  A toque   : trades=48 recusadas por capital=0 caixa min (MtM)=142.50 sem trade=75/123 liquido=3784.00 zerado=False saidas={'stop': 32, 'forced_flatten': 16} flatten=16 (ultimo bar=16; call=0)
  B atrav+1t: sinais=63 fills=47 sem_fill=16 (25.4%) atraso mediana/p90 (min)=0.0/5.0 win=29.8% BE emp=15.2% liquido=3594.50 nulo medio=885.6 [p5 -1170.5 ; p95 2960.5] p=0.016 saidas={'stop': 32, 'forced_flatten': 15} flatten=15 (no ultimo bar do continuo=15) saidas na barra do call=0 stop tocado na barra do fill=9 pior op=-242.50
  A atrav+1t: trades=47 recusadas por capital=0 caixa min (MtM)=142.50 sem trade=76/123 liquido=3594.50 zerado=False saidas={'stop': 32, 'forced_flatten': 15} flatten=15 (ultimo bar=15; call=0)
  INDICIO CRU: n=123 | V1 fade: media 408 pts, 61% dias +, p=0.013; gap alta (n=66) mov -564 pts, 32% altas; gap baixa (n=57) mov 263 pts, 54% altas; rho(gap,mov)=-0.20 | V2: n=63 resto na direcao da 1a barra 696 pts, 60% dias +, p=0.002 | rho(vol call D-1, amplitude D)=-0.24

## VAL2 2026-02-20..04-03
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes       modo       fill     sinais  sem fill% atraso min    BE emp%     p nulo  caixa min  sem trade
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
V2 r150 s350 a-                  -85,8%      -214,50   -89,7%      309,00    -0,69   0,0%      3      -7,15     0,1          35,50      30      conta      toque         12       25,0        0,0        nan          —      35,50      27/30  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 6 ordens
V2 r150 s350 a-                       —      -710,50        —      710,50    -1,00   0,0%      9     -23,68     0,3              —      30     pregao      toque         12       25,0        0,0        nan      0,904          —      21/30  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                  -85,8%      -214,50   -89,7%      309,00    -0,69   0,0%      3      -7,15     0,1          35,50      30      conta   atrav+1t         12       25,0        0,0        nan          —      35,50      27/30  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 6 ordens
V2 r150 s350 a-                       —      -710,50        —      710,50    -1,00   0,0%      9     -23,68     0,3              —      30     pregao   atrav+1t         12       25,0        0,0        nan      0,904          —      21/30  desliz.alvo 1,0t fila NAO CALIBRADA
  B toque   : sinais=12 fills=9 sem_fill=3 (25.0%) atraso mediana/p90 (min)=0.0/2.0 win=0.0% BE emp=nan% liquido=-710.50 nulo medio=-187.6 [p5 -794.0 ; p95 420.0] p=0.904 saidas={'stop': 9} flatten=0 (no ultimo bar do continuo=0) saidas na barra do call=0 stop tocado na barra do fill=3 pior op=-126.50
  A toque   : trades=3 recusadas por capital=6 caixa min (MtM)=35.50 sem trade=27/30 liquido=-214.50 zerado=False saidas={'stop': 3} flatten=0 (ultimo bar=0; call=0)
  B atrav+1t: sinais=12 fills=9 sem_fill=3 (25.0%) atraso mediana/p90 (min)=0.0/2.0 win=0.0% BE emp=nan% liquido=-710.50 nulo medio=-187.6 [p5 -794.0 ; p95 420.0] p=0.904 saidas={'stop': 9} flatten=0 (no ultimo bar do continuo=0) saidas na barra do call=0 stop tocado na barra do fill=3 pior op=-126.50
  A atrav+1t: trades=3 recusadas por capital=6 caixa min (MtM)=35.50 sem trade=27/30 liquido=-214.50 zerado=False saidas={'stop': 3} flatten=0 (ultimo bar=0; call=0)
  INDICIO CRU: n=30 | V1 fade: media -153 pts, 50% dias +, p=0.641; gap alta (n=13) mov 305 pts, 54% altas; gap baixa (n=17) mov -36 pts, 53% altas; rho(gap,mov)=-0.03 | V2: n=12 resto na direcao da 1a barra 294 pts, 58% dias +, p=0.269 | rho(vol call D-1, amplitude D)=0.25

## VAL1 2022
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes       modo       fill     sinais  sem fill% atraso min    BE emp%     p nulo  caixa min  sem trade
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
V2 r150 s350 a-                  -87,4%      -218,50   -92,8%      403,00    -0,54  14,3%      7      -0,90     0,0          31,50     243      conta      toque        113       40,7        0,0       25,4          —      31,50    236/243  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 60 ordens
V2 r150 s350 a-                       —     1.404,50        —    1.102,50     1,27  23,9%     67       5,78     0,3              —     243     pregao      toque        113       40,7        0,0       18,4      0,347          —    176/243  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                  -87,4%      -218,50   -92,8%      403,00    -0,54  14,3%      7      -0,90     0,0          31,50     243      conta   atrav+1t        113       42,5        0,0       25,4          —      31,50    236/243  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 58 ordens
V2 r150 s350 a-                       —     1.547,50        —    1.031,00     1,50  24,6%     65       6,37     0,3              —     243     pregao   atrav+1t        113       42,5        0,0       18,4      0,274          —    178/243  desliz.alvo 1,0t fila NAO CALIBRADA
  B toque   : sinais=113 fills=67 sem_fill=46 (40.7%) atraso mediana/p90 (min)=0.0/20.0 win=23.9% BE emp=18.4% liquido=1404.50 nulo medio=924.8 [p5 -1023.1 ; p95 2865.0] p=0.347 saidas={'stop': 50, 'forced_flatten': 17} flatten=17 (no ultimo bar do continuo=17) saidas na barra do call=0 stop tocado na barra do fill=0 pior op=-71.50
  A toque   : trades=7 recusadas por capital=60 caixa min (MtM)=31.50 sem trade=236/243 liquido=-218.50 zerado=False saidas={'stop': 6, 'forced_flatten': 1} flatten=1 (ultimo bar=1; call=0)
  B atrav+1t: sinais=113 fills=65 sem_fill=48 (42.5%) atraso mediana/p90 (min)=0.0/15.0 win=24.6% BE emp=18.4% liquido=1547.50 nulo medio=841.7 [p5 -1070.0 ; p95 2740.5] p=0.274 saidas={'stop': 48, 'forced_flatten': 17} flatten=17 (no ultimo bar do continuo=17) saidas na barra do call=0 stop tocado na barra do fill=0 pior op=-71.50
  A atrav+1t: trades=7 recusadas por capital=58 caixa min (MtM)=31.50 sem trade=236/243 liquido=-218.50 zerado=False saidas={'stop': 6, 'forced_flatten': 1} flatten=1 (ultimo bar=1; call=0)
  INDICIO CRU: n=243 | V1 fade: media 64 pts, 52% dias +, p=0.252; gap alta (n=116) mov -60 pts, 50% altas; gap baixa (n=127) mov 67 pts, 54% altas; rho(gap,mov)=-0.02 | V2: n=113 resto na direcao da 1a barra 37 pts, 52% dias +, p=0.398 | rho(vol call D-1, amplitude D)=-0.17

## VAL1 2023
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes       modo       fill     sinais  sem fill% atraso min    BE emp%     p nulo  caixa min  sem trade
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
V2 r150 s350 a-                  441,4%     1.103,50   -86,2%    1.390,50     0,79  28,0%     75       4,60     0,3       1.353,50     240      conta      toque        108       30,6        0,0       23,2          —     159,50    165/240  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                       —     1.103,50        —    1.094,00     1,01  28,0%     75       4,60     0,3              —     240     pregao      toque        108       30,6        0,0       23,2      0,620          —    165/240  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                  441,4%     1.103,50   -86,2%    1.390,50     0,79  28,0%     75       4,60     0,3       1.353,50     240      conta   atrav+1t        108       30,6        0,0       23,2          —     159,50    165/240  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                       —     1.103,50        —    1.094,00     1,01  28,0%     75       4,60     0,3              —     240     pregao   atrav+1t        108       30,6        0,0       23,2      0,571          —    165/240  desliz.alvo 1,0t fila NAO CALIBRADA
  B toque   : sinais=108 fills=75 sem_fill=33 (30.6%) atraso mediana/p90 (min)=0.0/25.0 win=28.0% BE emp=23.2% liquido=1103.50 nulo medio=1422.0 [p5 -279.5 ; p95 3093.0] p=0.620 saidas={'stop': 53, 'forced_flatten': 22} flatten=22 (no ultimo bar do continuo=22) saidas na barra do call=0 stop tocado na barra do fill=0 pior op=-71.50
  A toque   : trades=75 recusadas por capital=0 caixa min (MtM)=159.50 sem trade=165/240 liquido=1103.50 zerado=False saidas={'stop': 53, 'forced_flatten': 22} flatten=22 (ultimo bar=22; call=0)
  B atrav+1t: sinais=108 fills=75 sem_fill=33 (30.6%) atraso mediana/p90 (min)=0.0/25.0 win=28.0% BE emp=23.2% liquido=1103.50 nulo medio=1288.2 [p5 -409.0 ; p95 2968.5] p=0.571 saidas={'stop': 53, 'forced_flatten': 22} flatten=22 (no ultimo bar do continuo=22) saidas na barra do call=0 stop tocado na barra do fill=0 pior op=-71.50
  A atrav+1t: trades=75 recusadas por capital=0 caixa min (MtM)=159.50 sem trade=165/240 liquido=1103.50 zerado=False saidas={'stop': 53, 'forced_flatten': 22} flatten=22 (ultimo bar=22; call=0)
  INDICIO CRU: n=240 | V1 fade: media 56 pts, 48% dias +, p=0.241; gap alta (n=119) mov -25 pts, 55% altas; gap baixa (n=121) mov 87 pts, 52% altas; rho(gap,mov)=-0.02 | V2: n=108 resto na direcao da 1a barra 84 pts, 53% dias +, p=0.229 | rho(vol call D-1, amplitude D)=-0.07

## VAL1 2024
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes       modo       fill     sinais  sem fill% atraso min    BE emp%     p nulo  caixa min  sem trade
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
V2 r150 s350 a-                  408,6%     1.021,50   -71,1%      708,00     1,44  33,3%     51       4,19     0,2       1.271,50     244      conta      toque         97       47,4       10,0       26,2          —     169,50    193/244  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                       —     1.305,00        —      440,50     2,96  34,0%     50       5,35     0,2              —     244     pregao      toque         97       48,5       10,0       24,5      0,124          —    194/244  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                  -65,6%      -164,00   -91,4%      909,50    -0,18  31,2%     32      -0,67     0,1          86,00     244      conta   atrav+1t         97       50,5       10,0       33,5          —      86,00    212/244  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 16 ordens
V2 r150 s350 a-                       —       844,50        —      742,00     1,14  31,9%     47       3,46     0,2              —     244     pregao   atrav+1t         97       51,5       10,0       25,2      0,192          —    197/244  desliz.alvo 1,0t fila NAO CALIBRADA
  B toque   : sinais=97 fills=50 sem_fill=47 (48.5%) atraso mediana/p90 (min)=10.0/25.0 win=34.0% BE emp=24.5% liquido=1305.00 nulo medio=357.5 [p5 -988.1 ; p95 1683.1] p=0.124 saidas={'stop': 30, 'forced_flatten': 20} flatten=20 (no ultimo bar do continuo=20) saidas na barra do call=0 stop tocado na barra do fill=2 pior op=-71.50
  A toque   : trades=51 recusadas por capital=0 caixa min (MtM)=169.50 sem trade=193/244 liquido=1021.50 zerado=False saidas={'stop': 31, 'forced_flatten': 20} flatten=20 (ultimo bar=20; call=0)
  B atrav+1t: sinais=97 fills=47 sem_fill=50 (51.5%) atraso mediana/p90 (min)=10.0/25.0 win=31.9% BE emp=25.2% liquido=844.50 nulo medio=164.5 [p5 -1105.0 ; p95 1418.5] p=0.192 saidas={'stop': 29, 'forced_flatten': 18} flatten=18 (no ultimo bar do continuo=18) saidas na barra do call=0 stop tocado na barra do fill=2 pior op=-71.50
  A atrav+1t: trades=32 recusadas por capital=16 caixa min (MtM)=86.00 sem trade=212/244 liquido=-164.00 zerado=False saidas={'stop': 20, 'forced_flatten': 12} flatten=12 (ultimo bar=12; call=0)
  INDICIO CRU: n=244 | V1 fade: media 22 pts, 52% dias +, p=0.381; gap alta (n=123) mov -107 pts, 46% altas; gap baixa (n=121) mov -65 pts, 51% altas; rho(gap,mov)=-0.02 | V2: n=97 resto na direcao da 1a barra 140 pts, 57% dias +, p=0.067 | rho(vol call D-1, amplitude D)=-0.23

## VAL1 2025 jan-set
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes       modo       fill     sinais  sem fill% atraso min    BE emp%     p nulo  caixa min  sem trade
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
V2 r150 s350 a-                  -85,8%      -214,50   -90,6%      340,50    -0,63   0,0%      3      -1,19     0,0          35,50     181      conta      toque         84       34,5       10,0        nan          —      35,50    178/181  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 52 ordens
V2 r150 s350 a-                       —       466,50        —      596,00     0,78  30,9%     55       2,58     0,3              —     181     pregao      toque         84       34,5        0,0       27,6      0,380          —    126/181  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                  -85,8%      -214,50   -90,6%      340,50    -0,63   0,0%      3      -1,19     0,0          35,50     181      conta   atrav+1t         84       34,5       10,0        nan          —      35,50    178/181  desliz.alvo 1,0t fila NAO CALIBRADA CENSURADO recusou 52 ordens
V2 r150 s350 a-                       —       466,50        —      596,00     0,78  30,9%     55       2,58     0,3              —     181     pregao   atrav+1t         84       34,5        0,0       27,6      0,273          —    126/181  desliz.alvo 1,0t fila NAO CALIBRADA
  B toque   : sinais=84 fills=55 sem_fill=29 (34.5%) atraso mediana/p90 (min)=0.0/25.0 win=30.9% BE emp=27.6% liquido=466.50 nulo medio=205.7 [p5 -1190.0 ; p95 1587.0] p=0.380 saidas={'stop': 38, 'forced_flatten': 17} flatten=17 (no ultimo bar do continuo=17) saidas na barra do call=0 stop tocado na barra do fill=2 pior op=-86.50
  A toque   : trades=3 recusadas por capital=52 caixa min (MtM)=35.50 sem trade=178/181 liquido=-214.50 zerado=False saidas={'stop': 3} flatten=0 (ultimo bar=0; call=0)
  B atrav+1t: sinais=84 fills=55 sem_fill=29 (34.5%) atraso mediana/p90 (min)=0.0/25.0 win=30.9% BE emp=27.6% liquido=466.50 nulo medio=-21.2 [p5 -1338.0 ; p95 1292.0] p=0.273 saidas={'stop': 38, 'forced_flatten': 17} flatten=17 (no ultimo bar do continuo=17) saidas na barra do call=0 stop tocado na barra do fill=2 pior op=-86.50
  A atrav+1t: trades=3 recusadas por capital=52 caixa min (MtM)=35.50 sem trade=178/181 liquido=-214.50 zerado=False saidas={'stop': 3} flatten=0 (ultimo bar=0; call=0)
  INDICIO CRU: n=181 | V1 fade: media -20 pts, 49% dias +, p=0.582; gap alta (n=89) mov 159 pts, 54% altas; gap baixa (n=92) mov 115 pts, 51% altas; rho(gap,mov)=0.07 | V2: n=84 resto na direcao da 1a barra 248 pts, 57% dias +, p=0.031 | rho(vol call D-1, amplitude D)=-0.05

## VAL1 2022-2025 (B junto)
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes       modo       fill     sinais  sem fill% atraso min    BE emp%     p nulo  caixa min  sem trade
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
V2 r150 s350 a-                       —     4.279,50        —    1.102,50     3,88  28,7%    247       4,71     0,3              —     908     pregao      toque        402       38,6        0,0       23,1      0,242          —    661/908  desliz.alvo 1,0t fila NAO CALIBRADA
V2 r150 s350 a-                       —     3.962,00        —    1.094,00     3,62  28,5%    242       4,36     0,3              —     908     pregao   atrav+1t        402       39,8        0,0       23,1      0,189          —    666/908  desliz.alvo 1,0t fila NAO CALIBRADA
  B toque   : sinais=402 fills=247 sem_fill=155 (38.6%) atraso mediana/p90 (min)=0.0/25.0 win=28.7% BE emp=23.1% liquido=4279.50 nulo medio=2916.5 [p5 -281.5 ; p95 6178.7] p=0.242 saidas={'stop': 171, 'forced_flatten': 76} flatten=76 (no ultimo bar do continuo=76) saidas na barra do call=0 stop tocado na barra do fill=4 pior op=-86.50
  B atrav+1t: sinais=402 fills=242 sem_fill=160 (39.8%) atraso mediana/p90 (min)=0.0/25.0 win=28.5% BE emp=23.1% liquido=3962.00 nulo medio=2280.3 [p5 -824.5 ; p95 5453.0] p=0.189 saidas={'stop': 168, 'forced_flatten': 74} flatten=74 (no ultimo bar do continuo=74) saidas na barra do call=0 stop tocado na barra do fill=4 pior op=-86.50
  INDICIO CRU: n=908 | V1 fade: media 34 pts, 50% dias +, p=0.209; gap alta (n=447) mov -20 pts, 51% altas; gap baixa (n=461) mov 47 pts, 52% altas; rho(gap,mov)=-0.00 | V2: n=402 resto na direcao da 1a barra 118 pts, 54% dias +, p=0.028 | rho(vol call D-1, amplitude D)=-0.19

```

## 6. Limitações que mudam a leitura

- O motor só avalia stop/alvo a partir da barra seguinte à do fill. Com M5 logo após a abertura, o stop de 350 pts foi tocado dentro da própria barra do fill em 9 das 48 operações do IS (e 4 de 247 nas janelas de validação em B); essas saem na abertura da barra seguinte, pior que o nível. Pior operação do IS: −R$242,50 (stop de 350 pts = R$70).
- Fila do WIN não calibrada. A sensibilidade `atrav+1t` muda pouco o resultado (entrada no último preço da barra, o próximo open costuma já estar ≥ 1 tick abaixo), então ela não mede fila: um nível a 150 pts do close tem fila própria que não foi estimada.
- Grade de 28 células com escolha do melhor: o p do IS não é corrigido para a escolha. Só a validação é fora da amostra.
- V1 e V3 não foram congeladas e portanto não foram rodadas na validação como estratégia; as premissas delas (gap reverte; volume do call vs amplitude) estão no bloco `INDICIO CRU` de cada janela.
- A morte de caixa do modo A é função do caminho: a mesma célula sobrevive ou morre conforme as primeiras operações da janela.

## 7. O indício sobrevive fora da amostra?

Célula congelada (V2, recuo 150, stop 350, sem alvo), modo B, fill=toque; p do nulo de direção aleatória nos mesmos dias:

| janela | sinais | fills | sem fill | líquido R$ | win% | BE emp% | nulo médio R$ [p5 ; p95] | p |
|---|---|---|---|---|---|---|---|---|
| IS 2026-04 a 10 | 63 | 48 | 23,8% | +3.784,00 | 31,2 | 15,7 | +979 [−1.095 ; +3.083] | 0,013 |
| VAL2 2026-02-20 a 04-03 | 12 | 9 | 25,0% | −710,50 | 0,0 | — | −188 [−794 ; +420] | 0,904 |
| 2022 | 113 | 67 | 40,7% | +1.404,50 | 23,9 | 18,4 | +925 [−1.023 ; +2.865] | 0,347 |
| 2023 | 108 | 75 | 30,6% | +1.103,50 | 28,0 | 23,2 | +1.422 [−280 ; +3.093] | 0,620 |
| 2024 | 97 | 50 | 48,5% | +1.305,00 | 34,0 | 24,5 | +358 [−988 ; +1.683] | 0,124 |
| 2025 jan-set | 84 | 55 | 34,5% | +466,50 | 30,9 | 27,6 | +206 [−1.190 ; +1.587] | 0,380 |
| 2022-2025 junto | 402 | 247 | 38,6% | +4.279,50 | 28,7 | 23,1 | +2.917 [−282 ; +6.179] | 0,242 |

- Líquido acima de zero em 4 dos 5 recortes de validação (2022, 2023, 2024, 2025); VAL2 negativo (9 operações, 9 stops). Win% acima do BE empírico nos 4 anos. O líquido observado fica dentro da faixa p5-p95 do nulo em todos os recortes de validação; p ≥ 0,124.
- O nulo de direção aleatória tem média positiva nas janelas longas (+2.917 em 2022-25): stop de 350 pts, sem alvo e segurando até o fim do dia ganha nos dois lados nos dias de tendência.
- Conta contínua R$250 (modo A, fill=toque): censurada em 3 de 6 janelas (2022: 7 trades, 60 ordens recusadas, caixa mín R$31,50; 2025: 3 trades, 52 recusadas, R$35,50; VAL2: 3 trades, 6 recusadas, R$35,50). Não censurada em 2023 (+R$1.103,50, caixa mín R$159,50, 75 trades) e 2024 (+R$1.021,50, caixa mín R$169,50, 51 trades); em 2024 com `atrav+1t` a conta é censurada (32 trades, 16 recusadas, caixa mín R$86,00, −R$164,00).
- Indício cru, sem geometria e sem custo (resto do dia depois da 1ª barra, na direção dela, dias em que ela fechou contra o gap): IS +696 pts, 60% dos dias positivos, n=63 (p 0,002); 2022 +37 pts (52%, n=113, p 0,40); 2023 +84 (53%, n=108, p 0,23); 2024 +140 (57%, n=97, p 0,067); 2025 jan-set +248 (57%, n=84, p 0,031); VAL2 +294 (58%, n=12, p 0,27); 2022-25 junto +118 pts (54%, n=402, p 0,028). Mesmo sinal em todos os recortes, magnitude de 1/6 a 1/20 da do IS nos anos longos.
- Fade do gap (hipótese 1), cru: IS gap de alta −564 pts (32% de pregões de alta, n=66), gap de baixa +263 (54%, n=57), ρ(gap, mov) = −0,20. 2022-25: gap de alta −20 pts (51% de alta, n=447), gap de baixa +47 (52%, n=461), ρ = −0,00; fade médio +34 pts, p 0,21. Por ano, ρ: −0,02; −0,02; −0,02; +0,07.
- Volume do call de D−1 vs amplitude de D (hipótese 3), ρ de Spearman: IS −0,24; 2022 −0,17; 2023 −0,07; 2024 −0,23; 2025 −0,05; VAL2 +0,25 (n=30); 2022-25 junto −0,19 (n=908; volume do call estimado nesses anos).

**Resposta:** o sinal da pista 2 se repete nos 5 recortes fora da amostra, com magnitude muito menor que no IS (+118 pts contra +696 pts, n=402 contra n=63), p 0,028 sem correção para as três hipóteses nem para as janelas. Como estratégia com R$250, a célula congelada não se distingue do nulo de direção aleatória em nenhuma janela de validação (p 0,124 a 0,904; pooled 0,242) e a conta contínua é censurada em 3 de 6 janelas. A pista 1 (fade do gap) não se repete fora da amostra (ρ −0,00 em 908 dias). A pista 3 (volume do call) mantém o sinal negativo em 4 dos 5 recortes de validação (VAL2, n=30, é +0,25), com volume estimado.
