# v4 - validacao dos candidatos fracos e hipoteses nao testadas

Script: `v4_candidatos_pendentes.py` (criterio de "validado" escrito no topo antes de rodar). CSVs `v4_*.csv` (separador `;`, virgula decimal). Registro completo dos testes (efeito, p, p Holm, sinal por ano): `v4_registro_testes.csv`.

## Metodo e criterio (fixados antes)
- WIN@D e WDO@D, M1, ajuste por diferenca. Dias validos: >=300 barras, abertura <10:00, termina >=17:50 (sai o dia parcial final de cada base). Anos cheios 2022..2026; 2021 (3 meses) so mostrado.
- VALIDADO = WIN pooled com p<0,05 corrigido por Holm (familia = 31 testes primarios WIN) E mesmo sinal em >=4 de 5 anos E replica no WDO (mesmo sinal, p<0,05). NAO VALIDADO = p WIN >=0,05 ou <=3 de 5 anos com mesmo sinal. INCONCLUSIVO = o resto.
- Nulos: item 2 embaralha BARRAS inteiras do dia (OHLC preservado), 20 replicas por instrumento; H12 sorteia, minuto a minuto, o retorno padronizado do mesmo minuto-do-dia em outro pregao e reescala pela vol do dia de destino, 20 replicas. Item 1 tem Monte Carlo de permutacao (5.000).
- OOS 2025+ ja foi visto: a validacao aqui e' estabilidade por ano + WDO + conta de multiplicidade.

## Tabela final
| hipotese | resultado (WIN pooled) | por ano 2022..2026 | WDO | passa? | veredito |
|---|---|---|---|---|---|
| 1. Sexta apos semana de baixa fecha em alta | 41,4% (n=128) vs base 51,6%: -10,2pp, p=0,021 (Holm 0,60) | -9,0 / -4,3 / -14,5 / -12,9 / -8,7 pp (5/5 negativos; taxas 43/50/36/41/39%) | 42,5% vs 48,4%: -5,9pp, p=0,175; 4/5 anos negativos (2025 ~0) | Nao: falha Holm e p do WDO | INCONCLUSIVO |
| 1b. Espelho: sexta apos semana de alta | 51,3%: -0,3pp, p=0,95 | +2,7 / +1,7 / +2,6 / +1,4 / -19,8 | +7,0pp, p=0,14 (sinal oposto ao esperado de simetria) | Nao | NAO VALIDADO (nao ha simetria) |
| 2. Correcao micro em 61,8% acima do nulo | razao real/nulo 0,997 a 1,113 nos 10 casos (5 limiares x close/HL); p<0,05 em 2 de 10 (k=0,07 e 0,10, so zigue-zague de closes: 1,105 e 1,113, p=0,016 / 0,027; Holm 0,46 / 0,72) | closes k=0,10: 1,08 / 1,13 / 1,00 / 1,20 / 1,12; HL: oscila ao redor de 1,0 (0,94 a 1,14) | razao 1,005 a 1,107, nenhum p<0,05 (menor 0,097) | Nao | NAO VALIDADO |
| 3. Reversao de curtissimo prazo M1 (descritivo) | lag 1 M1: -0,017 (p<0,001) | -0,013 / -0,024 / -0,010 / -0,019 / -0,022 (5/5 negativo; 2021 +0,004) | -0,040; por ano -0,022 / -0,034 / -0,055 / -0,050 / -0,062 (5/5) | Fenomeno: sim em M1 lag 1. Aproveitavel: nao | FENOMENO ESTAVEL, NAO APROVEITAVEL |
| 4a. H13 corpo/range de D-1 -> range de D | rho parcial -0,096 (controlando range e volume de D-1), p=0,0008, Holm 0,026 | -0,16 / +0,02 / -0,12 / -0,23 / +0,02 (3/5) | rho bruto +0,009; parcial -0,041, p=0,16 | Nao: 3/5 anos e sem replicacao | NAO VALIDADO |
| 4b. H13 corpo cheio vs pavio -> continuacao de D-1 | +2,2pp, p=0,53 | 1,4 / 15,7 / -5,5 / 4,0 / -6,6 | +5,1pp, p=0,14 | Nao | NAO VALIDADO |
| 4c. H13 corpo -> tamanho do gap | rho parcial -0,019, p=0,50 | oscila | -0,025, p=0,38 | Nao | NAO VALIDADO |
| 4d. H13 corpo cheio vs pavio -> gap contra D-1 | +6,7pp, p=0,051 (Holm 0,87) | 5,0 / 1,1 / 11,4 / 11,3 / -1,0 (4/5) | +7,3pp, p=0,036; 5/5 anos | Nao (p WIN 0,051 e Holm); e' a borda do criterio | NAO VALIDADO (pista de borda, ver abaixo) |
| 4e. H15 divergencia WIN x WDO em D-1 -> range de D | +4,5% no log(range/ATR), p=0,043 (Holm 1,0); ~33% dos dias sao "divergentes" | +2,5 / +7,7 / +1,3 / +11,6 / +1,4 (5/5) | +2,3%, p=0,32 | Nao: falha Holm e WDO | INCONCLUSIVO |
| 4f. H15 divergencia -> direcao do WIN em D (ambos subiram / ambos cairam) | -2,2pp (p=0,53) / +0,8pp (p=0,83) | sem padrao | +2,1pp / +0,9pp (p>0,5) | Nao | NAO VALIDADO |
| 4g. H15 divergencia -> continuacao do sinal de D-1 | -1,4pp, p=0,65 | sem padrao | -0,2pp, p=0,95 | Nao | NAO VALIDADO |
| 4h. H12 1a hora faz extremo do dia (nunca superado) | real 54,2% vs nulo 54,1 +- 1,4 (z=0,09) | dif -8,1 / -7,9 / +2,9 / +9,1 / +6,0 pp (ruido) | real 65,8% vs nulo 63,8% (z=1,1, p=0,27) | Nao | NAO VALIDADO |
| 4i. H12 versao "nunca revisitado" (>=0,10 ATR de folga) | 30,5% vs 31,1% (z=-0,37) | oscila de sinal | 43,3% vs 41,5% (p=0,36) | Nao | NAO VALIDADO |
| 5. Eficiencia M1 de D-1 -> D (Spearman) | rho -0,085, p=0,0026 (Holm 0,079); IS 2021-24 -0,120 / OOS 2025-26 -0,022 | -0,224 / -0,153 / -0,029 / -0,090 / +0,064 (4/5; 2021 +0,130) | -0,036, p=0,20; IS -0,056 / OOS -0,004 | Nao: falha Holm e WDO | INCONCLUSIVO (pende para NAO: decai a zero e nao replica) |

