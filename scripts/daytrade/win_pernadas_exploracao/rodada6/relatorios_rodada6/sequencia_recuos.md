# Sequência dos recuos dentro do movimento (WIN, 2026)

Pasta de trabalho: `rodada6/sequencia_recuos/` (gera.py = motor; lib.py e analisa.py = tabelas; tick_sens.py = ticks; out_txt/ = todas as tabelas; regras_congeladas.json = regras congeladas antes de abrir jul–ago).

## Resposta curta

A sequência dos recuos **não tem estrutura além do acaso** (nulo = velas M1 embaralhadas em blocos de 30 min, 40 sorteios). Em T=750, recuo mínimo 150 pts (descoberta jan–jun, 122 pregões):

- Depois do 1º recuo, supera o topo de origem sem fundo novo mais baixo em 45,6% dos casos (nulo 45,2%, z 0,4).
- Tentativas até superar o topo: 1 = 59,2% | 2 = 12,7% | 3 = 4,7% | 4+ = 1,9% (nulo 59,1 / 12,3 / 4,3 / 2,4). O movimento morre antes de superar em ~22% (nulo igual).
- 2º recuo menor que o 1º: 50,1% (nulo 49,7%, IC 45,8–54,8). Correlação de posto r1×r2 = +0,02 (nulo +0,02). Trios r1,r2,r3: crescente 15,9%, decrescente 16,2%, misto 67,9% (nulo 15,9 / 16,2 / 68,0; iid = 16,7 / 16,7 / 66,7).
- Recuos encolhendo ou crescendo não dizem nada do próximo: P(próximo supera) = 80,2% (encolhendo) × 79,0% (crescendo), nulo 78,8 / 78,6; alcance restante 0,72 T × 0,72 T.
- O 1º recuo não difere do 3º/4º: P(supera de primeira) 48,9 / 44,8 / 46,3 / 44,0% (ordens 1/2/3/4+; nulo 45,2 / 45,5 / 44,7 / 45,4). Alcance restante 0,69 / 0,70 / 0,66 / 0,64 T (nulo 0,66 / 0,67 / 0,66 / 0,63).
- O "fractal" (sobe metade, volta, sobe) existe, mas é exatamente o que o passeio aleatório produz: P(novo topo | recuo atingiu x% de A) = (T−d)/T, z entre −2,1 e +1,0 em todas as linhas.

## Definições (congeladas)

- Caminho: 2 pontos por vela M1 (alta: mín→máx; baixa: máx→mín). Alta e baixa com o mesmo código (preço invertido). Só 2026; dez/2025 só aquece o ATR.
- Movimento: origem o = mínimo corrente (reseta a cada novo mínimo ou morte); H = máxima desde a origem; A = H − o.
- Recuo: queda ≥ m = T/div a partir de H. Elegível: A ≥ T (pernada de T já confirmada quando o recuo começa; a "ordem k" conta só elegíveis). Supera: preço > H. Morre: H − p ≥ T (zigzag-T vira) ou p ≤ o.
- Tentativa: dentro do recuo, fundo L; "bounce" = preço volta a L+m (entrada candidata); a tentativa falha se faz novo fundo abaixo de L. Supera de primeira = H superada antes de qualquer fundo abaixo do L do 1º bounce.
- Entrada de teste: em L+m, stop em L (risco = m), alvo K×risco, K = 3, 5, 10. Fórmula do passeio aleatório = 1/(K+1).
- Escalas: T ∈ {250, 500, 750} × m = T/5 (principal), T/4, T/8 (sensibilidade) = 9 configs. Estratos: A/T (<1,5 | 1,5–2,5 | ≥2,5), hora (<11h | 11–13h | ≥13h; versão alinhada à abertura de NY em T1d), profundidade em % de A, ATR dos 5 pregões anteriores (tercis).
- Nulo: M1 embaralhadas em blocos de 30 min por pregão, 40 sorteios, reconstruindo o preço encadeando (gap, máx, mín, fechamento relativos à vela). A versão crua (velas absolutas embaralhadas, 10 sorteios) cria saltos e está distorcida: P(supera | recuo confirmado) cai de 0,78 para 0,46 e P(5R) de 0,138 para 0,062; por isso não foi usada. IC = bootstrap por dia; z = (real − média do nulo) / desvio entre sorteios.

## Tabelas principais (descoberta, T750/m150)

P(recuo supera o topo | já atingiu x% do avanço A):

