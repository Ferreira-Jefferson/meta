# Hipótese C — saída por regime (a favor / contra o mês)

Variantes rodadas: **124** (+ baseline). Baseline reproduzido exatamente (+R$4.968,60; 988 trades).
Janela de maior ganho do baseline (leave-one-out): 2026-07 WINQ26 01-31 (1930.60).

Nomenclatura: `regime|C:<saída contra>|F:<saída a favor>`; C: orig, EMA5/EMA7, stopK (K×ATR14), /alvoMx (M×stop).

## Baseline e melhores (regime VWAP, por líquido)

| variante | líquido R$ | janelas + | pior janela | PF | pts/op | payoff | acerto% | trades | maior DD R$/% | fator recup. | líq. s/ melhor janela do baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BASELINE | 4968.60 | 10/14 | -987.10 | 1.18 | 27.6 | 2.51 | 32.1 | 988 | 1750.50 / 98.7% | 2.84 | 3038.00 |
| vwap|C:EMA5|F:c21 | 5979.20 | 10/14 | -904.40 | 1.26 | 48.5 | 2.4 | 34.5 | 650 | 1784.00 / 90.4% | 3.35 | 4473.10 |
| vwap|C:EMA7|F:c21 | 5970.40 | 9/14 | -923.40 | 1.26 | 49.1 | 2.42 | 34.2 | 640 | 1886.00 / 92.3% | 3.17 | 4445.90 |
| vwap|C:orig|F:c21 | 5857.10 | 9/14 | -923.40 | 1.26 | 48.9 | 2.48 | 33.6 | 631 | 1920.00 / 92.3% | 3.05 | 4339.30 |
| vwap|C:stop1.0|F:c21 | 5846.19 | 9/14 | -922.80 | 1.26 | 48.4 | 2.5 | 33.4 | 637 | 1977.02 / 92.3% | 2.96 | 4287.57 |
| vwap|C:stop0.75|F:c21 | 5725.37 | 9/14 | -910.71 | 1.25 | 47.2 | 2.51 | 33.2 | 641 | 1949.89 / 91.1% | 2.94 | 4164.93 |
| vwap|C:stop1.0/alvo1.5x|F:9x21 | 5593.02 | 10/14 | -954.06 | 1.25 | 66.5 | 2.0 | 38.4 | 437 | 2297.56 / 98.0% | 2.43 | 4646.59 |
| vwap|C:stop0.5|F:c21 | 5570.57 | 8/14 | -908.51 | 1.24 | 44.6 | 2.61 | 32.2 | 661 | 1916.14 / 90.9% | 2.91 | 3997.36 |
| vwap|C:stop1.0|F:9x21 | 5565.91 | 10/14 | -971.02 | 1.27 | 70.4 | 2.22 | 36.3 | 410 | 2314.52 / 98.8% | 2.4 | 4343.89 |
| vwap|C:EMA7|F:9x21 | 5558.50 | 10/14 | -957.30 | 1.26 | 69.8 | 2.13 | 37.3 | 413 | 2285.00 / 97.5% | 2.43 | 4370.60 |
| vwap|C:EMA5|F:9x21 | 5453.70 | 10/14 | -935.50 | 1.26 | 66.7 | 2.12 | 37.2 | 425 | 2279.00 / 97.2% | 2.39 | 4292.40 |
| vwap|C:stop0.75|F:9x21 | 5451.13 | 10/14 | -943.89 | 1.26 | 68.2 | 2.25 | 35.9 | 415 | 2287.39 / 97.6% | 2.38 | 4227.29 |
| vwap|C:orig|F:9x21 | 5410.10 | 10/14 | -957.30 | 1.26 | 69.3 | 2.18 | 36.5 | 405 | 2257.50 / 96.3% | 2.4 | 4228.90 |
| vwap|C:stop1.0/alvo2.0x|F:9x21 | 5409.91 | 10/14 | -914.09 | 1.25 | 66.1 | 2.11 | 37.2 | 425 | 2244.31 / 95.8% | 2.41 | 4361.94 |
| vwap|C:stop1.0/alvo1.0x|F:9x21 | 5388.05 | 10/14 | -951.89 | 1.24 | 60.6 | 1.76 | 41.4 | 464 | 2272.29 / 97.0% | 2.37 | 4397.87 |
| vwap|C:stop0.75/alvo2.0x|F:9x21 | 5330.03 | 10/14 | -946.82 | 1.24 | 61.5 | 2.09 | 37.2 | 452 | 2261.00 / 96.5% | 2.36 | 4417.75 |

## Platô: média por opção (regime VWAP; delta de líquido vs baseline)

**saída CONTRA** (média sobre as demais opções)

