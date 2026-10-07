# WIN 2026 - mapa de excursoes apos o recuo (MFE/MAE) e superficie de esperanca

Dados: WIN@D M1, so 2026. Descoberta jan-jun (122 pregoes), confirmacao jul-ago (44), referencia set (21). Codigo e saidas brutas em `rodada4/excursao/` (`exc.py` motor de eventos e simulacao, `agg.py`, `stage0.py`/`stage1.py` real e nulo, `cand.py` bootstrap/plato, `mao.py` tamanho, `quantis_*.csv`, `candidatos_*.csv`).

## Metodo
- **Evento**: avanco A = do ultimo fundo (reinicia se o preco o perde) ate a maxima corrente, 150 <= A <= 2.000 pts. Recuo r = 10/20/30/38/50/62/78% de A, em tempo real, um evento por nivel por maxima. Os dois lados espelhados (alta e queda) no mesmo quadro "tendencia anterior = alta". Cortes: faixa de A (150-250, 250-400, 400-750, 750-2000), r, horario (<11h, 11-13h, >=13h), velocidade do recuo em pts/min (tercis congelados na descoberta: <55,6; 55,6-109; >109), ordem do recuo no movimento (1o, 2o, 3o+).
- **MFE/MAE**: a partir do ponto em que o recuo e atingido, maximo a favor da tendencia anterior (MFE) e maximo contra (MAE) em 15/30/60 min e ate o fim do pregao (15/30 em `quantis_*.csv`).
- **Nulo**: velas M1 embaralhadas em blocos de 30 min, mesmo codigo, 40 simulacoes por janela. Excesso = real - media do nulo; z = excesso / desvio entre simulacoes.
- **Execucao simulada** (desenho fechado): entrada por ordem-limite no nivel do recuo, prazo de 5 min; alvo por limite; stop a mercado com 5 pts de deslize; custo 2 pts/op; R$0,20/pt; fim do pregao = saida a mercado. Fill conservador: so enche se o preco negociar 1 tick (5 pts) alem do nivel (alvo idem); otimista: basta tocar. Alvo minimo 25 pts. Dois lados: **a favor** = comprar o recuo da alta (e vender o da queda); **contra** = vender o recuo da alta como inicio de virada (e comprar o da queda).
- **Geometrias** (25): pts fixos T x S em {75,150,300,600}^2 (16) e multiplos de A, alvo {0,25;0,5;1,0}A x stop {0,3;0,6;1,0}A (9).
- **Testes**: 136 celulas (12 cortes) x 2 lados x 25 geometrias x 2 fills = 13.600 combinacoes por janela; selecionadas 6.800 (fill conservador, n de operacoes >= 150) e 6.800 no otimista. IC por bootstrap de dias (2.000 reamostragens); plato = vizinhos de geometria (+-1 passo em T e S) e de r (+-1 nivel).

## 1. Mapa de excursoes: real contra nulo (descoberta; confirmacao abaixo)
Leitura (pts, por contrato, p50/p90 entre parenteses = nulo):

- A extensao a favor e a contra **nao dependem do tamanho de A nem de r**; dependem do horario e da volatilidade do dia. Em 60 min a mediana do MFE vai de ~430 a ~590 pts e a do MAE de ~335 a ~450, para qualquer A e r. Ate o fim do pregao: MFE mediano 770-1.010, MAE mediano 725-900.
- Em multiplos de A isso significa que o recuo "devolvido" pouco informa: para A de 150-250 o preco anda em mediana 2,4A a favor e 1,8A contra em 60 min; para A de 750-2000, 0,5A e 0,4A. O alcance e ~ constante em pontos, nao proporcional a A.
- **Real x nulo**: o MFE e igual ao nulo (diferencas de -11% a +5%, sem sinal consistente). O MAE real e **um pouco menor** que o nulo em A < 750 (mediana 335-400 contra 400-446, p90 ~1.100 contra ~1.300) na descoberta, e o mesmo na confirmacao em 150-250 (275-305 contra 335-354); em A >= 750 o MAE real e igual ou ate maior que o nulo. E um efeito de poucos %, que nao vira esperanca depois de custo (secao 2).
- Superficie por r: a favor, recuos rasos (r <= 30%) tem excesso medio de +1 a +5 pts sobre o nulo; recuos fundos (r >= 50%) tem -5 a -12. Contra (fade) e o espelho: -8 pts em r 10-20% e +4 a +8 em r >= 50%. O padrao reaparece na confirmacao com o mesmo sinal em r raso e r extremo, mas com magnitude de 1 a 10 pts contra um custo medio de 30-50 pts por operacao.

