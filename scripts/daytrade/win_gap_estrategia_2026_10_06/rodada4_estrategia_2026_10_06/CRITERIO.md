# Rodada 4 — critério de escolha da célula final (escrito ANTES de ver a tabela stop × alvo)

Escrito em 2026-10-06, antes de rodar a grade da rodada 4. O holdout 2025-12-19..2026-02-19 (já gasto na rodada 3) é só descritivo e NÃO entra na escolha.

## Grade
Entrada fixa V2 r0 (1ª barra M5 contínua fecha contra o gap; limite no close dela; ttl 6 barras M5). Stops em pontos: 300, 400, 500, 600, 700, 800, 900, 1000, 1200, 1500. Alvos: nenhum; fixo 500, 1000, 1500, 2000 pts; 1R, 1,5R, 2R, 3R (R = distância do stop); parcial (50% em 1R, resto até o fim); breakeven após +1R, sem alvo. 110 células. IS 2026-04-06..2026-10-05, simulador a tick da rodada 2, R$1.000, sizing de produção, modos A e B, fills `toque` e `atrav+1t`.

## Vizinhança e suavidade
- Vizinhos de uma célula = os stops a ±1 e ±2 posições na lista de stops, MESMO alvo (até 4 vizinhos).
- Pontuação de suavidade (platô) da célula = **mediana do líquido B (fill `toque`) dos vizinhos**, sem a própria célula.
- Pico = líquido B da célula > 1,5 × mediana dos vizinhos.

## Elegibilidade (todas necessárias)
1. Pelo menos 3 vizinhos (exclui os stops 300, 400 e 1500 nas pontas, que só têm 2).
2. Modo A (conta contínua R$1.000) NÃO censurado na célula, nos dois fills (nenhuma ordem recusada por capital e caixa mínimo ≥ margem R$100), e em pelo menos 80% dos vizinhos.
3. Líquido B > 0 em `toque` e em `atrav+1t`, e > 0 nas duas metades (abr–jun e jul–out), na célula; e em pelo menos 80% dos vizinhos (líquido B > 0 em `toque`).
4. p do nulo de direção aleatória da célula ≤ 0,05 (fill `toque`).
5. Não é pico (líquido B ≤ 1,5 × mediana dos vizinhos).

## Escolha
A célula elegível com a MAIOR pontuação de suavidade. Desempate: maior mínimo do líquido B entre célula + vizinhos. Não se escolhe pelo máximo da tabela. Se o melhor platô for "sem alvo", isso é dito.

## Reportado sem entrar na escolha
Mapa de calor líquido B e R$/trade; censura do modo A; por alvo, quantos stops vizinhos de 700 ficam positivos e acima do nulo; 700 é platô ou pico; nulo de máximo da grade (p ajustado) e metades; holdout descritivo (regra M1 conservadora, rotulado como gasto).