| opção | líquido médio | delta | janelas+ média | n |
|---|---|---|---|---|
| orig | 5011 | +42 | 9.0 | 3 |
| EMA5 | 5090 | +121 | 9.2 | 4 |
| EMA7 | 5095 | +127 | 9.2 | 4 |
| stop0.5 | 4775 | -194 | 8.8 | 4 |
| stop0.75 | 4962 | -7 | 9.0 | 4 |
| stop1.0 | 5071 | +102 | 9.0 | 4 |
| stop0.5/alvo1.0x | 3432 | -1536 | 8.2 | 4 |
| stop0.5/alvo1.5x | 3552 | -1416 | 8.2 | 4 |
| stop0.5/alvo2.0x | 3982 | -987 | 8.5 | 4 |
| stop0.75/alvo1.0x | 3986 | -983 | 8.8 | 4 |
| stop0.75/alvo1.5x | 4308 | -661 | 9.0 | 4 |
| stop0.75/alvo2.0x | 4533 | -436 | 9.0 | 4 |
| stop1.0/alvo1.0x | 4512 | -456 | 9.0 | 4 |
| stop1.0/alvo1.5x | 4734 | -235 | 9.0 | 4 |
| stop1.0/alvo2.0x | 4671 | -298 | 9.0 | 4 |

**saída A FAVOR** (média sobre as demais opções)

| opção | líquido médio | delta | janelas+ média | n |
|---|---|---|---|---|
| 9x21 | 5170 | +201 | 10.0 | 15 |
| c34 | 3397 | -1571 | 8.2 | 15 |
| orig | 4528 | -441 | 8.9 | 14 |
| c21 | 4930 | -39 | 8.4 | 15 |

## Controles: a mesma saída solta em TODOS os trades / aplicada ao regime invertido

| variante | líquido R$ | janelas + | pior janela | PF | pts/op | payoff | acerto% | trades | maior DD R$/% | fator recup. | líq. s/ melhor janela do baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BASELINE | 4968.60 | 10/14 | -987.10 | 1.18 | 27.6 | 2.51 | 32.1 | 988 | 1750.50 / 98.7% | 2.84 | 3038.00 |
| todos|C:orig|F:c21 | 5181.00 | 8/14 | -925.10 | 1.23 | 45.8 | 2.41 | 33.8 | 598 | 1988.00 / 92.5% | 2.61 | 3677.10 |
| todos|C:orig|F:9x21 | 4633.00 | 10/14 | -931.90 | 1.22 | 67.6 | 2.07 | 37.1 | 356 | 2261.50 / 96.5% | 2.05 | 3600.80 |
| todos|C:orig|F:c34 | 3215.70 | 8/14 | -942.40 | 1.15 | 39.0 | 2.44 | 32.0 | 441 | 2089.00 / 96.0% | 1.54 | 1598.60 |
| invertido|C:orig|F:c34 | 4376.20 | 8/14 | -900.90 | 1.17 | 26.3 | 2.46 | 32.2 | 920 | 1868.00 / 90.1% | 2.34 | 2330.30 |
| invertido|C:orig|F:9x21 | 3635.40 | 8/14 | -961.70 | 1.14 | 22.5 | 2.36 | 32.5 | 910 | 1852.00 / 96.2% | 1.96 | 1651.70 |
| invertido|C:orig|F:c21 | 4450.50 | 8/14 | -910.50 | 1.17 | 26.0 | 2.45 | 32.3 | 945 | 1806.00 / 91.1% | 2.46 | 2530.60 |

## Oráculo (regime = direção real do mês) — só teto

| variante | líquido R$ | janelas + | pior janela | PF | pts/op | payoff | acerto% | trades | maior DD R$/% | fator recup. | líq. s/ melhor janela do baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BASELINE | 4968.60 | 10/14 | -987.10 | 1.18 | 27.6 | 2.51 | 32.1 | 988 | 1750.50 / 98.7% | 2.84 | 3038.00 |
| oraculo|C:EMA5|F:c21 | 6125.80 | 10/14 | -925.10 | 1.25 | 39.6 | 2.47 | 33.7 | 826 | 1558.50 / 92.5% | 3.93 | 4894.90 |
| oraculo|C:EMA5|F:9x21 | 6015.00 | 10/14 | -931.90 | 1.26 | 47.5 | 2.33 | 35.0 | 668 | 1905.00 / 93.2% | 3.16 | 5051.10 |
| oraculo|C:stop1.0/alvo2.0x|F:c21 | 6009.15 | 9/14 | -925.10 | 1.21 | 37.0 | 2.52 | 32.5 | 872 | 1922.98 / 93.3% | 3.12 | 4747.36 |
| oraculo|C:stop0.75|F:c21 | 6000.46 | 10/14 | -925.10 | 1.26 | 41.6 | 2.84 | 30.6 | 767 | 1920.08 / 92.5% | 3.13 | 4702.19 |
| oraculo|C:stop0.75/alvo2.0x|F:c21 | 5905.19 | 9/14 | -925.10 | 1.2 | 32.3 | 2.46 | 32.8 | 992 | 2054.93 / 92.5% | 2.87 | 4574.38 |
| oraculo|C:EMA7|F:c21 | 5887.90 | 9/14 | -925.10 | 1.25 | 40.8 | 2.54 | 32.9 | 769 | 1946.50 / 92.5% | 3.02 | 4507.20 |
| oraculo|C:orig|F:c21 | 5747.50 | 9/14 | -925.10 | 1.24 | 42.5 | 2.56 | 32.7 | 719 | 2049.00 / 92.5% | 2.81 | 4228.60 |
| oraculo|C:stop0.75|F:9x21 | 5744.16 | 10/14 | -931.90 | 1.26 | 50.2 | 2.81 | 30.9 | 602 | 2266.58 / 96.7% | 2.53 | 4712.89 |