## 2. Superficie de esperanca (liquida, por operacao executada; descoberta, sem corte)
Esperanca liquida em pts (entre parenteses o nulo) e acerto/breakeven empirico em %, por geometria; a favor | contra, fill conservador; depois fill otimista.

| geometria | a favor, cons. | contra, cons. | a favor, otim. | contra, otim. |
|---|---|---|---|---|
| 75/75 pts | -32,1 (-32,8) · 32,2/52,9 | -26,9 (-26,0) · 35,6/52,9 | -29,7 (-30,2) · 33,7/52,9 | -23,4 (-22,7) · 37,8/52,9 |
| 150/150 pts | -40,1 (-40,9) · 38,3/51,5 | -34,3 (-32,4) · 40,2/51,5 | -36,6 (-37,3) · 39,5/51,5 | -29,7 (-27,7) · 41,7/51,5 |
| 300/300 pts | -48,4 (-47,2) · 42,6/50,7 | -36,2 (-34,0) · 44,8/50,9 | -44,3 (-42,8) · 43,3/50,7 | -31,1 (-28,9) · 45,7/50,9 |
| 600/600 pts | -62,8 (-61,2) · 44,7/50,2 | -25,7 (-22,3) · 48,6/50,9 | -58,6 (-56,8) · 45,0/50,2 | -20,4 (-17,1) · 49,0/50,8 |
| 75/600 pts | -48,1 (-50,5) · 81,7/89,0 | -54,0 (-41,5) · 80,8/88,9 | -42,4 (-44,3) · 82,5/89,0 | -47,1 (-35,3) · 81,8/88,9 |
| 600/75 pts | -27,1 (-30,9) · 8,4/12,6 | -20,7 (-19,1) · 9,4/12,6 | -25,4 (-29,4) · 8,7/12,6 | -17,7 (-16,4) · 9,8/12,6 |
| 0,25A/0,3A | -41,3 (-40,1) · 38,7/52,2 | -33,2 (-31,8) · 42,3/53,1 | -37,6 (-36,7) · 40,2/52,6 | -28,6 (-27,7) · 44,3/53,7 |
| 1,0A/0,3A | -36,9 (-39,5) · 18,3/23,6 | -25,6 (-27,4) · 20,6/24,4 | -34,6 (-37,2) · 18,7/23,6 | -21,6 (-23,9) · 21,5/24,7 |

(25 geometrias completas por celula em `tab_desc.pkl`, `tab_conf.pkl`, `tab_set.pkl`.) O fill medio e de ~89% (a limite enche na maior parte das vezes dentro de 5 min). **Nenhuma das 25 geometrias, em nenhum dos lados, tem esperanca positiva sem corte, e o acerto fica 10 a 20 pp abaixo do breakeven empirico**; o breakeven ja inclui o custo (7 pts de perda a mais que o alvo). O real esta praticamente em cima do nulo (diferencas de 0 a 8 pts). Fill otimista melhora a esperanca de 0 a 8 pts, nunca vira o sinal.

