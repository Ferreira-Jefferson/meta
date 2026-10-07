# A virada (WIN, setembro/2026): topo que vira x topo que segue

Scripts: `rodada2/virada/ev.py` (eventos), `an.py`, `an2.py`, `an3.py`, `an4.py`.

## Método
- Ticks de 21 pregões, só negócios. Pernada = zigzag de 750 pts sobre os ticks. Topo (ou fundo, espelhado) candidato = máximo corrente da perna; o evento dispara quando o preço recua X (150/250/375/500) desse máximo (tempo real). Rótulo: **vira** = esse máximo é o topo final da perna (o preço depois cai 750 dele); **segue** = o preço faz novo máximo. Um evento por (máximo, X). Só eventos com alta acumulada desde o fundo >= 750 (com piso de 500 o rótulo era contaminado mecanicamente: todo topo final tem >=750).
- Sinal alinhado: positivo = a favor da virada. Indicadores (EMA9/21, RSI14, VWAP, ATR) do M1 com agosto só de aquecimento; fluxo dos ticks.
- Controle: AUC estratificada por faixa de hora x faixa de tamanho da alta (aprox. 12 estratos); nulo = permutação do rótulo dentro do estrato (200x); erro padrão do nulo ~0,03 (pool) a ~0,05-0,07 (topo ou fundo isolados).
- n: topos 457/262/172/129 eventos (X=150/250/375/500) com 85 viradas; fundos 466/300/182/125 com 83 viradas.

## 1. Detecção cedo: P(virar 750 | recuou X do máximo), alta >= 750
| X | topo | fundo |
|---|---|---|
| 150 | 18,6% | 17,8% |
| 250 | 32,4% | 27,7% |
| 375 | 49,4% | 45,6% |
| 500 | 65,9% | 66,4% |

Por hora (X=500): 9-10h 61-62% (n 145), 11-12h 57-63% (57), 13-14h 84-88% (35), 15h+ 78-100% (17). Em X=250: 9-10h 23-31%, 11-12h 22-28%, 13-14h 44-54%. A tarde vira mais porque há menos intermediários (as perdas são mais curtas e as pernadas acabam), não por sinal. Topo e fundo têm a mesma taxa (diferença <= 5 pp, dentro do ruído): a virada é simétrica.
Tempo do topo até o recuo de 250 nas viradas: mediana 62 s (p25 29, p75 132). Tamanho da alta (750-1250 / 1250-2000 / >2000) não muda a taxa (X=250: 27/27/32% fundo, 32/35/30% topo).

## 2. Medianas, vira x segue (X=250, topo+fundo; n 168 / 394)
| variável | vira (med; q1-q3) | segue |
|---|---|---|
| alta (pts) | 1318 (959-1780) | 1280 (986-1764) |
| duração (min) | 27 (12-59) | 23 (8-45) |
| velocidade (pts/min) | 53 (26-96) | 67 (37-148) |
| delta agressor da perna (a favor) / volume | 0,073 | 0,076 |
| distância ao VWAP (ATR M5) | 1,43 (0,44-2,52) | 1,05 (-0,04-2,14) |
| volume/min do recuo vs perna | 1,06 | 0,97 |
| tamanho médio do negócio no recuo vs perna | 1,02 | 1,01 |
| velocidade do recuo (pts/s) | 4,0 | 4,9 |
| minutos desde 9h | 110 | 93 |
Diferenças pequenas frente à dispersão.

## 3. AUC estratificada (hora x tamanho), permutação, n comparações ~290
Só aparecem (p da permutação < 0,05); todos com AUC 0,35-0,40 ou 0,60-0,67:
| X | var | topo | fundo | pool |
|---|---|---|---|---|
| 250 | delta da perna (agressão a favor da alta) | 0,39 (p .03) | 0,49 | 0,45 (p .12) |
| 250 | distância ao VWAP | 0,60 (p .04) | 0,52 | 0,55 (p .10) |
| 250 | vol/min do recuo vs perna | 0,59 (p .04) | 0,51 | 0,55 |
| 250 | vol último minuto antes do topo vs perna | 0,52 | 0,37 (p .005) | 0,43 (p .05) |
| 250 | tam. médio negócio 5 min antes vs perna | 0,53 | 0,38 (p .01) | 0,44 (p .08) |
| 250 | velocidade da alta | 0,40 (p .02) | 0,48 | 0,45 |
| 500 | EMA9 abaixo de EMA21 no recuo | 0,37 (p .01) | 0,51 | 0,44 (p .13) |
| 500 | vol/ritmo no recuo | 0,64 (p .04) | 0,47 | 0,55 |
| 500 | corpo da vela do topo (a favor da virada) | 0,55 | 0,67 (p .02) | 0,61 (p .02) |
(AUC <0,5 = quem tem mais da variável tende a seguir; no cruzamento EMA, o sinal está invertido e é a favor de seguir.) Dos ~156 testes com permutação, 14 tiveram p<0,05 (esperado por acaso ~8); só um passa no pool (corpo, p .02). Sinais de topo e fundo discordam entre si em várias variáveis (volume pré-topo: fundo 0,37, topo 0,52), o que é típico de ruído. RSI no topo, divergência de delta (último x primeiro terço), pavio da vela, ATR relativo, perna anterior, cruzamento EMA9 (virou no recuo), cruzamento do VWAP, sequência: AUC 0,43-0,57, nada.
Cruzamento EMA9 durante o recuo (X=250): P(vira) 50% (n=38) contra 27-31% sem cruzar (n=509); em X=500 AUC 0,50. Nem o cruzamento de EMA9/21 nem o VWAP discriminam depois de X=250.

## 4. O que se aguenta
- Única regularidade coerente nos dois lados e nos dois X: **quanto mais forte o delta agressor da perna (a favor), menos vira** (AUC 0,39-0,52, só topo significativo). Combina com "agressão é clímax só quando o movimento termina": agressão forte ao longo de toda a perna indica perna saudável, não fim.
- Distância ao VWAP (alta longe do VWAP vira mais): 0,55-0,62, consistente em sinal (topo e fundo, X 250 e 500) mas só topo chega a p<.05.
- Resto: ruído em n=85 viradas.
