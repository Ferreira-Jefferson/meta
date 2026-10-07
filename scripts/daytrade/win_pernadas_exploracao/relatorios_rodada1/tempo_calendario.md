# WIN set/2026 — tempo, relógio e calendário (exploratório)

Base: WINV26 M1, 21 pregões de 01 a 30/09/2026 (nenhum outro período usado; o gap do 1º pregão não foi calculado, n=20). Pernadas: zigzag 750 pts sobre o caminho dentro da vela. Reprodução: M5 195 pernadas (9,3/pregão; 4,5 correções/pernada), M15 177 (8,4; 2,2), H1 127 (6,0; 0,7) — próximo do conhecido (9,0/8,2/5,8); diferença vem de detalhes de borda. Scripts em `tempo/` (t_a a t_d). Tudo é pista (n pequeno).

## 1. Relógio: atividade concentrada no início, dois picos
Média por minuto relativa à média do dia (blocos de 30 min): range 09:00 = 2,10x; 10:00 = 1,81x; 10:30 = 1,95x; 12:00 = 1,07x; 14:00 = 0,74x; 17:30 = 0,40x. Volume idem (2,06x / 2,15x / 2,20x / 1,08x / 0,71x / 0,21x). Dois picos: abertura (09:02-09:05) e 10:00-11:00, com degrau nítido às 10:30: range médio por minuto 10:29 = 246 pts, 10:30 = 390, 10:31 = 383, 10:32 = 372, decaindo a ~250 às 10:37; volume 67 mil -> 137 mil contratos (2x) — compatível com abertura de NY. O minuto 09:03 é o de maior volume/range do dia (186 mil contratos, 801 pts).
Range de 30 min (mediana por pregão): 09:00 1.560; 10:00 1.280; 10:30 1.210; 12:00 685; 14:00 495; 15:30 380.

## 2. Quanto do range do dia já aconteceu
Até 10:30: mediana 71% (média 68%, dp 18%; min 34%, máx 100%). Até 12:00: mediana 92% (média 88%). Até 14:00: mediana 100%, média 96%. Horário da máxima e da mínima do dia: mediana 10:28 e 10:29; quartil inferior 09:05 (máx) e 09:20 (mín). Exceções que "acordaram" tarde: 22/09 (60% às 14h; máxima 16:49), 24/09 (64% às 10:30; mínima 17:23), 11/09 (85% às 14h). Spearman do range diário com volume do dia: 0,55; com a fração feita até 10:30: -0,27 (dias de range grande ainda tinham muito a fazer depois das 10:30). Range dos primeiros 30 min não prediz o do dia (rho -0,01). Volume diário muito uniforme (CV ~7%; 16,0 a 20,8 milhões); 10-13% dele nos primeiros 30 min.

## 3. Pernadas: horário, tamanho, duração, velocidade (M5; M15 em paralelo)
- Início: 54 de 195 pernadas nascem 09:00-09:30, 53 entre 09:30 e 11:00; 40 entre 12-15h; 15 após 15h. Tamanho mediano por início: manhã (<12h) 1.333 (n=140); 12-15h 1.160 (n=40); 15h+ 1.010 (n=15). Pernadas >3.000 pts só nascem entre 09:00 e 11:00 (máx. 6.265, início 10:00).
- Duração mediana: manhã 20 min; 12-15h 77,5; 15h+ 95. Velocidade mediana (pts/min): 70 / 15 / 12. A tarde faz pernadas de tamanho parecido em 4x o tempo.
- Correções por pernada (M5): manhã 3,8; 12-15h 6,9; 15h+ 5,4. Por 1.000 pts: 1,8 / 5,6 / 4,4. M15: 0,65 / 2,4 / 3,0 por 1.000 pts. Pernada da tarde é "suja" (parte disso é mecânico, ver artefatos).
- Tamanho vs duração: Spearman 0,38 (M5) / 0,33 (M15); tamanho vs nº de correções 0,47 / 0,42; velocidade vs tamanho: -0,08 / 0,01 (nada). Terços de velocidade (M5): rápidas mediana 5 min, 1,1 correção, tamanho 1.235; lentas 115 min, 8,1 correções, tamanho 1.290. Velocidade não diz o tamanho; diz quanto a pernada será "suja".
- Movimento nos 10 primeiros min da pernada vs tamanho final: rho 0,22 (n=178); terço mais forte (1.088 em 10 min) termina em 1.428 vs 1.290 no mais fraco. Efeito fraco e em parte mecânico.
- Ordem no dia (M5): pernadas 1-3 maiores (mediana 1.305 / 1.545 / 1.610); 4ª-5ª ~1.205; da 7ª em diante 1.140 (n=70).
- Direção: 102 baixa / 93 alta; tamanho mediano igual (1.292 vs 1.285).