### Cortes (descoberta, fill conservador)
- 6.800 combinacoes com >= 150 operacoes: **44 (0,6%) com esperanca > 0**, maximo +57,8 pts (celula de 1.175 operacoes cuja esperanca real nao difere do nulo, z = 0,6). Fill otimista: 83 com esperanca > 0, maximo +64,5.
- Excesso sobre o nulo: 48 combinacoes com z > 3 e 121 com z < -3 (mais combinacoes piores que o acaso do que melhores). Replicacao na confirmacao: das 48 com z > 3, 65% mantem o sinal do excesso (moeda justa = 50%, com excesso de z > 1 na confirmacao em 27%); das 121 com z < -3, 83% mantem. Correlacao do excesso descoberta x confirmacao entre as 6.775 combinacoes comuns: 0,17.
- Muitas combinacoes positivas na descoberta sao positivas tambem no **nulo** (ex.: contra a tendencia depois das 13h com 600/600: +11,9 real, +13,8 nulo): e efeito de relogio/saida no fim do pregao, nao de direcao.

## 3. Lista congelada (regra fixada antes da confirmacao)
Regra, escrita antes de abrir jul-ago: **esperanca liquida > 0, z do excesso sobre o nulo >= 2, >= 150 operacoes executadas na descoberta**. Passaram 7 combinacoes. Para cada uma, IC por bootstrap de dias e plato na descoberta:

| spec | cell | side | geom | nf | dias | fill% | exp | lo95 | hi95 | nulo | z | win | be | plato_geom | plato_r |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rA | lv=5|ab=3 | 1 | 0.5A/0.6A | 420 | 115 | 0.93 | 2.2 | -46.9 | 52.0 | -65.7 | 3.66 | 0.555 | 0.553 | 0.12 | 0.0 |
| AV | ab=0|vb=2 | 0 | 300/600 pts | 632 | 113 | 0.85 | 35.6 | -27.4 | 96.3 | -31.2 | 2.92 | 0.706 | 0.666 | 0.2 | nan |
| rA | lv=5|ab=3 | 1 | 600/600 pts | 420 | 115 | 0.93 | 0.2 | -52.8 | 56.5 | -66.5 | 2.87 | 0.51 | 0.509 | 0.0 | 0.0 |
| rO | lv=5|od=2 | 1 | 600/600 pts | 858 | 122 | 0.93 | 1.2 | -56.3 | 55.9 | -38.8 | 2.59 | 0.513 | 0.512 | 0.0 | 0.0 |
| rV | lv=5|vb=1 | 1 | 600/600 pts | 510 | 122 | 0.93 | 23.0 | -48.8 | 94.7 | -32.6 | 2.56 | 0.531 | 0.511 | 0.0 | 0.0 |
| rA | lv=5|ab=3 | 1 | 0.5A/1.0A | 420 | 115 | 0.93 | 1.4 | -67.2 | 71.0 | -54.4 | 2.42 | 0.645 | 0.644 | 0.2 | 0.0 |
| rA | lv=3|ab=3 | 1 | 1.0A/1.0A | 682 | 118 | 0.91 | 10.8 | -66.1 | 85.2 | -53.4 | 2.2 | 0.509 | 0.503 | 0.0 | 0.5 |
`plato_geom` = fracao de geometrias vizinhas com esperanca > 0; `plato_r` = idem para os niveis de r vizinhos (0 = nenhum vizinho positivo). **Nota de integridade:** a tabela de positivos que usei para inspecionar os candidatos trazia, na mesma linha, as colunas da confirmacao; a regra acima ja tinha sido aplicada e contada (7) antes de eu olhar essas colunas, mas isso nao e um congelamento limpo. Nenhuma celula teria sido escolhida diferente.

Todas as 7 tem IC de dias que cobre zero com folga (largura de +-50 a +-90 pts), acerto a 0,1-4 pp do breakeven, e plato inexistente (vizinhos de geometria 0-20% positivos, vizinhos de r 0-50%). Sao as 7 melhores entre ~6.800 combinacoes fortemente correlacionadas entre si.

