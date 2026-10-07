# WIN (WINV26) setembro/2026 - transicoes e probabilidades condicionais entre pernadas

Dados: M1 de 01-30/09/2026 (21 pregoes), caminho dentro da vela por cor, cada pregao separado. Scripts em `rodada2/transicoes/` (`lib.py`, `an.py`, `rep.py`, `chk.py`, `cnt.py`; saida bruta `res.pkl`).

## Metodo e nulo
- Zigzag 750 (principal) e 500 (conferencia de escala); 250 para sub-pernadas ("tentativas").
- **Nulo com controle de horario:** embaralhei as velas M1 (forma + retorno) **dentro de blocos de 30 min** de cada pregao, reencadeei os precos, 300 simulacoes; mesmo codigo nas duas pontas. Conferencia com blocos de 60 e 15 min nos achados de tarde. Nulo "dia inteiro" (rodada 1) apagava a sazonalidade e inflava efeitos.
- Tempo real: o evento "recuo de X pts a partir da maxima corrente" so usa o que ja se sabia; o desfecho ("recuo chega a D antes de o preco fazer nova maxima") e olhado para frente. Eventos por pernada sao dependentes; n e de eventos, nao de pernadas independentes. Pregoes sem desfecho (fim do dia) foram descartados.
- **Mecanica a lembrar:** se nada mais atua, P(recuo de X chegar a D antes de nova maxima) = X/D (ruina do jogador). 250->750 = 33%, 375->750 = 50%, 500->750 = 67%, 250->1000 = 25%, 500->1500 = 33%. O nulo reproduz isso; o real tambem, quase sempre.
- Eventos com A (tamanho da alta no momento) < 750 tem P(750)=0 por definicao do zigzag (artefato): ignorar essas linhas.
- Comparacoes: 349 estatisticas calculadas, 304 com n>=20 contra o nulo; 21 com |z|>=2 (esperado por acaso ~14 se independentes, mas sao muito correlacionadas entre si). Mais 3 checagens de robustez (bootstrap por dia, blocos 60 e 15 min).

## 1. Transicao tamanho(n) -> tamanho(n+1), zigzag 750 (pernadas fechadas, n=150 pares; sem 1a do dia n=129)

| tamanho da anterior | n | P(prox>=1000) real/nulo | P(prox>=1500) | P(prox>=2000) | mediana prox real/nulo | razao med. prox/ant real/nulo |
|---|---|---|---|---|---|---|
| 750-1000 | 38 | 0,76 / 0,71 | 0,47 / 0,37 (z 1,6) | 0,29 / 0,20 | 1430 / 1261 | 1,58 / 1,47 |
| 1000-1500 | 53 | 0,59 / 0,68 | 0,30 / 0,36 | 0,13 / 0,19 | 1055 / 1232 | 0,87 / 1,02 (z -1,8) |
| 1500-2500 | 46 | 0,83 / 0,70 (z 1,9) | 0,30 / 0,33 | 0,15 / 0,16 | 1300 / 1235 | 0,71 / 0,66 |
| >=2500 | 13 | 0,92 / 0,78 | 0,62 / 0,43 (z 1,5) | 0,23 / 0,17 | 1605 / 1404 | 0,48 / 0,42 |
| TODAS | 150 | 0,73 / 0,70 | 0,37 / 0,36 | 0,19 / 0,19 | 1288 / 1251 | **0,88 / 0,97 (z -2,9)** |

Leitura: o **tamanho** da proxima pernada nao depende do tamanho da anterior alem do que o nulo ja da (correlacao log n vs n+1 = 0,00 real, nulo -0,01 [-0,13; 0,12]; com controle de hora 0,01). A mediana da proxima (1.245-1.288) e igual a do nulo. As faixas 750-1000 e >=2500 sobem em relacao ao nulo, mas com n 38 e 13 e sem consistencia monotona (a faixa 1000-1500 cai).

Em zigzag 500 (n=376) nada disso aparece: P(prox>=1000) 0,38/0,36; razao 0,97/0,99; correlacao 0,00.

## 2. O que sobrou do "devolucao parcial" da rodada 1 (so a 750)
P(prox >= ant), isto e, a pernada seguinte supera o inicio da anterior: real **0,42** (n=150) vs nulo com horario **0,48** [0,44; 0,52]; sem a 1a do dia 0,40 vs 0,48 (z -2,9). A rodada 1 achava 30% contra 50%; **uma boa parte era sazonalidade** (nulo sem horario), sobra ~6-8 pontos percentuais. Razao mediana 0,88 vs 0,97. Em zigzag 500 desaparece (0,48 vs 0,49).

Dependencias (n=129, sem a 1a):
| condicao da pernada anterior | n | prox>=ant real/nulo | razao med. real/nulo |
|---|---|---|---|
| terminou em extremo alem do anterior mesmo lado ("estendeu") | 47 | 0,28 / 0,31 | 0,69 / 0,75 |
| nao estendeu | 61 | 0,49 / 0,65 (z -3,1) | 0,99 / 1,20 (z -2,5) |
| terminou longe da abertura, no lado da deriva do dia | 85 | 0,34 / 0,43 (z -2,7) | 0,78 / 0,90 (z -2,9) |
| terminou perto/lado oposto da abertura | 44 | 0,52 / 0,59 | 1,06 / 1,12 |

