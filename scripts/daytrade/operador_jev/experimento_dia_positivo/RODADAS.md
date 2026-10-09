# RODADAS - registro vivo do experimento "perguntas para o dia positivo"

**Regra.** Cada rodada usa dias NOVOS. Dia já usado em estudo (autópsia, escolha de pergunta, ablação, teste) não serve mais para teste. Nunca rodar a base inteira. O sorteio é aleatório, com seed registrada, e feito antes de ver o resultado da rodada; o resultado do Jev v1 do dia (`../sessoes_dec/{OOS,IS}/`) é a referência e não se roda de novo.

Dias já usados (queimados para teste): **40** da v2 (`referencia.json`: 20 treino + 20 validação, escolhidos pelos extremos do v1) e **50** da v3 (`rodada_v3_dias.json`). Dias com resultado v1: 372 (OOS 252 + IS 120); restam 282 fora dos 90 usados. A próxima rodada sorteia entre eles.

| rodada | dias | de onde | perguntas | resultado | custo | o que se aprendeu |
|---|---|---|---|---|---|---|
| **v1** (referência) | OOS 252 + IS 120 (amostra seed 20261009) | pasta inteira do v1 | 54 de mercado + 4 de gestão, 1 chamada por vela | OOS +R$ 2.339 (p do nulo 0,03); IS (120 dias) -R$ 3.678 (p 0,96); acerto ~50%, opera contra a tendência, não é calibrado | ~US$ 5,6 (total, inclui testes) | o OOS é o único bloco com sinal e o IS o desmente; o Jev compra a queda e vende a alta |
| **v2** treino | 20 (10 melhores + 10 piores dias do v1, no treino) | `referencia.json` > treino | 17 de mercado + gestão; A = duas etapas, B = veto | v1 -R$ 215 -> A +R$ 3.094, B +R$ 2.425 | A US$ 0,46; B US$ 0,28 | perguntas desenhadas olhando estes 20 dias (4 agentes): é in-sample |
| **v2** validação | 20 (idem, outros dias) | `referencia.json` > validação | as mesmas | v1 -R$ 357 -> **A +R$ 3.023**, B +R$ 1.548 | A US$ 0,46; B US$ 0,31 | o ganho era regressão à média: dias escolhidos pelos extremos do v1 (ruído da API ~R$ 170/dia); 20 dias não validam |
| **v3** | **50** (33 OOS + 17 IS, aleatórios, seed 20261010) | `rodada_v3_dias.json`, fora dos 40 da v2 | 8 de mercado + `v2_g_acao` + finais; estado 16 velas M15 sem DIARIO; duas etapas | v1 **-R$ 969** (134 ops) x v3 **-R$ 1.864** (265 ops); `zerar` limitado -R$ 2.251 | US$ 0,5035 (50 dias) + US$ 3,15 de ablações em treino | **a vantagem da v2 não replica em dias sorteados**: pareado -R$ 17,9/dia, IC95 [-94 ; +62]; v3 não passa do nulo (p 0,66); opera 2x mais (265 x 134) e 66% das saídas são `zerar` a mercado, que somam -R$ 7.073 |

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
