# Confluencia M5 x barreira M15/H1 (WIN, 2026)

Scripts: `rodada3/confluencia/` (lib.py, runner.py, run_desc.py, run_conf.py, an.py, rank.py, pooled.py, rank_conf.py, frozen.json).

## Metodo
- Dados: so 2026. Descoberta jan-jun, confirmacao jul-ago (setembro nao usado). Barras de 09:00 a 17:54.
- Evento: M1 em queda ativa (maximo dos ultimos 60 min menos fechamento >= D, e fechamento abaixo do de 15 min antes; espelhado para alta) que ENTRA a ate N pts de uma barreira vinda de fora da zona (da distancia >N para 0..N, do lado certo). Um evento por familia/direcao a cada 30 min. Janela 09:30-16:50. D em {300, 600}, N em {100, 200}.
- Resultado (60 min, caminho dentro da vela): B = repique de Y antes de continuar Z (150/150, 250/250, 400/250); S = continuacao primeiro; PL = faixa dos 20 min seguintes <= 400 pts (plato); deriva 60 min.
- Metrica primaria: B250 = P(sobe 250 antes de cair 250 | queda tocando suporte; espelhado para resistencia).
- Nulos: (a) niveis deslocados por um deslocamento aleatorio por dia (U -1500..+1500 pts), 40 repeticoes; mesma dinamica, sem significado do nivel; reponderado ao mix de hora (4 faixas) dos eventos reais. (b) velas M1 embaralhadas em blocos de 30 min, pipeline inteiro refeito (barreiras incluidas), 16 repeticoes. z = (obs - nulo)/max(dp do nulo, dp binomial).
- Barreiras (34 familias): pivos M15 (k=2,3) e H1 (k=2,3) - ultimos 4; max/min do dia ate t-1; H/L/fechamento do dia anterior; abertura; maxmin dos primeiros 30 e 60 min; VWAP, VWAP+-1dp, +-2dp; EMA21/EMA50/SMA200 do M15; EMA20/EMA50/SMA100 do H1; retracao 38/50/62% da ultima perna H1; POC, VAL/VAH (15%/85%) e POC anterior do perfil de volume; nivel tocado >=3 vezes (extremos M5, bins de 100 pts); retorno percentual +-0,5/1/1,5/2% da abertura e do fechamento anterior. Numero redondo nao testado (serie ajustada por diferenca).
- Total: 34 familias x 2 N x 2 D = 136 configuracoes (132 com n>=60), x 3 pares (Y,Z) + plato + deriva; 56 execucoes da serie por rodada.

## Descoberta (jan-jun): ranking por |z| em B250 (n>=60)
Base (nulo deslocado, B250): 0,496. Das 119 configuracoes com n>=60: |z|>2 em 5 (esperado por acaso ~5,4); |z|>3 em 0. Nada destoa alem do acaso. Tendencia: quase todas apontam para MENOS repique que o nulo (continuacao pelo nivel).

