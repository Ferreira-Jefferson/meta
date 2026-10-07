# Gerador de hipóteses novas: WIN, setembro/2026

Dados: WINV26 M1 de 01 a 30/09/2026 (21 pregões; agosto só como aquecimento do ATR de 5 dias) e WDO@D M1 de setembro. Script: `rodada2/gerador/checagens.py`, saída em `rodada2/gerador/saida.txt`. Aproximadamente 85 comparações no total (a maior parte são os 60 minutos-da-hora do item D). Tudo é pista: n = 20 a 21 dias, observações intradiárias dependentes.

## Lista de hipóteses (papel candidato; mede com os dados atuais?)

| # | Hipótese | Papel | Mede? |
|---|---|---|---|
| H1 | Degrau das 10:30 (abertura de NY): a atividade dobra e o movimento da manhã tende a ser devolvido depois | LIGA/DESLIGA, DIREÇÃO | sim (checado, A) |
| H2 | Reversão micro na primeira hora: a razão de variância em 5 min é baixa às 9h (movimentos de 1 min são devolvidos) | ACEITA/REJEITA, SAÍDA | sim (checado, B) |
| H3 | Salto de 1 minuto muito acima da mediana da hora é devolvido ou continua nos 5 min seguintes | SAÍDA, DIREÇÃO | sim (checado, B) |
| H4 | Volatilidade em aglomerados: faixa alta no bloco de 15 min prevê faixa alta no seguinte, depois de remover o relógio | LIGA/DESLIGA, TAMANHO± | sim (checado, C) |
| H5 | O dólar antecipa a volatilidade do WIN (não a direção) | LIGA/DESLIGA | sim (checado, C) |
| H6 | Minutos cheios (:00, :30) concentram faixa: agenda de dados e abertura de barra de algoritmos | LIGA/DESLIGA, STOP+ nesses minutos | sim (checado, D) |
| H7 | Manhã (09–10:30) e resto do dia têm sinal oposto | DIREÇÃO (tarde), ALVO− | sim (checado, E) |
| H8 | Gap grande em ATR antecipa extremos tardios e menos range feito cedo (cruza P4 com P6) | LIGA/DESLIGA, ALVO± | sim (checado, E) |
| H9 | Gap com sinal prevê o retorno do resto do dia (gap contra o dia) | DIREÇÃO | sim (checado, E) |
| H10 | Persistência do range diário: range de D-1 em ATR prevê o de D | TAMANHO±, STOP± | sim (checado, C, n=20) |
| H11 | Vencimento de opções (quarta mais próxima do dia 15; 16/09) e dia da semana mudam o range | LIGA/DESLIGA | fraco: 1 vencimento e 4 dias por dia da semana |
| H12 | Tempo desde o último novo extremo do dia (idade do range) antecipa rompimento ou rejeição | ACEITA/REJEITA | sim, a fazer |
| H13 | Coluna SPREAD do M1 (liquidez) antecede faixa maior | LIGA/DESLIGA, STOP+ | sim, a fazer (campo ruidoso, moda 5 pts) |
| H14 | Volume M1 acima de 3× a mediana da hora antecede mais faixa nos 30 min seguintes | LIGA, TAMANHO− | sim, a fazer |
| H15 | Última meia hora (17:30–18:00, leilão de fechamento) devolve ou continua o movimento da tarde | SAÍDA, DIREÇÃO | sim, a fazer (n=21) |
| H16 | Pernada anterior grande × horário: pernada grande às 9h pede alvo diferente de uma às 14h | ALVO± | sim, mas já na chave horário×vol×pernada (outro agente) |
| H17 | Pernada que nasce no minuto cheio é mais longa que a que nasce no meio da hora | ACEITA | sim, a fazer (cruza H6 com pernadas) |
| H18 | Abertura fora da área de valor anterior (60% dos dias) e volta à borda (83%): trade de volta à borda | DIREÇÃO, ALVO | sim, já nas pistas de pontos cegos; precisa de nulo |
| H19 | Assimetria de queda: dólar sobe forte (WDO) em minuto isolado antecede queda do WIN em 2–5 min | ACEITA | sim, mas o lead-lag M1 já deu nulo |
| H20 | Rolagem WINV26→WINZ26: dias próximos da troca têm volume concentrado diferente | LIGA/DESLIGA | não: só um mês |
| H21 | Juros/DI e S&P futuro (NY) como regime | todos | não: sem dado |

## Checagens (5 famílias)