## 4. Confirmacao (jul-ago) e referencia (set), lado a lado
| spec | cell | side | geom | janela | nf | dias | exp | lo95 | hi95 | win | be |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rA | lv=5|ab=3 | 1 | 0.5A/0.6A | conf | 118 | 43 | -29.0 | -115.4 | 70.0 | 0.508 | 0.534 |
| rA | lv=5|ab=3 | 1 | 0.5A/0.6A | set | 71 | 21 | -57.7 | -166.5 | 64.9 | 0.479 | 0.523 |
| AV | ab=0|vb=2 | 0 | 300/600 pts | conf | 164 | 33 | -11.9 | -109.4 | 81.1 | 0.652 | 0.666 |
| AV | ab=0|vb=2 | 0 | 300/600 pts | set | 68 | 18 | -194.4 | -354.5 | 23.8 | 0.456 | 0.671 |
| rA | lv=5|ab=3 | 1 | 600/600 pts | conf | 118 | 43 | -24.6 | -109.5 | 70.3 | 0.483 | 0.504 |
| rA | lv=5|ab=3 | 1 | 600/600 pts | set | 71 | 21 | -58.3 | -159.7 | 56.9 | 0.451 | 0.499 |
| rO | lv=5|od=2 | 1 | 600/600 pts | conf | 260 | 44 | -0.9 | -92.8 | 87.0 | 0.496 | 0.497 |
| rO | lv=5|od=2 | 1 | 600/600 pts | set | 117 | 20 | -87.4 | -210.1 | 49.3 | 0.436 | 0.511 |
| rV | lv=5|vb=1 | 1 | 600/600 pts | conf | 165 | 42 | -69.9 | -176.2 | 31.9 | 0.424 | 0.486 |
| rV | lv=5|vb=1 | 1 | 600/600 pts | set | 69 | 21 | -64.9 | -198.4 | 78.8 | 0.435 | 0.492 |
| rA | lv=5|ab=3 | 1 | 0.5A/1.0A | conf | 118 | 43 | -28.9 | -144.2 | 90.0 | 0.602 | 0.623 |
| rA | lv=5|ab=3 | 1 | 0.5A/1.0A | set | 71 | 21 | -105.0 | -255.4 | 47.1 | 0.563 | 0.627 |
| rA | lv=3|ab=3 | 1 | 1.0A/1.0A | conf | 203 | 43 | 14.2 | -106.1 | 128.8 | 0.502 | 0.494 |
| rA | lv=3|ab=3 | 1 | 1.0A/1.0A | set | 124 | 21 | -348.7 | -531.8 | -135.0 | 0.323 | 0.49 |
**0 de 7 confirmam**: 6 viram esperanca negativa (-1 a -70 pts), 1 fica positiva (rA lv=3|ab=3 1,0A/1,0A: +14,2, IC [-106; +129], 43 dias) e em set perde -349 (IC [-532; -135]). Em set todas as 7 sao negativas. Na confirmacao como um todo, 492 de 6.775 combinacoes (n >= 60) tem esperanca > 0 (7%), nenhuma delas previsivel pela descoberta.

## 5. Tamanho de mao e ruina (motor.py, capital R$250)
Para as 7 celulas congeladas, com p observado encolhido (n0=100, base = breakeven), Kelly 1/4, teto de pior caso 25% do caixa: **mao = 0 em todas**. A perda de 1 contrato com alvo/stop dessas geometrias e de R$121 a R$234 (stop de 600 a 1.165 pts + 7), isto e 48% a 94% de R$250, acima do teto de 25%. Mesmo sem teto, a esperanca encolhida (+5 a +28 pts) vem com IC que cobre zero e confirmacao negativa. Risco de ruina com E[X] <= 0 (a medida na confirmacao): 100% (`ruina_formula` devolve 1,0 para E[X] <= 0).

## 6. Veredito
Depois de custo, **nao ha celula que valha operar**: 0 de 7 confirmam, 0 tem plato, as geometrias sem corte perdem 20-60 pts por operacao tanto a favor quanto contra, e o real nao se afasta do nulo alem de 1-8 pts. O que o mapa mostra de real, e pequeno: (i) o MAE depois de um recuo em A < 750 e ~10% menor que o do acaso na descoberta e na confirmacao; (ii) recuos rasos favorecem levemente a continuacao e recuos fundos (>= 50%) a virada em +4 a +8 pts sobre o nulo, mas esses ganhos sao 5 a 10 vezes menores que o custo e do tamanho do ruido (correlacao descoberta x confirmacao 0,17).

