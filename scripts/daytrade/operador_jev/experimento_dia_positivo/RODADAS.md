# RODADAS - registro vivo do experimento "perguntas para o dia positivo"

**Regra.** Cada rodada usa dias NOVOS. Dia já usado em estudo (autópsia, escolha de pergunta, ablação, teste) não serve mais para teste. Nunca rodar a base inteira. O sorteio é aleatório, com seed registrada, e feito antes de ver o resultado da rodada; o resultado do Jev v1 do dia (`../sessoes_dec/{OOS,IS}/`) é a referência e não se roda de novo.

Dias já usados (queimados para teste): **40** da v2 (`referencia.json`: 20 treino + 20 validação, escolhidos pelos extremos do v1), **50** da v3 (`rodada_v3_dias.json`) e **50** da v4 (`rodada_v4_dias.json`, seed 20261011). Dias com resultado v1: 372 (OOS 252 + IS 120); restam **232** fora dos 140 usados (a lista está em `rodada_v4_dias.json` > `pool_restante`: OOS 152 + IS 80; a v4 sorteou entre 185 + 97 e tirou 33 + 17). A próxima rodada sorteia entre eles (e exclui 2026-10-05, ver verificação de dado).

| rodada | dias | de onde | perguntas | resultado | custo | o que se aprendeu |
|---|---|---|---|---|---|---|
| **v1** (referência) | OOS 252 + IS 120 (amostra seed 20261009) | pasta inteira do v1 | 54 de mercado + 4 de gestão, 1 chamada por vela | OOS +R$ 2.339 (p do nulo 0,03); IS (120 dias) -R$ 3.678 (p 0,96); acerto ~50%, opera contra a tendência, não é calibrado | ~US$ 5,6 (total, inclui testes) | o OOS é o único bloco com sinal e o IS o desmente; o Jev compra a queda e vende a alta |
| **v2** treino | 20 (10 melhores + 10 piores dias do v1, no treino) | `referencia.json` > treino | 17 de mercado + gestão; A = duas etapas, B = veto | v1 -R$ 215 -> A +R$ 3.094, B +R$ 2.425 | A US$ 0,46; B US$ 0,28 | perguntas desenhadas olhando estes 20 dias (4 agentes): é in-sample |
| **v2** validação | 20 (idem, outros dias) | `referencia.json` > validação | as mesmas | v1 -R$ 357 -> **A +R$ 3.023**, B +R$ 1.548 | A US$ 0,46; B US$ 0,31 | o ganho era regressão à média: dias escolhidos pelos extremos do v1 (ruído da API ~R$ 170/dia); 20 dias não validam |
| **v3** | **50** (33 OOS + 17 IS, aleatórios, seed 20261010) | `rodada_v3_dias.json`, fora dos 40 da v2 | 8 de mercado + `v2_g_acao` + finais; estado 16 velas M15 sem DIARIO; duas etapas | v1 **-R$ 969** (134 ops) x v3 **-R$ 1.864** (265 ops); `zerar` limitado -R$ 2.251 | US$ 0,5035 (50 dias) + US$ 3,15 de ablações em treino | **a vantagem da v2 não replica em dias sorteados**: pareado -R$ 17,9/dia, IC95 [-94 ; +62]; v3 não passa do nulo (p 0,66); opera 2x mais (265 x 134) e 66% das saídas são `zerar` a mercado, que somam -R$ 7.073 |
| **v4** | **50** (33 OOS + 17 IS, aleatórios, seed 20261011) | `rodada_v4_dias.json`, fora dos 90 da v2/v3 | as 8 da v3 + portão de direção (>= 0,20) + gestão "tese invalidada" + risco 6% do caixa + reentrada (máx. 3, espera 2 velas); `zerar` limitado | v1 **-R$ 1.105** (122 ops) x v3 L **-R$ 1.703** (269) x v4 **-R$ 857** (102) | v4 US$ 0,248 + v3 US$ 0,518 (mesmos dias) | **v4 -R$ 857**: pareado v4-v3 +R$ 16,9/dia (IC95 [-36 ; +75], p 0,59), v4-v1 +R$ 5,0/dia (p 0,86): **não se distingue de nenhum dos dois**; nulo livre p 0,70; o portão a 0,20 não cortou nada (o Jev já obedecia); o ganho sobre a v3 vem de operar 62% menos (reentrada/máx. 3 + gestão sem `zerar`), mas o stop vira a perda (52% das saídas, -R$ 3.730) |

## Detalhe da rodada v3 (50 dias novos)

