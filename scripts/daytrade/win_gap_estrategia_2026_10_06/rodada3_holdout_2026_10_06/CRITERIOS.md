# Rodada 3 — holdout: critérios de passa/falha (escritos ANTES de qualquer execução no holdout)

Escrito em 2026-10-06, antes de rodar a janela 2025-12-19 a 2026-02-19.

## O que é congelado (nada muda)
- Células da rodada 2, mesmo código (`regras.py`), mesmos parâmetros: **V2 r0 | S700** e **V2 r0 | S.6atr**.
  - 1ª barra M5 contínua fecha contra o gap; limite no close dela; ttl 6 barras M5 (30 min); stop 700 pts (ou 0,6 × ATR dos ≤ 10 pregões anteriores, mínimo 3); sem alvo; zera na última barra do contínuo (18:20).
- Capital R$1.000, dimensionamento de produção (`sizing.py`, `config_for`) = 2 contratos. Modo A (conta contínua, 1 a 5 contratos pela escada) e modo B (R$1.000 novos por pregão, 2 contratos). Fill `toque` e `atrav+1t`.
- Janela: 2025-12-19 a 2026-02-19. Nenhum dia da IS (a partir de 2026-04-06), de fev-mar/26 (usado na rodada 1) nem de out a meados de dez/25. Aquecimento do ATR: só PREÇOS dos pregões imediatamente anteriores à janela.

## Execução (decisão tomada antes de ver qualquer número)
- Sem ticks para a janela (corretora só entrega ticks de 2026-02-20 em diante; ver `DADOS_HOLDOUT.md`). Execução em barras **M1** com regra conservadora na barra do fill: se o nível do stop está dentro da faixa [low, high] da barra M1 em que a ordem enche, assume-se que o stop foi acionado (preço = nível − 1 tick de deslize). Nas barras seguintes: regra do motor (stop se low ≤ nível, preço = min(open, nível) − 1 tick).
- Variante mais dura (sensibilidade): saída do stop na barra do fill ao LOW da barra.
- Preços de leilão e de call são PROXY nesta janela (não há ticks de fases).
- Para comparar com a IS no MESMO método, a IS também é rodada com a regra M1 conservadora.

## Critérios (cada um é passa ou falha, individualmente; sem nota composta)
Modo B, fill `toque`, por célula, salvo indicação:
1. **C1** líquido B > 0 (em `toque` e em `atrav+1t`).
2. **C2** R$ por trade no holdout ≥ 50% do R$ por trade da IS medida com a mesma regra M1 (e > 0).
3. **C3** nulo de direção aleatória (mesmo método da rodada 2: 20.000 sorteios por pregão, direção real × oposta nos MESMOS dias de gatilho): p ≤ 0,05 por célula; também reportado o p com Bonferroni (× 2 células).
4. **C4** win% > breakeven empírico (`perda média / (ganho médio + perda média)`).
5. **C5** modo A (conta contínua R$1.000) sem censura (nenhuma ordem recusada por capital; caixa mínimo ≥ margem R$100).
6. **C6** pior trade ≤ 1,5 × o stop nominal da célula (S700: ≤ 1.050 pts; S.6atr: ≤ 1,5 × o stop do dia).

## Reportado sem critério
n de pregões, sinais, fills, % sem fill, tabela padrão (`report.py`) para as duas células e as duas premissas de fill, R$/trade e R$/pregão lado a lado com a IS, e nota de poder estatístico (efeito mínimo detectável com ~40 pregões e ~20 trades).
