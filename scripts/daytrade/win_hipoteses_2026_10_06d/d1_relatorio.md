# D1 - Familia STOP sobre WinCincoMedias v2.01 (so 2026)

Baseline reproduzido exatamente pela copia desligada: +R$7.805,20, 13/14, pior -117,00, PF 1,68, 248 trades, DD 781,50, sem setembro 7.370,70.
Stop a mercado (nivel -/+ 1 tick; gap -> abertura), niveis so com barras fechadas, stop na barra da entrada conta, stop vence saida favoravel na mesma barra. ATR(14) M30 (Wilder) da ultima barra fechada antes do preenchimento.
Codigo: `d1_stop.py` (simula estendida; `stop=dict(init, be, trail, trailn, aperta=(N,k), widen=(N,ka,kb))`).

## 1. Diagnostico MAE/MFE (248 trades do baseline; MAE/MFE intrabarra, do preenchimento ate a barra da saida)

| grupo | n | MAE pts p50/75/90 | MAE ATR p50/75/90 | MFE pts p50/75/90 | MFE ATR p50/75/90 | ATR medio (pts) | resultado medio (pts) |
|---|---|---|---|---|---|---|---|
| todos | 248 | 308.0 / 574.8 / 848.0 | 0.5 / 0.8 / 1.4 | 445.0 / 1123.0 / 1798.0 | 0.7 / 1.6 / 3.0 | 678 | 160 |
| vencedores | 100 | 110.5 / 230.8 / 408.9 | 0.2 / 0.3 / 0.6 | 1206.5 / 1796.0 / 3093.4 | 1.7 / 3.0 / 4.2 | 683 | 964 |
| perdedores | 148 | 427.0 / 721.8 / 1113.0 | 0.7 / 1.1 / 1.5 | 226.0 / 442.5 / 761.5 | 0.3 / 0.6 / 1.2 | 675 | -384 |
| a favor do mes | 220 | 319.5 / 593.2 / 856.0 | 0.5 / 0.8 / 1.4 | 457.5 / 1143.5 / 1867.1 | 0.7 / 1.7 / 3.2 | 687 | 168 |
| neutros (regime 0) | 28 | 273.5 / 397.8 / 561.5 | 0.4 / 0.6 / 1.0 | 364.5 / 822.5 / 1445.3 | 0.6 / 1.2 / 2.4 | 609 | 99 |
| venc. a favor | 88 | 110.5 / 228.0 / 377.3 | 0.2 / 0.3 / 0.5 | 1273.0 / 1889.8 / 3098.2 | 1.7 / 3.2 / 4.6 | 693 | 1019 |
| venc. neutros | 12 | 164.5 / 294.8 / 475.2 | 0.3 / 0.4 / 0.6 | 1046.5 / 1427.8 / 1776.5 | 1.5 / 2.4 / 2.5 | 614 | 568 |
| perd. a favor | 132 | 454.0 / 757.2 / 1155.0 | 0.7 / 1.1 / 1.6 | 226.0 / 453.5 / 796.9 | 0.3 / 0.6 / 1.3 | 683 | -400 |
| perd. neutros | 16 | 328.5 / 450.5 / 671.5 | 0.5 / 0.7 / 1.1 | 224.5 / 347.8 / 491.5 | 0.4 / 0.5 / 0.8 | 605 | -252 |

Acerto geral 40.3% ; a favor do mes 220 trades (acerto 40.0%, pnl R$ 7263); neutros 28 (acerto 42.9%, pnl R$ 542). Barras medias de duracao: venc nan.

**(a) Vencedores cortados por stop inicial k x ATR** (MAE >= k ATR; ignora que o stop, ao disparar, muda a sequencia):

