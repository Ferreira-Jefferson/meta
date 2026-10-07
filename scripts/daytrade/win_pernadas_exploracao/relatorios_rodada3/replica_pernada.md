# Réplica das regras de pernada do WIN em jan–ago/2026 (R13–R19, R25, R26 e base)

Replicação com definições congeladas (REGRAS.md). Nada de lucro de estratégia. Só 2026 (jan–set); 2025 e antes não foram abertos.

## Veredito

| ID | Regra | jan–ago/26 (166 pregões) | Base / acaso | set/26 | Veredito |
|---|---|---|---|---|---|
| R13 | pernada seguinte passa do início da anterior | 49,1% (IC 46,9–51,4; n=894 pares) | 49,1% (nulo) | 42,0% (n=150) | **falhou** (a pista de set/26 não existe nos 8 meses) |
| R14 | P(recuo de X virar 750) | 150: 20,3 · 250: 32,0 · 375: 47,5 · 500: 64,7% | 21,1 · 33,0 · 48,8 · 64,8% | 20,7 · 30,7 · 47,3 · 63,7% | **replicou** (negativa: igual ao acaso, nos 8 meses) |
| R15 | indicadores no recuo mudam a chance | AUC 0,47–0,52 (nenhum p<0,09) | 0,50 | 0,46–0,55 | **replicou** (negativa) |
| R16 | tamanho anterior prevê o próximo | corr. log 0,02 (IC −0,04 a 0,07) | −0,00 | −0,02 | **replicou** (negativa) |
| R17 | alta × baixa diferem | razão alta/baixa: tamanho 0,97, velocidade 1,00, correção 1,04; virada topo−fundo +1,1 pp (ICs cruzam 1 / 0) | 1,00 | 1,02 · 1,26 · 1,05 · +2,4 pp | **replicou** (negativa: simétricas) |
| R18 | agressão forte a favor → continua | AUC 0,489 (X=250) e 0,529 (X=500), p 0,39 e 0,10 | 0,50 | 0,452 (p 0,06) e 0,412 (p 0,03) | **falhou** (efeito de set aparece só em set; sinal troca com X) |
| R19 | pernada esticada do VWAP vira mais | AUC 0,508; P(vira) 32,4% (>1,5 ATR) × 31,5% (≤1,5) | 0,50 | 0,539; 32,4 × 29,2% | **falhou** |
| R25 | volume da vela anterior prevê o tamanho | Spearman M5 0,00, M15 0,04 | ±0,03 | 0,13 · 0,15 | **replicou** (negativa) |
| R26 | WDO antecipa o WIN | lag 0 −0,50; WDO lidera 1 min +0,006, 2 min −0,004; oposto em 83,5% das pernadas | oposto 83,1% (nulo) | −0,41 · +0,02 · −0,05 · 78% | **replicou** (negativa: anda contra, mas no mesmo minuto) |
| base | dentro da pernada = acaso | 7,4 pernadas/dia e 3,25 correções/perna | 7,4 e 3,43 | 9,1 e 3,13 | **replicou** na contagem; correções ~5% abaixo do nulo (ressalva) |

## Observações principais

1. **R13 é a única pista de pernada que sumiu por completo**: em set/26 deu 42% contra 48% do nulo (z −2,5, n=150), mas nos 8 meses deu 49,1% contra 49,1%. Nenhum mês isolado passa de |z|=1,5. Era acaso de uma janela.
2. **R14, R15, R16, R17 e R25 (as "negativas") se repetem**: as probabilidades de virada por recuo batem com o acaso mês a mês (z entre −1,9 e +1,1 nas 32 células mês×X) e com os valores de set/26 (18–21 / 27–32 / 46–49 / 63–66%). Nenhum indicador (médias, RSI, divergência, VWAP, volume, vela do extremo, velocidade) tem AUC fora de 0,47–0,52 no pool.
3. **R18 foi um efeito de setembro.** Com o fluxo reconstruído pela regra do tick, set/26 reproduz o achado (AUC 0,45/0,41, p 0,06/0,03), mas mar–ago dão 0,46–0,57 sem consistência e o pool fica em 0,49/0,53 — sinal diferente entre X=250 e X=500. Com as flags reais (só 12–31/ago, 252 e 122 eventos) o AUC foi 0,54/0,61 (IC largo, direção oposta à de set). Tratar como falhou.
4. **R19 não replica**: a distância do extremo ao VWAP é em mediana 1,59 ATR M5 nas viradas e 1,57 nas continuações; em set/26 era 1,51 × 1,35 (mesma direção do relatório de origem). O AUC mensal oscila 0,48–0,56 sem direção estável.
5. **R26**: a correlação simultânea WIN×WDO é −0,50 (jan–ago) e o dólar anda contra o WIN em 83,5% das pernadas — mas o nulo com a mesma permutação aplicada aos dois também dá 83,1%, ou seja, é só a correlação do mesmo minuto. O WDO não lidera (lags +1/+2 ≈ 0); o WIN lidera o WDO em 1 minuto com +0,033 (IC 0,023–0,042), efeito minúsculo.
6. **Base**: o nº de pernadas por dia é igual ao do nulo em todos os meses. As correções por perna do real ficam consistentemente um pouco abaixo do nulo (3,25 × 3,43; o IC do real, 3,14–3,37, não cobre a média do nulo) — como já notado na rodada 1. A ordem das velas carrega um sinal fraco de menos correção, de magnitude pequena.