## Anexo: tabelas de quantis (todas as faixas de A x r em 20/38/50/62%)

### Quantis MFE/MAE (desc) - pts a partir do ponto do recuo; real (nulo entre parenteses)


Horizonte 60 min

| A | r | n | MFE p25 | MFE p50 | MFE p75 | MFE p90 | MAE p25 | MAE p50 | MAE p75 | MAE p90 |
|---|---|---|---|---|---|---|---|---|---|---|
| 150-250 | 20% | 1498 | 235 (231) | 430 (458) | 805 (838) | 1275 (1289) | 145 (168) | 375 (414) | 709 (807) | 1096 (1284) |
| 150-250 | 38% | 1058 | 245 (252) | 442 (482) | 795 (867) | 1265 (1322) | 141 (156) | 360 (402) | 684 (792) | 1037 (1259) |
| 150-250 | 50% | 822 | 246 (256) | 462 (490) | 830 (872) | 1270 (1327) | 131 (153) | 345 (400) | 660 (787) | 1005 (1253) |
| 150-250 | 62% | 608 | 240 (258) | 470 (494) | 851 (875) | 1285 (1328) | 134 (153) | 335 (398) | 645 (782) | 987 (1241) |
| 250-400 | 20% | 1347 | 248 (252) | 495 (509) | 898 (922) | 1327 (1403) | 170 (174) | 425 (435) | 780 (842) | 1155 (1341) |
| 250-400 | 38% | 918 | 270 (276) | 502 (539) | 905 (959) | 1347 (1449) | 165 (166) | 440 (435) | 794 (847) | 1173 (1349) |
| 250-400 | 50% | 748 | 279 (283) | 520 (543) | 918 (962) | 1395 (1456) | 154 (163) | 440 (433) | 806 (849) | 1170 (1345) |
| 250-400 | 62% | 567 | 290 (286) | 535 (544) | 935 (964) | 1395 (1460) | 168 (161) | 435 (432) | 800 (847) | 1207 (1336) |
| 400-750 | 20% | 1525 | 275 (264) | 535 (543) | 945 (950) | 1450 (1443) | 150 (178) | 425 (446) | 830 (862) | 1200 (1374) |
| 400-750 | 38% | 918 | 295 (277) | 575 (559) | 1000 (972) | 1500 (1466) | 136 (174) | 400 (446) | 810 (879) | 1188 (1396) |
| 400-750 | 50% | 719 | 290 (280) | 585 (562) | 1032 (981) | 1545 (1469) | 140 (168) | 395 (441) | 795 (877) | 1130 (1398) |
| 400-750 | 62% | 560 | 285 (283) | 590 (559) | 1025 (970) | 1585 (1451) | 159 (163) | 398 (440) | 805 (870) | 1150 (1388) |
| 750-2000 | 20% | 1412 | 289 (300) | 560 (574) | 985 (1006) | 1435 (1515) | 165 (173) | 430 (443) | 850 (836) | 1320 (1283) |
| 750-2000 | 38% | 737 | 275 (313) | 550 (594) | 965 (1010) | 1403 (1531) | 160 (160) | 440 (431) | 880 (828) | 1350 (1287) |
| 750-2000 | 50% | 565 | 315 (319) | 550 (607) | 960 (1006) | 1428 (1504) | 160 (160) | 440 (422) | 855 (823) | 1332 (1297) |
| 750-2000 | 62% | 441 | 325 (324) | 545 (611) | 915 (1006) | 1375 (1463) | 175 (154) | 450 (414) | 850 (819) | 1285 (1313) |

Horizonte ate o fim do pregao

