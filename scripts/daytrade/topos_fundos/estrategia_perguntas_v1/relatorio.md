# Estratégia de perguntas v1 (WIN M15)

Código: lib.py (simulação, modelos, painel, nulo), prep.py (resultado por vela-lado), cv.py (CV por trimestre no IS), final.py (A/B/C), diag1.py (diagnósticos), var_d.py (variação D). Logs: cv.log, final.log, diag1.log, var_d.log.

## Desenho
Operação por vela-lado: limitada no fechamento (enche se passar 10 pts em 3 velas, nunca a mercado), stop 1 ou 1,5 ATR, sem alvo, trailing na mínima das últimas N velas (4 ou 8), fim do dia, custo 10 pts/contrato. 2 contratos, R$ = pts × 0,20 × 2. Baseline aleatório = −10 pts/contrato/op.
Modelo escolhido por leave-one-quarter-out no IS (15 trimestres) entre 4 geometrias × 2 conjuntos × 7 modelos × 6 cortes × 4 K (~1.100 configs); objetivo = média trimestral − 0,5·desvio.

## Tabela (R$, 2 contratos; IC90 por bootstrap de dias; nulo 300x)
| desenho | período | ops | total R$ | IC90 | pior queda | FL | acerto | % meses+ | Sharpe | nulo média / p95 | p(nulo) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A ridge, 1 rep./grupo \|phi\|>0,5, 53 perg., stop1/N8, corte p80, K livre | IS (fora-da-amostra por CV) | 1204 | +16.016 | [+4.610; +27.741] | 2.966 | 1,22 | 32% | 58% | 1,20 | −4.418 / +5.048 | 0,00 |
| | OOS | 424 | −3.745 | [−13.375; +5.933] | 7.941 | 0,91 | 26% | 54% | −0,64 | −2.590 / +6.690 | 0,58 |
| | virgem | 127 | −1.651 | [−5.343; +2.357] | 3.224 | 0,86 | 28% | 33% | −1,50 | −1.321 / +2.772 | 0,56 |
| B ridge + 3 perguntas de hora, stop1/N4, p70, K1 | IS | 763 | +13.474 | [+3.734; +23.521] | 2.557 | 1,28 | 28% | 60% | 1,17 | −3.246 / +3.850 | 0,00 |
| | OOS | 209 | −5.445 | [−11.419; +716] | 6.601 | 0,74 | 19% | 23% | −1,48 | −1.530 / +4.161 | 0,88 |
| | virgem | 50 | −1.270 | [−3.337; +1.149] | 1.804 | 0,70 | 20% | 0% | −1,98 | −585 / +1.765 | 0,68 |
| C boosting prof. 2 (20 rodadas), stop1,5/N8, p80, K1 | IS | 498 | +11.398 | [+2.858; +20.027] | 1.736 | 1,29 | 41% | 60% | 1,11 | −1.748 / +5.055 | 0,01 |
| | OOS | 140 | +787 | [−6.004; +8.267] | 4.247 | 1,04 | 34% | 46% | 0,18 | −1.113 / +4.661 | 0,29 |
| | virgem | 26 | −1.961 | [−3.600; −346] | 1.898 | 0,40 | 23% | 0% | −4,13 | −288 / +1.708 | 0,93 |
| **D contagem simples de 18 perguntas de tendência/posição (sem pesos), stop1,5/N8, corte 16 de 18 (p90 IS), K livre** | IS | 565 | +4.807 | [−3.621; +13.517] | 3.708 | 1,11 | 39% | 62% | 0,47 | −1.551 / +5.421 | 0,08 |
| | OOS | 132 | **+7.636** | [+524; +14.894] | 2.483 | 1,51 | 39% | 62% | 1,69 | −703 / +4.154 | **0,00** |
| | virgem | 17 | +197 | [−933; +1.359] | 286 | 1,17 | 41% | 67% | 0,61 | −182 / +1.245 | 0,30 |
| Escada v4.1 (referência) | IS / OOS / virgem | 416 / 109 / 23 | +12.398 / +10.521 / +316 | | | | | | | | |

