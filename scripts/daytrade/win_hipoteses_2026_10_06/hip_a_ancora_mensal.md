# Hipótese A — média/VWAP/abertura ancorada no 1º pregão do mês

Variantes testadas: **62** (1 baseline + 60 variantes + 1 oráculo). Motor, capital (R$1.000/janela) e execução (entrada limite) idênticos ao baseline.

Âncora = primeiro pregão do mês DENTRO do contrato (max(início do mês, início do contrato)); só usa dados até o fechamento da barra do sinal. Primeiros D pregões: `0` opera os dois lados; `mesant` usa o regime da última barra do mês anterior (se estiver no mesmo contrato; senão os dois lados).

| variante | líquido R$ | jan + | pior jan | PF | pts/op | trades | maior DD R$ | DD % | fator recup. | LOWO (sem a melhor jan) vs base |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 4.969 | 10/14 | -987 | 1.18 | 27.6 | 988 | 1.750 | 98.7 | 2.84 | 3.038 vs 3.038 |
| abertura|pos|k0|D5|mesant | 6.661 | 10/14 | -626 | 1.4 | 52.4 | 667 | 957 | 74.0 | 6.96 | 5.064 vs 3.538 |
| abertura|pos|k1|D5|mesant | 6.615 | 10/14 | -626 | 1.39 | 51.8 | 671 | 957 | 74.0 | 6.91 | 5.095 vs 3.038 |
| abertura|pos|k0|D0 | 6.578 | 9/14 | -662 | 1.34 | 47.2 | 736 | 1.044 | 80.9 | 6.3 | 4.893 vs 3.538 |
| abertura|pos|k2|D2 | 6.119 | 10/14 | -914 | 1.32 | 45.2 | 716 | 1.044 | 91.4 | 5.86 | 4.526 vs 3.038 |
| abertura|pos|k0.5|D2 | 6.106 | 10/14 | -907 | 1.32 | 45.9 | 704 | 1.044 | 90.7 | 5.85 | 4.406 vs 3.538 |
| abertura|pos|k2|D0 | 6.023 | 10/14 | -1.060 | 1.31 | 44.8 | 712 | 1.060 | 106.0 | 5.68 | 4.429 vs 3.038 |
| abertura|pos|k0.5|D0 | 5.957 | 9/14 | -931 | 1.32 | 45.4 | 695 | 1.044 | 93.1 | 5.71 | 4.257 vs 3.538 |
| abertura|pos|k0|D2 | 5.916 | 10/14 | -928 | 1.31 | 44.3 | 707 | 1.044 | 92.8 | 5.67 | 4.231 vs 3.538 |
| abertura|pos|k1|D2 | 5.883 | 10/14 | -1.039 | 1.31 | 43.8 | 713 | 1.044 | 103.9 | 5.63 | 4.310 vs 3.538 |
| abertura|pos|k1|D0 | 5.877 | 9/14 | -950 | 1.31 | 44.2 | 705 | 1.044 | 95.1 | 5.63 | 4.304 vs 3.538 |
| abertura|pos|k0.5|D5 | 5.824 | 10/14 | -987 | 1.3 | 42.0 | 738 | 1.044 | 98.7 | 5.58 | 4.211 vs 3.538 |
| abertura|pos|k2|D5 | 5.800 | 10/14 | -987 | 1.29 | 41.5 | 743 | 1.044 | 98.7 | 5.56 | 4.207 vs 3.038 |
| abertura|pos|k0|D5 | 5.781 | 10/14 | -987 | 1.3 | 41.7 | 737 | 1.044 | 98.7 | 5.54 | 4.183 vs 3.538 |
| abertura|pos|k1|D5 | 5.735 | 10/14 | -987 | 1.29 | 41.2 | 741 | 1.044 | 98.7 | 5.49 | 4.206 vs 3.038 |
| vwap|pos|k2|D0 | 4.661 | 9/14 | -987 | 1.18 | 27.6 | 928 | 1.706 | 98.7 | 2.73 | 3.023 vs 3.038 |
| vwap|pos|k2|D5 | 4.596 | 9/14 | -987 | 1.18 | 27.2 | 929 | 1.706 | 98.7 | 2.69 | 2.987 vs 3.538 |
| vwap|pos|k2|D2 | 4.596 | 9/14 | -987 | 1.18 | 27.2 | 929 | 1.706 | 98.7 | 2.69 | 2.987 vs 3.538 |
| media|pos|k2|D2 | 4.562 | 8/14 | -987 | 1.18 | 27.1 | 929 | 1.706 | 98.7 | 2.67 | 2.953 vs 3.538 |
| media|pos|k2|D0 | 4.562 | 8/14 | -987 | 1.18 | 27.1 | 929 | 1.706 | 98.7 | 2.67 | 2.953 vs 3.538 |
| media|pos|k2|D5 | 4.562 | 8/14 | -987 | 1.18 | 27.1 | 929 | 1.706 | 98.7 | 2.67 | 2.953 vs 3.538 |
| media|incl|N96|D5 | 4.451 | 9/14 | -987 | 1.21 | 30.5 | 794 | 1.372 | 98.7 | 3.24 | 2.780 vs 3.538 |
| vwap|incl|N96|D5 | 4.313 | 9/14 | -987 | 1.2 | 29.6 | 795 | 1.477 | 98.7 | 2.92 | 2.585 vs 3.538 |
| vwap|incl|N96|D2 | 4.244 | 9/14 | -994 | 1.2 | 30.0 | 773 | 1.477 | 99.4 | 2.87 | 2.419 vs 3.538 |
| vwap|pos|k1|D5|mesant | 4.207 | 8/14 | -905 | 1.18 | 26.9 | 862 | 1.662 | 90.5 | 2.53 | 2.675 vs 3.038 |
| media|pos|k1|D5|mesant | 4.161 | 8/14 | -905 | 1.17 | 26.6 | 864 | 1.718 | 90.5 | 2.42 | 2.710 vs 3.038 |
| vwap|incl|N12|D0 | 4.118 | 9/14 | -1.023 | 1.17 | 26.3 | 865 | 1.716 | 102.3 | 2.4 | 2.498 vs 3.038 |
| vwap|pos|k1|D0 | 4.081 | 8/14 | -987 | 1.16 | 24.6 | 922 | 1.662 | 98.7 | 2.46 | 2.477 vs 3.038 |
| media|pos|k1|D0 | 4.036 | 8/14 | -987 | 1.16 | 24.3 | 924 | 1.718 | 98.7 | 2.35 | 2.512 vs 3.038 |
| vwap|pos|k1|D2 | 4.016 | 8/14 | -987 | 1.16 | 24.3 | 923 | 1.662 | 98.7 | 2.42 | 2.477 vs 3.038 |
| media|incl|N48|D5 | 4.003 | 9/14 | -987 | 1.17 | 26.2 | 846 | 1.782 | 98.7 | 2.25 | 2.315 vs 3.538 |
| vwap|pos|k1|D5 | 3.988 | 8/14 | -987 | 1.16 | 24.1 | 924 | 1.662 | 98.7 | 2.4 | 2.449 vs 3.038 |
| vwap|incl|N12|D2 | 3.985 | 9/14 | -987 | 1.17 | 25.5 | 868 | 1.716 | 98.7 | 2.32 | 2.430 vs 3.038 |
| media|pos|k1|D2 | 3.971 | 8/14 | -987 | 1.15 | 24.0 | 925 | 1.718 | 98.7 | 2.31 | 2.512 vs 3.038 |
| media|pos|k1|D5 | 3.943 | 8/14 | -987 | 1.15 | 23.8 | 926 | 1.718 | 98.7 | 2.29 | 2.484 vs 3.038 |
| vwap|pos|k0.5|D0 | 3.939 | 8/14 | -931 | 1.16 | 24.0 | 914 | 1.728 | 93.1 | 2.28 | 2.387 vs 3.038 |
| vwap|incl|N12|D5 | 3.908 | 9/14 | -987 | 1.16 | 25.0 | 870 | 1.716 | 98.7 | 2.28 | 2.353 vs 3.038 |
| vwap|incl|N96|D0 | 3.902 | 9/14 | -930 | 1.19 | 28.0 | 765 | 1.477 | 93.0 | 2.64 | 2.077 vs 3.538 |
| media|incl|N12|D0 | 3.897 | 9/14 | -1.002 | 1.16 | 24.5 | 887 | 1.912 | 100.1 | 2.04 | 2.355 vs 3.538 |
| vwap|pos|k0|D5|mesant | 3.895 | 9/14 | -905 | 1.17 | 25.5 | 847 | 1.896 | 90.5 | 2.05 | 2.410 vs 3.038 |
| media|pos|k0|D5|mesant | 3.865 | 8/14 | -905 | 1.16 | 25.3 | 848 | 1.740 | 90.5 | 2.22 | 2.423 vs 3.538 |
| media|incl|N48|D2 | 3.838 | 9/14 | -996 | 1.17 | 25.4 | 839 | 1.782 | 99.6 | 2.15 | 2.109 vs 3.538 |
| media|incl|N48|D0 | 3.775 | 9/14 | -950 | 1.17 | 25.2 | 830 | 1.782 | 95.0 | 2.12 | 2.045 vs 3.538 |
| vwap|pos|k0|D0 | 3.754 | 8/14 | -917 | 1.15 | 23.3 | 903 | 1.896 | 91.7 | 1.98 | 2.196 vs 3.038 |
| vwap|pos|k0.5|D2 | 3.745 | 8/14 | -987 | 1.15 | 22.9 | 916 | 1.728 | 98.7 | 2.17 | 2.258 vs 3.038 |
| vwap|pos|k0.5|D5 | 3.717 | 8/14 | -987 | 1.15 | 22.8 | 917 | 1.728 | 98.7 | 2.15 | 2.230 vs 3.038 |
| media|pos|k0.5|D0 | 3.715 | 8/14 | -987 | 1.15 | 22.7 | 918 | 1.784 | 98.7 | 2.08 | 2.120 vs 3.038 |
| media|incl|N96|D2 | 3.709 | 8/14 | -1.057 | 1.18 | 26.5 | 774 | 1.372 | 105.7 | 2.7 | 1.969 vs 3.538 |
| vwap|pos|k0|D2 | 3.704 | 9/14 | -987 | 1.15 | 22.9 | 908 | 1.896 | 98.7 | 1.95 | 2.212 vs 3.038 |
| vwap|pos|k0|D5 | 3.676 | 9/14 | -987 | 1.15 | 22.7 | 909 | 1.896 | 98.7 | 1.94 | 2.184 vs 3.038 |
| media|pos|k0|D2 | 3.675 | 8/14 | -987 | 1.15 | 22.7 | 909 | 1.740 | 98.7 | 2.11 | 2.232 vs 3.538 |
| media|pos|k0.5|D2 | 3.650 | 8/14 | -987 | 1.14 | 22.4 | 919 | 1.784 | 98.7 | 2.05 | 2.120 vs 3.038 |
| media|pos|k0|D5 | 3.647 | 8/14 | -987 | 1.14 | 22.5 | 910 | 1.740 | 98.7 | 2.1 | 2.204 vs 3.538 |
| media|pos|k0|D0 | 3.637 | 8/14 | -1.005 | 1.14 | 22.6 | 906 | 1.740 | 100.5 | 2.09 | 2.142 vs 3.038 |
| media|incl|N12|D2 | 3.636 | 9/14 | -1.002 | 1.15 | 23.0 | 888 | 1.912 | 100.1 | 1.9 | 2.093 vs 3.538 |
| media|pos|k0.5|D5 | 3.622 | 8/14 | -987 | 1.14 | 22.2 | 920 | 1.784 | 98.7 | 2.03 | 2.092 vs 3.038 |
| media|incl|N12|D5 | 3.544 | 9/14 | -1.002 | 1.14 | 22.4 | 891 | 1.912 | 100.1 | 1.85 | 2.001 vs 3.538 |
| vwap|incl|N48|D0 | 3.458 | 8/14 | -997 | 1.15 | 23.2 | 837 | 1.772 | 99.7 | 1.95 | 1.944 vs 3.538 |
| vwap|incl|N48|D2 | 3.417 | 8/14 | -948 | 1.15 | 22.8 | 843 | 1.772 | 95.9 | 1.93 | 1.903 vs 3.538 |
| media|incl|N96|D0 | 3.282 | 8/14 | -962 | 1.16 | 23.9 | 767 | 1.372 | 96.2 | 2.39 | 1.542 vs 3.538 |
| vwap|incl|N48|D5 | 3.258 | 8/14 | -987 | 1.14 | 21.6 | 852 | 1.772 | 98.7 | 1.84 | 1.786 vs 3.538 |
| ORACULO | 6.725 | 10/14 | -905 | 1.38 | 53.4 | 661 | 1.044 | 90.5 | 6.44 | 4.886 vs 3.538 |

