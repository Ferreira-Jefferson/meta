# WIN 2026 - o recuo dentro do movimento aponta o tamanho final?

Dados: WIN@D M1, somente 2026. Descoberta jan-jun (122 pregoes), confirmacao jul-ago (44), referencia set (21). Scripts e tabelas brutas em `rodada3/recuo_tamanho/` (`lib.py`, `run.py`, `an.py`; saidas `an_desc/conf/set.txt`, `res_*.pkl`).

## Metodo
- Caminho dentro da vela (alta: min->max; baixa: max->min). Cada pregao separado; os dois lados (alta e baixa) agrupados (R17).
- "Movimento" = do menor preco (piso, que reinicia se o preco o perde) ate a maxima corrente, avanco A >= 150 pts. "Recuo r" = o preco devolveu r x A a partir da maxima (r = 10, 20, 30, 38, 50, 62, 78%). Um evento por nivel por maxima.
- Desfechos olhando para frente, a partir do instante em que o recuo r e atingido: NH = faz nova maxima antes de perder o piso; P1,5A / P2A = chega a piso+1,5A / piso+2A antes de perder o piso. Eventos sem resolucao ate o fim do pregao sao descartados.
- Nulo: velas M1 embaralhadas em blocos de 30 min dentro de cada pregao, mesmo codigo, 300 simulacoes por janela. Excesso = real - media do nulo; z = excesso / desvio do nulo. Em passeio aleatorio P(NH) = 1 - r (ruina do jogador).
- Cortes: tamanho de A (150-250, 250-375, 375-750, >=750), horario do recuo (<11h, 11-13h, >=13h), ordinal do recuo no movimento (1o, 2o, 3o+; pullback de >=20%), duracao do recuo em barras (<=2, 3-8, >8).

## Resultado 1 - sem corte: o recuo NAO diz nada (tabela descoberta | confirmacao | set), P(novo extremo)
| r | n desc | real desc | nulo | z | n conf | real conf | nulo | z | real set | nulo set | z set |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 10% | 8631 | 0,809 | 0,807 | 0,8 | 2455 | 0,803 | 0,806 | -0,7 | 0,825 | 0,807 | 2,6 |
| 20% | 6206 | 0,740 | 0,738 | 0,6 | 1770 | 0,730 | 0,736 | -0,7 | 0,755 | 0,738 | 1,8 |
| 30% | 4706 | 0,668 | 0,671 | -0,6 | 1346 | 0,652 | 0,665 | -1,4 | 0,693 | 0,675 | 1,5 |
| 38% | 3850 | 0,607 | 0,615 | -1,4 | 1131 | 0,592 | 0,608 | -1,5 | 0,647 | 0,624 | 1,6 |
| 50% | 3014 | 0,527 | 0,531 | -0,5 | 891 | 0,515 | 0,521 | -0,5 | 0,554 | 0,546 | 0,5 |
| 62% | 2304 | 0,428 | 0,438 | -1,3 | 681 | 0,438 | 0,428 | 0,6 | 0,460 | 0,458 | 0,1 |
| 78% | 1517 | 0,302 | 0,314 | -1,2 | 430 | 0,282 | 0,307 | -1,3 | 0,332 | 0,335 | -0,1 |

P(2A) por r (desc | conf | set): 38%: 0,302/0,297/0,331 (nulo 0,305/0,298/0,326); 50%: 0,258/0,260/0,284 (nulo 0,261/0,255/0,283). Identico ao nulo. P(virar sem novo extremo) = 1 - NH. Distribuicao do tamanho final = a da ruina do jogador (ex.: recuo de 50%: 53% faz novo extremo, 36% chega a 1,5A, 26% a 2A).

**Nivel de 50%: nem barreira nem imã.** O excesso em 38/50/62% e -0,7/-0,3/-1,0 pp (desc), sem descontinuidade; o recuo que chega a 50% e o que chega a 38% ou 62% seguem a mesma reta 1-r.

## Resultado 2 - cortes (unica estrutura fraca)
Regras congeladas ao fim da descoberta (arquivo `REGRAS_CONGELADAS.txt`), antes de rodar jul-ago:
- F1: A >= 375 e r >= 38% -> menos novos extremos que o acaso.
- F2: A < 375 e r >= 38% -> mais que o acaso.
- F3: 2o recuo ou mais no movimento e r >= 50% -> menos que o acaso.

| regra | metrica | n desc | real/nulo desc | z | n conf | real/nulo conf | z | set (real/nulo, z) |
|---|---|---|---|---|---|---|---|---|
| F1 | NH | 5515 | 0,452/0,485 | -4,2 | 1512 | 0,467/0,483 | -1,0 | 0,540/0,510 (+1,5) |
| F1 | P1,5A | 5515 | 0,282/0,312 | -3,1 | 1512 | 0,274/0,316 | -2,2 | 0,379/0,351 (+1,1) |
| F1 | P2A | 5515 | 0,191/0,220 | -3,1 | 1512 | 0,180/0,224 | -2,5 | 0,285/0,262 (+1,0) |
| F2 | NH | 5170 | 0,553/0,536 | +1,6 | 1621 | 0,518/0,519 | 0,0 | 0,536/0,549 (-0,5) |
| F2 | P2A | 5170 | 0,290/0,279 | +1,0 | 1621 | 0,299/0,262 | +2,0 | 0,252/0,285 (-1,1) |
| F3 | NH | 4477 | 0,402/0,427 | -2,8 | 1262 | 0,418/0,415 | +0,2 | 0,446/0,450 (-0,2) |
| F3 | P2A | 4477 | 0,177/0,198 | -2,2 | 1262 | 0,175/0,194 | -1,0 | 0,221/0,228 (-0,3) |

F1 em set/26 inverte (+3 pp). Outros cortes (horario, duracao do recuo): sem padrao consistente entre descoberta, confirmacao e set (ex.: duracao >8 barras em 38%: -4,7 pp desc, -0,1 conf). Recuos muito rapidos (<=2 barras) sao 90% dos casos e iguais ao nulo.

## Contagem de comparacoes
Descoberta: 294 celulas (7 niveis x [1 + 4 + 3 + 3 + 3 cortes] x 3 metricas, n>=30) + 9 das regras agrupadas = 303. |z|>=2: 25 (esperado ao acaso ~14 se fossem independentes; sao muito correlacionadas, sobreposicao de niveis). Na confirmacao 35/303 e em set 6/300 passam de |z|>=2, sem repetir as mesmas celulas.