| x | n | real | fórmula (T−d)/T | nulo | z |
|---|---|---|---|---|---|
| confirmado (m) | 4014 | 0,786 | 0,800 | 0,781 | +0,9 |
| 23% | 2252 | 0,627 | 0,631 | 0,621 | +0,9 |
| 38% | 1238 | 0,419 | 0,435 | 0,432 | −1,4 |
| 50% | 814 | 0,313 | 0,322 | 0,320 | −0,6 |
| 62% | 516 | 0,209 | 0,222 | 0,225 | −1,0 |
| 79% | 203 | 0,079 | 0,114 | 0,121 | −2,1 |

Por A, horário e ordem do recuo as linhas seguem o nulo.

P(supera de primeira) por profundidade do 1º fundo (% de A):

| prof. | n | real | nulo | z |
|---|---|---|---|---|
| 0–23 | 1237 | 0,485 | 0,506 | −1,7 |
| 23–38 | 931 | 0,481 | 0,440 | +2,6 |
| 38–50 | 335 | 0,358 | 0,370 | −0,5 |
| 50–62 | 156 | 0,353 | 0,336 | +0,5 |
| 62–79 | 61 | 0,311 | 0,333 | −0,5 |

(A fórmula contínua m/r superestima: o ponto de confirmação é extremo de vela; o nulo captura isso e o real o acompanha.)

Recuos completos por ordem (1 / 2 / 3 / 4+): profundidade média 309 / 305 / 296 / 310 pts (nulo 317 / 311 / 309 / 307); mediana em % de A 31 / 25 / 21 / 16% (só reflete A crescente); duração mediana 4 / 4 / 4 / 5 min; tempo entre o novo topo e o próximo recuo ~1,5 min.
P(recuo k+1 < k): 0,501 / 0,507 / 0,462 / 0,488 (z −1,5 a +0,5). Razão média r(k+1)/r(k): 1,18 / 1,17 / 1,25 / 1,21 (nulo 1,19–1,21).

Auto-semelhança (9 escalas, descoberta): P(r2<r1) fica em 0,47–0,51 e a diferença para o nulo é ≤ 0,022 (|z| > 2 só em T250/m31); P(supera | confirmado) vai de 0,62 a 0,84 conforme m/T e acompanha (T−m)/T. A ausência de padrão é auto-semelhante.

## Geometria (entrada em L+m, stop em L, alvo K×risco; T750/m150, descoberta, 5.021 entradas)

| alvo | P(alvo) real, ordem 1 / 4+ | fórmula | nulo | expectativa em R (ordem 1) |
|---|---|---|---|---|
| 3R | 0,254 / 0,223 | 0,250 | 0,235 | +0,06 (nulo −0,03) |
| 5R | 0,162 / 0,138 | 0,167 | 0,146 | −0,03 |
| 10R | 0,070 / 0,065 | 0,091 | 0,067 | −0,23 |

Todas as ordens juntas: P(3R) 0,225, P(5R) 0,141, P(10R) 0,063 (nulo 0,220 / 0,138 / 0,063). Breakeven de 5R = 0,167, então a expectativa média é ≈ −0,15R antes de custo. Stop de 150 pts = R$30 por contrato, alvo 5R = 750 pts. Alvos de 5R e 10R existem (14% e 6%), na frequência que o passeio aleatório dá; o fim do pregão (17:55) deixa 10R abaixo de 1/11.
Desvio isolado: depois de 1º fundo em 23–38% de A, P(5R) = 0,116 contra nulo 0,096 (z +2,6), ainda abaixo da fórmula (expectativa −0,30R).

## Sensibilidade ticks × M1 (mar–jun, 83 pregões, mesmo código; ticks alinhados ao M1, filtrados fora da faixa do minuto ±100, só pontos de virada)

