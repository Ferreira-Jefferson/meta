# Hipótese D — detectores de tendência vs. direção do mês (WIN, 2026)

**Veredito: refutada.** Nenhum detector reproduz a direção do mês. 27 detectores/parâmetros bloqueando o lado contra: 26 pioram o líquido (−R$264 a −R$3.883). Só a concordância unânime (ret10d + inclinação EMA20 diária + semana ancorada) sobe (+R$417), mas melhora só 6/14 janelas, e cada componente sozinho piora (−R$548, −R$2.799, −R$1.340): sem platô, ponto isolado. O oráculo (+R$1.756, 9/14 janelas melhor) mostra o teto.

Dados: direção só do arquivo ajustado WIN@D_M5 (2021-2026), nunca para preço. Detectores diários usam pregões encerrados (D-1); semana ancorada e H1 usam barras fechadas. Diagnóstico lê o valor em t-30min (t = barra do preenchimento); simulação usa a barra do sinal. Baseline: 988 trades, +R$4.968,60, 10/14 janelas, PF 1,18.

## Etapa 1 — diagnóstico nos 988 trades

| detector | % a favor | pts/op a favor | pts/op contra | diferença | janelas c/ sinal certo | neutros |
|---|---|---|---|---|---|---|
| ORACULO | 66,1 | 56,3 | -28,1 | 84,4 | 12/13 | 0 |
| ret3d | 66,9 | 21,3 | 40,6 | -19,3 | 8/14 | 0 |
| ret5d | 67,3 | 28,0 | 26,9 | 1,1 | 9/14 | 0 |
| ret10d | 62,7 | 46,1 | -3,4 | 49,5 | 9/14 | 0 |
| ret20d | 51,8 | 22,9 | 32,8 | -9,9 | 5/12 | 0 |
| emaslope10 | 64,5 | 36,5 | 11,6 | 24,9 | 10/14 | 0 |
| emaslope20 | 62,8 | 26,4 | 29,8 | -3,4 | 8/14 | 0 |
| emaslope50 | 57,1 | 40,2 | 10,9 | 29,3 | 8/13 | 0 |
| semana_ancorada | 79,8 | 34,7 | 0,0 | 34,7 | 9/13 | 0 |
| mes_anterior | 58,6 | 29,4 | 25,1 | 4,4 | 6/14 | 0 |
| donchpos10 | 64,0 | 36,6 | 18,5 | 18,1 | 9/14 | 9 |
| donchestado10 | 57,2 | 31,7 | 22,2 | 9,5 | 6/13 | 0 |
| donchpos20 | 60,0 | 31,4 | 22,1 | 9,3 | 8/14 | 0 |
| donchestado20 | 47,8 | 12,0 | 42,0 | -30,0 | 3/13 | 0 |
| donchpos50 | 57,7 | 37,6 | 14,1 | 23,4 | 8/13 | 0 |
| donchestado50 | 49,9 | 14,4 | 40,9 | -26,5 | 5/13 | 0 |
| h1ema21_50 | 72,2 | 30,9 | 19,3 | 11,6 | 9/13 | 0 |
| h1ema9_21 | 89,5 | 26,5 | 37,6 | -11,2 | 6/13 | 0 |
| h1ema50_200 | 56,4 | 22,6 | 34,2 | -11,5 | 6/13 | 0 |
| er5_t0.0 | 67,3 | 28,0 | 26,9 | 1,1 | 9/14 | 0 |
| er5_t0.25 | 69,8 | 38,6 | 59,9 | -21,4 | 7/13 | 328 |
| er10_t0.0 | 62,7 | 46,1 | -3,4 | 49,5 | 9/14 | 0 |
| er10_t0.25 | 67,7 | 31,4 | -0,2 | 31,6 | 7/11 | 430 |
| er20_t0.0 | 51,8 | 22,9 | 32,8 | -9,9 | 5/12 | 0 |
| er20_t0.25 | 63,7 | 14,7 | -2,7 | 17,4 | 5/9 | 545 |
| conc_unan(ret10,emaslope20,semana) | 82,4 | 41,0 | -38,3 | 79,3 | 7/10 | 413 |
| conc_maj(ret10,emaslope20,h1ema21_50) | 70,8 | 37,5 | 19,0 | 18,4 | 7/13 | 256 |
| conc_maj(ret5d,donchpos20,semana) | 84,2 | 40,1 | 14,6 | 25,6 | 6/10 | 462 |
| conc_unan(ret5d,donchpos20) | 68,0 | 35,0 | 33,2 | 1,8 | 8/14 | 240 |

Leitura: ret10d (+49,5), emaslope50 (+29,3), semana (+34,7), donchpos50 (+23,4) têm diferença grande, mas vizinhos viram negativos (ret5d +1,1, ret20d -9,9, ret3d -19,3; emaslope20 -3,4) e as janelas certas ficam em 8-10/14 (oráculo 12/13). Semana ancorada tem 80% a favor por viés mecânico: o alinhamento das EMAs já implica preço acima da abertura semanal.

## Etapa 2 — simulação com bloqueio do lado contra (27 detectores + oráculo)

