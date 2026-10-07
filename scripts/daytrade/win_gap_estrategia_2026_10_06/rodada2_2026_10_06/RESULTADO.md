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
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes        fill        modo         ctr     BE emp%   sem fill%  atraso min    seq perdsaidas s/a/tr/te/f      p nulo       p adj   sem trade
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
V2 r0 | S700                          —     9.572,00        —    1.785,00     5,36  40,3%     62      79,77     0,5              —     120       toque    B pregao           2        25,6         1,6         0,0           7 34/0/0/0/28       0,003       0,064      58/120  fila NAO CALIBRADA (WIN); fill toque
V2 r0 | S700                   1.312,0%    13.120,00    16,9%    2.677,50     4,90  40,3%     62     109,33     0,5      14.120,00     120       toque     A conta   3.3 [1-4]        27,4         1,6         0,0           7 34/0/0/0/28           —           —      58/120  fila NAO CALIBRADA (WIN)
V2 r0 | S700                          —     9.572,00        —    1.785,00     5,36  40,3%     62      79,77     0,5              —     120    atrav+1t    B pregao           2        25,6         1,6         0,0           7 34/0/0/0/28       0,003       0,065      58/120  fila NAO CALIBRADA (WIN); fill atrav+1t
V2 r0 | S700                   1.312,0%    13.120,00    16,9%    2.677,50     4,90  40,3%     62     109,33     0,5      14.120,00     120    atrav+1t     A conta   3.3 [1-4]        27,4         1,6         0,0           7 34/0/0/0/28           —           —      58/120  fila NAO CALIBRADA (WIN)
V2 r0 | S.3atr                        —    11.533,00        —    2.237,00     5,16  45,9%     61      96,11     0,5              —     120       toque    B pregao           2        29,3         1,6         0,0           7 29/0/0/0/32       0,002       0,070      59/120  fila NAO CALIBRADA (WIN); fill toque
V2 r0 | S.3atr                 1.799,0%    17.989,50    23,2%    5.592,50     3,22  45,9%     61     149,91     0,5      18.989,50     120       toque     A conta   3.7 [2-5]        31,6         1,6         0,0           7 29/0/0/0/32           —           —      59/120  fila NAO CALIBRADA (WIN)
V2 r0 | S.3atr                        —    11.533,00        —    2.237,00     5,16  45,9%     61      96,11     0,5              —     120    atrav+1t    B pregao           2        29,3         1,6         0,0           7 29/0/0/0/32       0,002       0,071      59/120  fila NAO CALIBRADA (WIN); fill atrav+1t
V2 r0 | S.3atr                 1.799,0%    17.989,50    23,2%    5.592,50     3,22  45,9%     61     149,91     0,5      18.989,50     120    atrav+1t     A conta   3.7 [2-5]        31,6         1,6         0,0           7 29/0/0/0/32           —           —      59/120  fila NAO CALIBRADA (WIN)
V2 r0 | S700 P50%T700                 —     6.972,00        —    1.040,00     6,70  45,2%     62      58,10     0,5              —     120       toque    B pregao           2        28,5         1,6         0,0           534/39/0/0/28       0,003       0,073      58/120  fila NAO CALIBRADA (WIN); fill toque
V2 r0 | S700 P50%T700            913,9%     9.139,00    16,5%    1.932,50     4,73  45,2%     62      76,16     0,5      10.139,00     120       toque     A conta   3.1 [1-4]        31,3         1,6         0,0           534/39/0/0/27           —           —      58/120  fila NAO CALIBRADA (WIN)
V2 r0 | S700 P50%T700                 —     6.972,00        —    1.040,00     6,70  45,2%     62      58,10     0,5              —     120    atrav+1t    B pregao           2        28,5         1,6         0,0           534/39/0/0/28       0,003       0,074      58/120  fila NAO CALIBRADA (WIN); fill atrav+1t
V2 r0 | S700 P50%T700            913,9%     9.139,00    16,5%    1.932,50     4,73  45,2%     62      76,16     0,5      10.139,00     120    atrav+1t     A conta   3.1 [1-4]        31,3         1,6         0,0           534/39/0/0/27           —           —      58/120  fila NAO CALIBRADA (WIN)
V2 r0 | S700 sai15h                   —     9.074,00        —    1.799,00     5,04  43,5%     62      75,62     0,5              —     120       toque    B pregao           2        28,3         1,6         0,0           7 33/0/0/29/0       0,004       0,076      58/120  fila NAO CALIBRADA (WIN); fill toque
V2 r0 | S700 sai15h            1.325,4%    13.254,00    19,6%    3.086,00     4,29  43,5%     62     110,45     0,5      14.254,00     120       toque     A conta   3.2 [1-4]        29,4         1,6         0,0           7 33/0/0/29/0           —           —      58/120  fila NAO CALIBRADA (WIN)
V2 r0 | S700 sai15h                   —     9.074,00        —    1.799,00     5,04  43,5%     62      75,62     0,5              —     120    atrav+1t    B pregao           2        28,3         1,6         0,0           7 33/0/0/29/0       0,004       0,077      58/120  fila NAO CALIBRADA (WIN); fill atrav+1t
V2 r0 | S700 sai15h            1.325,4%    13.254,00    19,6%    3.086,00     4,29  43,5%     62     110,45     0,5      14.254,00     120    atrav+1t     A conta   3.2 [1-4]        29,4         1,6         0,0           7 33/0/0/29/0           —           —      58/120  fila NAO CALIBRADA (WIN)
V2 r0 | S.6atr                        —    13.701,00        —    3.490,00     3,93  57,4%     61     114,17     0,5              —     120       toque    B pregao           2        38,6         1,6         0,0           6 13/0/0/0/48       0,003       0,077      59/120  fila NAO CALIBRADA (WIN); fill toque
V2 r0 | S.6atr                 2.327,1%    23.271,00    23,6%    5.854,50     3,97  57,4%     61     193,93     0,5      24.271,00     120       toque     A conta   3.6 [2-5]        39,5         1,6         0,0           6 13/0/0/0/48           —           —      59/120  fila NAO CALIBRADA (WIN)
V2 r0 | S.6atr                        —    13.701,00        —    3.490,00     3,93  57,4%     61     114,17     0,5              —     120    atrav+1t    B pregao           2        38,6         1,6         0,0           6 13/0/0/0/48       0,003       0,078      59/120  fila NAO CALIBRADA (WIN); fill atrav+1t
V2 r0 | S.6atr                 2.327,1%    23.271,00    23,6%    5.854,50     3,97  57,4%     61     193,93     0,5      24.271,00     120    atrav+1t     A conta   3.6 [2-5]        39,5         1,6         0,0           6 13/0/0/0/48           —           —      59/120  fila NAO CALIBRADA (WIN)
V3 r150 | S700 BE500                  —     4.629,00        —      849,00     5,45  29,0%     31      38,58     0,3              —     120       toque    B pregao           2        12,7        31,1         0,9           5  9/0/13/0/9       0,002       0,082      89/120  fila NAO CALIBRADA (WIN); fill toque
V3 r150 | S700 BE500             460,7%     4.607,00    15,2%      852,00     5,41  29,0%     31      38,39     0,3       5.607,00     120       toque     A conta   2.7 [1-3]        14,5        31,1         0,9           5  9/0/13/0/9           —           —      89/120  fila NAO CALIBRADA (WIN)
V3 r150 | S700 BE500                  —     4.250,00        —      849,00     5,01  26,7%     30      35,42     0,2              —     120    atrav+1t    B pregao           2        12,0        33,3         0,8           5  9/0/13/0/8       0,005       0,143      90/120  fila NAO CALIBRADA (WIN); fill atrav+1t
V3 r150 | S700 BE500             422,8%     4.228,00    16,3%      852,00     4,96  26,7%     30      35,23     0,2       5.228,00     120    atrav+1t     A conta   2.7 [1-3]        13,7        33,3         0,8           5  9/0/13/0/8           —           —      90/120  fila NAO CALIBRADA (WIN)
V2 r0 | S.6atr T1.2atr                —    12.569,00        —    3.490,00     3,60  57,4%     61     104,74     0,5              —     120       toque    B pregao           2        39,6         1,6         0,0           6 13/8/0/0/40       0,003       0,083      59/120  fila NAO CALIBRADA (WIN); fill toque
V2 r0 | S.6atr T1.2atr         2.027,3%    20.273,00    23,8%    5.195,50     3,90  57,4%     61     168,94     0,5      21.273,00     120       toque     A conta   3.4 [2-5]        40,6         1,6         0,0           6 13/8/0/0/40           —           —      59/120  fila NAO CALIBRADA (WIN)
V2 r0 | S.6atr T1.2atr                —    12.569,00        —    3.490,00     3,60  57,4%     61     104,74     0,5              —     120    atrav+1t    B pregao           2        39,6         1,6         0,0           6 13/8/0/0/40       0,003       0,085      59/120  fila NAO CALIBRADA (WIN); fill atrav+1t
V2 r0 | S.6atr T1.2atr         2.027,3%    20.273,00    23,8%    5.195,50     3,90  57,4%     61     168,94     0,5      21.273,00     120    atrav+1t     A conta   3.4 [2-5]        40,6         1,6         0,0           6 13/8/0/0/40           —           —      59/120  fila NAO CALIBRADA (WIN)
V3 r150 | S700 BE500 T1400            —     4.151,00        —      849,00     4,89  38,7%     31      34,59     0,3              —     120       toque    B pregao           2        19,4        31,1         0,9           5 9/12/10/0/0       0,005       0,100      89/120  fila NAO CALIBRADA (WIN); fill toque
V3 r150 | S700 BE500 T1400       400,4%     4.004,00    17,0%      849,00     4,72  38,7%     31      33,37     0,3       5.004,00     120       toque     A conta   2.3 [1-3]        21,2        31,1         0,9           5 9/12/10/0/0           —           —      89/120  fila NAO CALIBRADA (WIN)
V3 r150 | S700 BE500 T1400            —     3.592,00        —      857,00     4,19  36,7%     30      29,93     0,2              —     120    atrav+1t    B pregao           2        19,4        33,3         0,8           5 9/11/10/0/0       0,013       0,219      90/120  fila NAO CALIBRADA (WIN); fill atrav+1t
V3 r150 | S700 BE500 T1400       359,1%     3.591,00    21,7%      994,50     3,61  36,7%     30      29,93     0,2       4.591,00     120    atrav+1t     A conta   2.1 [1-3]        19,4        33,3         0,8           5 9/11/10/0/0           —           —      90/120  fila NAO CALIBRADA (WIN)
V3 r150 | S350                        —     6.295,00        —      715,00     8,80  35,5%     31      52,46     0,3              —     120       toque    B pregao           2        14,4        31,1         0,9           5 19/0/0/0/12       0,003       0,113      89/120  fila NAO CALIBRADA (WIN); fill toque
V3 r150 | S350                   825,4%     8.253,50    11,6%    1.072,50     7,70  35,5%     31      68,78     0,3       9.253,50     120       toque     A conta   2.9 [2-4]        15,1        31,1         0,9           5 19/0/0/0/12           —           —      89/120  fila NAO CALIBRADA (WIN)
V3 r150 | S350                        —     5.916,00        —      715,00     8,27  33,3%     30      49,30     0,2              —     120    atrav+1t    B pregao           2        13,7        33,3         0,8           5 19/0/0/0/11       0,004       0,139      90/120  fila NAO CALIBRADA (WIN); fill atrav+1t
V3 r150 | S350                   787,5%     7.874,50    12,1%    1.072,50     7,34  33,3%     30      65,62     0,2       8.874,50     120    atrav+1t     A conta   2.9 [2-4]        14,3        33,3         0,8           5 19/0/0/0/11           —           —      90/120  fila NAO CALIBRADA (WIN)
V3 r150 | S350 T700                   —     2.741,00        —      572,00     4,79  54,8%     31      22,84     0,3              —     120       toque    B pregao           2        33,9        31,1         0,9           4 14/17/0/0/0       0,007       0,117      89/120  fila NAO CALIBRADA (WIN); fill toque
V3 r150 | S350 T700              253,0%     2.530,00    14,2%      500,50     5,05  54,8%     31      21,08     0,3       3.530,00     120       toque     A conta   2.0 [1-3]        35,4        31,1         0,9           4 14/17/0/0/0           —           —      89/120  fila NAO CALIBRADA (WIN)
V3 r150 | S350 T700                   —     2.462,00        —      572,00     4,30  53,3%     30      20,52     0,2              —     120    atrav+1t    B pregao           2        33,9        33,3         0,8           4 14/16/0/0/0       0,008       0,146      90/120  fila NAO CALIBRADA (WIN); fill atrav+1t
V3 r150 | S350 T700              253,3%     2.533,50    14,2%      500,50     5,06  53,3%     30      21,11     0,2       3.533,50     120    atrav+1t     A conta   2.0 [1-3]        33,1        33,3         0,8           4 14/16/0/0/0           —           —      90/120  fila NAO CALIBRADA (WIN)
```

## 5. Famílias de saída com entrada fixa V2 recuo 150

```
   familia  celulas         melhor     B_liq  t_melhor  t_mediano  liq_mediano  frac_liq_pos  p_adj_melhor  A_liq_melhor  A_censurada
   F1 fixo        5           S350  8,180.00      2.39       1.78     5,594.00          1.00          0.14     12,451.00        False
    F2 vol        5 S.6atr T1.2atr 12,193.00      2.36       2.24     9,455.00          1.00          0.15     20,194.50        False
 F3 estrut        2          Sbar1  5,746.00      1.44       0.95     3,379.00          1.00          0.61      6,105.00        False
    F4 gap        3      S350 Tgap    594.00      1.51       0.93       594.00          0.67          0.57        469.50        False
  F5 trail        4  S700 trail700  3,658.00      1.39       1.26     2,836.00          1.00          0.64      3,565.00        False
     F6 BE        2     S700 BE500  5,238.00      2.02       1.97     4,539.00          1.00          0.30      5,237.50        False