| A | r | n | MFE p25 | MFE p50 | MFE p75 | MFE p90 | MAE p25 | MAE p50 | MAE p75 | MAE p90 |
|---|---|---|---|---|---|---|---|---|---|---|
| 150-250 | 20% | 1529 | 350 (331) | 770 (748) | 1465 (1509) | 2378 (2461) | 295 (301) | 740 (770) | 1415 (1579) | 2206 (2558) |
| 150-250 | 38% | 1077 | 370 (356) | 770 (786) | 1475 (1554) | 2309 (2503) | 295 (296) | 740 (766) | 1405 (1562) | 2204 (2531) |
| 150-250 | 50% | 839 | 375 (362) | 800 (796) | 1475 (1563) | 2264 (2520) | 285 (295) | 735 (766) | 1388 (1548) | 2078 (2516) |
| 150-250 | 62% | 619 | 365 (363) | 780 (799) | 1495 (1567) | 2322 (2507) | 295 (292) | 725 (764) | 1388 (1538) | 2070 (2498) |
| 250-400 | 20% | 1374 | 370 (374) | 870 (843) | 1605 (1658) | 2505 (2682) | 320 (329) | 802 (817) | 1665 (1652) | 2490 (2648) |
| 250-400 | 38% | 934 | 400 (403) | 902 (889) | 1629 (1719) | 2510 (2751) | 340 (328) | 820 (830) | 1689 (1661) | 2461 (2662) |
| 250-400 | 50% | 761 | 405 (413) | 930 (896) | 1665 (1727) | 2540 (2761) | 340 (325) | 835 (829) | 1705 (1657) | 2455 (2648) |
| 250-400 | 62% | 581 | 410 (411) | 935 (897) | 1685 (1722) | 2510 (2766) | 350 (324) | 825 (829) | 1780 (1642) | 2440 (2642) |
| 400-750 | 20% | 1547 | 470 (415) | 890 (906) | 1745 (1745) | 2772 (2773) | 315 (345) | 825 (851) | 1652 (1739) | 2530 (2674) |
| 400-750 | 38% | 934 | 506 (432) | 938 (933) | 1840 (1789) | 2770 (2840) | 320 (344) | 828 (864) | 1674 (1757) | 2557 (2703) |
| 400-750 | 50% | 735 | 495 (433) | 955 (938) | 1885 (1792) | 2812 (2848) | 335 (332) | 825 (856) | 1692 (1742) | 2599 (2695) |
| 400-750 | 62% | 575 | 480 (431) | 935 (935) | 1808 (1766) | 2796 (2811) | 335 (320) | 830 (845) | 1710 (1725) | 2636 (2658) |
| 750-2000 | 20% | 1433 | 485 (463) | 1010 (983) | 1900 (1829) | 2948 (2932) | 315 (328) | 845 (800) | 1745 (1672) | 2835 (2694) |
| 750-2000 | 38% | 752 | 480 (469) | 948 (994) | 1840 (1854) | 2860 (2905) | 340 (312) | 850 (802) | 1700 (1696) | 2800 (2659) |
| 750-2000 | 50% | 577 | 480 (475) | 950 (1004) | 1845 (1850) | 2840 (2873) | 370 (310) | 865 (814) | 1800 (1704) | 2720 (2633) |
| 750-2000 | 62% | 453 | 460 (470) | 945 (988) | 1785 (1819) | 2709 (2840) | 340 (308) | 900 (823) | 1880 (1688) | 2713 (2592) |

### Quantis MFE/MAE (conf) - pts a partir do ponto do recuo; real (nulo entre parenteses)


Horizonte 60 min