| | v1 | v3 (zerar a mercado) | v3 (zerar limitado) |
|---|---|---|---|
| total R$ | -969 | -1.864 | -2.251 |
| ops | 134 | 265 | 264 |
| acerto | 52,2% | 40,8% | 40,9% |
| fator de lucro | 0,84 | 0,81 | 0,77 |
| pior queda R$ | 1.558 | 2.340 | 2.726 |
| pior dia R$ | -288 | -775 | -777 |
| dias positivos | 24/50 | 20/50 | 20/50 |
| R$/dia | -19 | -37 | -45 |

- Pareado v3 - v1: média -R$ 17,9/dia, IC95 bootstrap [-94,5 ; +62,4], t = -0,43 (p 0,67), sign-flip p 0,67; v3 melhor em 19 dias, pior em 31.
- Nulo (300 sorteios, mesma geometria): v3 média R$ -1.029, p5 -4.046, p95 +2.336, p(nulo >= v3) = 0,66; v1 p = 0,62. Nenhum dos dois se distingue de entrada aleatória nestes 50 dias.
- Por tipo de dia (eficiência ex-post): 39 dias de rotação (<0,15): v1 +R$ 546, v3 -R$ 3.858 (v3 opera 199 vezes contra 82, acerto 37% x 66%); 11 dias intermediários (0,15-0,30): v1 -R$ 1.515, v3 +R$ 1.994; nenhum dia direcional (>=0,30) caiu no sorteio. OOS: v1 -768, v3 -1.444; IS: v1 -201, v3 -420.
- `zerar`: 175 saídas a mercado (66%), -R$ 7.073, média -R$ 40; alvo 58 (+R$ 5.080), stop 24 (-R$ 866), fim do pregão 8 (+R$ 995). v1: 2 `zerar`. Variante limitada: 181 pedidos, 175 encheram, 6 expiraram; as saídas por stop passam de -R$ 866 para -R$ 1.882 (a posição fica 2 velas a mais exposta), e o total piora R$ 387 (pareado L - M -R$ 7,7/dia, IC [-14,3 ; -2,4]). O custo de execução NÃO explica o resultado negativo: o `zerar` é a decisão ruim, não o preço em que sai.
- Capital (escada: R$ 1.000/contrato, máx. 2, início R$ 2.000, 1 contrato abaixo de R$ 2.000, para abaixo de R$ 1.000): v3 chega a R$ 2.370 no 7º dia, termina 48 dos 50 dias abaixo do piso de R$ 2.000, cai abaixo de R$ 1.000 em 2026-03-05 (R$ 972) e o robô PARA ali (70 trades pulados); v3 limitado para em 2025-11-28. v1 também para (2026-03-04, R$ 813). A ordem dos dias é cronológica mas os dias são esparsos (sorteio), então a curva é ilustrativa.
- 30 dos 50 dias são "ruins" (v3 < 0 ou v3 - v1 <= -R$ 300): `dias_ruins_v3.json` (com respostas do Jev na entrada, saídas e o v1 do dia). Padrão visível: 29 dos 30 são dias de rotação (eficiência < 0,15) e em 22 deles a primeira entrada saiu de uma resposta `alta/baixa_dirigida` (o Jev lê o dia como dirigido cedo; depois ele vira rotação), seguida de várias entradas e saídas por `zerar`.
- Falhas de API 0, 429 0. Versão `typesafe/jev-1.13-20260917`, limiar 0,3.

## Custo real total (esta rodada de trabalho)

Ablação de perguntas (2 rodadas) US$ 2,20 + estado/fusão US$ 0,95 + teste de 2 dias US$ 0,02 + 50 dias da v3 US$ 0,50 = **~US$ 3,67**.

## Notas de método para a próxima rodada

- A v2 foi medida só em dias escolhidos pelos extremos do v1: qualquer regra que melhore dias ruins do v1 e piore dias bons parece vitória por regressão à média. Dias sorteados são o teste honesto, e ele refutou o ganho.
- As 8 perguntas v3 foram escolhidas por decisão (não por lucro). Cortar pergunta não era o problema: a v3 reproduz a decisão da v2 (concordância 92-95% com o ruído em 95-96%), e a decisão é que não tem edge fora dos 40 dias.
- Hipóteses para a fase seguinte (autópsia dos dias ruins): por que o Jev diz "dirigida" cedo em dia que vira rotação; por que `zerar` sai pior que o stop; o efeito do número de entradas por dia (v3 faz 5,3 ops/dia contra 2,7 do v1).