## Mês a mês — baseline vs. 3 melhores (VWAP)

| janela | baseline | vwap|C:EMA5|F:c21 | vwap|C:EMA7|F:c21 | vwap|C:orig|F:c21 |
|---|---|---|---|---|
| 2026-01 WING26 07-30 | 1430.90 | 1798.80 | 1742.00 | 1813.60 |
| 2026-02 WING26 01-18 | 416.60 | 570.10 | 679.80 | 690.90 |
| 2026-02 WINJ26 24-27 | -420.00 | -450.30 | -450.30 | -450.30 |
| 2026-03 WINJ26 01-31 | 34.20 | 396.50 | 560.90 | 442.00 |
| 2026-04 WINJ26 01-15 | -987.10 | -904.40 | -923.40 | -923.40 |
| 2026-04 WINM26 22-30 | 1359.20 | 1340.80 | 1340.80 | 1305.40 |
| 2026-05 WINM26 01-29 | 490.30 | 565.80 | 565.80 | 520.50 |
| 2026-06 WINM26 01-17 | -645.40 | -443.40 | -424.80 | -380.50 |
| 2026-06 WINQ26 23-30 | 162.40 | 83.60 | 47.00 | 47.00 |
| 2026-07 WINQ26 01-31 | 1930.60 | 1506.10 | 1524.50 | 1517.80 |
| 2026-08 WINQ26 01-12 | 621.90 | 936.60 | 936.60 | 936.60 |
| 2026-08 WINV26 18-31 | 693.50 | 655.50 | 655.50 | 655.50 |
| 2026-09 WINV26 01-30 | 151.00 | 71.50 | -43.00 | -77.00 |
| 2026-10 WINV26 01-01 | -269.50 | -148.00 | -241.00 | -241.00 |
## Veredito

- Total de variantes: **124** (+ baseline): 2 regimes (VWAP, oráculo) x 15 saídas contra x 4 saídas a favor, menos o controle, + 6 controles (saída solta em todos os trades / regime invertido). Cópia do motor reproduz o baseline exatamente (+R$4.968,60, 988 trades).
- **Lado CONTRA (curto, stop k×ATR, alvo m×stop): não ajuda.** Quebra pela EMA5/EMA7 e stop 1,0×ATR ficam dentro do ruído (+100 a +130 de média); stop 0,5/0,75 e qualquer alvo-limite pioram (−240 a −1.500 de média): cortar o lado contra mais cedo tira os trades que viram. Sem platô positivo.
- **Lado A FAVOR (deixar correr): único sinal.** Saída `c21` (sai só quando o fechamento cruza a EMA21, em vez da quebra do alinhamento completo) no lado a favor do regime VWAP, com o contra original: **+R$5.857 (+R$889 vs baseline)**, PF 1,26, pts/op 48,9, 631 trades (vs 988), mas 9/14 janelas (vs 10/14) e maior DD R$1.920 (vs 1.750). Sobrevive ao leave-one-window-out (sem a melhor janela do baseline: 4.339 vs 3.038). `9x21` dá 10/14 janelas e pts/op 69, mas DD R$2.257 e líquido +R$440. `c34` é pior que o baseline.
- **Controle que importa:** a mesma `c21` em TODOS os trades dá +R$5.181 (8/14); no regime INVERTIDO dá +R$4.450 (8/14). Ou seja, ~R$700 do ganho vem de o regime escolher o lado certo e o resto (~R$210) é só "sair mais frouxo". O detector VWAP tem valor, mas a diferença é pequena para 14 janelas, uma amostra de 1 ano.
- Oráculo (teto): melhor +R$6.126 (EMA5 contra + c21 a favor), só +R$1.157 sobre o baseline — mesmo sabendo a direção do mês, mexer na saída por lado rende pouco. A saída não é a alavanca do regime; o lado/tamanho (hipóteses A/B) é.
- **Conclusão:** nada supera o baseline de forma clara. `VWAP|C:orig|F:c21` é candidata fraca (+18% líquido, pior janela melhor, mas 1 janela positiva a menos e DD maior, ganho concentrado em poucas janelas — perde em jul/set). Não recomendo trocar a MELHOR ATUAL por isso sem confirmar fora da amostra.
