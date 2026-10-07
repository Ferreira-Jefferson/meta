# WIN gap — rodada 2 (2026-10-06): execução a tick, 6 meses, R$1.000

Janela única: **2026-04-06 a 2026-10-05** (nada de 2022-25 nem fev-mar/26). Os indícios nasceram nesta mesma janela: nenhum número daqui é fora da amostra.
Capital **R$1.000** (ordem do dono, substitui os R$250 da rodada 1), dimensionado pela função de produção (`config_for` + `contracts_from_capital_operacional` / escada, via `sizing.py`): **2 contratos** a R$1.000; o caixa arrastado do modo A leva a 1 a 5 contratos.
Dados checados em `CHECAGEM_DADOS.md`. Estratégia/execução em `regras.py`, `sim.py`; grade em `regras.grade()`. Reprodução: `ticks_prep.py` → `rodada.py` → `analise.py` → `antes_depois.py` → `crosscheck.py` → `checagem.py` → `gera_resultado.py`.

## 1. Correções feitas

**a) Stop dentro da barra do fill.** O motor só avalia stop/alvo a partir da barra M5 seguinte ao fill (o fill é resolvido depois do passo de saídas). Com ticks reais, escrevi um simulador a tick (`sim.py`), sem tocar `machine.py`/`profiles.py`: mesmas regras (EnterLimit + ttl 6 barras M5, alvo limite real, stop a mercado com 1 tick de deslize, `anchor_exits_at_fill`, zera no último tick do contínuo = barra das 18:20, fee R$0,50 por contrato). Sinais seguem em M5. O motor não é alimentado com ticks: 1,2 milhão de eventos por pregão × 120 pregões inviabiliza o motor em Python.

Cruzamento com o motor (R$1.000, `config_for`, 6 células: stop fixo, ATR, 1ª barra, estrutural, alvo-gap, RR; `crosscheck.py`):

- simulador em modo barra × motor, conta contínua: **6/6 idênticos** em entrada, contratos (1 a 4 por trade, caixa crescente), motivo, preço e P&L por fatia (ex.: V2 r150|S350 +R$9.114,50 nos dois; V1 r150|S.3atr T.6atr +R$12.548,50 nos dois).
- tick × barra, nos trades cuja saída por stop/alvo NÃO foi dentro da barra do fill: **entrada, motivo e barra de saída iguais em 39/39, 41/41, 91/91, 19/19, 21/21, 46/46**.
- Premissa de alvo: o simulador trata o alvo como limite parado desde o fill (fila 0). O caminho do motor com `exit_ttl_bars=10**9` arma a fatia no 1º toque e só preenche numa barra seguinte que toque de novo (uma fatia por barra): no mesmo conjunto de ordens de V2 r150|S700 T700 ele dá +R$4.067,00, contra +R$2.676,00 do limite-desde-o-fill (que é também o que o motor dá com `exit_ttl_bars=None`, usado no cruzamento). Escolha declarada: alvo parado desde o fill.

Antes (motor, barra) × depois (tick), 60 células de saída sem estado, R$1.000 por pregão, 2 contratos (`antes_depois.py`):

| medida | antes (barra/motor) | depois (tick) |
|---|---|---|
| trades com saída por STOP dentro da barra do fill (ignorada pelo motor) | 457 de 3.283 (13,9%) | 0 ignoradas (o tick resolve) |
| trades com saída por ALVO dentro da barra do fill | 111 de 3.283 (3,4%) | 0 ignoradas |
| pior trade, stop fixo de 350 pts | −1.210 a −1.360 pts (3,5× a 3,9× o stop) | −355 pts (1,01×) |
| pior trade, stop fixo de 700 pts | −1.210 a −1.360 pts (1,7× a 1,9×) | −705 pts (1,01×) |
| líquido somado das 60 células | R$323.440 | R$304.863 |

Na rodada 1 (R$250, 1 contrato) o pior trade foi −R$242,50 para um stop nominal de R$70 (3,5×). Stops por ATR/1ª barra/estrutural variam por dia: o pior trade fica a 1,2× a 2,7× a mediana do stop nominal (o stop de um dia ruim é maior que a mediana).

**b) Dados:** `CHECAGEM_DADOS.md` (resumo na seção 2).

## 2. Resumo da checagem de dados

- Gap == recalculado do CSV de fases em 125/125 dias comparáveis (diferença máxima 0 pt).
- Barras M5: abertura da 1ª barra == 1º negócio contínuo do CSV em 120/120; fechamento da última == último negócio contínuo em 120/120; última barra = 18:20 em 120/120; nenhuma barra ≥ 18:25. Máxima/mínima das barras == CSV em 117/120 e 118/120 (3 e 2 dias, 5 a 15 pts). Todas as 13.560 barras × ticks: high difere em 26, low em 28, close em 34; **sinal da barra 1 igual em 120/120 dias**.
- Ticks contínuos == CSV: fechamento 120/120, máxima 120/120, mínima 120/120, abertura 115/120 (5 dias com 5 pts de diferença no 1º tick, antes de 09:05; não afeta a execução).
- Excluídos (7 de 127): 3 rolagens (gap bruto 3.350 a 4.415 pts contra |gap| mediano 500; o dia seguinte tem gap normal, 235 a 345, e entra), 07-31 (abertura 12:34) e os 3 com ticks faltando (05-06, 08-10, 09-24: buracos de 6 a 12 min na janela de ordem ou com posição aberta; o simulador a tick não vê nível tocado dentro de buraco e o M1 não devolve a sequência). 10-05 (gap +17.775) fica.
- O leilão de abertura cai DENTRO da barra 09:00-09:05 em 120/120 dias (contínuo começa em mediana 09:02:52); a barra 1 é parcial e a decisão só acontece no fecho (09:05). Nenhum pregão com 1ª barra fora de 09:00.
- Look-ahead: ATR de dias anteriores e filtro de volume do call só usam o passado dentro da janela; 5 testes pytest em `tests/test_win_gap_rodada2_lookahead.py` (5 passed, em paralelo). `src/` não foi tocado, então a suíte inteira não foi reexecutada.