## Detalhe da rodada v4 (50 dias novos; regras em `perguntas_v4.md`, tudo pré-registrado antes de sortear)

Dias, painel e testes: `rodada_v4_dias.json`, `analise_R50_v4.txt` / `.json`, `analise_R50_v4_ablacao2.txt` (ablação com entradas da v3), `extras_v4.txt` (descritivo pós-hoc), `dias_ruins_v4.json`, `verificacao_dado.json`. Sessões: `sessoes_v3/R50v4/{M,L}`, `sessoes_v4/R50/L`.

| | v1 | v3 (zerar a mercado) | v3 (zerar limitado) | v4 |
|---|---|---|---|---|
| total R$ | -1.105 | -1.578 | -1.703 | **-857** |
| ops | 122 | 271 | 269 | 102 |
| acerto | 47,5% | 42,1% | 41,6% | 46,1% |
| fator de lucro | 0,80 | 0,83 | 0,82 | 0,78 |
| pior queda R$ | 1.746 | 2.189 | 2.247 | 1.464 |
| pior dia R$ | -290 | -1.146 | -1.148 | -230 |
| dias positivos | 19/50 | 20/50 | 20/50 | 16/50 |
| R$/dia | -22 | -32 | -34 | -17 |

- Pareado por dia: v4 - v3(L) +R$ 16,9/dia, IC95 [-36,4 ; +75,0], p 0,56 (sign-flip 0,59), melhor em 26 dias e pior em 23; v4 - v3(M) +14,4 (p 0,62); **v4 - v1 +R$ 5,0/dia, IC95 [-50,5 ; +61,1], p 0,86**; v3(L) - v1 -12,0 (p 0,78). Nenhuma diferença é distinguível de zero.
- Nulo (300 sorteios, mesma geometria das 102 ordens preenchidas): **livre** (qualquer vela, 2 lados) média -R$ 439, p5 -1.590, p95 +768, p(nulo >= v4) = 0,70. **Com o mesmo portão** (só as 599 combinações dia-vela que passam eficiência >= 0,20, só no lado a favor): média **-R$ 1.905**, p5 -3.064, p95 -555, p(nulo >= v4) = 0,083. Leitura: entrar "a favor, com direção comprovada" ao acaso perde mais do que entrar ao acaso (-1.905 contra -439), então o portão não é o que faz o resultado; entre as entradas que passam o portão a v4 fica acima do acaso por ~R$ 1.050 (p 0,08, borderline), e contra o nulo livre não há separação. Não é "Jev bom": é "Jev menos ruim que entrada a favor aleatória".
- Por tipo de dia (eficiência ex-post): 41 dias de rotação (<0,15): v1 +245, v3 L -3.218, v4 -1.633 (76 ops, 38% de acerto); 7 intermediários (0,15-0,30): v1 -1.110, v3 +743, v4 +680; 2 direcionais: v1 -240, v3 +772, v4 +96. IS (17 dias): v1 -868, v3 -1.215, v4 **+35**; OOS (33): v1 -237, v3 -488, v4 **-892**.
- Saídas (v4, 102): stop 53 (52%, -R$ 3.730, média -70), alvo 45 (44%, +2.594, média +58), fim do pregão 2 (+397), `zerar` limitado 2 (-118). v3 L: `zerar` 163 (61%, -5.545), alvo 72 (+5.596), stop 28 (-2.097). **O `zerar` desapareceu (163 -> 2) e virou stop (28 -> 53)**: o prejuízo continua, agora como stop. Ganho médio R$ 63,6 contra perda média R$ 70,0: breakeven empírico 52,4%, acerto 46,1% (as duas leituras concordam: R$/trade -8,40).
- O que as regras fizeram: das 330 intenções de entrada do Jev (p >= 0,3, com o bloco de regras no pacote), **o portão determinístico bloqueou 2** (99-100% das intenções já passavam: o Jev leu a regra no pacote e só propôs entradas que a cumprem; a pergunta `v4_direcao_comprovada` concorda com o cálculo em 328/330). Reentrada/máx. 3 bloqueou 155 e o risco de 6% bloqueou 71 (0 reduções de mão: o que não cabe com 2 também não cabe com 1 nesses stops). Gestão: 198 chamadas, o Jev pediu `zerar` 2 vezes e `stop_pivo` 0; a guarda determinística nunca precisou agir (ele também lê o bloco TESE DA POSIÇÃO e obedece).
- Hora da entrada (v4, pós-hoc): antes das 10:00 n 56, -R$ 882 (-15,8/trade); 10:00-11:59 n 31, +R$ 266; 12:00-14:59 n 14, -R$ 190; depois das 15:00 n 1. 69 das 102 entradas ocorrem nas primeiras 5 velas do dia (-R$ 628), quando a eficiência é alta por construção (1 vela: |c-o|/(h-l)): o portão literal, sem mínimo de velas, não filtra o começo do dia. Entradas com >= 6 velas: n 33, -R$ 229.
- Capital (escada R$ 1.000/contrato, máx. 2, início R$ 2.000): v4 termina em R$ 985 e **para** em 2026-04-17 (caixa < R$ 1.000, 29 trades pulados), 34 dos 50 dias abaixo de R$ 2.000; v1 para em 2025-10-07 (R$ 917, 68 pulados); v3 L para em 2025-07-31 (R$ 649, 174 pulados). A ordem é cronológica mas os dias são esparsos: a curva é ilustrativa.
- Dias ruins (v4 < 0 ou v4 - v1 <= -R$ 300): **34 de 50** (`dias_ruins_v4.json`, uma linha de diagnóstico por dia). Padrão: 30 dos 34 são rotação (eficiência ex-post < 0,15) e o prejuízo é um ou dois stops de R$ 30-120 em entradas das 09:15-10:30; os piores são 2026-03-10 (-230, 3 stops), 2025-04-07 (-220, 2 stops) e 2026-04-07 (-187). Nenhum dia da v4 passa de -R$ 230 (a v3 teve -R$ 1.148 em 2025-04-07, onde a v4 fez -220).