F7 parcial        2  S700 P50%T700  4,987.00      1.81       1.47     3,115.00          1.00          0.41      3,098.00        False
  F8 tempo        2    S700 sai15h  6,478.00      1.78       1.78     6,353.00          1.00          0.42      6,234.00        False
```

Entradas × saídas, líquido B toque em R$ (100 células):

```
entrada                 V1 r150  V2 r0  V2 r150  V3 r150
saida                                                   
S350                      4,748  6,252    8,180    6,295
S700                      5,992  9,572    7,822    5,331
S350 T700                  -224  2,950    2,842    2,741
S700 T700                -1,456  4,372    2,152    1,905
S700 T1400                2,678  6,352    5,594    4,407
S.3atr                    8,806 11,533    9,455    7,952
S.6atr                   10,796 13,701   12,207    8,998
S.3atr T.6atr             8,004  8,265    8,027    7,240
S.6atr T1.2atr           10,714 12,569   12,193    8,886
S1R1 T2R1                 8,216  9,192    8,092    5,745
Sbar1                     4,394  7,600    5,746    4,741
Sbar1 T2R                   364  1,746    1,012    1,555
S350 Tgap                -2,940    973      594    1,046
S700 Tgap                -2,716    549      -72      546
Sbar1 Tgap                 -684    195      692      426
S700 trail400               766    624    1,610    1,997
S700 trail700             2,604  2,560    3,658    2,435
S700 swing3               2,336  2,000    2,842    2,785
S700 ema21                2,466  1,036    2,830    3,301
S700 BE500                5,078  2,696    5,238    4,629
S700 BE500 T1400          2,624  1,884    3,840    4,151
S700 P50%T700             2,268  6,972    4,987    3,618
S700 P50%T700 trail400      157    779    1,243    1,881
S700 sai12h               5,866  8,978    6,228    5,219
S700 sai15h               5,208  9,074    6,478    3,869