### A. Degrau das 10:30 e continuidade antes/depois (H1)
Janela anterior de 84 min, posterior de 30 min, cortes a cada 5 min das 10:30 às 16:00 (67 cortes) como controle por horário.
- Faixa média por minuto nos 15 min após 10:30 sobre os 15 antes: mediana 1,28. Nos outros cortes: mediana 0,94 [p5 0,83; p95 1,06]. Nenhum dos 67 cortes passa o das 10:30. É o degrau já conhecido, agora com controle.
- Concordância entre o sinal do movimento 09:06–10:29 e o do 10:30–10:59: 7 de 21 (33%). Nos outros cortes: mediana 48% [33%; 65%]. Rho de Spearman -0,19 (outros cortes: -0,04 [-0,32; 0,22]). Está no limite inferior do controle. Binomial 7/21: p~0,19. Pista de reversão, não estável.
- Derruba: concordância em dado novo dentro de 40–60%; o degrau de faixa em si não cai (é mecânico).

### B. Reversão micro e saltos (H2, H3)
Razão de variância em 5 min (VR5), nulo por permutação dos retornos dentro do dia (100 sorteios):
- 9–10h: VR5 0,70, VR15 0,63; nulo 0,98 [0,84; 1,11]. Fora do nulo.
- 10–12h: 1,04 (nulo 1,00 [0,90; 1,08]); 12–15h: 0,97 (0,99 [0,93; 1,06]); 15–18h: 0,94 (0,99 [0,92; 1,06]). Dentro ou na borda.
- Saltos de 1 min (retorno absoluto ≥3× a mediana da hora, depois das 10h): n=1.151, 21 dias; continuação nos 5 min seguintes média -5,7 pts, mediana -10, 46% continuam; IC por dia [-15,4; 4,5]; salto médio 155 pts. Com ≥6×: n=128, média +17,2, mediana -10, IC [-10,2; 45,2]. Nada.
- Leitura: a única reversão fora do nulo é a da primeira hora (n=21 dias, dominada pelos choques dos minutos iniciais, que se devolvem). Pode ser o leilão de abertura e não regra.
- Medir em dado novo: VR5 das 9h em agosto e outubro. Derruba: VR5 dentro de [0,85; 1,10].

### C. Aglomerados de volatilidade e dólar como líder de volatilidade (H4, H5, H10)
Faixa por bloco de 15 min, log, subtraída a média do mesmo horário; nulo embaralha o dia dentro de cada horário (300 sorteios). 632 blocos.
- Correlação de um bloco com o seguinte (mesmo dia): 0,25; nulo [-0,08; 0,08]. Forte. Ressalva: mistura o regime do dia (dia agitado inteiro) com o aglomerado de curto prazo; não separei.
- WDO no bloco t com WIN no bloco t+1: 0,17 (nulo [-0,08; 0,08]); correlação parcial dado o WIN em t: 0,07 (nulo [-0,08; 0,08]). O dólar não acrescenta nada além do próprio WIN.
- Range diário de D-1 com o de D: rho 0,38 (n=20), sem teste de permutação; compatível com a pista P2.
- Medir em dado novo: separar efeito dia de efeito bloco (remover a média do dia do z). Derruba: correlação intradia cair a ~0 depois de remover o regime do dia.

### D. Minutos do relógio (H6)
Faixa M1 relativa à média da mesma hora, 10h–17h sem 10:30–10:32; nulo permuta minutos dentro de cada hora-dia (200 sorteios).
- :00 = 1,57; :30 = 1,25; :01 = 1,23; :02 = 1,21; :03 = 1,19; demais ~0,98. Acima do p95 do nulo (1,11): minutos 0, 1, 2, 3, 15 e 30. O :00 é maior em todas as horas (1,35 a 2,09). O :30 só em parte (1,02 a 1,57; 13:30 e 16:30 altos).
- Parte do efeito é mecânico (a barra do :00 abre com informação acumulada e algoritmos de barra horária). Não distingue notícia de mecânica de gráfico.
- Medir em dado novo: o mesmo perfil em ticks (tamanho de tick e volume no :00); separar dias com agenda macro. Derruba: perfil dos 60 minutos plano em outro mês.

### E. Manhã contra resto do dia e gap (H7, H8, H9)
n=21 (gap n=20 pela falta do D-1 do primeiro dia; nulo por permutação, 5.000).
- Sinal da manhã (09:00–10:30) oposto ao do resto: 14 de 21 (67%). Rho -0,10 (p=0,66).
- Gap com sinal x retorno do resto do dia: rho -0,37, p=0,10. Mesma direção da pista P4.
- |gap|/ATR x fração do range feita até 10:30: -0,20 (p=0,37); x range do dia/ATR: 0,17 (p=0,46); x horário do último extremo: -0,07 (p=0,75). Dias de gap grande (≥ mediana): fração até 10:30 0,69 contra 0,76; range/ATR 0,97 contra 0,84; último extremo 11:35 contra 12:12. Nenhum passa.
- Cruzar P4 com P6 não rende nada além da pista isolada. Derruba: rho do gap com o resto do dia cair para ~0.

## Onde NÃO há nada
Saltos de 1 minuto (continuação ou reversão), dólar como líder de volatilidade, gap × extremos cedo, manhã × tarde com sinal.