| T / m | caminho | recuos elegíveis | P(supera) | tentativas 1/2/3/4+ (%) | P(supera de 1ª) | mediana r1 | P(r2<r1) | P(3R) | P(5R) | P(10R) |
|---|---|---|---|---|---|---|---|---|---|---|
| 750 / 150 | M1 | 2897 | 0,789 | 68/18/9/5 | 0,456 | 330 | 0,490 | 0,229 | 0,140 | 0,061 |
| 750 / 150 | ticks | 3149 | 0,806 | 65/19/10/7 | 0,586 | 300 | 0,486 | 0,236 | 0,147 | 0,069 |
| 500 / 100 | M1 | 5734 | 0,754 | 71/18/8/4 | 0,434 | 260 | 0,508 | 0,245 | 0,159 | 0,078 |
| 500 / 100 | ticks | 7243 | 0,801 | 64/19/10/7 | 0,580 | 200 | 0,504 | 0,244 | 0,158 | 0,078 |
| 250 / 50 | M1 | 15061 | 0,637 | 84/12/4/1 | 0,457 | 170 | 0,476 | 0,287 | 0,188 | 0,095 |
| 250 / 50 | ticks | 29570 | 0,793 | 63/19/10/8 | 0,563 | 105 | 0,467 | 0,244 | 0,162 | 0,085 |
| 250 / 31 | M1 | 16025 | 0,656 | 82/12/4/3 | 0,433 | 165 | 0,471 | 0,447 | 0,284 | 0,151 |
| 250 / 31 | ticks | 41632 | 0,853 | 57/17/10/17 | 0,543 | 75 | 0,464 | 0,268 | 0,174 | 0,095 |

(Tabela completa de 12 linhas, incluindo T500/m62 e T750/m93, em `sequencia_recuos/out_txt/tick_sens.txt`.)
Leitura: em T ≥ 500 (m ≥ 100) M1 e ticks concordam em P(r2<r1), P(3R/5R/10R) e P(supera). Em escala pequena o M1 tem menos tentativas, mediana de r1 bem maior e um **excesso de P(3R)/P(5R) sobre a fórmula que não existe nos ticks** (T250/m50: 0,287 contra 0,244; fórmula 0,25). O "efeito" encontrado em m pequeno é do caminho de 2 pontos. P(supera de primeira) é maior nos ticks em toda escala (0,54–0,59 contra 0,43–0,46) porque o ponto de confirmação deixa de ser o extremo da vela; não comparar essa métrica entre as bases. P(r2<r1) é robusta (0,46–0,51).

## ATR (5 pregões anteriores; tercis da descoberta 107,6 / 137,7), T750/m150

P(supera | confirmado) 0,814 / 0,769 / 0,781 (nulo 0,811 / 0,768 / 0,774); P(supera de 1ª) 0,479 / 0,455 / 0,446 (nulo 0,482 / 0,449 / 0,439); P(5R) 0,172 / 0,133 / 0,147 (nulo 0,161 / 0,122 / 0,147). Nada destoa.

## Descoberta → confirmação (jul–ago, 44 pregões)

Regras congeladas em `regras_congeladas.json` antes de abrir jul–ago. Critério: mesmo sinal, z ≥ 1,64 contra o nulo, n ≥ 100, nas duas escalas principais (T750/m150 e T500/m100).

- N1–N5 (negativas, tudo igual ao nulo): **confirmaram**. T750/m150 em jul–ago: P(supera | x%) 0,654 / 0,483 / 0,373 / 0,260 (nulo 0,640 / 0,457 / 0,346 / 0,242, z ≤ 0,9); r2<r1 = 0,44 / 0,55 / 0,52 / 0,49 (z −1,1 a +1,6); ρ r1×r2 = −0,11 (z −1,0); trios 14,2 / 17,8 / 68,0% (nulo 15,6 / 16,4 / 68,0); padrão dos recuos anteriores 0,805 × 0,832 (nulo 0,807 / 0,811). Isolado: P(supera de 1ª) na ordem 2 = 0,571 × nulo 0,474 (z +2,7), não congelado.
- C1 (1º fundo em 23–38% de A, P(5R) acima do nulo): T750/m150 0,197 × nulo 0,152 (z +2,4, n 380); T500/m100 0,183 × 0,153 (z +2,4, n 694). Sinal confirmado nas duas escalas principais, mas o P(5R) fica a 1–3 pp do breakeven 0,167 e o IC cruza. Parcial.
- C4 (bounce entre 11 e 13h): P(5R) 0,220 × 0,173 (z +2,6) em T750; 0,202 × 0,174 (z +1,8) em T500; P(10R) 0,097 × 0,071 (z +2,5) e 0,128 × 0,100 (z +3,2). Confirmado em sinal, n 350–650; na descoberta T750 era 0,165 × 0,147 (z +2,5). Parcial.
- C2 (fundo ≥ recuo anterior): P(5R) 0,176 × 0,155 (z +2,0) em T750; 0,181 × 0,168 (z +1,5) em T500 — abaixo do critério na 2ª escala. Parcial/fraco.
- C3 (ordem 4+, A ≥ 2,5T): era um efeito de T250 no M1 (ver ticks); em T750 desc 0,144 × 0,144, conf 0,209 × 0,155 (z +2,5). Inconsistente. Falhou.
- Em jul–ago a ordem 2 mostrou P(3R) 0,346 × 0,246 (z +4,1, n 211) em T750. Não estava congelado; não conta.