## Método (e o que foi declarado, não mudado)

- **Dados**: WIN@D M1 contínuo (ajuste por diferença), 2026-01-02 a 2026-09-30; 187 pregões com ≥100 velas (166 em jan–ago, 21 em set). WDO@D M1 só para R26 (termina em 29/09 10:20). O relatório original de set/26 usou WINV26; aqui set/26 vem da série contínua, e os números batem (R13: 150 pares, 42% × 48%; 9,1 pernadas/dia contra 9,05).
- **Pernada**: zigzag de 750 pts sobre o caminho da vela (alta mín→máx, baixa máx→mín), 4 pontos por vela, velas encadeadas dentro do pregão, estado só com o passado. "Fechada" = pivô confirmado; a última do dia é aberta e sai das medidas de tamanho.
- **Nulo**: velas M1 (forma + retorno) embaralhadas dentro de blocos de 30 min de cada pregão (bloco = (minuto−540)//30), reencadeadas; 200 simulações por pregão; o nulo de um mês soma os pregões do mês em cada simulação e reporta média e [p5;p95]. IC do real = bootstrap de pregões (1.000 reamostragens; 500 no R17; 150 nos AUCs).
- **R13**: pares de pernadas fechadas consecutivas do mesmo pregão (inclui a 1ª do dia); critério = tamanho(n+1) ≥ tamanho(n).
- **R14**: um evento por (extremo corrente, X) quando o recuo atinge X, só com alta acumulada da perna ≥ 750; vira = o preço recua 750 do extremo antes de fazer novo extremo; eventos sem desfecho no dia são descartados; topo e fundo juntos. Evento em que o preço atravessa X e 750 no mesmo ponto não é registrado (igual ao kit original).
- **R15/R18/R19**: mesmos eventos de R14 (X=250 e 500); indicadores do último minuto completo antes da vela do evento (EMA9/21 e RSI14 de Wilder na série contínua; VWAP do dia desde 09:00 com volume; ATR M5 = média do range das últimas 5 velas M5 completas do dia). Sinais alinhados com a virada. AUC estratificado por faixa de hora (<10:30, 10:30–13:00, ≥13:00) × tamanho da alta (<1250, 1250–2000, ≥2000); p por permutação do rótulo dentro do estrato (200 permutações; só para jan–ago e set).
- **R17**: pernadas fechadas sem a 1ª do dia; correção máxima = maior recuo desde o extremo corrente dentro da perna.
- **R25**: pernadas de zigzag 750 sobre velas M5 e M15 (caminho da vela), vela anterior à que contém o pivô de início; volume relativo = volume / média do mesmo horário no mesmo mês; Spearman com o tamanho; pernadas que começam na 1ª vela do dia saem.
- **R26**: movimento do WDO entre o pivô de início e o extremo da pernada do WIN (variação de fechamento M1); oposto = sinal contrário. Nulo = a mesma permutação das velas aplicada aos retornos do WDO. Correlação de retornos M1 por pregão, defasagens −2 a +2.
- **Base**: "correção" = recuo ≥ max(50 pts, 30% do avanço corrente) a partir do extremo corrente da perna, contada uma vez por extremo (leitura mais próxima de "recuo ≥30% do avanço e ≥50 pts", a definição exata não estava no material).

### Desvios da instrução

- **O cache de ticks contínuo (WIN@D) NÃO traz o lado do agressor**: `flags` é constante em cada arquivo (1080 ou 1336) e bid/ask são zero, em todos os meses, inclusive set. Só o cache WINV26 tem flags 32/64 reais, mas o contrato era ilíquido antes de ~12/08 (volume diário de dezenas a milhares de contratos). O R18 foi então medido de duas formas: (a) fluxo reconstruído pela **regra do tick** sobre os negócios do WIN@D (mar–set; concordância de 78% por negócio e correlação 0,97 do delta por minuto com as flags reais em 2 pregões de set/26) — medida principal; (b) flags reais do WINV26 só de 12/08 a 30/09 (em ago, só 12–31/ago, n pequeno). Fuso conferido: primeiro negócio 09:00–09:04.
- Fluxo da perna = (compras−vendas)/volume dos minutos entre o início da perna e o minuto anterior ao evento (janela por minuto).
- R15 usou indicadores de M1; o "fluxo" do R15 está coberto pelo R18; divergência de RSI = melhor RSI da perna menos o RSI do extremo.
- Scripts em `rodada3/replica_pernada/` (`core.py`, `run_dias.py`, `agg.py`, `agg2.py`, `r25_r26.py`, `prep_ticks.py`, `gen_md.py`).

## Tabelas por mês

Valor real; "nulo" = média das 200 simulações (jan–ago com [p5;p95]); IC95 por bootstrap de pregões na coluna jan–ago. AUC 0,50 = nada. Na linha de fluxo real, a coluna ago cobre só 12–31/ago e jan–ago é a mesma amostra.

### R13 — a pernada seguinte passa do início da anterior

| métrica | jan/26 | fev/26 | mar/26 | abr/26 | mai/26 | jun/26 | jul/26 | ago/26 | jan–ago [IC95 dias] | set/26 |
|---|---|---|---|---|---|---|---|---|---|---|
| real % | 50,0 | 46,7 | 52,0 | 52,6 | 45,3 | 45,8 | 49,3 | 47,7 | 49,1 [46,9;51,4] | 42,0 |
| nulo (blocos 30 min) % | 48,6 | 48,1 | 50,9 | 48,5 | 44,4 | 50,7 | 48,0 | 50,5 | 49,1 [47,5;50,6] | 48,1 |
| z real−nulo | 0,4 | -0,5 | 0,6 | 1,4 | 0,3 | -1,5 | 0,4 | -0,9 | -0,0 | -2,5 |
| n pares | 100 | 122 | 225 | 97 | 86 | 107 | 71 | 86 | 894 | 150 |

### R14 — P(recuo de X chegar a 750 antes de novo extremo | alta ≥ 750), eventos de topo e fundo

| métrica | jan/26 | fev/26 | mar/26 | abr/26 | mai/26 | jun/26 | jul/26 | ago/26 | jan–ago [IC95 dias] | set/26 |
|---|---|---|---|---|---|---|---|---|---|---|
| X=150 real % | 21,1 | 20,5 | 20,9 | 19,7 | 19,7 | 22,1 | 18,8 | 18,6 | 20,3 [19,2;21,3] | 20,7 |
| X=150 nulo % | 20,8 | 22,6 | 21,7 | 21,0 | 20,1 | 22,5 | 19,6 | 19,2 | 21,1 [20,3;21,9] | 20,9 |
| X=150 z | 0,2 | -1,7 | -0,9 | -1,0 | -0,3 | -0,3 | -0,6 | -0,5 | -1,9 | -0,2 |
| X=250 real % | 34,9 | 34,4 | 31,3 | 31,2 | 31,9 | 33,4 | 29,8 | 29,6 | 32,0 [30,5;33,6] | 30,7 |
| X=250 nulo % | 32,5 | 35,4 | 33,0 | 32,8 | 32,6 | 35,0 | 31,4 | 31,1 | 33,0 [31,9;34,1] | 31,7 |
| X=250 z | 1,1 | -0,5 | -1,3 | -0,8 | -0,3 | -0,9 | -0,7 | -0,7 | -1,6 | -0,6 |
| X=375 real % | 49,3 | 52,4 | 44,6 | 45,9 | 51,0 | 48,6 | 46,7 | 45,5 | 47,5 [45,5;49,6] | 47,3 |
| X=375 nulo % | 47,6 | 51,5 | 48,4 | 48,6 | 48,8 | 51,2 | 47,3 | 46,9 | 48,8 [47,4;50,2] | 47,0 |
| X=375 z | 0,6 | 0,3 | -1,9 | -1,0 | 0,7 | -1,0 | -0,2 | -0,5 | -1,5 | 0,1 |
| X=500 real % | 66,5 | 68,1 | 61,8 | 62,6 | 69,1 | 70,0 | 61,7 | 61,3 | 64,7 [62,4;67,2] | 63,7 |
| X=500 nulo % | 63,1 | 67,0 | 63,7 | 64,9 | 65,8 | 67,2 | 64,0 | 63,3 | 64,8 [62,8;66,4] | 63,2 |
| X=500 z | 0,9 | 0,4 | -0,8 | -0,7 | 0,9 | 0,9 | -0,6 | -0,6 | -0,1 | 0,2 |
| n eventos X=250 | 321 | 401 | 773 | 362 | 332 | 377 | 312 | 348 | 3226 | 541 |

### R16 — correlação do log do tamanho da pernada n com a n+1

| métrica | jan/26 | fev/26 | mar/26 | abr/26 | mai/26 | jun/26 | jul/26 | ago/26 | jan–ago [IC95 dias] | set/26 |
|---|---|---|---|---|---|---|---|---|---|---|
| real | 0,06 | -0,03 | -0,11 | 0,07 | 0,10 | 0,03 | 0,12 | 0,08 | 0,02 [-0,04;0,07] | -0,02 |
| nulo | -0,02 | -0,07 | -0,00 | -0,02 | 0,01 | 0,00 | 0,07 | -0,04 | -0,00 [-0,04;0,05] | 0,00 |

### R17 — alta × baixa (pernadas fechadas sem a 1ª do dia; razão alta/baixa das medianas; virada X=250 topo menos fundo em pp)

| métrica | jan/26 | fev/26 | mar/26 | abr/26 | mai/26 | jun/26 | jul/26 | ago/26 | jan–ago [IC95 dias] | set/26 |
|---|---|---|---|---|---|---|---|---|---|---|
| tamanho (alta/baixa) | 0,98 | 1,04 | 1,00 | 0,90 | 0,84 | 0,99 | 1,03 | 0,96 | 0,97 [0,91;1,04] | 1,02 |
| velocidade pts/min | 0,81 | 1,08 | 0,93 | 0,98 | 1,33 | 1,12 | 1,25 | 0,88 | 1,00 [0,88;1,15] | 1,26 |
| correção máx. | 1,16 | 0,90 | 1,11 | 1,10 | 0,87 | 0,99 | 1,05 | 0,99 | 1,04 [0,97;1,12] | 1,05 |
| P(vira) topo−fundo, pp | -8,6 | 0,9 | -2,8 | 3,2 | 11,9 | 4,4 | -0,5 | 4,3 | 1,1 [-1,9;4,0] | 2,4 |
| n pernadas alta/baixa | 48/52 | 59/63 | 115/110 | 48/49 | 43/43 | 56/51 | 32/39 | 45/41 | 446/448 | 75/75 |

### R15 — indicadores no momento do recuo vs virada (AUC estratificado hora × tamanho; 0,50 = nada)

| AUC (X=250) | jan/26 | fev/26 | mar/26 | abr/26 | mai/26 | jun/26 | jul/26 | ago/26 | jan–ago [IC95 dias] | set/26 |
|---|---|---|---|---|---|---|---|---|---|---|
| cruzamento EMA9/21 (contra a perna) | 0,488 | 0,489 | 0,520 | 0,483 | 0,413 | 0,459 | 0,526 | 0,565 | 0,493 [0,473;0,519] p=0,47 | 0,543 p=0,14 |
| distância à EMA21 | 0,564 | 0,448 | 0,483 | 0,510 | 0,538 | 0,524 | 0,405 | 0,368 | 0,482 [0,452;0,504] p=0,09 | 0,510 p=0,73 |
| RSI14 | 0,537 | 0,464 | 0,484 | 0,525 | 0,555 | 0,533 | 0,434 | 0,394 | 0,488 [0,464;0,508] p=0,22 | 0,503 p=0,89 |
| divergência de RSI | 0,431 | 0,566 | 0,522 | 0,496 | 0,549 | 0,565 | 0,523 | 0,495 | 0,516 [0,497;0,537] p=0,09 | 0,490 p=0,70 |
| distância do extremo ao VWAP (ATR M5) | 0,476 | 0,497 | 0,521 | 0,559 | 0,528 | 0,494 | 0,510 | 0,489 | 0,508 [0,486;0,530] p=0,46 | 0,539 p=0,15 |
| volume do último minuto vs perna | 0,544 | 0,465 | 0,501 | 0,502 | 0,546 | 0,560 | 0,487 | 0,451 | 0,505 [0,483;0,527] p=0,70 | 0,514 p=0,58 |
| volume do minuto pré-extremo | 0,495 | 0,493 | 0,486 | 0,541 | 0,532 | 0,536 | 0,457 | 0,464 | 0,501 [0,481;0,525] p=0,95 | 0,517 p=0,68 |
| corpo da vela do extremo | 0,425 | 0,584 | 0,542 | 0,466 | 0,539 | 0,536 | 0,530 | 0,506 | 0,517 [0,493;0,538] p=0,11 | 0,506 p=0,81 |
| pavio do extremo | 0,477 | 0,474 | 0,517 | 0,504 | 0,546 | 0,452 | 0,545 | 0,563 | 0,507 [0,484;0,530] p=0,53 | 0,493 p=0,83 |
| velocidade da perna | 0,498 | 0,439 | 0,575 | 0,488 | 0,454 | 0,441 | 0,415 | 0,506 | 0,490 [0,464;0,512] p=0,36 | 0,515 p=0,62 |
| n eventos | 319 | 398 | 770 | 362 | 331 | 376 | 310 | 347 | 3213 | 540 |

| AUC (X=500) | jan/26 | fev/26 | mar/26 | abr/26 | mai/26 | jun/26 | jul/26 | ago/26 | jan–ago [IC95 dias] | set/26 |
|---|---|---|---|---|---|---|---|---|---|---|
| cruzamento EMA9/21 (contra a perna) | 0,417 | 0,491 | 0,500 | 0,502 | 0,458 | 0,476 | 0,569 | 0,587 | 0,510 [0,482;0,537] p=0,57 | 0,461 p=0,32 |
| distância à EMA21 | 0,544 | 0,480 | 0,529 | 0,506 | 0,566 | 0,467 | 0,418 | 0,432 | 0,489 [0,462;0,517] p=0,50 | 0,526 p=0,53 |
| RSI14 | 0,548 | 0,495 | 0,519 | 0,492 | 0,553 | 0,485 | 0,452 | 0,429 | 0,486 [0,457;0,514] p=0,31 | 0,547 p=0,29 |
| divergência de RSI | 0,468 | 0,597 | 0,485 | 0,423 | 0,529 | 0,584 | 0,550 | 0,483 | 0,506 [0,468;0,536] p=0,74 | 0,468 p=0,42 |
| distância do extremo ao VWAP (ATR M5) | 0,489 | 0,505 | 0,504 | 0,547 | 0,521 | 0,470 | 0,497 | 0,541 | 0,502 [0,473;0,535] p=0,90 | 0,551 p=0,14 |
| volume do último minuto vs perna | 0,624 | 0,588 | 0,465 | 0,469 | 0,575 | 0,488 | 0,430 | 0,460 | 0,498 [0,465;0,531] p=0,92 | 0,566 p=0,08 |
| volume do minuto pré-extremo | 0,506 | 0,451 | 0,560 | 0,574 | 0,482 | 0,509 | 0,413 | 0,480 | 0,505 [0,478;0,538] p=0,61 | 0,514 p=0,72 |
| corpo da vela do extremo | 0,406 | 0,525 | 0,509 | 0,443 | 0,548 | 0,471 | 0,520 | 0,458 | 0,492 [0,464;0,523] p=0,63 | 0,472 p=0,47 |
| pavio do extremo | 0,436 | 0,478 | 0,537 | 0,514 | 0,576 | 0,416 | 0,571 | 0,559 | 0,520 [0,489;0,552] p=0,20 | 0,494 p=0,98 |
| velocidade da perna | 0,436 | 0,358 | 0,567 | 0,531 | 0,487 | 0,346 | 0,406 | 0,490 | 0,472 [0,434;0,510] p=0,12 | 0,493 p=0,94 |
| n eventos | 155 | 191 | 368 | 171 | 152 | 169 | 149 | 160 | 1515 | 250 |

### R18 — fluxo agressor a favor da pernada vs virada

| AUC (X=250) | jan/26 | fev/26 | mar/26 | abr/26 | mai/26 | jun/26 | jul/26 | ago/26 | jan–ago [IC95 dias] | set/26 |
|---|---|---|---|---|---|---|---|---|---|---|
| fluxo agressor da perna (regra do tick) | - | - | 0,502 | 0,531 | 0,472 | 0,463 | 0,461 | 0,534 | 0,489 [0,458;0,513] p=0,39 | 0,452 p=0,06 |
| fluxo agressor da perna (flags reais WINV26, 12–31/ago + set) | - | - | - | - | - | - | - | 0,536 | 0,536 [0,436;0,602] p=0,51 | 0,489 p=0,78 |
| n eventos | 0 | 0 | 769 | 362 | 331 | 374 | 309 | 345 | 2490 | 536 |

| AUC (X=500) | jan/26 | fev/26 | mar/26 | abr/26 | mai/26 | jun/26 | jul/26 | ago/26 | jan–ago [IC95 dias] | set/26 |
|---|---|---|---|---|---|---|---|---|---|---|
| fluxo agressor da perna (regra do tick) | - | - | 0,554 | 0,570 | 0,523 | 0,568 | 0,458 | 0,561 | 0,529 [0,503;0,561] p=0,10 | 0,412 p=0,03 |
| fluxo agressor da perna (flags reais WINV26, 12–31/ago + set) | - | - | - | - | - | - | - | 0,613 | 0,613 [0,505;0,754] p=0,03 | 0,462 p=0,39 |
| n eventos | 0 | 0 | 368 | 171 | 152 | 169 | 148 | 159 | 1167 | 249 |

### R19 — extremo esticado do VWAP vira mais?

| AUC (X=250) | jan/26 | fev/26 | mar/26 | abr/26 | mai/26 | jun/26 | jul/26 | ago/26 | jan–ago [IC95 dias] | set/26 |
|---|---|---|---|---|---|---|---|---|---|---|
| distância do extremo ao VWAP (ATR M5) | 0,476 | 0,497 | 0,521 | 0,559 | 0,528 | 0,494 | 0,510 | 0,489 | 0,508 [0,486;0,530] p=0,46 | 0,539 p=0,15 |
| n eventos | 319 | 398 | 770 | 362 | 331 | 376 | 310 | 347 | 3213 | 540 |

| P(vira), X=250 | jan/26 | fev/26 | mar/26 | abr/26 | mai/26 | jun/26 | jul/26 | ago/26 | jan–ago [IC95 dias] | set/26 |
|---|---|---|---|---|---|---|---|---|---|---|
| dist > 1,5 ATR M5 % | 33,5 (n=182) | 32,8 (n=201) | 33,2 (n=367) | 29,9 (n=184) | 35,1 (n=188) | 34,0 (n=191) | 28,7 (n=164) | 30,1 (n=186) | 32,4 (n=1663) | 32,4 (n=256) |
| dist ≤ 1,5 ATR % | 36,5 (n=137) | 35,5 (n=197) | 29,5 (n=403) | 32,6 (n=178) | 28,0 (n=143) | 32,4 (n=185) | 31,5 (n=146) | 28,6 (n=161) | 31,5 (n=1550) | 29,2 (n=284) |
| mediana dist, vira | 1,62 | 1,48 | 1,54 | 1,45 | 1,81 | 1,54 | 1,51 | 1,60 | 1,59 | 1,51 |
| mediana dist, segue | 1,90 | 1,58 | 1,32 | 1,55 | 1,71 | 1,56 | 1,72 | 1,67 | 1,57 | 1,35 |

### R25 — Spearman(volume relativo da vela anterior ao início, tamanho da pernada)

| métrica | jan/26 | fev/26 | mar/26 | abr/26 | mai/26 | jun/26 | jul/26 | ago/26 | jan–ago [IC95 dias] | set/26 |
|---|---|---|---|---|---|---|---|---|---|---|
| rho M5 | 0,15 | 0,05 | -0,15 | -0,09 | 0,13 | 0,00 | 0,09 | 0,07 | 0,00 [-0,07;0,07] | 0,13 |
| n / sd do nulo M5 | 93 / 0,10 | 117 / 0,09 | 206 / 0,07 | 92 / 0,10 | 88 / 0,11 | 104 / 0,10 | 68 / 0,13 | 72 / 0,12 | 840 / 0,03 | 143 / 0,08 |
| rho M15 | 0,14 | -0,05 | -0,07 | 0,15 | 0,20 | 0,02 | 0,08 | 0,03 | 0,04 [-0,03;0,12] | 0,15 |
| n / sd do nulo M15 | 88 / 0,11 | 107 / 0,10 | 183 / 0,07 | 90 / 0,11 | 78 / 0,11 | 92 / 0,11 | 58 / 0,14 | 66 / 0,13 | 762 / 0,04 | 121 / 0,09 |

### R26 — dólar (WDO) × WIN

| métrica | jan/26 | fev/26 | mar/26 | abr/26 | mai/26 | jun/26 | jul/26 | ago/26 | jan–ago [IC95 dias] | set/26 |
|---|---|---|---|---|---|---|---|---|---|---|
| pernadas do WIN com WDO em sentido oposto, real % | 83,0 | 81,3 | 89,0 | 86,7 | 86,8 | 81,3 | 76,9 | 75,0 | 83,5 [81,0;85,7] | 78,3 |
| idem, nulo (mesma permutação nos dois) % | 78,3 | 81,3 | 88,6 | 85,8 | 85,0 | 83,2 | 78,5 | 76,6 | 83,1 [81,4;84,6] | 80,5 |
| n pernadas | 112 | 134 | 245 | 113 | 106 | 123 | 91 | 100 | 1024 | 152 |

| corr. de retornos M1 | jan/26 | fev/26 | mar/26 | abr/26 | mai/26 | jun/26 | jul/26 | ago/26 | jan–ago [IC95 dias] | set/26 |
|---|---|---|---|---|---|---|---|---|---|---|
| lag 0 (mesmo minuto) | -0,400 | -0,473 | -0,613 | -0,515 | -0,502 | -0,504 | -0,467 | -0,350 | -0,499 [-0,516;-0,476] | -0,414 |
| WDO lidera 1 min | 0,006 | 0,031 | 0,002 | -0,009 | -0,006 | 0,017 | -0,000 | 0,014 | 0,006 [-0,004;0,017] | 0,022 |
| WDO lidera 2 min | 0,009 | -0,028 | -0,024 | 0,029 | -0,005 | 0,007 | 0,014 | -0,001 | -0,004 [-0,014;0,005] | -0,047 |
| WIN lidera 1 min | 0,047 | 0,053 | 0,030 | 0,033 | 0,008 | 0,041 | 0,039 | 0,011 | 0,033 [0,023;0,042] | -0,006 |
| WIN lidera 2 min | 0,008 | -0,009 | -0,011 | 0,009 | 0,000 | -0,005 | -0,011 | 0,000 | -0,004 [-0,013;0,004] | -0,010 |

### Base — dentro da pernada = acaso

| métrica | jan/26 | fev/26 | mar/26 | abr/26 | mai/26 | jun/26 | jul/26 | ago/26 | jan–ago [IC95 dias] | set/26 |
|---|---|---|---|---|---|---|---|---|---|---|
| pernadas/dia real | 6,6 | 8,8 | 12,2 | 6,8 | 6,3 | 7,1 | 5,1 | 6,1 | 7,4 [6,8;8,0] | 9,1 |
| pernadas/dia nulo | 6,4 | 9,0 | 12,8 | 6,9 | 6,1 | 6,9 | 5,3 | 6,0 | 7,4 [7,2;7,6] | 9,0 |
| correções/perna real | 2,97 | 3,42 | 3,19 | 3,60 | 3,42 | 3,35 | 3,11 | 2,95 | 3,25 [3,14;3,37] | 3,13 |
| correções/perna nulo | 3,31 | 3,54 | 3,36 | 3,77 | 3,59 | 3,35 | 3,33 | 3,22 | 3,43 [3,34;3,51] | 3,22 |
| dias | 21 | 18 | 22 | 20 | 20 | 21 | 23 | 21 | 166 | 21 |
