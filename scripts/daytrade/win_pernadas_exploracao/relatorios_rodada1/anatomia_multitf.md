# Anatomia multi-tempo das pernadas do WIN, setembro/2026 (exploratório)

Escopo: WINV26 M1, 21 pregões de 01 a 30/09/2026. Zigzag 750 pts sobre o caminho dentro da vela (alta: mín→máx; baixa: máx→mín). Correção = recuo >= 5 pts seguido de novo extremo. Os totais batem com os números já conhecidos (M5 190 pernadas, M15 172, H1 121). Tudo aqui é pista (n pequeno, um mês). Script: a.py. Saída crua abaixo; leitura no final.

## Saída crua
```
5min pernadas 190 confirmadas 169 por pregao 9.05 corr/pernada 4.45
  tamanho n=190 med=1292.50 media=1505.53 dp=785.47 p25=956.25 p75=1761.25
  duracao min n=190 med=35.00 media=55.68 dp=60.39 p25=10.00 p75=80.00
15min pernadas 172 confirmadas 151 por pregao 8.19 corr/pernada 2.0
  tamanho n=172 med=1320.00 media=1554.01 dp=824.32 p25=958.75 p75=1806.25
  duracao min n=172 med=30.00 media=60.96 dp=62.15 p25=15.00 p75=90.00
1h pernadas 121 confirmadas 100 por pregao 5.76 corr/pernada 0.6
  tamanho n=121 med=1535.00 media=1780.87 dp=988.23 p25=1095.00 p75=2160.00
  duracao min n=121 med=60.00 media=83.31 dp=71.69 p25=60.00 p75=120.00

== Decomposicao H1 -> 15min
  n pernadas H1 conf 100
  subpernadas total n=100 med=3.00 media=3.35 dp=1.87 p25=2.00 p75=5.00
  mesma dir n=100 med=2.00 media=1.82 dp=0.91 p25=1.00 p75=2.25
  contra n=100 med=2.00 media=1.53 dp=1.06 p25=1.00 p75=2.00
  soma pts mesma dir / tamanho H1 n=100 med=1.36 media=1.63 dp=0.88 p25=1.00 p75=1.86
  soma pts contra / tamanho H1 n=100 med=1.14 media=1.34 dp=1.11 p25=0.49 p75=1.90
  corr(size H1, n subpernadas) 0.26
  pernadas H1 sem nenhuma subpernada contra: 19 de 100

== Decomposicao H1 -> 5min
  n pernadas H1 conf 100
  subpernadas total n=100 med=3.00 media=3.65 dp=2.06 p25=2.00 p75=5.00
  mesma dir n=100 med=2.00 media=1.97 dp=1.03 p25=1.00 p75=3.00
  contra n=100 med=2.00 media=1.68 dp=1.12 p25=1.00 p75=3.00
  soma pts mesma dir / tamanho H1 n=100 med=1.44 media=1.71 dp=0.93 p25=1.00 p75=2.07
  soma pts contra / tamanho H1 n=100 med=1.30 media=1.42 dp=1.14 p25=0.59 p75=2.00
  corr(size H1, n subpernadas) 0.32
  pernadas H1 sem nenhuma subpernada contra: 15 de 100

== Sequencia de correcoes 5min
  corr #1: n=162 dep med=208 %adv med=41.9 %size med=14.2 dur(ext->novo ext) med=5.0min
  corr #2: n=133 dep med=220 %adv med=33.0 %size med=14.6 dur(ext->novo ext) med=5.0min
  corr #3: n=108 dep med=255 %adv med=29.0 %size med=15.5 dur(ext->novo ext) med=5.0min
  corr #4: n=92 dep med=195 %adv med=18.8 %size med=11.6 dur(ext->novo ext) med=5.0min
  corr #5+: n=351 dep med=205 %adv med=12.9
  (conf, >=3 corr) primeira: n=88 dep med=198 %adv med=43.6 dur med=5.0
  (conf, >=3 corr) penultima: n=88 dep med=228 %adv med=16.2 dur med=5.0
  (conf, >=3 corr) ultima: n=88 dep med=280 %adv med=17.7 dur med=10.0
  spearman(j,%adv) -0.55  spearman(posicao%,%adv) -0.34
  pernadas sem correcao: 28 de 190
  corr/pernada conf 3.88  aberta 9.1

== Sequencia de correcoes 15min
  corr #1: n=118 dep med=295 %adv med=36.6 %size med=17.4 dur(ext->novo ext) med=15.0min
  corr #2: n=79 dep med=280 %adv med=26.6 %size med=14.4 dur(ext->novo ext) med=15.0min
  corr #3: n=55 dep med=345 %adv med=28.3 %size med=21.0 dur(ext->novo ext) med=15.0min
  corr #4: n=35 dep med=340 %adv med=24.6 %size med=19.4 dur(ext->novo ext) med=15.0min
  corr #5+: n=57 dep med=235 %adv med=11.9
  (conf, >=3 corr) primeira: n=37 dep med=290 %adv med=36.5 dur med=15.0
  (conf, >=3 corr) penultima: n=37 dep med=280 %adv med=24.7 dur med=15.0
  (conf, >=3 corr) ultima: n=37 dep med=390 %adv med=27.3 dur med=15.0
  spearman(j,%adv) -0.41  spearman(posicao%,%adv) -0.2
  pernadas sem correcao: 54 de 172
  corr/pernada conf 1.64  aberta 4.62

== Sequencia de correcoes 1h
  corr #1: n=47 dep med=410 %adv med=39.0 %size med=23.9 dur(ext->novo ext) med=60.0min
  corr #2: n=16 dep med=375 %adv med=25.9 %size med=18.3 dur(ext->novo ext) med=60.0min
  corr #3: n=6 dep med=268 %adv med=17.2 %size med=12.4 dur(ext->novo ext) med=60.0min
  (conf, >=3 corr) primeira: n=3 dep med=575 %adv med=32.1 dur med=60.0
  (conf, >=3 corr) penultima: n=3 dep med=400 %adv med=16.5 dur med=60.0
  (conf, >=3 corr) ultima: n=3 dep med=280 %adv med=11.1 dur med=60.0
  spearman(j,%adv) -0.47  spearman(posicao%,%adv) -0.16
  pernadas sem correcao: 74 de 121
  corr/pernada conf 0.4  aberta 1.57

== Correspondencia de fins (extremo, mesma direcao)
 fim 5min tem fim 15min em +-0min: 79/190 = 42%
 fim 5min tem fim 1h em +-0min: 22/190 = 12%
 fim 15min tem fim 1h em +-0min: 35/172 = 20%
 fim 15min tem fim 5min em +-0min: 79/172 = 46%
 fim 1h tem fim 15min em +-0min: 35/121 = 29%
 fim 1h tem fim 5min em +-0min: 22/121 = 18%
 fim 5min tem fim 15min em +-15min: 177/190 = 93%
 fim 5min tem fim 1h em +-15min: 49/190 = 26%
 fim 15min tem fim 1h em +-15min: 76/172 = 44%
 fim 15min tem fim 5min em +-15min: 171/172 = 99%
 fim 1h tem fim 15min em +-15min: 73/121 = 60%
 fim 1h tem fim 5min em +-15min: 47/121 = 39%
 fim 5min tem fim 15min em +-30min: 181/190 = 95%
 fim 5min tem fim 1h em +-30min: 102/190 = 54%
 fim 15min tem fim 1h em +-30min: 114/172 = 66%
 fim 15min tem fim 5min em +-30min: 172/172 = 100%
 fim 1h tem fim 15min em +-30min: 102/121 = 84%
 fim 1h tem fim 5min em +-30min: 89/121 = 74%
 fim 5min tem fim 15min em +-60min: 185/190 = 97%
 fim 5min tem fim 1h em +-60min: 159/190 = 84%
 fim 15min tem fim 1h em +-60min: 150/172 = 87%
 fim 15min tem fim 5min em +-60min: 172/172 = 100%
 fim 1h tem fim 15min em +-60min: 120/121 = 99%
 fim 1h tem fim 5min em +-60min: 120/121 = 99%

== Pernadas M5 por quartil de tamanho: coincide com fim M15 (+-15min) / H1 (+-30min)
                    n   m15    h1    nc   dur
b                                            
(749.999, 956.25]  48  0.92  0.40  2.06  15.0
(956.25, 1292.5]   47  0.87  0.45  3.70  25.0
(1292.5, 1761.25]  47  0.94  0.60  3.64  30.0
(1761.25, 6265.0]  48  1.00  0.71  8.38  75.0
  corr(size,m15) 0.14

== Por pregao
           day  5min  15min  1h  m5/h1  m15/h1
0   2026-09-01     6      6   6   1.00    1.00
1   2026-09-02     9      9   5   1.80    1.80
2   2026-09-03     9      7   3   3.00    2.33
3   2026-09-04     9     10   6   1.50    1.67
4   2026-09-08    11      9   5   2.20    1.80
5   2026-09-09     6      6   8   0.75    0.75
6   2026-09-10    13     10   6   2.17    1.67
7   2026-09-11    11     11   7   1.57    1.57
8   2026-09-14    11     11   7   1.57    1.57
9   2026-09-15    12     10   8   1.50    1.25
10  2026-09-16    12     10   6   2.00    1.67
11  2026-09-17     6      6   3   2.00    2.00
12  2026-09-18     7      7   4   1.75    1.75
13  2026-09-21    10      8   6   1.67    1.33
14  2026-09-22     5      4   4   1.25    1.00
15  2026-09-23    11      9   7   1.57    1.29
16  2026-09-24     9      9   6   1.50    1.50
17  2026-09-25     5      5   5   1.00    1.00
18  2026-09-28    11     10   6   1.83    1.67
19  2026-09-29     6      6   4   1.50    1.50
20  2026-09-30    11      9   9   1.22    1.00
razao m5/h1 med 1.57 dp 0.49 | m15/h1 1.57 0.39
5min tamanho/limiar med 1.72 media 2.01
15min tamanho/limiar med 1.76 media 2.07
1h tamanho/limiar med 2.05 media 2.37

== Hora do fim das pernadas H1 (contagem por hora)
9     12
10    21
11    17
12     9
13    14
14    15
15     8
16     8
17     9
18     8

== Duracao H1 por n correcoes e tamanho H1 por n correcoes
     n  size_med  dur_med
nc                       
0   71    1535.0     60.0
1   21    2125.0    120.0
2    5    2360.0    120.0
3    3    4155.0    240.0```