LOWO: remove de cada série (variante e baseline separadamente) a sua janela de maior ganho e compara o líquido restante.

- Âncora `media`: 23 variantes, líquido min/mediana/max = 3.282 / 3.838 / 4.562 (baseline 4.969); superam o baseline: 0/23.
- Âncora `vwap`: 23 variantes, líquido min/mediana/max = 3.258 / 3.939 / 4.661 (baseline 4.969); superam o baseline: 0/23.
- Âncora `abertura`: 14 variantes, líquido min/mediana/max = 5.735 / 5.936 / 6.661 (baseline 4.969); superam o baseline: 14/14.

## Mês a mês — baseline vs candidatas (líquido R$ por janela)

| janela | baseline | abertura|pos|k0|D0 | abertura|pos|k0.5|D2 |
|---|---|---|---|
| 2026-01 WING26 07-30 | 1.431 | 1.684 | 1.700 |
| 2026-02 WING26 01-18 | 417 | 380 | 318 |
| 2026-02 WINJ26 24-27 | -420 | -272 | -272 |
| 2026-03 WINJ26 01-31 | 34 | -134 | 35 |
| 2026-04 WINJ26 01-15 | -987 | -285 | -907 |
| 2026-04 WINM26 22-30 | 1.359 | 1.399 | 1.399 |
| 2026-05 WINM26 01-29 | 490 | 524 | 524 |
| 2026-06 WINM26 01-17 | -645 | -662 | -662 |
| 2026-06 WINQ26 23-30 | 162 | 147 | 147 |
| 2026-07 WINQ26 01-31 | 1.931 | 1.488 | 1.465 |
| 2026-08 WINQ26 01-12 | 622 | 607 | 622 |
| 2026-08 WINV26 18-31 | 694 | 589 | 626 |
| 2026-09 WINV26 01-30 | 151 | 1.382 | 1.382 |
| 2026-10 WINV26 01-01 | -270 | -270 | -270 |
| **total** | **4.969** | **6.578** | **6.106** |

