# WIN: semana, mês, alinhamento e viradas (b_semana_mes_viradas)

Estudo descritivo, não é backtest de robô. Script: `b_semana_mes_viradas.py`. CSVs: `b_taxas_dia.csv`, `b_semana_mes.csv`, `b_viradas_dia_auc.csv`, `b_viradas_semana_auc.csv`.

## Método e premissas
- Base: WIN@D M1, 2021-10-01 a 2026-10-01. Série com ajuste por DIFERENÇA, então todas as medidas são em pontos ou em múltiplos de ATR14. Nada é calculado em % do preço ajustado.
- Pregão = todas as barras do dia (abertura = OPEN da 1ª, fechamento = CLOSE da última). O horário de fechamento muda com o horário de verão (17:54 ou 18:24).
- O último dia (2026-10-01, só até 17:17) foi descartado por ser parcial. Restam 1.247 pregões: IS 810 e OOS 437.
- "Direção do dia" = CLOSE > OPEN. Semana = ISO, do open do 1º pregão ao close do último. Semanas com menos de 3 pregões foram ignoradas como "semana". Mês = mês civil (o mês final, set/26, está completo; out/26 só tem 1 dia e foi descartado).
- Amostras: IS 171 semanas e 39 meses; OOS 91 semanas e 21 meses. Os IC de semana e mês são largos.
- Nulo: taxa-base incondicional da própria janela. Alta de dia: IS 51,7% e OOS 51,0%. Alta de semana: IS 45,0% e OOS 54,9%. Alta de mês: IS 48,7% e OOS 66,7%. Teste: z contra a taxa-base. IC de Wilson 95%.
- ATR14 usa só dados até D-1. Estados de "semana/mês até D-1" = open do período de D-1 até o close de D-1. Se D abre um período novo, vale o período completo anterior.
- Comparações múltiplas: 41 taxas de dia testadas por janela. Esperados por acaso com p<0,05: ~2. Observados: 1 no IS e 1 no OOS (e não são os mesmos testes). Ou seja, no conjunto não há mais sinal do que o acaso produz.

## 1. Semana
| condição | IS taxa (n) [IC] | OOS taxa (n) [IC] | nulo IS / OOS |
|---|---|---|---|
| semana W alta, W-1 alta | 49,4% (77) [38,5-60,3] | 57,1% (49) [43,3-70,0] | 45,0% / 54,9% |
| semana W alta, W-1 baixa | 40,9% (93) [31,4-51,0] | 52,4% (42) [37,7-66,6] | idem |
| dia D alta, W-1 alta | 55,2% (366) | 52,1% (234) | 51,7% / 51,0% |
| dia D alta, W-1 baixa | 48,8% (443) | 49,8% (203) | idem |
| 1º dia da semana alta, W-1 alta | 48,1% (77) | 49,0% (49) | idem |
| 1º dia da semana alta, W-1 baixa | 58,1% (93) | 52,4% (42) | idem |

Todos os p são maiores que 0,18. A direção da semana anterior não separa a da semana seguinte, nem a do 1º dia.

Dia da semana (taxa de alta):
- IS: seg 54,6%, ter 51,9%, qua 54,9%, qui 48,8%, sex 48,4%.
- OOS: seg 51,7%, ter 60,2%, qua 40,4%, qui 60,0%, sex 43,2%.
- Quarta e quinta invertem entre as janelas (qua 54,9% → 40,4%; qui 48,8% → 60,0%). Só 1 dos 10 pontos tem p<0,05 (qua OOS, p=0,046), e ele inverte o IS. É padrão instável.
- Dado W-1: sex dado W-1 baixa tem 42,5% no IS (p=0,086) e 41,5% no OOS (p=0,22). Mesma direção nas duas janelas, mas nenhuma é significativa e n≈40-87. É o único candidato fraco, sem teste confirmatório.