## Item 1 - multiplicidade e leitura
- Dez combinacoes dia-da-semana x semana anterior (5 x 2). Por acaso se esperam 0,5 combinacoes com p<0,05 por instrumento; a chance de pelo menos uma sair com p<0,05 e' 33% (permutacao, 5.000 rodadas); saiu 1 em 10 no WIN (a sexta de baixa) e 0 em 10 no WDO.
- Probabilidade de o MAIOR |z| entre as dez combinacoes chegar a 2,30 (o da sexta de baixa) so por acaso: 15%. Ou seja: o melhor de dez com este tamanho acontece 1 vez em 7. Nao e' raro.
- O sinal e' consistente nos 5 anos no WIN, mas o espelho (sexta apos semana de alta) nao existe (-0,3pp), o que nao sustenta uma historia de "reversao semanal"; no WDO a mesma sexta de baixa vem mais fraca (-5,9pp, 2025 ~0) e o espelho aparece com +7pp. Sem simetria e sem replicacao com p<0,05 fica INCONCLUSIVO; mereceria um teste pre-registrado so se alguem precisar dele.

## Item 2 - micro-correcoes em 61,8% (5 limiares, closes e maximas/minimas)
- Banda 61,8% +- 2,5pp, share real vs nulo de embaralhamento de barras (20 replicas). Razao real/nulo na banda 61,8%:

| k (ATR) | WIN closes | WIN HL | WDO closes | WDO HL |
|---|---|---|---|---|
| 0,05 | 1,062 (p 0,066) | 0,997 | 1,014 | 1,026 |
| 0,07 | 1,105 (p 0,016) | 1,009 | 1,009 | 1,022 |
| 0,10 | 1,113 (p 0,027) | 1,051 (p 0,105) | 1,028 | 1,015 |
| 0,15 | 1,004 | 1,065 (p 0,16) | 1,103 (p 0,097) | 1,031 |
| 0,20 | 1,020 | 1,022 | 1,107 | 1,005 |