### Ablação offline (respostas logadas, sem nova chamada; checagem: a v4 resimulada reproduz o vivo, -857 = -857, e a v3 resimulada reproduz a v3 L, -1.703)

| variante | total R$ | ops | acerto | pior queda | vs v4 (R$/dia, IC95, sign-flip) |
|---|---|---|---|---|---|
| v4 completa | -857 | 102 | 46,1% | 1.464 | - |
| sem portão | -870 | 102 | 46,1% | 1.477 | -0,3 (p 1,0) |
| sem gestão nova (gestão da v3) | -1.212 | 101 | 42,6% | 1.563 | -7,1 [-24 ; +7] (p 0,43) |
| sem risco | -676 | 114 | 54,4% | 1.281 | +3,6 [-25 ; +28] (p 0,82) |
| sem reentrada/máx. 3 | -1.023 | 134 | 47,8% | 1.753 | -3,3 [-24 ; +17] (p 0,76) |
| sem nenhuma das 4 (aprox. v3) | -1.061 | 183 | 47,5% | 1.994 | -4,1 (p 0,83) |
| portão do Jev em vez do determinístico | -870 | 102 | 46,1% | 1.477 | -0,3 |
| portão 0,15 / 0,25 (descritivo) | -870 / **-190** | 102 / 83 | 46,1% / 49,4% | 1.477 / 699 | -0,3 / +13,3 [+1,6 ; +26] (p 0,04; uma de várias leituras, não é achado) |

Com as respostas de ENTRADA da v3 (o Jev que não leu o bloco de regras) e as regras aplicadas depois, determinísticas (gestão v4 só onde há resposta logada; sem resposta = `manter`):

| variante | total R$ | ops | acerto | fator de lucro | pior queda |
|---|---|---|---|---|---|
| v3 pura resimulada | -1.703 | 269 | 41,6% | 0,82 | 2.247 |
| + só o portão 0,20 | -1.167 | 135 | 44,4% | 0,83 | 2.115 |
| + só reentrada/máx. 3 | -1.071 | 141 | 45,4% | 0,81 | 1.436 |
| + só risco 6% | -143 | 123 | 45,5% | 0,96 | 584 |
| + só gestão v4 | -478 | 188 | 58,5% | 0,96 | 2.019 |
| **+ as 4 regras** | **+665** | 48 | 64,6% | 1,51 | 372 |
| + as 4 regras, sem portão | +508 | 88 | 54,5% | 1,17 | 431 |

