# Hipótese B — tamanho de posição conforme o regime do mês (WIN, MELHOR ATUAL)

Motor e execução do kit (`win_melhor_kit.py`), 14 janelas de 2026, R$1.000 por janela, 1 contrato base.
Detectores (só informação até c[t]):
- `vwap`: fechamento > VWAP ancorada no 1º pregão do mês (preço típico (h+l+c)/3 x vol). Âncora = max(início do mês, início do contrato).
- `abert`: fechamento > abertura do mês (1ª barra do mês no contrato; mesma âncora). Em mês que começa na rolagem, é a abertura do contrato.
- `oraculo`: sinal de (fechamento final - abertura) do mês no contrato. Usa o futuro; só como teto.
Variante `fav/contra` = contratos no lado a favor do regime / no lado contrário (0 = não opera). O motor reduz sozinho se o caixa não comportar.

Nº de variantes rodadas: 22 (baseline + 3 detectores x grade 4x2, menos o caso 1/1 que é o baseline, 3x7 = 21). A "escala progressiva pelo caixa" (variante 2) NÃO foi rodada à parte: o hook não vê o caixa e o motor já limita contratos por `caixa >= 100 + 250(q-1)`, que é o mesmo efeito que floor(caixa/250); pedir 2 ou 4 a favor já é essa escala (as linhas fav2 e fav4).
Colunas: cx<250 / cx<100 = nº de janelas (de 14) em que o caixa mínimo caiu abaixo disso. DD% pode passar de 100 porque o caixa fica negativo. seq perd = maior sequência de trades perdedores consecutivos em R$. LOWO = líquido sem a janela de maior ganho da variante; LOWO base = líquido do baseline sem essa mesma janela.

| variante | liq R$ | jan+ | pior jan | PF | trades | DD R$ | DD% | DDmed% | fator rec | cx<250 | cx<100 | seq perd | LOWO liq | LOWO base |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BASELINE 1/1 | 4969 | 10/14 | -987 | 1.18 | 988 | 1750 | 98.7 | 45.9 | 2.84 | 1 | 1 | -955 | 3038 | 3038 |
| vwap fav1/contra0 | 3754 | 8/14 | -917 | 1.15 | 903 | 1896 | 91.7 | 46.2 | 1.98 | 2 | 1 | -955 | 2196 | 3038 |
| vwap fav2/contra0 | 8039 | 7/14 | -946 | 1.17 | 858 | 3649 | 98.4 | 62.5 | 2.2 | 4 | 4 | -1864 | 4924 | 3038 |
| vwap fav2/contra1 | 9737 | 9/14 | -982 | 1.21 | 945 | 3468 | 98.8 | 60.2 | 2.81 | 4 | 3 | -1864 | 6278 | 3038 |
| vwap fav3/contra0 | 12413 | 7/14 | -974 | 1.22 | 740 | 5026 | 99.2 | 69.3 | 2.47 | 7 | 5 | -2543 | 7740 | 3038 |
| vwap fav3/contra1 | 13845 | 8/14 | -952 | 1.22 | 900 | 4969 | 98.1 | 67.9 | 2.79 | 6 | 5 | -2543 | 8857 | 3038 |
| vwap fav4/contra0 | 12904 | 6/14 | -1023 | 1.21 | 661 | 6443 | 100.4 | 75.1 | 2.0 | 8 | 7 | -2514 | 6674 | 3038 |
| vwap fav4/contra1 | 12476 | 6/14 | -976 | 1.19 | 752 | 6373 | 99.3 | 76.4 | 1.96 | 9 | 8 | -2528 | 5960 | 3038 |
| abert fav1/contra0 | 6578 | 9/14 | -662 | 1.34 | 736 | 1044 | 80.9 | 35.0 | 6.3 | 1 | 0 | -641 | 4893 | 3538 |
| abert fav2/contra0 | 12686 | 9/14 | -1014 | 1.36 | 673 | 2088 | 101.4 | 51.6 | 6.08 | 2 | 2 | -1281 | 9317 | 3538 |
| abert fav2/contra1 | 11854 | 10/14 | -987 | 1.28 | 957 | 2253 | 98.8 | 57.0 | 5.26 | 3 | 3 | -1376 | 8434 | 3038 |
| abert fav3/contra0 | 19888 | 9/14 | -1043 | 1.44 | 613 | 2060 | 104.3 | 59.7 | 9.65 | 4 | 3 | -1714 | 14835 | 3538 |
| abert fav3/contra1 | 19925 | 10/14 | -987 | 1.35 | 940 | 3289 | 98.7 | 60.6 | 6.06 | 4 | 3 | -1922 | 15017 | 3038 |
| abert fav4/contra0 | 23994 | 8/14 | -950 | 1.46 | 557 | 2712 | 97.0 | 64.8 | 8.85 | 6 | 5 | -2285 | 17497 | 3538 |
| abert fav4/contra1 | 22938 | 8/14 | -987 | 1.36 | 855 | 3909 | 99.1 | 66.5 | 5.87 | 6 | 6 | -2540 | 16543 | 3038 |
| oraculo fav1/contra0 | 6725 | 10/14 | -905 | 1.38 | 661 | 1044 | 90.5 | 34.0 | 6.44 | 1 | 1 | -641 | 4886 | 3538 |
| oraculo fav2/contra0 | 14574 | 10/14 | -922 | 1.44 | 632 | 2088 | 95.1 | 46.7 | 6.98 | 2 | 2 | -1281 | 10897 | 3538 |
| oraculo fav2/contra1 | 12582 | 10/14 | -994 | 1.3 | 948 | 2253 | 99.6 | 54.5 | 5.58 | 3 | 3 | -1376 | 9177 | 3038 |
| oraculo fav3/contra0 | 22997 | 10/14 | -1026 | 1.48 | 631 | 3132 | 101.4 | 53.0 | 7.34 | 3 | 2 | -1922 | 17483 | 3538 |
| oraculo fav3/contra1 | 21070 | 10/14 | -963 | 1.38 | 930 | 3289 | 97.6 | 57.8 | 6.41 | 4 | 3 | -1922 | 15962 | 3538 |
| oraculo fav4/contra0 | 29718 | 9/14 | -958 | 1.51 | 602 | 3800 | 98.9 | 57.9 | 7.82 | 5 | 4 | -2516 | 22365 | 3538 |
| oraculo fav4/contra1 | 26495 | 9/14 | -976 | 1.4 | 900 | 3797 | 98.9 | 62.2 | 6.98 | 5 | 5 | -2516 | 19697 | 3538 |