colunas: entrada | liquido por saida; soma por entrada: {'V1 r150': 86065.0, 'V2 r0': 132424.0, 'V2 r150': 123490.0, 'V3 r150': 101699.0}
```

## 6. Correção por seleção e metades

```
=== SELECAO === vencedor por t: V2 r0 | S700 | B toque liquido 9572.00 | t=2.74 | p celula=0.0027 | p ajustado (max-stat sobre 100 celulas)=0.0641 | p ajustado com estatistica em R$ bruto=0.1270
vencedor por liquido B: V2 r0 | S.6atr liquido 13701.00 t=2.67 p celula=0.0032 p ajustado=0.0772 p ajustado R$=0.0222
celulas com p celula<0,05: 52/100 (esperado ao acaso ~5); com p ajustado<0,05: 0

METADES (modo B toque, liquido R$)
pregoes: abr-jun 56 | jul-out 64 | correlacao de postos entre metades (100 celulas) = 0.59 | celulas no top10 das DUAS metades: 1
vencedor (V2 r0 | S700): abr-jun 5010.00 | jul-out 4562.00 | positivo nas 2 metades: True
celulas com liquido>0 nas duas metades: 72/100; >0 so' numa: 26; <=0 nas duas: 2
top10 abr-jun: ['V1 r150 | S.3atr', 'V1 r150 | S.3atr T.6atr', 'V1 r150 | S700 BE500', 'V2 r0 | S.3atr', 'V1 r150 | S700', 'V2 r150 | S.3atr', 'V3 r150 | S.3atr', 'V1 r150 | S700 sai12h', 'V2 r150 | S.3atr T.6atr', 'V3 r150 | S.6atr']
top10 jul-out: ['V2 r0 | S.6atr', 'V2 r0 | S.6atr T1.2atr', 'V2 r150 | S.6atr T1.2atr', 'V2 r150 | S.6atr', 'V1 r150 | S.6atr T1.2atr', 'V1 r150 | S.6atr', 'V2 r0 | S.3atr', 'V2 r0 | S700 sai12h', 'V2 r0 | S700 sai15h', 'V2 r0 | S1R1 T2R1']
top10 geral em cada metade (abr-jun / jul-out):
   V2 r0 | S700                          5010.00    4562.00
   V2 r0 | S.3atr                        5483.00    6050.00
   V2 r0 | S700 P50%T700                 3884.00    3088.00
   V2 r0 | S700 sai15h                   4228.00    4846.00
   V2 r0 | S.6atr                        4871.00    8830.00
   V3 r150 | S700 BE500                  3748.00     881.00
   V2 r0 | S.6atr T1.2atr                4127.00    8442.00
   V3 r150 | S700 BE500 T1400            2488.00    1663.00
   V3 r150 | S350                        4082.00    2213.00
   V3 r150 | S350 T700                   1224.00    1517.00
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
V2 r0 | S700                       toque      9,572 | 1t      9,572 | 3t      8,101 (fills 61/63) | 5t      8,101 (fills 61/63)
V2 r0 | S.3atr                     toque     11,533 | 1t     11,533 | 3t     10,062 (fills 60/62) | 5t     10,062 (fills 60/62)
V2 r0 | S700 P50%T700              toque      6,972 | 1t      6,972 | 3t      6,097 (fills 61/63) | 5t      5,816 (fills 61/63)
V2 r0 | S700 sai15h                toque      9,074 | 1t      9,074 | 3t      7,817 (fills 61/63) | 5t      7,817 (fills 61/63)
V2 r0 | S.6atr                     toque     13,701 | 1t     13,701 | 3t     12,230 (fills 60/62) | 5t     12,230 (fills 60/62)
V3 r150 | S700 BE500               toque      4,629 | 1t      4,250 | 3t      4,250 (fills 30/45) | 5t      2,289 (fills 29/45)
V2 r0 | S.6atr T1.2atr             toque     12,569 | 1t     12,569 | 3t     11,266 (fills 60/62) | 5t     11,266 (fills 60/62)
V3 r150 | S700 BE500 T1400         toque      4,151 | 1t      3,592 | 3t      3,592 (fills 30/45) | 5t      3,033 (fills 29/45)
V3 r150 | S350                     toque      6,295 | 1t      5,916 | 3t      5,916 (fills 30/45) | 5t      3,955 (fills 29/45)
V3 r150 | S350 T700                toque      2,741 | 1t      2,462 | 3t      2,462 (fills 30/45) | 5t      2,183 (fills 29/45)
```