| familia | N | D | n | B250 obs | nulo desl. | nulo emb. | z desl. | z emb. | meia 1 / meia 2 (dif.) |
|---|---|---|---|---|---|---|---|---|---|
| h1_ema50 | 100 | 600 | 80 | 0,388 | 0,515 | 0,455 | -2,3 | -1,2 | -0,08 / -0,19 |
| pctPC_0,5 (fech. anterior +-0,5%) | 100 | 300 | 322 | 0,432 | 0,495 | 0,488 | -2,1 | -2,0 | -0,07 / -0,05 |
| vwap | 200 | 300 | 366 | 0,434 | 0,498 | 0,488 | -2,1 | -1,7 | -0,07 / -0,06 |
| touch (nivel tocado 3x) | 200 | 600 | 160 | 0,406 | 0,488 | 0,504 | -2,1 | -2,5 | -0,03 / -0,14 |
| poc (perfil de volume) | 100 | 300 | 343 | 0,431 | 0,493 | 0,488 | -2,0 | -2,1 | -0,06 / -0,07 |
| piv15_k2 | 100 | 600 | 437 | 0,453 | 0,496 | 0,511 | -1,8 | -2,4 | -0,07 / -0,01 |
| prevpoc | 200 | 600 | 88 | 0,591 | 0,496 | 0,519 | +1,8 | +1,3 | +0,19 / -0,04 |
| piv15_k3 | 100 | 300 | 655 | 0,450 | 0,487 | 0,496 | -1,7 | -2,3 | -0,04 / -0,04 |
| m15_ema21 | 200 | 300 | 352 | 0,449 | 0,497 | 0,487 | -1,7 | -1,4 | |
Fibonacci H1, bandas de VWAP, max/min do dia, dia anterior, abertura, OR30/OR60, medias H1/M15 longas, pivos H1: |z|<1,5.
Todas as barreiras agrupadas (9.894 eventos, N100 D300): B250 0,479 contra 0,488 (z -1,5; z emb. -2,7). Efeito de ~1 pp.
Plato (faixa 20 min <=400 pts): nenhuma barreira ficou consistentemente acima do nulo (piv15_k3 N100 D300 z +3,1 isolado, uma de 119).
Melhor definicao de barreira: nenhuma separa; as de "valor" (VWAP, POC, fechamento anterior +-0,5%, nivel tocado) apontam para menos repique, as de tendencia (medias, fib, pivos) ficam no acaso.

## Congelado antes da confirmacao (frozen.json)
Criterio: |z desl.|>=2, |z emb.|>=1,5, n>=60, mesmo sinal nas duas metades. Congelados: pctPC_0,5 (N100 D300), vwap (N200 D300), touch (N200 D600), poc (N100 D300). Hipotese: B250 abaixo do nulo (a queda tende a atravessar o nivel). Aceita se mesmo sinal e |z desl.|>=1,5 em jul-ago.

## Confirmacao (jul-ago), regras congeladas
| familia (N,D) | n | B250 obs | nulo desl. | nulo emb. | z desl. | z emb. | jul / ago | B150 obs/nulo | B400 | continuacao S250 | plato |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pctPC_0,5 (100,300) | 99 | 0,465 | 0,483 | 0,495 | -0,3 | -0,6 | +0,01 / -0,05 | 0,505/0,514 | 0,313/0,342 | 0,485/0,468 | 0,17/0,27 |
| vwap (200,300) | 114 | 0,430 | 0,477 | 0,469 | -0,7 | -0,8 | +0,04 / -0,15 | 0,474/0,519 | 0,298/0,324 | 0,518/0,474 | 0,29/0,29 |
| touch (200,600) | 45 | 0,467 | 0,470 | 0,481 | 0,0 | -0,2 | -0,07 / +0,04 | 0,467/0,493 | 0,422/0,339 | 0,511/0,511 | 0,13/0,18 |
| poc (100,300) | 98 | 0,398 | 0,477 | 0,511 | -1,5 | -2,1 | -0,09 / -0,07 | 0,408/0,515 | 0,255/0,323 | 0,551/0,466 | 0,32/0,34 |
Mesmo sinal em B250 nas 4, mas so o POC chega ao limiar (-1,5 / -2,1, ambos os meses negativos), no limite e entre 4 testados. Os demais nao confirmam.

## Leitura
- Chegar a uma barreira de M15/H1 NAO aumenta a chance de repique no WIN: 0 de 4 confirmam com folga; 1 (POC do dia) fraca. Nao ha plato mensuravel.
- Resultado negativo util: nao usar barreira (media, pivo, fib, VWAP, nivel) como motivo de entrada/saida de repique. O efeito residual, se existir, e continuacao (~ -5 a -8 pp de repique, +5 a +8 pp de continuacao) perto de POC/VWAP/fechamento anterior, e ainda dentro do ruido.
- Eventos de familias diferentes se sobrepoem (nao sao independentes); n e de eventos, nao de dias.