## Oráculo (teto, nunca candidata)
Líquido 6.725, janelas+ 10/14, PF 1.38, pior janela -905, maior DD 1.044.

## LOWO correto (remove a janela de maior ganho sobre o baseline, em ambos)
```
LOWO correto: remove a janela de maior GANHO sobre o baseline, em ambos
abertura|pos|k0|D0           total    +1609 sobre base; sem jan 2026-09:     +379; janelas melhores que base: 6/14
abertura|pos|k0|D5           total     +812 sobre base; sem jan 2026-09:     -418; janelas melhores que base: 6/14
abertura|pos|k0|D2           total     +947 sobre base; sem jan 2026-09:     -284; janelas melhores que base: 7/14
abertura|pos|k0.5|D0         total     +989 sobre base; sem jan 2026-09:     -242; janelas melhores que base: 6/14
abertura|pos|k0.5|D2         total    +1137 sobre base; sem jan 2026-09:      -93; janelas melhores que base: 7/14
abertura|pos|k0.5|D5         total     +856 sobre base; sem jan 2026-09:     -375; janelas melhores que base: 6/14
abertura|pos|k1|D0           total     +908 sobre base; sem jan 2026-09:     -322; janelas melhores que base: 6/14
abertura|pos|k1|D2           total     +915 sobre base; sem jan 2026-09:     -316; janelas melhores que base: 6/14
abertura|pos|k2|D0           total    +1054 sobre base; sem jan 2026-09:     -176; janelas melhores que base: 6/14
abertura|pos|k1|D5           total     +766 sobre base; sem jan 2026-09:     -464; janelas melhores que base: 6/14
abertura|pos|k2|D2           total    +1151 sobre base; sem jan 2026-09:      -80; janelas melhores que base: 7/14
abertura|pos|k2|D5           total     +832 sobre base; sem jan 2026-09:     -399; janelas melhores que base: 6/14
abertura|pos|k0|D5|mesant    total    +1693 sobre base; sem jan 2026-09:     +462; janelas melhores que base: 7/14
abertura|pos|k1|D5|mesant    total    +1647 sobre base; sem jan 2026-09:     +416; janelas melhores que base: 7/14
```