Leitura: **(a)** nenhuma regra isolada passa de ruído nas respostas da v4. **(b)** Sobre as respostas de entrada da v3 as 4 regras juntas dão +R$ 665 (v4 vivo -857; diferença +30,4/dia, IC95 [-0,6 ; +59,2], p 0,053), com o portão pesando pouco (+157, 88 -> 48 ops). **Isto é ablação pós-hoc, resimulada, em 48 operações e nos mesmos 50 dias: é hipótese para a v5, não resultado** (e o desenho "regras determinísticas sobre um Jev que NÃO as lê" a v4 não testou ao vivo). **(c)** Quando o Jev lê o bloco de regras no pacote ele passa a obedecê-las por conta própria (portão 99% atendido) e o resultado piora de +665 para -857: ler a regra mudou outras decisões dele (entra mais cedo: 69 das 102 entradas nas 5 primeiras velas) e perdeu o efeito das regras determinísticas. Para separar de verdade é preciso rodar ao vivo a variante "regras determinísticas, pacote sem bloco" (custo ~US$ 0,25).

### Verificação do dado (item 6)

O salto de **+17.405 pts (+9,0%, +5,0 ATR diários)** de 2026-10-02 (fechamento 193.350) para 2026-10-05 (abertura 210.755) **não é defeito da base**: aparece igual em `data/win_sem_leiloes/m1_WIN$N.parquet`, em `data/comparativo_win_2026/m1_WIN$N.parquet` (193.000 -> 210.775; a diferença do fechamento é o call do leilão) e nos ticks (último tick 193.000, primeiro 210.775); e o **MT5 ao vivo confirma** em `WIN$N`, `WINV26` e `WINZ26` (Z26: 197.020 -> 214.000, +8,6%). Não é troca de contrato (faltavam 9 dias para o vencimento de 14/10; os dois contratos saltam). Coincide com o primeiro pregão após o 1º turno das eleições (4/10/2026; em 2022 o pregão após o 1º turno, 2022-10-03, abriu +3,3%): leitura minha, não verificada em fonte de notícia. É um gap real, mas 5 ATR é um evento sem precedente na amostra e contamina `gap` e `preco_vs_ref` nesse dia (a v3 perdeu -R$ 775 nele). Já estava na rodada v3; foi excluído do pool da v4 e deve sair dos próximos.
Outros saltos fechamento -> abertura > 3 ATR diários na base inteira (1.245 dias, virgem + IS + OOS): **nenhum**; os maiores depois dele são 2022-10-31 (-3,4%, 1,4 ATR), 2022-10-03 (+3,3%), 2021-11-26 (-3,1%). Saltos intradia de M1 (abertura vs. fechamento do M1 anterior) acima de 1 ATR diário: **nenhum**. Pregões curtos (< 400 M1): 2022-03-02, 2023-02-22, 2024-02-14, 2025-03-05, 2026-02-18 (quartas de cinzas) e 2026-07-31 (351 M1); legítimos, não excluídos, nenhum caiu no sorteio da v4. A base não foi alterada.

## Custo real da rodada v4

v3 nos 50 dias novos US$ 0,518 + v4 US$ 0,248 + teste de 2 dias US$ 0,010 = **US$ 0,78**. Falhas de API 0, 429 0. A etapa 1 da v4 foi toda reusada da v3 (0 chamadas ao vivo); a etapa 2 + gestão da v4 custam ~US$ 0,005 por dia (1.697 chamadas), metade da v3, porque só são chamadas com o mesmo estado sem posição / com posição.

## Aprendizado da v4

- **A v4 não passou**: -R$ 857 contra -R$ 1.105 (v1) e -R$ 1.703 (v3); pareados e nulo livre não distinguem de zero. O diagnóstico das duas rodadas é o mesmo: **a entrada não tem vantagem** (acerto 46% com payoff 0,91; breakeven 52%). Consertar a saída e o excesso de troca corta o custo (de 269 para 102 operações), não cria edge.
- O portão de eficiência, a maior aposta da análise dos 30 dias ruins, **não funcionou como trava**: (1) o Jev que lê a regra a cumpre sozinho; (2) sem mínimo de velas, a 1ª hora passa sempre; (3) entradas a favor com direção comprovada, sorteadas ao acaso, perdem mais que entradas ao acaso (-1.905 contra -439) neste período: continuação não é o lado certo aqui.
- **Pista a testar ao vivo (v5)**: regras determinísticas sobre as respostas do Jev sem que ele as leia (+R$ 665 em ablação, 48 ops, p 0,053 contra a v4 viva). Precisa de dias novos (restam 232) e de uma rodada própria; nada nos 140 dias queimados vale como validação.
- Nota de método: a ablação "sem portão" deu o mesmo número que a v4 completa porque o Jev obedece à regra que lê; ablação que mexe só na regra, sem refazer as chamadas, esconde esse efeito. O contraste só aparece trocando as respostas de entrada (segunda tabela).