## 4. Primeira pernada do dia
- M5: tamanho mediano 1.305 (M15 1.550); ~46% (M5) / 49% (M15) do range do dia; duração mediana 5 min (10 de 21 acabam dentro da própria vela das 09:00).
- ARTEFATO PROVÁVEL: a 1ª pernada é de BAIXA em 19/21 (M5) e 21/21 (M15). A vela das 09:00 só tem dados a partir de 09:02 e, com o pico de range da abertura, o caminho "máxima->mínima" da vela fecha o zigzag para baixo. Direção real nos 15 primeiros minutos: 13/21 negativos (mediana -270 pts); excursão máxima abaixo da abertura 765 pts vs 435 acima (medianas). Existe um viés leve para baixo, bem menor que 19/21.
- Vs gap (abertura menos fechamento anterior, n=20): 1ª pernada na direção do gap 11 vezes, contra 9. |gap| vs tamanho da 1ª pernada: rho 0,01 (M5) / 0,07 (M15). |gap| vs range do dia: 0,09. 1ª pernada na mesma direção do dia (abertura->fechamento): 11/21. Retorno 09:00-10:30 vs restante: mesmo sinal 7/21 (rho -0,11); manhã (<12h) vs tarde: mesmo sinal 10/21 (rho -0,31). Reversão leve, indistinguível de ruído.

## 5. Calendário
- Dia da semana (n 3-5 cada): range mediano seg 2.460 (n=3), ter 2.950, qua 3.775, qui 4.385 (n=4), sex 3.060. Volume menor em sex (16,8 mi) e seg (17,8 mi). Pode ser acaso.
- Semana: range médio sem. 1 (1-4/09) 4.841; sem. 2 3.456; sem. 3 3.358; sem. 4 2.843; sem. 5 (28-30/09) 3.202. A volatilidade caiu ao longo do mês. Retorno líquido por semana: +6.795, -830, -1.070, -2.045, +3.515.
- Agenda (datas NÃO verificadas, tratar como incertas): 04/09 (suposto payroll) range 3.470, 81% até 10:30, volume 16,9 mi; 10/09 (suposto IPCA) range 4.505, só 34% até 10:30, ret +2.965; 16/09 (suposto Copom/FOMC) range 3.320, 82% até 10:30; 17/09 range 4.620, 40% até 10:30; 18/09 (3ª sexta, opções de ações) range 2.850, 92% até 10:30, volume 16,0 mi (o menor do mês). Dois dos dias de agenda (10/09, 17/09) tiveram range "tardio" (35-40% às 10:30) e dois (04/09, 16/09) não. n=5: nada.
- 30/09: 100% do range do dia ocorreu até 10:30 (4.360 pts em 30 min, 184.700 -> 187.700, fechando na máxima); 01/09 também +3.000 de abertura a fechamento. Dias de tendência única.

## 6. Fim do pregão
Últimos 55 min (17:30-18:24): range mediano 380 pts, |retorno| mediano 210. Volume cai a ~0,2x, mas há pico às 18:00 (9 mil vs 5-6 mil) e um spike no último minuto 18:24 (22 mil contratos, range médio 140 pts vs 2-3 mil nos vizinhos) — leilão de fechamento.

## 7. Possíveis artefatos de definição
(a) 1ª pernada de baixa 19/21. (b) Correções/pernada crescem com a duração porque o limiar de 5 pts é fixo: mais minutos, mais chances de recuo. (c) Pernada aberta no fim do dia (21) tem tamanho truncado. (d) O limiar fixo de 750 pts é relativamente mais exigente à tarde (range por minuto 0,4-0,7x da média): menos pernadas e mais lentas. (e) Os blocos de 30 min têm n pequeno à tarde (3-9 pernadas).