## Veredito: INCONCLUSIVO (âncora de abertura) / NÃO (média acumulada e VWAP)
- Média acumulada e VWAP ancoradas no mês: 0/46 variantes superam o baseline (líquido 3.258–4.661 vs 4.969). Reduzem trades sem separar bons de maus. NÃO.
- Preço vs abertura do mês: 14/14 variantes superam o baseline (5.735–6.661; platô nos 4 níveis de k e 3 de D), PF 1,29–1,40, trades 988->~700. Mas o ganho vem de UMA janela (set/26 WINV26: 151 -> 1.382). Sem ela, só 2 das 14 variantes seguem acima do baseline (k0|D0: +379; mesant: +416/+462); as outras 12 ficam abaixo. Só 6-7 das 14 janelas melhoram. Abr/1-15 melhora só com k0|D0 e mesant.
- O oráculo (6.725) mal supera as melhores células: o "teto" já está praticamente atingido por uma regra sem look-ahead, o que é bom sinal mas com n=14 janelas e 1 janela decisiva é frágil. Pior janela e DD (R$1.044 vs 1.750) melhoram nas candidatas, mas o DD% sobre R$1.000 segue ~74-99%.
- Candidata a validar (não a adotar): abertura|k0|D5|mesant ou k0|D0 — exige confirmação em outros anos/contratos (2025) antes de qualquer decisão. Sem plateau de 'sem a janela de set' nas demais.