## 2. Mês (n pequeno)
| condição | IS | OOS | nulo IS / OOS |
|---|---|---|---|
| mês M alta, M-1 alta | 52,6% (19) [31,7-72,7] | 69,2% (13) [42,4-87,3] | 48,7% / 66,7% |
| mês M alta, M-1 baixa | 47,4% (19) [27,3-68,3] | 62,5% (8) [30,6-86,3] | idem |
| dia D alta, M-1 alta | 51,8% (398) | 53,7% (270) | 51,7% / 51,0% |
| dia D alta, M-1 baixa | 52,0% (392) | 46,7% (167) | idem |
| semana alta, M-1 alta | 45,8% (83) | 56,1% (57) | 45,0% / 54,9% |
| semana alta, M-1 baixa | 43,4% (83) | 52,9% (34) | idem |

Nada se separa do nulo (p>0,26). Os IC dos meses abrangem 30 a 87 pontos percentuais, então o dado não permite concluir nada sobre mês.

## 3. Alinhamento (dia D-1, semana até D-1, mês até D-1)
| estado | IS: P(alta) n, ret ATR | OOS: P(alta) n, ret ATR | nulo IS / OOS |
|---|---|---|---|
| 3 em alta | 54,9% (215), -0,005 | 49,2% (122), -0,004 | 51,7% / 51,0% |
| 3 em baixa | 54,2% (238), +0,016 | 56,3% (103), +0,047 | idem |
| preço > SMA5 e SMA20 | 55,7% (255), +0,033 | 49,2% (181), +0,034 | idem |
| preço < SMA5 e SMA20 | 50,9% (328), -0,005 | 51,8% (139), +0,027 | idem |

- Quando os três estão alinhados em alta a tendência NÃO continua mais: 54,9% no IS e 49,2% no OOS, ambos dentro do ruído. O retorno médio é ≈0 em ATR nas duas janelas.
- Alinhado em baixa: a P(alta) vai para 54-56%, o que seria reversão, mas p>0,28 nas duas.
- Estados isolados (d1, w1, m1, SMA5, SMA20, alta ou baixa): nenhum com p<0,29 em nenhuma janela. As 6 combinações mistas têm n de 18 a 97 e nenhuma é consistente entre IS e OOS. A única com p<0,05 (dia- sem+ mes- no IS, 35,9%, n=39) vira 44,4% no OOS (n=18).
- O retorno médio de D em ATR fica em ±0,05 na maior parte das células, sem relação com o estado.

## 4. Viradas
Definição: virada = o dia D fecha contra uma sequência de 2 dias de mesma direção (D-2 e D-1). Continuação = D fecha a favor. Dojis (ret=0) são excluídos. Taxa de virada: IS 49,0% (n=390) e OOS 50,2% (n=213), ou seja, mesmo a base da moeda. As características são as do dia D-1, com sinal orientado a favor da sequência. AUC > 0,5 = valor maior em viradas. IC de bootstrap e p de permutação (500) estão em `b_viradas_dia_auc.csv`.

| característica (D-1) | AUC IS [IC] | AUC OOS [IC] | AUC nulo |
|---|---|---|---|
| range/ATR | 0,486 [0,425-0,540] | 0,542 [0,461-0,615] | 0,5 |
| CLV (fecha no extremo a favor) | 0,480 [0,424-0,538] | 0,518 [0,434-0,595] | 0,5 |
| volume rel. 20d | 0,483 [0,431-0,538] | 0,485 [0,401-0,574] | 0,5 |
| gap/ATR | 0,516 [0,454-0,576] | 0,569 [0,486-0,640] | 0,5 |
| corpo/range | 0,476 [0,417-0,528] | 0,566 [0,490-0,651] | 0,5 |
| sombra do lado da sequência | 0,520 [0,466-0,574] | 0,482 [0,408-0,558] | 0,5 |
| sombra do lado oposto | 0,522 [0,466-0,576] | 0,430 [0,362-0,505] | 0,5 |
| distância ao extremo da semana/ATR | 0,537 [0,474-0,596] | 0,480 [0,412-0,557] | 0,5 |
| nº de barras que testaram o extremo de D-2 | 0,433 [0,372-0,492] (p=0,022) | 0,522 [0,445-0,585] | 0,5 |