- O "pico" existe so como excesso pequeno (0 a 11%) e sem p<0,05 em 18 de 20 configuracoes; 19 de 20 razoes ficam >=1, mas as configuracoes sao aninhadas sobre os mesmos dados, entao nao sao 20 sorteios independentes. Por ano a razao oscila de 0,82 a 1,45 (ruido de n pequeno por ano).
- O pico NAO e' especifico de 61,8%: nas bandas informativas, o de 78,6% e' tao ou mais forte (WIN closes: 1,114 / 1,072 / 1,057 / 1,119 / 1,119; WDO closes k=0,05: 1,102, p=0,005), e o de 38,2% fica abaixo do nulo em varios casos (0,89 a 0,99). Padrao difuso, compativel com a reversao M1 do item 3 (que o embaralhamento destroi), e nao com razao de Fibonacci.
- Veredito: NAO VALIDADO. O resultado anterior (1,07 / 1,18, z<2) era exatamente esse excesso pequeno.

## Item 3 - autocorrelacao dos retornos (so descricao; retornos de fechamento dentro do dia, em pontos, cortados a 6 desvios)
| instrumento | TF | lag 1 pooled | por ano 2022..2026 | lag 2..5 |
|---|---|---|---|---|
| WIN | M1 | -0,017 | todos negativos | |corr| <= 0,003 (lag 2 +0,003) |
| WIN | M5 | -0,004 (p 0,11) | -0,003 / -0,030 / -0,005 / -0,018 / +0,015 (4/5) | lag 3 +0,008, estavel em 5/5 anos |
| WIN | M15 | +0,005 (p 0,27) | sem padrao | |corr| <= 0,008 |
| WDO | M1 | -0,040 | -0,022 / -0,034 / -0,055 / -0,050 / -0,062 (5/5, cada vez maior) | lag 2 -0,003, lag 3 -0,004 |
| WDO | M5 | -0,011 e lag 2 -0,011 | 5/5 negativos em ambos | resto ~0 |
| WDO | M15 | -0,009 (p 0,054) | 4/5 | lag 3 +0,014 (5/5 positivo), lag 5 -0,012 |

- Por faixa horaria, lag 1 M1: WIN negativo em 4-5 de 5 anos em 9 das 10 faixas (11h so 3/5), mediana por faixa -0,013 a -0,046; WDO negativo em 5/5 (4/5 as 11h e 15h), de -0,028 (10h) a -0,099 (16h). A reversao e' mais forte no fim da tarde (16-17h). Em M5 e M15 o sinal por faixa e' instavel (0-5 de 5 anos negativos).
- Tamanho: o spread gravado e' constante (WIN 5 pts, WDO 500 = 0,5 pt) = 1 tick. Movimento esperado condicional ao retorno anterior de 1 desvio: WIN M1 0,97 pt (0,19 tick; sd do M1 56,6 pts), WDO M1 0,073 pt (0,15 tick). Muito abaixo de 1 tick de custo (spread) mais o custo de operar. Os valores M5/M15 (<=1,8 pt WIN, <=0,09 pt WDO) sao ruido estatistico.
- Parte e' provavelmente microestrutura (quique bid/ask do fechamento M1): a magnitude relativa e' maior no WDO, cujo tick pesa mais em relacao a sd (0,5 / 1,8).
- Veredito: fenomeno estavel em M1 lag 1 (5/5 anos, os dois instrumentos), nao aproveitavel por tamanho (0,15-0,19 tick). M5/M15: sem estrutura estavel.