## Leitura
1. Pernada de H1 (confirmada, n=100) contém mediana 3 subpernadas de M15 (média 3,35, dp 1,87): 2 a favor, 2 contra. A soma dos pontos das subpernadas a favor é 1,36x o tamanho da pernada H1 e a das contra 1,14x (M5: 1,44x e 1,30x). A pernada de H1 é o saldo líquido de um vai-e-vem do M15 de amplitude parecida; só 19% (M15) e 15% (M5) das pernadas H1 não têm nenhuma subpernada contrária de 750.
2. Fins de pernada: de 121 fins H1, 29% coincidem exatamente com um fim M15 (mesma vela de extremo), 18% com fim M5. Fim M5 vira fim M15 exato em 42%, fim H1 em 12%. Com tolerância de 30 min: M5 em M15 95%, M15 em H1 66%, H1 em M5 74%. Tolerâncias >= 30 min são quase triviais para H1 (vela de 60 min). Atenção: a coincidência exata só tem sentido por vela.
3. Quanto maior a pernada M5, mais ela "sobe de nível": coincidência com fim H1 (+-30 min) 40% / 45% / 60% / 71% nos quartis de tamanho (n=47-48 cada). Para M15 não discrimina (87-100% em todos, vela M15 é larga).
4. Correções dentro da pernada: em % do tamanho da pernada, 1ª..4ª correção M5 = 14,2 / 14,6 / 15,5 / 11,6% (mediana, n=162/133/108/92). Em % do avanço feito cai (41,9 / 33,0 / 29,0 / 18,8; Spearman j x %avanço = -0,55), mas isso é em grande parte artefato do denominador (o avanço cresce). Em pontos absolutos a profundidade é plana (208/220/255/195 pts). Mesma coisa no M15 (295/280/345/340) e no H1 (410/375/268, n=47/16/6).
5. Última correção antes do fim (M5, pernadas confirmadas com >=3 correções, n=88): mediana 280 pts vs 228 na penúltima e 198 na primeira; no M15 (n=37) 390 vs 280 vs 290. Pista fraca de correção final maior, mas a "última" é selecionada em retrospecto (a que precede o extremo final) e pernadas longas têm mais correções.
6. Pernadas H1 sem correção: 74/121 (61%). Com 0, 1, 2 e 3+ correções: tamanho mediano 1.535 / 2.125 / 2.360 / 4.155 pts e duração 60 / 120 / 120 / 240 min (n=71/21/5/3). A correção em H1 é rara e marca pernada mais longa. As pernadas abertas (última do dia) têm muito mais correções (M5 9,1 vs 3,9 nas confirmadas): pernada aberta é um "fim de dia sem 750 de recuo".
7. Razões entre níveis: nº de pernadas M5/H1 por pregão mediana 1,57 (dp 0,49; faixa 0,75 a 3,0), M15/H1 1,57 (dp 0,39). Tamanho mediano / limiar: M5 1,72x, M15 1,76x, H1 2,05x; ou seja, as pernadas de 750 em M5 e M15 têm tamanho quase idêntico (1.292 vs 1.320), só o H1 é maior (1.535). Razão não é estável por pregão (pregões de 6 pernadas M5 e de 13).
8. Fins de pernada H1 concentrados em 10h-11h (21 e 17 de 121) e 14h (15); 15h-18h têm 8-9 cada.

## Artefatos possíveis
- Ordem dentro da vela (alta: mín→máx) cria ou apaga recuos de 750 em velas grandes (H1 média 854-1.062 pts: uma vela H1 sozinha pode conter 750 de recuo que o modelo "esconde" ou fabrica). Isso explica parte do alto número de pernadas H1 sem subpernada contrária e da pouca correção no H1.
- Limiar de 750 fixo: M5 e M15 têm quase o mesmo tamanho de pernada (1,7x) porque o limiar domina; a "diferença entre níveis" é em boa parte o filtro, não o mercado.
- Duração de correção é quantizada pela vela (5/15/60 min), não interprete.
- %avanço da 1ª correção é inflado pelo denominador pequeno.
- Pernada aberta e estimativas com n<10 (H1 com 3+ correções n=6) não sustentam nada.