A diferenca real-nulo e **uniforme** (todas as celulas ~ -0,07 a -0,16): nao ha uma condicao que a concentre. Memoria de 2 passos: correlacao log tamanho (n-1 vs n+1) = **-0,21** real vs -0,05 nulo (z -2,1, n=108; vale so a 750, zigzag 500 da -0,00): alta grande -> baixa -> alta tende a menor. Fraco e isolado.

## 3. Tempo real: o recuo ja em curso vai virar uma pernada de 750?
P(recuo de X chegar a D antes de nova maxima), eventos de todas as pernadas (altas e baixas espelhadas):

| X -> D | n | real | nulo [p5;p95] | ruina X/D |
|---|---|---|---|---|
| 250 -> 750 | 705 | 0,243 | 0,248 [0,23; 0,27] | 0,33 |
| 250 -> 1000 | 696 | 0,180 | 0,183 | 0,25 |
| 375 -> 750 | 405 | 0,422 | 0,414 | 0,50 |
| 500 -> 750 | 273 | 0,626 | 0,610 | 0,67 |
| 500 -> 1000 | 264 | 0,473 | 0,462 | 0,50 |
| 375 -> 1500 | 374 | 0,217 | 0,198 (z 1,5) | 0,25 |
| 500 -> 1500 | 242 | 0,335 | 0,302 (z 1,8) | 0,33 |

(o menor que ruina pois o recuo ocorre sobre maxima ja estendida e ha censura de fim de dia.) **Nenhum dos condicionantes testados descola do nulo**, porque o nulo reproduz o mesmo gradiente:
- tamanho A da alta (750-1000 / 1000-1500 / >=1500), 250->750: 0,30 / 0,31 / 0,32 (nulo 0,33 / 0,32 / 0,33).
- numero da tentativa (1a, 2a, 3a+ vez que o recuo de 250 acontece na mesma pernada), 250->750: 0,13 / 0,25 / 0,30 (nulo 0,15 / 0,25 / 0,30). Sobe com a tentativa, mas o nulo sobe igual: e a mecanica (a maxima estendida fica mais longe da base... e o evento fica em pernadas ja longas), nao memoria.
- a favor da deriva do dia vs contra, 250->750: 0,27 / 0,21 (nulo 0,28 / 0,21): igual ao nulo.
- A relativo a media das pernadas anteriores do dia (<0,8 / 0,8-1,25 / >=1,25), 250->750: 0,18 / 0,29 / 0,33 (nulo 0,18 / 0,33 / 0,31).
- topo de alta vs fundo de baixa: 0,247 / 0,238. Sem assimetria.

Excecoes (z>=2, tratar como acaso ate prova): A>=1500 e recuo de 375/500 chegando a 1500: **0,32 vs 0,24 (n=111)** e **0,44 vs 0,34 (n=81)**; mesma direcao com A/mediaPrev >=1,25 (0,31 vs 0,24; 0,42 vs 0,34). Alta muito esticada tem recuo que vira pernada grande um pouco mais do que o nulo.

### 3.1 O unico descolamento consistente: tarde (13h+)
| X -> 750, eventos a partir das 13h | n (pernadas) | real | nulo 30 min [p95] | nulo 60 min / 15 min |
|---|---|---|---|---|
| 250 | 147 (66) | **0,320** (IC 90% por dia 0,28-0,36) | 0,249 [0,28] | 0,256 / 0,260 |
| 375 | 89 (63) | **0,528** (0,47-0,59) | 0,439 | 0,452 / 0,457 |
| 500 | 61 (53) | **0,770** (0,70-0,85) | 0,662 [0,74] | 0,661 / 0,678 |
| 250 -> 1000 | 138 | 0,210 | 0,173 | |
Antes das 13h o real e igual ou ligeiramente abaixo do nulo (250->750: 0,23 vs 0,26 antes das 10:30; 0,21 vs 0,24 entre 10:30 e 13h). Ou seja: **de manha recuos se desfazem um pouco mais que o acaso, a tarde viram pernada de verdade um pouco mais (~+7 a +11 pontos)**. Nos 3 X as estimativas estao aninhadas (nao sao independentes). So 21 pregoes e 27 pernadas de 750 comecam depois das 13h.

## 4. Sub-pernadas (zigzag 250) dentro de uma pernada de 750
Pivos de 250 contidos por pernada: media 7,8 real vs 7,2 nulo (z 1,4); 14,6% das pernadas tem 0 (nulo 17,1%). Por tamanho: 750-1000: 2,9 (nulo 2,8); 1000-1500: 5,4 (5,1); 1500-2500: **11,6 (9,9; z 2,1)**; >=2500: 19,9 (20,0). Uma pernada de 750 ja "se anuncia" por 3 sub-pernadas em media; quanto maior, mais tentativas, na proporcao do nulo. Dica pratica: numero de tentativas ~ proporcional ao tamanho (~7 pivos por 1000 pts).

## 5. O que NAO descola do nulo (para nao refazer)
- P(prox >=1000/1500/2000) dado o tamanho da anterior (so a faixa 1500-2500 -> >=1000 chega a z 1,9).
- Correlacao de tamanho n vs n+1, n-1 vs n+1 em zigzag 500; qualquer dependencia por tentativa, deriva, tamanho do avanco, direcao (alta/baixa).
- Mediana do tamanho da proxima pernada (1.245-1.288 vs 1.239-1.251 do nulo).