## Mês a mês (R$ líquido por janela)

| janela | mercado pts | base 1/1 | vwap 2/0 | vwap 2/1 | abert 2/0 | abert 2/1 | oraculo 2/0 |
|---|---|---|---|---|---|---|---|
| 2026-01 WING26 07-30 | 17829 | 1431 | 2886 | 2995 | 3369 | 3104 | 3677 |
| 2026-02 WING26 01-18 | 6104 | 417 | -19 | 261 | 761 | 797 | 761 |
| 2026-02 WINJ26 24-27 | -1244 | -420 | -922 | -900 | -545 | -957 | -545 |
| 2026-03 WINJ26 01-31 | -1329 | 34 | -52 | 198 | -268 | 91 | 70 |
| 2026-04 WINJ26 01-15 | 8158 | -987 | -946 | -916 | -1014 | -987 | -915 |
| 2026-04 WINM26 22-30 | -11000 | 1359 | 2798 | 2758 | 2798 | 2758 | 2798 |
| 2026-05 WINM26 01-29 | -15335 | 490 | 744 | 710 | 744 | 710 | 1671 |
| 2026-06 WINM26 01-17 | -7419 | -645 | -945 | -982 | -945 | -982 | -922 |
| 2026-06 WINQ26 23-30 | 2434 | 162 | 174 | 309 | 294 | 309 | 294 |
| 2026-07 WINQ26 01-31 | 4817 | 1931 | 3115 | 3459 | 2976 | 3419 | 2948 |
| 2026-08 WINQ26 01-12 | -12841 | 622 | 1244 | 1244 | 1214 | 1378 | 1257 |
| 2026-08 WINV26 18-31 | 10435 | 694 | 1387 | 1387 | 1178 | 1321 | 1356 |
| 2026-09 WINV26 01-30 | 8310 | 151 | -939 | -352 | 2763 | 1532 | 2763 |
| 2026-10 WINV26 01-01 | 510 | -270 | -486 | -434 | -640 | -640 | -640 |