Trimestres A (R$): IS 2022T1 +3.239, T2 +982, T3 +2.885, T4 +2.194, 2023T1 +794, T2 −139, T3 +631, T4 +290, 2024T1 +314, T2 −134, T3 +1.776, T4 +1.789, 2025T1 +2.875, T2 −1.241, T3 −240 | OOS 25T4 −907, 26T1 +1.013, T2 +742, T3 −1.301, T4 −3.292 | virgem −1.651.
Trimestres D (R$): IS +406, −580, +347, +1.566, −198, −155, −1.391, +546, +41, −114, +1.345, −233, +2.493, −769, +1.501 (8/15 positivos) | OOS +1.160, +2.654, −21, +3.256, +587 | virgem +197.
Sobreposição com a escada: A 212/1204 (IS), 64/424 (OOS); D 162/565 (IS), 38/132 (OOS), 4/17 (virgem). Ou seja ~70% das ops de D não coincidem com a escada.
Mão 1/2 (2 contratos só com score ≥ p95) em A/B/C: não ajuda em OOS (A −3.376, B −3.306, C +300).

Pesos de A (pts por contrato por resposta "sim", maiores em módulo): C6 −75, N07 −49, Q24 −48, N13 +42, N42 −36, N18 −28, T3 −25, Q42b +24, N12 +23, N30 −22 (intercepto −8,7; corte = +40 pts previstos/contrato). Metade são perguntas sem lado (C6, Q24, N30, N29, N14…) que atuam como "operar ou não". Lista completa em final.log.

## Por que A/B/C falham (números)
1. Pesos não estacionários: correlação de Spearman dos pesos refeitos por período IS×OOS = 0,02, IS×virgem = −0,29, OOS×virgem = 0,00 (C6: −75 → +58 → +11; T3: −25 → −296).
2. Modelo não ordena fora do IS: correlação previsto×realizado por vela-lado = +0,036 no IS (OOF), +0,024 no OOS, −0,078 no virgem; decis do OOS não monotônicos (−50 … +48 … −10).
3. O "edge" do IS é parcialmente regime e seleção: walk-forward (só passado) no IS dá +R$3.424 em 948 ops (+9 pts/op; 6/9 trimestres) contra +R$6.060 do leave-one-quarter-out no mesmo trecho (+19 pts/op). A CV por trimestre empresta regime vizinho; mesmo assim ela seleciona entre ~1.100 configs.
4. Custo: 1,2–1,7 ops/dia de A; média por op de −22 pts no OOS vs aleatório −10; o aleatório já é negativo (custo), o modelo ficou abaixo do nulo médio no OOS de A e B.
5. Redundância tratada (um representante por |phi|>0,5; ridge) não resolveu: o problema é instabilidade, não dupla contagem.

## D: o que sobrou
Sem estimar nada, só "quantas das 18 perguntas de tendência/posição respondem a favor" (N16–N24, N36–N38, N40, N45, C1–C4; família fixada a priori) e corte alto: OOS +R$7.636 (IC90 +524 a +14.894; p_nulo 0,00; acerto 39%, FL 1,51, pior queda R$2.483, 62% meses+), virgem ≈ 0 (n=17), IS +R$4.807 mas IC cruza zero (p_nulo 0,08). Vizinhança descritiva (K livre, 4 geometrias × cortes p70–p95): em p≥90 todas as 8 células são positivas no OOS (+5.035 a +7.818) e no IS quase todas (+336 a +4.807); em p70/p80 o IS é negativo (−5.596 a −1.787) enquanto o OOS segue positivo. Ressalvas: a escolha da família foi guiada pelo diagnóstico anterior (continuação > reversão); IS fraco; virgem sem poder (17 ops); n OOS = 132 ops em 1 ano, +R$3,3 mil de um único trimestre (26T3). Não é evidência suficiente; é a única pista.

## Veredito
Pesos aprendidos (ridge/boosting) sobre as 81 perguntas: REFUTADO (bom na CV do IS, nulo/negativo em OOS e virgem; pesos instáveis). A contagem simples de perguntas de tendência a favor com alvo assimétrico/trailing é a única pista positiva (OOS +7,6 mil, p_nulo 0,00), mas é fraca no IS e no virgem.
Próximo passo: congelar D como hipótese pré-registrada (família, geometria stop 1,5/N8, corte p90 do IS) e testar em dado novo (out/26+) e em janelas rolantes, medindo se acrescenta algo à escada (só ~30% de sobreposição) e ampliando o virgem (Q4/2021 tem 17 ops). Se continuar, usar as perguntas sem lado como porteiro com sinal pré-fixado (não estimado), e pesos só com regularização forte à direção da literatura, já que pesos livres não sobrevivem a regime.