| A | r | n | MFE p25 | MFE p50 | MFE p75 | MFE p90 | MAE p25 | MAE p50 | MAE p75 | MAE p90 |
|---|---|---|---|---|---|---|---|---|---|---|
| 150-250 | 20% | 451 | 175 (173) | 425 (386) | 730 (802) | 1255 (1304) | 120 (160) | 305 (354) | 598 (682) | 1170 (1145) |
| 150-250 | 38% | 338 | 205 (194) | 462 (420) | 769 (842) | 1283 (1345) | 121 (145) | 290 (343) | 584 (671) | 1109 (1114) |
| 150-250 | 50% | 279 | 200 (201) | 475 (428) | 765 (855) | 1278 (1360) | 115 (140) | 275 (336) | 580 (667) | 1175 (1131) |
| 150-250 | 62% | 200 | 199 (199) | 482 (421) | 775 (846) | 1464 (1340) | 99 (140) | 252 (335) | 582 (666) | 1177 (1117) |
| 250-400 | 20% | 362 | 170 (207) | 388 (459) | 850 (919) | 1400 (1396) | 140 (168) | 368 (384) | 678 (746) | 1145 (1245) |
| 250-400 | 38% | 245 | 180 (230) | 420 (486) | 870 (947) | 1448 (1430) | 140 (157) | 380 (382) | 680 (762) | 1172 (1281) |
| 250-400 | 50% | 201 | 200 (236) | 435 (491) | 875 (941) | 1395 (1432) | 120 (151) | 355 (373) | 625 (751) | 1265 (1274) |
| 250-400 | 62% | 158 | 196 (228) | 440 (476) | 836 (920) | 1320 (1401) | 141 (144) | 355 (364) | 739 (737) | 1278 (1255) |
| 400-750 | 20% | 417 | 235 (247) | 450 (538) | 940 (980) | 1440 (1436) | 170 (166) | 395 (418) | 770 (798) | 1150 (1270) |
| 400-750 | 38% | 268 | 250 (258) | 475 (538) | 885 (993) | 1386 (1467) | 175 (159) | 410 (417) | 835 (809) | 1311 (1297) |
| 400-750 | 50% | 207 | 230 (259) | 485 (534) | 850 (990) | 1404 (1466) | 148 (155) | 400 (411) | 828 (806) | 1440 (1304) |
| 400-750 | 62% | 168 | 250 (263) | 492 (526) | 791 (987) | 1358 (1464) | 164 (153) | 388 (403) | 806 (795) | 1348 (1301) |
| 750-2000 | 20% | 426 | 295 (299) | 565 (576) | 950 (964) | 1458 (1396) | 96 (138) | 358 (390) | 744 (769) | 1198 (1199) |
| 750-2000 | 38% | 222 | 270 (306) | 515 (586) | 854 (991) | 1329 (1426) | 136 (126) | 392 (381) | 769 (767) | 1212 (1183) |
| 750-2000 | 50% | 166 | 308 (308) | 595 (585) | 929 (985) | 1300 (1413) | 115 (125) | 362 (385) | 725 (747) | 1145 (1171) |
| 750-2000 | 62% | 128 | 319 (290) | 580 (574) | 1020 (977) | 1294 (1398) | 159 (138) | 335 (391) | 706 (725) | 1113 (1154) |

Horizonte ate o fim do pregao