## 3. Grade (100 células, definida antes de rodar)

Entradas (4): V2 recuo 150, V2 recuo 0, V1 (fade do gap) recuo 150, V3 (V2 sem trade quando o volume do call de D−1 é alto) recuo 150. Saídas (25, 8 famílias): fixo (S350, S700, S350/T700, S700/T700, S700/T1400); volatilidade (stop 0,3 ou 0,6 × ATR dos 10 pregões anteriores, com/sem alvo; stop 1× e alvo 2× a faixa da 1ª barra); estrutural (stop no outro extremo da 1ª barra, com/sem alvo 2R); alvo = call de D−1 (3); trailing (400 pts, 700 pts, mínima das últimas 3 barras M5, EMA21 M5; stop inicial 700); breakeven +500 (com/sem alvo 1400); parcial (metade em T700; resto segura / trailing 400); saída por tempo 12:00 e 15:00.
Trailing, breakeven, swing e EMA são recalculados no fecho de cada barra M5 e valem da barra seguinte (AdjustStop de produção), com os extremos medidos nos ticks desde a entrada. ttl da ordem 6 barras M5 (30 min). Alvo-gap só opera se o call de D−1 estiver a ≥ 100 pts do preço de entrada; stops por ATR exigem ≥ 3 pregões anteriores.
Cada eixo mexeu no resultado: as 100 células têm líquidos distintos e as 8 famílias diferem da referência fixa (seção 5). Fills: `toque` (enche ao tocar o nível, fila 0/0) e `atrav+1t` (≥ 1 tick atravessado). **O WIN não tem fila calibrada em `fidelidade.py`; nenhuma premissa de fila foi inventada.**

Modos: **B** = cada pregão com R$1.000 novos (2 contratos); aqui vivem o nulo e o máximo. **A** = conta contínua desde R$1.000 (contratos pela escada, caixa arrastado). O caixa mínimo do A inclui a pior excursão intradia (aproximação: pior excursão × contratos).

## 4. Top 10 (por t = excesso do líquido sobre o nulo de direção aleatória, em desvios-padrão; modo B, toque)

Cada célula tem 4 linhas: B toque, A toque, B atrav+1t, A atrav+1t. `p nulo` = nulo de direção aleatória da célula; `p adj` = p ajustado pelo máximo da grade inteira (seção 6). `seq perd` = maior sequência de trades perdedores; `saidas s/a/tr/te/f` = stop/alvo/trail/tempo/flatten (pernas).

```
{{TOP10}}
```

## 5. Famílias de saída com entrada fixa V2 recuo 150

```
{{FAMILIAS}}
```

Entradas × saídas, líquido B toque em R$ (100 células):

```
{{MATRIZ}}
```

## 6. Correção por seleção e metades

```
{{SELECAO}}
```

Nulo: 20.000 sorteios de direção por pregão (o MESMO sorteio para todas as células, preservando a correlação entre elas); estatística da célula = líquido B; `t` = (observado − média do nulo) / desvio do nulo da própria célula. p ajustado da célula = fração dos sorteios em que o MELHOR t da grade inteira ≥ o t observado dela; também com a estatística em R$ bruto (escala dominada pelas saídas largas).

## 7. Censura

- Modo A (conta contínua R$1.000, toque): 7 de 100 células censuradas (ordens recusadas por capital ou caixa mínimo < margem R$100): V2 r0|Sbar1 T2R (40 recusadas, caixa mín R$84), V1 r150|S350 T700 (49; R$63,50), V1 r150|S700 T700 (89; −R$39), V1 r150|Sbar1 T2R (0; −R$123,50), V1 r150|S350 Tgap (71; R$15,50), V1 r150|S700 Tgap (72; R$73,50), V1 r150|Sbar1 Tgap (9; −R$35). Todas com líquido A < 0. Nenhuma das 10 melhores censurada (top 10 por t: caixa mínimo de R$564,50 a R$898).
- Modo B não tem censura de caixa por construção (R$1.000 novos a cada pregão).
- Pregões sem trade: coluna `sem trade` (sem gatilho: V2 ~57 de 120, V3 ~75, V1 nenhum; não-preenchimento 1,6% em V2 r0 e 25 a 31% com recuo 150).

## 8. Limitações

- A janela é a mesma onde as pistas foram achadas; o p ajustado corrige a escolha DENTRO da grade de 100 células, não a escolha das 3 hipóteses nem a da grade.
- Fila do WIN não calibrada. Sensibilidade mais dura nas 10 melhores (`antes_depois.py`, parte b): atravessar 3 e 5 ticks (seção 9).
- Stop e saídas a mercado pagam 1 tick de deslize contra a posição; o stop executa no 1º tick que cruza o nível (preço do tick, nunca melhor que o nível).
- ATR de 10 dias usa só pregões da janela (≥ 3); nada anterior a 04-06.
- Modo A: contratos de 1 a 5 pela escada (compõe resultado e risco com o caixa); caixa mínimo aproximado.
- Trailing/BE por barra M5 fechada: um stop móvel de corretora tick a tick daria outro número.

## 9. Preenchimento mais duro (10 melhores por t; modo B, 2 contratos, líquido R$)

```
{{FILL}}
```
