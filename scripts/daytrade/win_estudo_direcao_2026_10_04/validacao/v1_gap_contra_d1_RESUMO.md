# V1 - Validacao: "o gap de abertura vai contra o dia anterior"

Script: `v1_gap_contra_d1.py` (criterio escrito no topo, antes de rodar). Saida bruta: `v1_stdout.log`. CSVs: `v1_checagens_1_2.csv`, `v1_ano_a_ano.csv`, `v1_reversao_intradia.csv`, `v1_magnitude_transmissao.csv`, `v1_winv26_vs_arquivoD.csv`.

Estatistica: concordancia sign(gap) = sign(retorno de D-1) menos o esperado sob independencia (diff, em pp; negativo = gap vai contra). WIN 1.227 pregoes (2021-10 a 2026-10), WDO 1.226. A janela 2025+ ja foi vista: nao conta como fora da amostra.

## Tabela de checagens (achado (a): retorno de D-1 close-close)
| checagem | resultado | passa? |
|---|---|---|
| Base WIN | diff -7,8pp (concord. 42,2% vs 50,0%; IC [-10,5;-5,0]); P(gap alta / D-1 alta) 42,9%, P(gap alta / D-1 baixa) 58,5% - reproduz o achado | - |
| C1 rolagem (exclui +-1 / +-3 dias uteis do vencimento) | -7,1pp (n=1.124) / -7,0pp (n=1.008), p<0,001 nas duas | SIM |
| C1b gaps do @D vs WINV26 (abr-out/2026) | sinal igual em 94,5% (n=73) - abaixo dos 95% escritos por 0,5pp; mediana da diferenca 0; as 21 divergencias >100 pts estao todas entre 19/06 e 11/08, quando o V26 e ilíquido (contrato de outubro, trocas fora do vencimento do @D); de 13/08 em diante 100% de sinal igual, dif. max 0 (n=35). Efeito (a) so no contrato unico WINV26: -11,2pp, p=0,057 (n=72, so confirma o sinal) | FALHA FORMAL (94,5<95), artefato do proprio WINV26, nao do achado |
| C2 horario: fech. 17:55 | -6,3pp (p<0,001) | SIM |
| C2 fech. 17:00 | -3,7pp (p=0,009) | SIM |
| C2 fech. media dos 10 min | -8,7pp | SIM |
| C2 abre 9:05 / 9:15 | -6,9pp / -7,0pp | SIM |
| C2 fech. 17:55 + abre 9:05 | -5,2pp (p<0,001) | SIM |
| C4 ano a ano WIN | 2021(parcial) -14,5 / 2022 -6,7 / 2023 -8,2 / 2024 -7,6 / 2025 -9,3 / 2026 -5,3pp; 5 de 5 anos completos negativos (IC de 2026 e 2022 cruzam 0 em parte; p por ano: 0,035 0,010 0,017 0,004 0,152) | SIM |
| C5 WDO (a) | agrupado -8,1pp (p<0,001); sem rolagem +-1 -9,5pp; anos 2022-2026: -8,8 / -4,8 / -1,3 / -10,9 / -10,7pp (5 de 5 negativos, 3 de 5 individualmente p<0,05 ... 2022, 2025, 2026) | SIM |
| C3 reversao generica (interpretativa) | WIN: overnight -7,8pp [-10,5;-5,0] contra -0,5pp [-1,2;+0,3] nos pares de blocos de 30 min adjacentes intradia (n=18.049); correlacao gap/ATR x D-1 -0,18 contra +0,006 intradia. WDO: -8,1pp contra -1,2pp [-2,0;-0,5]. ICs sem sobreposicao: o overnight e ESPECIAL, nao e a reversao de sempre | informativa: especial |

## Achado (b): o gap vai contra os ultimos 30 min de D-1
| checagem | resultado | passa? |
|---|---|---|
| Base WIN | -7,6pp (concord. 42,4%) | - |
| C1 rolagem +-1 / +-3 | -8,2 / -8,4pp | SIM |
| C2 fech. 17:55 (ult. 30 = 17:25-17:55) | -2,3pp, p=0,11 | NAO |
| C2 fech. 17:55 + abre 9:05 | -1,6pp, p=0,28 | NAO |
| C2 fech. media 10 min | -4,7pp (p=0,001) | SIM |
| C2 abre 9:05 / 9:15 | -8,6 / -8,7pp | SIM |
| C4 anos WIN | -10,2 / -7,0 / -10,1 / -6,7 / -1,8pp (2022-2026; 2026 p=0,62) | SIM (5/5 negativos) |
| C5 WDO | -5,0pp (p=0,001); anos 2022-2026 -4,1 / -3,1 / -3,0 / -5,1 / -6,7pp | SIM |
Quando o fechamento de referencia sai da ultima barra (18:24) e vai para 17:55, 3/4 do efeito de (b) some: parte do "contra os ultimos 30 min" e o movimento do periodo 17:55-18:24 (leilao/call de fechamento), isto e, microestrutura. Em (a) isso nao acontece.

## Magnitude pratica (WIN, descricao)
- Gap medio apos D-1 alta -61 pts; apos D-1 baixa +67 pts (diferenca entre as condicoes ~127 pts, cerca de 0,06 ATR). ATR(14) mediano ~1.980 pts; |gap| mediano 325 pts (0,16 ATR). O efeito medio vale ~1/5 do gap tipico e ~3% do ATR.
- WDO: -3,8 / +2,0 pontos (~-0,06 / +0,03 ATR); |gap| mediano 9,75 pts (0,15 ATR).
- Transmissao para o inicio de D: o preco nao continua nem devolve de forma mensuravel. WIN, a favor do gap em 5/15/30 min: 50,8% [48,0;53,6], 48,6% [45,8;51,5], 48,6% [45,8;51,4]; retorno medio a favor do gap +2,5 / -8,4 / -13,0 pts (ruido). Gap contra D-1: 49,9% a favor nos 30 min; gap a favor de D-1: 47,0%. WDO: 49,4 / 50,0 / 48,9%. Efeito fica na abertura, nao vira direcao.

## Veredito
- Achado (a): **VALIDADO** pelo criterio escrito (C1, C2, C4, C5 passam; C3 mostra que o overnight tem algo proprio, nao e a reversao intradia comum). Ressalvas: C1b falha por 0,5pp no limiar escrito (94,5% vs 95%), por causa do WINV26 ilíquido antes de meados de agosto, e a janela de 2026 sozinha nao e significativa (p=0,15); 5 de 5 anos com o mesmo sinal, tamanho pequeno (~8pp na frequencia, ~0,06 ATR em pontos).
- Achado (b) como formulado: **NAO VALIDADO** (falha C2 ao trocar o fechamento para 17:55 - efeito cai de -7,6pp para -2,3pp, p=0,11). O sinal continua negativo em todas as variantes e anos, mas boa parte e fechamento/leilao. (a) e a versao robusta; (b) nao acrescenta.
- Nada disto e sinal de direcao do dia: o gap contra D-1 nao se transmite aos primeiros 5/15/30 min.