Nenhuma característica tem AUC claramente diferente de 0,5 nas duas janelas. As diferenças de médias são pequenas: por exemplo, range/ATR 0,94 contra 0,96 no IS e 1,01 contra 0,96 no OOS. Várias características mudam de lado entre IS e OOS (corpo, sombra oposta, range). A única com p<0,05 (testes do extremo de ontem, IS) fica em 0,52 no OOS. O melhor valor de AUC em qualquer janela é 0,57 (gap, OOS, p=0,09). Com 18 testes, esperam-se ~1 acerto por acaso.

Virada semanal (sinal da semana W diferente do de W-1, características da W-1; IS n=166 e OOS n=91; taxa de virada 45,8% e 47,3%):
- CLV da semana a favor da direção de W-1: AUC 0,370 no IS (p=0,008) e 0,519 no OOS. Não se confirma.
- range/ATR, corpo/range e volume relativo ficam em 0,44-0,52 e não são significativos.
- Resultado completo em `b_viradas_semana_auc.csv`.

## Tabela final
| achado | IS | OOS | nulo | sobrevive? |
|---|---|---|---|---|
| W-1 alta → W alta | 49,4% (n=77) | 57,1% (n=49) | 45,0% / 54,9% | Não (p>0,44) |
| W-1 → dia D / 1º dia | 55,2% / 48,1% | 52,1% / 49,0% | 51,7% / 51,0% | Não (p>0,18) |
| Dia da semana (qua, qui) | 54,9% / 48,8% | 40,4% / 60,0% | 51,7% / 51,0% | Não (inverte entre janelas) |
| sex, dado W-1 baixa | 42,5% (n=87) | 41,5% (n=41) | 51,7% / 51,0% | Candidato fraco, p>0,08, só direção |
| M-1 → M (n=60 meses) | 52,6% / 47,4% | 69,2% / 62,5% | 48,7% / 66,7% | Não (IC ±25pp) |
| Alinhado dia+sem+mês (alta) | 54,9% (n=215) | 49,2% (n=122) | 51,7% / 51,0% | Não |
| Alinhado em baixa → alta de D | 54,2% (n=238) | 56,3% (n=103) | 51,7% / 51,0% | Não (p>0,28) |
| Preço vs SMA5/20 | 55,7% / 50,9% | 49,2% / 51,8% | 51,7% / 51,0% | Não |
| Viradas de dia: AUC das 9 características | 0,43-0,54 | 0,43-0,57 | 0,50 | Não (nenhuma fora do ruído nas 2 janelas) |
| Virada semanal: CLV da semana | AUC 0,370 (p=0,008) | AUC 0,519 | 0,50 | Não (só IS) |

## Conclusão
Neste WIN M1 (2021-2026), nem o dia anterior, nem a semana, nem o mês, nem o alinhamento entre eles, nem as médias de 5 e 20 dias dão informação direcional que apareça nas duas janelas. As taxas de alta ficam em 49-57% contra uma base de 51% e todos os IC cobrem o nulo. A quantidade de testes que passa de p<0,05 (1 em 41 por janela) é igual ao que o acaso produz. Quando os três períodos estão alinhados, a tendência não continua mais. Em alta o resultado é 49-55%, que é a taxa-base.

As viradas não são antecipáveis por nenhuma das 9 características do dia anterior (AUC 0,43-0,57, sem sinal repetido nas duas janelas). O único achado do IS (CLV semanal, testes do extremo de ontem) não se confirma no OOS.

Limitações:
- Definição de virada: a escolhida foi "2 dias iguais e depois um oposto". Outras definições não foram testadas.
- Direção medida em open → close. Close → close do dia não foi testado.
- Meses e semanas: n pequeno, então não dá para excluir efeitos pequenos.
- O estudo descreve a direção, não mede magnitude nem possibilidade de operar. Qualquer efeito de 1-3 pontos percentuais está abaixo do que n=400-800 detecta.