## Item 4 - H13, H15, H12
- H13: o unico resultado que parecia vivo (corpo cheio de D-1 -> range menor em D, rho parcial -0,096, passa Holm no WIN) nao e' estavel (3/5 anos, 2023 e 2026 invertem) e some no WDO (bruto +0,009). Nao replica = nao validado. Corpo/range nao informa a direcao de D (+-2pp, p>0,5 em tudo) e nao informa o tamanho do gap.
- H13d (gap contra a direcao de D-1 mais comum apos corpo cheio que apos pavio: +6,7pp WIN, p=0,051; +7,3pp WDO, p=0,036; 4/5 e 5/5 anos) e' a unica pista de borda. Pelo criterio fixado e' NAO VALIDADO (WIN p>=0,05 e Holm 0,87). Em boa parte e' conhecida: corpo cheio = fechamento perto do extremo, e a rodada anterior ja mostrava que gap tende a ir contra o fechamento (fechou perto da maxima -> gap baixa).
- H15: 33,2% dos dias tem WIN e WDO no mesmo sentido em D-1 (o normal e' opostos, 66,8%). Esse estado so move o range de D de leve (+4,5% em log, p=0,043, 5/5 anos no WIN) e nao replica no WDO (p=0,32); nao move direcao nem continuacao. INCONCLUSIVO so no range, pequeno e sem poder de direcao.
- H12: em 54% dos dias o maximo ou o minimo do dia (por fechamentos M1) sai na 1a hora e sobrevive ate o fim do pregao (WDO 66%). O nulo que preserva a volatilidade por minuto-do-dia da exatamente igual (WIN 54,1 +- 1,4; WDO 63,8 +- 1,1). A "tendencia limpa a partir da 1a hora" e' consequencia da vol concentrada no inicio, nao estrutura.

## Item 5 - eficiencia D-1 -> D, ano a ano
WIN: 2021 +0,13, 2022 -0,22, 2023 -0,15, 2024 -0,03, 2025 -0,09, 2026 +0,06 (pooled -0,085, IS -0,120, OOS -0,022). WDO: -0,11 / -0,02 / -0,07 / -0,07 / -0,05 / +0,02 (pooled -0,036, p=0,20). Fecha a questao: efeito fraco, decrescente ao longo dos anos, sinal que vira em 2026 nos dois instrumentos e sem significancia no WDO. Nao e' um sinal usavel.

## Contagem de testes
- Familia primaria WIN: 31 testes pooled (T1 10, T2 10 [5 limiares x 2 series, banda 61,8%], H13 4, H15 4, H12 2, T5 1). Por acaso a 5%: 1,55. Observados p<0,05: 6 (H13a, T5, T2 k=0,07 closes, T1 sexta de baixa, T2 k=0,10 closes, H15a). Passam Holm: 1 (H13a), que cai por 3/5 anos e pela falta de replicacao.
- Total de linhas de teste pooled (WIN + WDO, incluindo 80 de banda de Fibonacci informativas e 30 de autocorrelacao descritivas): 152. Por acaso a 5%: 7,6. Observados p<0,05: 23 (10 na autocorrelacao descritiva, que tem n de centenas de milhares; 8 nas bandas de Fibonacci, aninhadas e dependentes entre si; 5 nos testes de hipotese de dia: H13a, H13d WDO, H15a, T1, T5 e as demais de T2; nao sao 23 achados independentes).
- Celulas por ano (so descritivas): T1 tem 10 combos x 5 anos x 2 instrumentos = 100 celulas, onde ~5 saem com p<0,05 por acaso.
- Resultado: 0 VALIDADOS; 3 INCONCLUSIVOS (sexta de baixa, H15 range, eficiencia); 10 NAO VALIDADOS (espelho da sexta, micro-correcoes 61,8%, H13a/b/c/d, H15 direcao e continuacao, H12 duas versoes); 1 fenomeno descritivo estavel porem nao aproveitavel (reversao M1 lag 1).

## Caminhos
1. Nada aqui sustenta robo. Os candidatos fracos se comportam como o esperado de ruido (efeito pequeno, sinal instavel, sem replicacao).
2. Unico fio com os dois instrumentos no mesmo sentido e p<0,05 no WDO: corpo cheio de D-1 -> gap contra D-1 (H13d). Se for testado, pre-registrar (corpo >=0,6 vs <=0,3, gap contra D-1, WIN e WDO, 2022-2026) e juntar com o resultado anterior de fechamento perto da maxima/minima, que e' o mesmo mecanismo; so avancar se sobreviver a controle por localizacao do fechamento (CLV) de D-1, senao e' a mesma informacao.
3. Reversao M1 de lag 1 e' real mas vale 0,15-0,19 tick: so seria explorada como ajuste de entrada/saida de ordem-limite (onde posicionar a limite), nao como sinal. Seu uso so faria sentido com medicao de fila (`fidelidade.py`), nao com esta base.
4. Escala (range de D) e' o que o passado prediz (rodada anterior: volume relativo de D-1). Os candidatos de hoje para range (H13a, H15a) sao pequenos e nao estaveis; se a meta for dimensionamento por volatilidade, ficar com volume relativo + ATR.
5. Limitacoes: ajuste por diferenca; p por aproximacao normal; teste de Spearman parcial por ranks e regressao linear; 20 replicas de nulo (dp do nulo subestimado levemente); zigue-zague de HL resolve barra ambigua priorizando a reversao; o H12 usa fechamentos M1 (nao maximas e minimas); sessao WIN termina as 17:54 ou 18:24 conforme horario de verao dos EUA.