| k | vencedores cortados | de | % | pnl desses vencedores (R$) | perdedores com MAE >= k ATR (ja' estariam no stop) |
|---|---|---|---|---|---|
| 0.5 | 12 | 100 | 12% | 3489 | 95 de 148 |
| 1 | 4 | 100 | 4% | 1003 | 43 de 148 |
| 1.5 | 0 | 100 | 0% | 0 | 15 de 148 |
| 2 | 0 | 100 | 0% | 0 | 7 de 148 |
| 3 | 0 | 100 | 0% | 0 | 1 de 148 |

**(b) MFE devolvido pelos vencedores** (MFE - resultado): mediana 463 pts (0.71 ATR), p75 811, p90 1139; MFE medio 1516 pts vs resultado medio 964 pts -> devolvem 36% do MFE. Perdedores: MFE mediano 226 pts.

**(c) Perdedores que estiveram no lucro** (MFE > 0,5 ATR): 52 de 148 (35%), pnl total deles R$ -4214; com MFE > 1 ATR: 20.


Duracao (barras M30) mediana: vencedores n/d.

## 2. Variantes (62 configuracoes unicas; 62 rodadas incl. duplicatas) - ordenadas por liquido

| variante | liquido R$ | janelas+ | pior | PF | acerto% | trades | DD | sem set | meses melhor/pior vs base |
|---|---|---|---|---|---|---|---|---|---|
| BASELINE | 7805.20 | 13/14 | -117.00 | 1.68 | 40.3 | 248 | 781.50 | 7370.70 | 0/0 |
| aperta(2,1)+BE 1 | 8446.74 | 13/14 | -117.00 | 1.79 | 39.3 | 252 | 761.50 | 7592.21 | 4/4 |
| aperta N=2 k=0.75 | 8436.51 | 13/14 | -117.00 | 1.78 | 40.3 | 248 | 781.50 | 7839.01 | 5/2 |
| aperta N=2 k=1 | 8377.14 | 13/14 | -117.00 | 1.77 | 40.3 | 248 | 781.50 | 7785.61 | 4/1 |
| aperta N=2 k=1.0 | 8377.14 | 13/14 | -117.00 | 1.77 | 40.3 | 248 | 781.50 | 7785.61 | 4/1 |
| aperta(2,1)+trail 3 | 8377.14 | 13/14 | -117.00 | 1.77 | 40.3 | 248 | 781.50 | 7785.61 | 4/1 |
| aperta(2,1)+init1.5+BE1 | 8367.17 | 13/14 | -117.00 | 1.78 | 39.3 | 252 | 783.21 | 7521.34 | 4/5 |
| aperta(2,1)+init 1.5 | 8333.00 | 13/14 | -117.00 | 1.76 | 40.3 | 248 | 803.21 | 7757.48 | 6/2 |
| aperta(2,1)+init1.5+trail3 | 8333.00 | 13/14 | -117.00 | 1.76 | 40.3 | 248 | 803.21 | 7757.48 | 6/2 |
| aperta(2,1)+BE 1.5 | 8286.44 | 13/14 | -117.00 | 1.76 | 39.8 | 249 | 761.50 | 7694.91 | 5/2 |
| aperta N=2 k=1.25 | 8255.26 | 13/14 | -117.00 | 1.75 | 40.3 | 248 | 781.50 | 7705.72 | 3/1 |
| aperta N=1 k=1.5 | 8198.52 | 13/14 | -117.00 | 1.74 | 40.3 | 248 | 781.50 | 7690.97 | 4/1 |
| aperta N=2 k=1.5 | 8138.15 | 13/14 | -117.00 | 1.73 | 40.3 | 248 | 781.50 | 7630.60 | 3/0 |
| init1.5+BE1 | 8128.17 | 12/14 | -117.00 | 1.74 | 39.3 | 252 | 783.21 | 7366.33 | 3/6 |
| init k=1.5 | 8093.99 | 12/14 | -117.00 | 1.73 | 40.3 | 248 | 803.21 | 7602.46 | 5/3 |
| aperta(2,1.5)+init1.5 | 8093.99 | 12/14 | -117.00 | 1.73 | 40.3 | 248 | 803.21 | 7602.46 | 5/3 |
| aperta(2,1)+init 2 | 8076.20 | 13/14 | -117.00 | 1.72 | 40.3 | 248 | 781.50 | 7484.67 | 2/3 |
| aperta(2,1)+trail 1.5 | 8071.73 | 11/14 | -117.00 | 1.73 | 39.9 | 253 | 744.00 | 7248.90 | 6/5 |
| aperta N=2 k=0.5 | 8058.73 | 13/14 | -117.00 | 1.72 | 39.7 | 252 | 781.50 | 7461.23 | 6/4 |
| aperta N=1 k=1.25 | 8034.40 | 12/14 | -153.55 | 1.72 | 40.2 | 249 | 760.90 | 7484.86 | 5/3 |
| init1.5+trail1.5 | 7915.16 | 11/14 | -117.00 | 1.71 | 39.9 | 253 | 765.71 | 7176.31 | 5/6 |
| aperta N=2 k=2.0 | 7893.09 | 13/14 | -117.00 | 1.7 | 40.3 | 248 | 781.50 | 7469.53 | 1/1 |
| BE m=1 | 7874.80 | 13/14 | -117.00 | 1.7 | 39.3 | 252 | 761.50 | 7177.30 | 2/4 |
| aperta N=3 k=0.75 | 7852.39 | 13/14 | -117.00 | 1.69 | 40.3 | 248 | 781.50 | 7417.89 | 1/1 |
| trail k=1.5 | 7851.60 | 11/14 | -117.00 | 1.7 | 39.9 | 253 | 744.00 | 7112.75 | 6/5 |
| trail k=1 | 7847.92 | 12/14 | -160.17 | 1.7 | 40.4 | 265 | 622.15 | 6838.25 | 7/7 |
| aperta N=1 k=2.0 | 7846.89 | 13/14 | -117.00 | 1.69 | 40.3 | 248 | 781.50 | 7423.33 | 1/2 |
| aperta N=4 k=0.5 | 7825.37 | 13/14 | -117.00 | 1.69 | 40.3 | 248 | 781.50 | 7390.87 | 1/0 |
| trail k=3 | 7818.84 | 13/14 | -117.00 | 1.68 | 40.3 | 248 | 781.50 | 7384.34 | 1/0 |
| aperta N=1 k=1.0 | 7809.50 | 12/14 | -112.24 | 1.7 | 39.4 | 251 | 721.42 | 7217.97 | 6/5 |
| aperta N=1 k=1 | 7809.50 | 12/14 | -112.24 | 1.7 | 39.4 | 251 | 721.42 | 7217.97 | 6/5 |
| BE m=2 | 7805.20 | 13/14 | -117.00 | 1.68 | 40.3 | 248 | 781.50 | 7370.70 | 0/0 |
| aperta N=4 k=1 | 7805.20 | 13/14 | -117.00 | 1.68 | 40.3 | 248 | 781.50 | 7370.70 | 0/0 |
| aperta N=4 k=1.5 | 7805.20 | 13/14 | -117.00 | 1.68 | 40.3 | 248 | 781.50 | 7370.70 | 0/0 |
| aperta N=8 k=0.5 | 7805.20 | 13/14 | -117.00 | 1.68 | 40.3 | 248 | 781.50 | 7370.70 | 0/0 |
| aperta N=8 k=1 | 7805.20 | 13/14 | -117.00 | 1.68 | 40.3 | 248 | 781.50 | 7370.70 | 0/0 |
| aperta N=8 k=1.5 | 7805.20 | 13/14 | -117.00 | 1.68 | 40.3 | 248 | 781.50 | 7370.70 | 0/0 |
| aperta N=3 k=1.25 | 7805.20 | 13/14 | -117.00 | 1.68 | 40.3 | 248 | 781.50 | 7370.70 | 0/0 |
| aperta N=3 k=2.0 | 7805.20 | 13/14 | -117.00 | 1.68 | 40.3 | 248 | 781.50 | 7370.70 | 0/0 |
| aperta N=3 k=1.5 | 7805.20 | 13/14 | -117.00 | 1.68 | 40.3 | 248 | 781.50 | 7370.70 | 0/0 |
| aperta N=3 k=1.0 | 7799.32 | 13/14 | -117.00 | 1.68 | 40.3 | 248 | 781.50 | 7364.82 | 0/1 |
| aperta N=3 k=1 | 7799.32 | 13/14 | -117.00 | 1.68 | 40.3 | 248 | 781.50 | 7364.82 | 0/1 |
| init k=3 | 7791.24 | 13/14 | -117.00 | 1.68 | 40.3 | 248 | 781.50 | 7356.74 | 0/1 |
| aperta N=3 k=0.5 | 7785.41 | 13/14 | -117.00 | 1.68 | 40.2 | 249 | 781.50 | 7350.91 | 2/3 |
| trailN N=5 | 7726.80 | 13/14 | -133.00 | 1.67 | 40.3 | 248 | 792.50 | 7292.30 | 1/5 |
| BE m=1.5 | 7714.50 | 13/14 | -117.00 | 1.67 | 39.8 | 249 | 761.50 | 7280.00 | 1/1 |
| init k=2 | 7592.15 | 12/14 | -197.28 | 1.65 | 40.3 | 248 | 781.50 | 7168.59 | 1/4 |
| aperta N=1 k=0.5 | 7416.75 | 11/14 | -74.61 | 1.66 | 37.1 | 264 | 642.46 | 6758.25 | 6/7 |
| trailN N=3 | 7389.60 | 11/14 | -318.20 | 1.63 | 38.9 | 252 | 762.50 | 6680.10 | 3/9 |
| aperta N=1 k=0.75 | 7341.38 | 12/14 | -70.93 | 1.64 | 38.1 | 257 | 681.94 | 6707.86 | 6/6 |
| afasta N=2 ka=1 kb=3 | 7239.60 | 11/14 | -112.24 | 1.6 | 38.8 | 258 | 782.97 | 6886.08 | 4/9 |
| afasta N=2 ka=1 kb=2 | 7239.60 | 11/14 | -112.24 | 1.6 | 38.8 | 258 | 782.97 | 6886.08 | 4/9 |
| trail k=2 | 7218.59 | 12/14 | -146.28 | 1.61 | 39.7 | 252 | 781.50 | 6753.40 | 2/6 |
| trailN N=2 | 7149.60 | 12/14 | -372.60 | 1.62 | 38.0 | 266 | 791.00 | 6366.60 | 5/9 |
| init k=1 | 6941.08 | 11/14 | -112.24 | 1.57 | 38.2 | 259 | 782.97 | 6518.43 | 4/10 |
| afasta N=4 ka=1 kb=2 | 6941.08 | 11/14 | -112.24 | 1.57 | 38.2 | 259 | 782.97 | 6518.43 | 4/10 |
| afasta N=4 ka=1 kb=3 | 6941.08 | 11/14 | -112.24 | 1.57 | 38.2 | 259 | 782.97 | 6518.43 | 4/10 |
| BE m=0.5 | 6893.70 | 11/14 | -162.00 | 1.62 | 34.6 | 263 | 709.50 | 6136.20 | 3/9 |
| init k=0.5 | 6683.22 | 9/14 | -433.59 | 1.58 | 32.2 | 298 | 691.19 | 6311.26 | 6/8 |
| afasta N=4 ka=0.5 kb=3 | 6683.22 | 9/14 | -433.59 | 1.58 | 32.2 | 298 | 691.19 | 6311.26 | 6/8 |
| afasta N=4 ka=0.5 kb=2 | 6683.22 | 9/14 | -433.59 | 1.58 | 32.2 | 298 | 691.19 | 6311.26 | 6/8 |
| afasta N=2 ka=0.5 kb=3 | 6580.46 | 9/14 | -365.22 | 1.57 | 32.2 | 298 | 622.82 | 6354.07 | 6/8 |
| afasta N=2 ka=0.5 kb=2 | 6580.46 | 9/14 | -365.22 | 1.57 | 32.2 | 298 | 622.82 | 6354.07 | 6/8 |

## 3. Mes a mes (liquido R$)

| janela | base | aperta N=2 k=1 | aperta(2,1)+BE 1 | aperta N=2 k=0.75 | init k=1.5 |
|---|---|---|---|---|---|
| 2026-01 07 | 3056.40 | 3056.40 | 3056.40 | 3045.05 | 3043.52 |
| 2026-02 01 | 816.00 | 816.00 | 816.00 | 780.24 | 816.00 |
| 2026-02 24 | 11.00 | 11.00 | 11.00 | 11.00 | 11.00 |
| 2026-03 01 | 42.00 | 253.85 | 253.85 | 307.44 | -5.38 |
| 2026-04 01 | 646.30 | 646.30 | 646.30 | 646.30 | 646.30 |
| 2026-04 22 | 989.00 | 989.00 | 926.10 | 989.00 | 989.00 |
| 2026-05 01 | 995.90 | 990.02 | 921.92 | 1010.12 | 1038.48 |
| 2026-06 01 | 350.00 | 350.00 | 239.30 | 350.00 | 365.56 |
| 2026-06 23 | 69.40 | 69.40 | 69.40 | 69.40 | 69.40 |
| 2026-07 01 | 291.70 | 311.84 | 311.84 | 338.66 | 417.92 |
| 2026-08 01 | 37.00 | 225.80 | 366.60 | 225.80 | 192.22 |
| 2026-08 18 | 183.00 | 183.00 | 90.50 | 183.00 | 135.44 |
| 2026-09 01 | 434.50 | 591.53 | 854.53 | 597.50 | 491.53 |
| 2026-10 01 | -117.00 | -117.00 | -117.00 | -117.00 | -117.00 |
| TOTAL | 7805.20 | 8377.14 | 8446.74 | 8436.51 | 8093.99 |

## 4. Leitura

- Os vencedores quase nao andam contra: MAE mediano 0,2 ATR (p90 0,6). Os perdedores andam contra bem mais (mediana 0,7 ATR, p75 1,1). Um stop inicial fixo de 1,5 ATR nao corta nenhum vencedor mas so' pega 15 dos 148 perdedores (e a saida por EMA4/quebra ja' fecha a maioria antes); stops de 0,5-1 ATR cortam 4-12% dos vencedores, que valem R$1.003-3.489 -> o stop inicial apertado destroi mais do que protege (init k=0,5: -R$1.122; k=1: -R$864).
- Vencedores devolvem 36% do MFE (mediana 0,71 ATR) e 35% dos perdedores (52/148, -R$4.214) passaram de 0,5 ATR no lucro. Mas trailing e break-even NAO recuperam isso: trail k=1/1,5 ~ +R$45 (e k=2 perde), BE m=0,5 perde R$912, BE m=1 +R$70. Trailing corta tambem os vencedores que respiram; a saida EMA4 ja' e' um trailing natural.
- O unico efeito consistente e' o "apertar quando vai contra" com N=2: trade negativo depois de 2 barras M30 fechadas -> stop a 0,5-1,5 ATR da entrada (todos os k de 0,5 a 1,5 superam o baseline: +R$253 a +R$632; k=2 +R$88). Nao muda o numero de trades (quando o stop nao muda a sequencia) nem o DD. Mas o ganho vem de 3 meses (mar +212, ago +189, set +157) e o parametro N e fragil: N=1 oscila (de -R$464 a +R$393 conforme k), N=3 e N=4 inertes (0 a +R$47), N=8 nenhum efeito (trades curtos). Platô em k, nao em N.
- AFASTAR (stop apertado no inicio, largo depois) sempre piora (-R$565 a -R$1.225).
- trailing por minima/maxima de N barras (N=2,3,5) piora (-R$78 a -R$656); pior janela chega a -372.
- Combinacoes: aperta(2,1)+BE1 = +R$8.446,74 (PF 1,79, DD 761,50, 4 meses melhores / 4 piores) - o BE sozinho tem plateau fraco (m=0,5 mal, 1 neutro, 1,5 negativo), logo o ganho extra de +R$70 sobre a aperta nao e' confiavel.

## 5. Candidatas congeladas (`d1_candidatas.py`)
1. `D1_aperta_N2_k1.0` : stop=dict(aperta=(2,1.0)) -> +R$8.377,14, 13/14, pior -117,00, PF 1,77, 248 trades, DD 781,50, sem set 7.785,61; 4 meses melhores / 1 pior. Vizinhos k 0,75/1,25/1,5 todos > baseline.
2. `D1_aperta_N2_k1.0_BE1` : idem + BE m=1 -> +R$8.446,74, PF 1,79, DD 761,50, sem set 7.592,21, 4/4 meses. Mais fraca (plateau do BE fraco); congelada como variante.
Ressalva: ganho de ~7% sobre baseline com 5 meses mexidos e N=2 isolado; a validacao em 2025 decide.

Total: 62 rodadas (33 no estagio 1 + 29 no estagio 2, incl. 4 duplicatas por grafia; ~58 configuracoes unicas), mais a diagnose.