| A | r | n | MFE p25 | MFE p50 | MFE p75 | MFE p90 | MAE p25 | MAE p50 | MAE p75 | MAE p90 |
|---|---|---|---|---|---|---|---|---|---|---|
| 150-250 | 20% | 482 | 191 (227) | 570 (598) | 1321 (1328) | 2130 (2089) | 190 (283) | 590 (732) | 1350 (1411) | 2261 (2249) |
| 150-250 | 38% | 359 | 245 (253) | 600 (644) | 1428 (1387) | 2236 (2175) | 190 (273) | 585 (719) | 1310 (1389) | 2265 (2258) |
| 150-250 | 50% | 292 | 245 (257) | 620 (645) | 1434 (1411) | 2441 (2213) | 174 (268) | 578 (707) | 1308 (1382) | 2294 (2251) |
| 150-250 | 62% | 211 | 232 (254) | 600 (627) | 1452 (1358) | 2475 (2162) | 165 (277) | 590 (713) | 1325 (1376) | 2375 (2238) |
| 250-400 | 20% | 367 | 255 (304) | 760 (773) | 1498 (1514) | 2182 (2344) | 280 (284) | 690 (751) | 1418 (1468) | 2155 (2375) |
| 250-400 | 38% | 246 | 265 (339) | 820 (823) | 1588 (1551) | 2198 (2398) | 276 (290) | 752 (765) | 1432 (1492) | 2362 (2421) |
| 250-400 | 50% | 202 | 270 (345) | 860 (820) | 1588 (1544) | 2200 (2373) | 265 (294) | 695 (768) | 1409 (1499) | 2370 (2415) |
| 250-400 | 62% | 159 | 250 (329) | 765 (787) | 1600 (1515) | 2196 (2327) | 278 (292) | 815 (760) | 1482 (1494) | 2482 (2407) |
| 400-750 | 20% | 417 | 395 (386) | 930 (889) | 1575 (1557) | 2696 (2399) | 300 (298) | 770 (799) | 1395 (1456) | 2277 (2380) |
| 400-750 | 38% | 270 | 391 (417) | 888 (906) | 1575 (1559) | 2724 (2378) | 331 (313) | 892 (832) | 1558 (1485) | 2608 (2471) |
| 400-750 | 50% | 209 | 405 (423) | 865 (903) | 1640 (1558) | 2668 (2352) | 365 (325) | 895 (825) | 1585 (1479) | 2670 (2469) |
| 400-750 | 62% | 169 | 430 (425) | 830 (898) | 1630 (1576) | 2732 (2376) | 395 (322) | 905 (800) | 1560 (1461) | 2606 (2465) |
| 750-2000 | 20% | 429 | 415 (429) | 890 (871) | 1655 (1557) | 2870 (2554) | 210 (253) | 680 (694) | 1345 (1416) | 2240 (2317) |
| 750-2000 | 38% | 222 | 469 (442) | 848 (873) | 1494 (1559) | 2834 (2604) | 238 (256) | 730 (706) | 1444 (1401) | 2682 (2370) |
| 750-2000 | 50% | 167 | 508 (454) | 875 (871) | 1480 (1530) | 2768 (2571) | 242 (257) | 710 (728) | 1340 (1416) | 2440 (2376) |
| 750-2000 | 62% | 129 | 475 (440) | 920 (854) | 1550 (1519) | 2440 (2502) | 295 (259) | 685 (716) | 1280 (1425) | 2517 (2375) |

### MFE/A e MAE/A medianos, real (desc), horizonte 60 min e fim do pregao

| A | r | MFE60/A | MAE60/A | MFEfim/A | MAEfim/A | P(MFEfim>=A) | P(MAEfim>=A) |
|---|---|---|---|---|---|---|---|
| 150-250 | 20% | 2.25 | 1.91 | 3.92 | 3.81 | 0.88 | 0.82 |
| 150-250 | 38% | 2.39 | 1.83 | 3.94 | 3.83 | 0.89 | 0.82 |
| 150-250 | 50% | 2.45 | 1.78 | 4.05 | 3.86 | 0.90 | 0.81 |
| 150-250 | 62% | 2.44 | 1.72 | 4.07 | 3.69 | 0.88 | 0.82 |
| 250-400 | 20% | 1.57 | 1.32 | 2.73 | 2.59 | 0.79 | 0.76 |
| 250-400 | 38% | 1.64 | 1.37 | 2.87 | 2.66 | 0.81 | 0.77 |
| 250-400 | 50% | 1.66 | 1.33 | 2.97 | 2.69 | 0.81 | 0.76 |
| 250-400 | 62% | 1.68 | 1.32 | 3.04 | 2.67 | 0.82 | 0.76 |
| 400-750 | 20% | 1.00 | 0.81 | 1.72 | 1.57 | 0.70 | 0.64 |
| 400-750 | 38% | 1.07 | 0.77 | 1.89 | 1.61 | 0.74 | 0.63 |
| 400-750 | 50% | 1.11 | 0.75 | 1.88 | 1.57 | 0.74 | 0.65 |
| 400-750 | 62% | 1.11 | 0.77 | 1.83 | 1.60 | 0.73 | 0.66 |
| 750-2000 | 20% | 0.51 | 0.38 | 0.90 | 0.76 | 0.46 | 0.39 |
| 750-2000 | 38% | 0.51 | 0.39 | 0.85 | 0.74 | 0.43 | 0.41 |
| 750-2000 | 50% | 0.50 | 0.40 | 0.87 | 0.78 | 0.45 | 0.44 |
| 750-2000 | 62% | 0.53 | 0.41 | 0.84 | 0.79 | 0.43 | 0.43 |