## Pistas (SE … ENTÃO …)

| # | SE | ENTÃO | Papel | desc → conf | Status |
|---|---|---|---|---|---|
| P1 | movimento com A ≥ T e recuo ≥ m | P(novo topo antes de morrer) = (T−d)/T com d em pts; os níveis 23/38/50/62/79% não são barreira | ALVO/STOP: usar a fórmula | z −2,1…+1,0 → ≤ 0,9 | confirmou (negativa) |
| P2 | qualquer ordem do recuo (1º … 4+) | P(supera de primeira) e alcance não mudam | não usar ordem como LIGA/DESLIGA | 48,9 → 44,0% vs nulo ~45% | confirmou (negativa) |
| P3 | 2º recuo menor/maior que o 1º; trios crescentes/decrescentes; recuos anteriores encolhendo | nada: P(r2<r1) = 0,50, ρ = 0,02 | REJEITA como filtro | igual ao nulo → igual | confirmou (negativa) |
| P4 | 1º fundo em 23–38% de A, bounce de m pts | P(5R) ≈ 0,18–0,20 (fórmula 0,167, nulo 0,15) | ACEITA; STOP em L, ALVO 5R | +2,6 → +2,4 (2 escalas) | parcial |
| P5 | bounce entre 11h e 13h | P(5R) 0,20–0,22; P(10R) 0,10–0,13 (fórmula 0,091) | LIGA | +2,5 → +2,6 / +1,8 | parcial |
| P6 | escala pequena (m ≤ 62) no M1 | excesso de 3R/5R sobre a fórmula | — | +3 a +5 → — (some nos ticks) | falhou (artefato) |

Geometria: com stop em L (risco = m = T/5: 150 pts no 750, 100 pts no 500) e alvo 5R (750 / 500 pts), breakeven = 16,7%. Real em desc: 14,1% (T750), 16,4% (T500/m100). Os subconjuntos P4/P5 chegam a 18–22% em jul–ago, sem custo e sem slippage; com R$0,50 + 1 tick por lado em 150 pts (R$30) o custo é ~5% do R e o ganho (+0,1 a +0,3R, IC cruzando zero) fica na mesma ordem. Nenhum filtro encontrado leva a razão alvo/stop de 5–10× para expectativa positiva robusta; o nulo dá 1/(K+1) e o real o acompanha.

## Contagem de testes

Células comparadas com o nulo: descoberta 3.166 (9 configs × ~350; |z| > 2: 562; |z| > 3: 195, contra 144 e 9 esperados se independentes — o excesso vem das escalas pequenas e é parcialmente artefato do M1/nulo; as configs usam os mesmos dias e não são independentes), confirmação 2.961 (|z| > 2: 285; |z| > 3: 61). Escala principal T750/m150: 339 células na descoberta, |z| > 2: 26, |z| > 3: 4 (esperado ~15 e ~1). Checagem de ticks: 12 linhas × 14 métricas (sem nulo). Regras congeladas: 5 negativas + 4 candidatas. Set/2026 não foi aberto.

## Limitações

- Caminho de 2 pontos por vela: concorda com ticks em m ≥ 100; abaixo disso gera artefatos (recuos a mais/menos, excesso de payoff, P(supera de 1ª) deslocado).
- O nulo embaralhado em blocos de 30 min destrói persistência/reversão dentro do bloco; quando o real destoa em escala pequena não dá para separar micro-estrutura de ordem de vela. O tempo entre recuos (z −2 a −10 contra o nulo) vem do embaralhamento, não do mercado.
- Fórmula 1/(K+1) vale em passo fino; com K grande e o fim do pregão o real fica abaixo (10R: 0,07 contra 0,091).
- Sem custo nem slippage; stop assumido executado em L; irrealista em m = 31–50.
- Entradas do mesmo dia se sobrepõem; IC por bootstrap de dias; z entre sorteios do nulo; as 9 configs usam os mesmos dias.
- Só 2026 (122 pregões na descoberta, 44 na confirmação); n pequeno em A ≥ 2,5T e profundidade ≥ 62%.