Filtro puro (abert 1/0, sem aumentar tamanho) vs baseline vs oráculo 1/0, por janela, com caixa mínimo da variante:

| janela | base | abert 1/0 | oraculo 1/0 | caixa mín abert 1/0 |
|---|---|---|---|---|
| 2026-01 WING26 | 1431 | 1684 | 1838 | 928 |
| 2026-02 WING26 | 417 | 380 | 380 | 883 |
| 2026-02 WINJ26 24-27 | -420 | -272 | -272 | 728 |
| 2026-03 WINJ26 | 34 | -134 | 35 | 706 |
| 2026-04 WINJ26 01-15 | -987 | -285 | -905 | 191 |
| 2026-04 WINM26 | 1359 | 1399 | 1399 | 1000 |
| 2026-05 WINM26 | 490 | 524 | 835 | 661 |
| 2026-06 WINM26 01-17 | -645 | -662 | -626 | 301 |
| 2026-06 WINQ26 | 162 | 147 | 147 | 1000 |
| 2026-07 WINQ26 | 1931 | 1488 | 1474 | 1000 |
| 2026-08 WINQ26 01-12 | 622 | 607 | 628 | 945 |
| 2026-08 WINV26 | 694 | 589 | 678 | 962 |
| 2026-09 WINV26 | 151 | 1382 | 1382 | 981 |
| 2026-10 WINV26 | -270 | -270 | -270 | 651 |

## Veredito

1. **Aumentar o tamanho (fav >= 2) não melhora o conjunto sem aumentar a ruína.** Com `abert` o líquido sobe (11.854 a 23.994), mas o nº de janelas com caixa < R$100 vai de 1 (baseline) para 2 a 6, o pior caso chega a -R$1.043 (caixa negativo) e a sequência de perdas vai de -R$955 para -R$1.281 a -R$2.540. Com R$1.000 de capital, é alavancagem: o mesmo trecho de inversão (01-15/abr) que custou 987 passa a zerar a conta. Com `vwap` é pior: janelas positivas caem (6 a 9/14), DD médio 60-76%, e em set/2026 o detector erra o regime e perde (-939 com 2/0 contra +151 do baseline).
2. **O ganho robusto vem de "contra = 0", não de "a favor > 1".** `abert 1/0` (nenhum contrato extra, só não operar contra o regime): +R$6.578 contra +R$4.969, PF 1,34 contra 1,18, 9/14 contra 10/14 janelas (perde 1), pior janela -662 contra -987, maior DD R$1.044 contra R$1.750 (-40%), DD médio 35% contra 46%, fator de recuperação 6,3 contra 2,8, 0 janelas com caixa < R$100 (baseline tem 1), sequência de perdas -641 contra -955. Sobrevive ao leave-one-window-out (tirando a janela de maior ganho: 4.893 contra 3.538 do baseline sem a mesma janela). Fica quase no mesmo patamar do oráculo 1/0 (6.725): o detector "acima/abaixo da abertura do mês" quase não perde para saber a direção do mês. Isto é um FILTRO de direção (território da outra frente de detectores), não de tamanho.
3. Fragilidade: o ganho do `abert 1/0` está concentrado em 2 janelas (set/2026 +1.231 e 01-15/abr +702 de diferença sobre o baseline); nas outras o efeito é pequeno e misto (jul/2026 perde 443, mar -168, jun -17). Com 14 janelas e um mês de abertura (o regime só fica "firme" depois dos primeiros dias; nos primeiros pregões a abertura do mês é quase o preço corrente), não é prova de edge; é candidata a confirmar em outro ativo/ano.
4. `vwap` não se sustenta como detector de regime mensal: pior que `abert` em todas as grades. Platô: em `abert`, todas as 7 células têm líquido > baseline e PF >= 1,28, mas o risco (caixa<100, seq. de perdas) cresce monotonicamente com o tamanho a favor; não existe célula com tamanho maior que reduz risco.
5. Oráculo (teto): fav4/contra0 chega a +29.718, mas com caixa < R$100 em 4 janelas e DD R$3.800. Mesmo sabendo o regime perfeitamente, mais contratos com R$1.000 aumenta ruína; o limite é capital, não detector.

**Recomendação:** não escalar contratos por regime com R$1.000. Se algo avança, é o filtro `abert 1/0` (contra = 0, a favor = 1) para validação por outra frente.