| variante | líquido R$ | janelas + | pior janela | trades | PF | pts/op | maior DD R$ | Δ vs base | janelas melhor | LOWO (pior Δ) |
|---|---|---|---|---|---|---|---|---|---|---|
| BASELINE | 4968,6 | 10/14 | -987,1 | 988 | 1,18 | 27,6 | 1750,5 | 0,0 | - | 0,0 |
| ret3d | 2327,9 | 7/14 | -987,1 | 677 | 1,12 | 19,7 | 1174,0 | -2640,7 | 6/14 | -2864,2 |
| ret5d | 2578,3 | 8/14 | -904,7 | 687 | 1,13 | 21,3 | 1417,5 | -2390,3 | 7/14 | -2668,7 |
| ret10d | 4420,9 | 9/14 | -904,7 | 637 | 1,26 | 37,2 | 957,2 | -547,7 | 8/14 | -1140,2 |
| ret20d | 1863,5 | 8/14 | -904,7 | 525 | 1,13 | 20,2 | 957,2 | -3105,1 | 6/14 | -4017,6 |
| emaslope10 | 2948,6 | 9/14 | -904,7 | 662 | 1,16 | 24,8 | 976,0 | -2020,0 | 6/14 | -2394,5 |
| emaslope20 | 2169,9 | 8/14 | -904,7 | 645 | 1,12 | 19,3 | 1266,2 | -2798,7 | 6/14 | -3223,2 |
| emaslope50 | 4147,4 | 10/14 | -904,7 | 580 | 1,27 | 38,3 | 957,2 | -821,2 | 7/14 | -2051,7 |
| semana_ancorada | 3628,6 | 8/14 | -960,5 | 832 | 1,15 | 24,3 | 2228,0 | -1340,0 | 7/14 | -1639,9 |
| mes_anterior | 2955,6 | 7/14 | -911,5 | 554 | 1,2 | 29,2 | 957,2 | -2013,0 | 6/14 | -2439,0 |
| donchpos10 | 3237,6 | 8/14 | -904,7 | 660 | 1,17 | 27,0 | 999,5 | -1731,0 | 7/14 | -2224,7 |
| donchestado10 | 2921,8 | 8/14 | -904,7 | 578 | 1,18 | 27,8 | 1044,1 | -2046,8 | 6/14 | -3277,3 |
| donchpos20 | 2841,8 | 7/14 | -904,7 | 620 | 1,17 | 25,4 | 957,2 | -2126,8 | 6/14 | -2950,3 |
| donchestado20 | 1086,1 | 8/14 | -838,8 | 517 | 1,07 | 13,0 | 957,2 | -3882,5 | 5/14 | -4871,3 |
| donchpos50 | 3676,4 | 9/14 | -904,7 | 588 | 1,23 | 33,8 | 957,2 | -1292,2 | 7/14 | -2522,7 |
| donchestado50 | 1161,4 | 7/14 | -904,7 | 504 | 1,08 | 14,0 | 957,2 | -3807,2 | 6/14 | -4214,6 |
| h1ema21_50 | 3341,1 | 9/14 | -904,7 | 747 | 1,16 | 24,9 | 1390,0 | -1627,5 | 7/14 | -2043,6 |
| h1ema9_21 | 3799,9 | 9/14 | -986,1 | 945 | 1,14 | 22,6 | 1662,8 | -1168,7 | 4/14 | -1366,2 |
| h1ema50_200 | 2079,4 | 8/14 | -913,3 | 566 | 1,13 | 20,9 | 1044,1 | -2889,2 | 6/14 | -3686,7 |
| er5_t0.0 | 2578,3 | 8/14 | -904,7 | 687 | 1,13 | 21,3 | 1417,5 | -2390,3 | 7/14 | -2668,7 |
| er5_t0.25 | 2132,5 | 9/14 | -944,8 | 813 | 1,09 | 15,6 | 1331,0 | -2836,1 | 5/14 | -3022,8 |
| er10_t0.0 | 4420,9 | 9/14 | -904,7 | 637 | 1,26 | 37,2 | 957,2 | -547,7 | 8/14 | -1140,2 |
| er10_t0.25 | 4704,3 | 9/14 | -908,8 | 825 | 1,21 | 31,0 | 1348,9 | -264,3 | 6/14 | -609,5 |
| er20_t0.0 | 1863,5 | 8/14 | -904,7 | 525 | 1,13 | 20,2 | 957,2 | -3105,1 | 6/14 | -4017,6 |
| er20_t0.25 | 4583,7 | 10/14 | -987,1 | 829 | 1,2 | 30,1 | 1199,9 | -384,9 | 3/14 | -1258,9 |
| conc_unan(ret10,emaslope20,semana) | 5385,4 | 10/14 | -987,1 | 908 | 1,22 | 32,2 | 1806,0 | 416,8 | 6/14 | 179,5 |
| conc_maj(ret10,emaslope20,h1ema21_50) | 4431,1 | 9/14 | -904,7 | 797 | 1,21 | 30,3 | 1254,0 | -537,5 | 8/14 | -882,7 |
| conc_maj(ret5d,donchpos20,semana) | 4706,7 | 9/14 | -987,1 | 925 | 1,19 | 27,9 | 1767,5 | -261,9 | 4/14 | -495,6 |
| conc_unan(ret5d,donchpos20) | 2893,0 | 8/14 | -904,7 | 772 | 1,13 | 21,2 | 1476,0 | -2075,6 | 6/14 | -2420,8 |
| ORACULO (dir. do mes) | 6724,7 | 10/14 | -904,7 | 661 | 1,38 | 53,4 | 1044,1 | 1756,1 | 9/14 | 525,6 |

Obs.: oráculo da simulação = sinal de (último fechamento − primeira abertura) do mês dentro do contrato. LOWO = menor Δ vs. baseline ao retirar uma janela (positivo = sobrevive).

## Nº de testes
28 detectores/parâmetros no diagnóstico + 28 simulações (27 detectores + oráculo) = 56 configurações. Com 14 janelas e 27 detectores, um acerto isolado é esperado por acaso; o único que subiu não tem platô.

## Conclusão
Bloquear o lado contra por detector de regime remove também trades lucrativos e altera a cadeia de reentradas. Candidata: nenhuma.