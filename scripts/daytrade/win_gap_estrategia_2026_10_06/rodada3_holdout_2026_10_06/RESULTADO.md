# WIN gap — rodada 3: holdout 2025-12-19 a 2026-02-19

Células congeladas da rodada 2 (V2 r0 | S700 e V2 r0 | S.6atr), mesmo código, R$1.000, 2 contratos (sizing de produção), modos A e B, fill `toque` e `atrav+1t`. Critérios escritos antes da execução em `CRITERIOS.md`. Dados em `DADOS_HOLDOUT.md`. Reprodução: `holdout.py`, `sens_gap.py`, `dados_holdout.py`.

## 0. Execução: sem ticks, barras M1 conservadoras

- A corretora entrega 0 ticks até 2026-02-19 e 2.074.311 em 2026-02-20 (WIN$N, WIN$, WIN@, WIN@D, WIN@N, WIN$D; WINZ25 e WING26 não existem no terminal). Não há tick local anterior a 02-20.
- Execução em M1: stop dentro da faixa da barra do fill = stop acionado (preço = nível − 1 tick); nas barras seguintes, regra do motor (min(open, nível) − 1 tick). Variante mais dura: stop da barra do fill ao low/high da barra: líquido B muda de R$3.201 para R$3.183 (S700) e fica R$2.551 (S.6atr); stops na barra do fill: 1 de 19 (S700) e 0 de 19 (S.6atr).
- Calibração do método na IS (mesma regra M1): `atrav+1t` reproduz exatamente os números a tick da rodada 2 (R$9.572 e R$13.701); `toque` dá R$10.373 e R$14.502 (1 fill a mais).
- Leilão e call são **PROXY** em toda a janela (`proxy=True`): call = close da última barra contínua; leilão = open da barra do leilão, não corrigido.
- 38 pregões elegíveis (2025-12-19 a 2026-02-19; 02-18 excluído: rolagem WING26→WINJ26 + sessão parcial às 13:00; 12-24, 12-25, 12-31, 01-01, 02-16 e 02-17 sem pregão na base). Aquecimento do ATR com os 10 pregões válidos de 2025-12-04 a 2025-12-18 (a rolagem de 12-17 fora da média), só preços. Nenhum dia da IS, de fev-mar/26 nem de out a início de dez/25 usado.

## 1. Critérios (passa / falha, cada um separado)

| critério | V2 r0 \| S700 | V2 r0 \| S.6atr |
|---|---|---|
| C1 líquido B > 0 (toque e atrav+1t) | R$3.201 e R$3.201: passa | R$2.551 e R$2.551: passa |
| C2 R$/trade ≥ 50% da IS (mesma regra M1) e > 0 | R$168,5 contra R$164,7 (102%; contra IS a tick R$154,4: 109%): passa | R$134,3 contra R$233,9 (57%; contra IS a tick R$224,6: 60%): passa |
| C3 p do nulo de direção ≤ 0,05 | 0,134 (Bonferroni 0,267): falha | 0,264 (Bonferroni 0,527): falha |
| C4 win% > BE empírico | 47,4% contra 29,7%: passa | 57,9% contra 46,1%: passa |
| C5 modo A sem censura | liquido R$1.868, 0 recusadas, caixa mín R$380: passa | 3 trades, 16 ordens recusadas, caixa mín R$82 (< margem R$100), líquido −R$918,50: falha |
| C6 pior trade ≤ 1,5× o stop | −705 pts = 1,01×: passa | −2.215 pts = 1,00×: passa |

## 2. Números lado a lado (modo B, 2 contratos)

```
janela                celula           fill       pregoes sinais fills sem fill%   liquido  R$/trade R$/pregao   win% BE emp% pior pts pior/stop  p nulo       nulo medio [p5;p95]
HOLDOUT               V2 r0 | S700     toque           38     19    19       0.0     3,201     168.5      84.2   47.4    29.7     -705      1.01   0.134        1042 [-2059;4147]
HOLDOUT               V2 r0 | S700     atrav+1t        38     19    19       0.0     3,201     168.5      84.2   47.4    29.7     -705      1.01   0.134        1042 [-2059;4147]
HOLDOUT               V2 r0 | S.6atr   toque           38     19    19       0.0     2,551     134.3      67.1   57.9    46.1    -2215      1.00   0.264         751 [-3789;5307]
HOLDOUT               V2 r0 | S.6atr   atrav+1t        38     19    19       0.0     2,551     134.3      67.1   57.9    46.1    -2215      1.00   0.264         751 [-3789;5307]
IS (M1 conservador)   V2 r0 | S700     toque          120     63    63       0.0    10,373     164.7      86.4   41.3    25.5     -705      1.01   0.002         733 [-4869;6369]
IS (M1 conservador)   V2 r0 | S700     atrav+1t       120     63    62       1.6     9,572     154.4      79.8   40.3    25.6     -705      1.01   0.003         337 [-5165;5952]
IS (M1 conservador)   V2 r0 | S.6atr   toque          120     62    62       0.0    14,502     233.9     120.8   58.1    38.5    -2135      1.00   0.003         362 [-8174;9000]
IS (M1 conservador)   V2 r0 | S.6atr   atrav+1t       120     62    61       1.6    13,701     224.6     114.2   57.4    38.6    -2135      1.00   0.003         -35 [-8489;8481]
referencia IS rodada 2 (ticks, modo B toque):  {'V2 r0 | S700': 9572, 'V2 r0 | S.6atr': 13701}
```

- Holdout: 38 pregões, 19 sinais (V2: a 1ª barra fechou contra o gap em metade dos dias), 19 fills, 0% sem fill nas duas premissas (a ordem a limite no close é tocada na barra M1 seguinte; `toque` e `atrav+1t` coincidem em M1).
- IS (mesma regra): 120 pregões, 62 a 63 sinais.
- Pior trade: S700 −705 pts (R$141 por contrato), S.6atr −2.215 pts (stop do dia = 2.215 pts).

## 3. Tabela padrão (`report.py`)

Holdout (`p adj` = 2 × p):

```
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes        fill        modo         ctr     BE emp%   sem fill%  atraso min    seq perdsaidas s/a/tr/te/f      p nulo       p adj   sem trade
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
V2 r0 | S700                          —     3.201,00        —      849,00     3,77  47,4%     19      84,24     0,5              —      38       toque    B pregao           2        29,7         0,0         0,0           3  10/0/0/0/9       0,134       0,267       19/38  fila NAO CALIBRADA (WIN); fill toque
V2 r0 | S700                     186,8%     1.868,00    24,7%      707,50     2,64  47,4%     19      49,16     0,5       2.868,00      38       toque     A conta   1.6 [1-3]        33,6         0,0         0,0           3  10/0/0/0/9           —           —       19/38  fila NAO CALIBRADA (WIN)
V2 r0 | S700                          —     3.201,00        —      849,00     3,77  47,4%     19      84,24     0,5              —      38    atrav+1t    B pregao           2        29,7         0,0         0,0           3  10/0/0/0/9       0,134       0,267       19/38  fila NAO CALIBRADA (WIN); fill atrav+1t
V2 r0 | S700                     186,8%     1.868,00    24,7%      707,50     2,64  47,4%     19      49,16     0,5       2.868,00      38    atrav+1t     A conta   1.6 [1-3]        33,6         0,0         0,0           3  10/0/0/0/9           —           —       19/38  fila NAO CALIBRADA (WIN)
V2 r0 | S.6atr                        —     2.551,00        —    2.007,00     1,27  57,9%     19      67,13     0,5              —      38       toque    B pregao           2        46,1         0,0         0,0           3  6/0/0/0/13       0,264       0,527       19/38  fila NAO CALIBRADA (WIN); fill toque
V2 r0 | S.6atr                   -91,8%      -918,50    91,4%      867,50    -1,06   0,0%      3     -24,17     0,1          81,50      38       toque     A conta   1.7 [1-2]         nan         0,0         0,0           3   2/0/0/0/1           —           —       35/38  CENSURADO recusou 16 caixa mín 82<margem fila NAO CALIBRADA (WIN)
V2 r0 | S.6atr                        —     2.551,00        —    2.007,00     1,27  57,9%     19      67,13     0,5              —      38    atrav+1t    B pregao           2        46,1         0,0         0,0           3  6/0/0/0/13       0,264       0,527       19/38  fila NAO CALIBRADA (WIN); fill atrav+1t
V2 r0 | S.6atr                   -91,8%      -918,50    91,4%      867,50    -1,06   0,0%      3     -24,17     0,1          81,50      38    atrav+1t     A conta   1.7 [1-2]         nan         0,0         0,0           3   2/0/0/0/1           —           —       35/38  CENSURADO recusou 16 caixa mín 82<margem fila NAO CALIBRADA (WIN)
```

IS, mesma regra M1 conservadora:

```
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes        fill        modo         ctr     BE emp%   sem fill%  atraso min    seq perdsaidas s/a/tr/te/f      p nulo       p adj   sem trade
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
V2 r0 | S700                          —    10.373,00        —    1.785,00     5,81  41,3%     63      86,44     0,5              —     120       toque    B pregao           2        25,5         0,0         0,0           7 34/0/0/0/29       0,002       0,004      57/120  fila NAO CALIBRADA (WIN); fill toque
V2 r0 | S700                   1.454,5%    14.545,50    15,5%    2.677,50     5,43  41,3%     63     121,21     0,5      15.545,50     120       toque     A conta   3.3 [1-5]        27,4         0,0         0,0           7 34/0/0/0/29           —           —      57/120  fila NAO CALIBRADA (WIN)
V2 r0 | S700                          —     9.572,00        —    1.785,00     5,36  40,3%     62      79,77     0,5              —     120    atrav+1t    B pregao           2        25,6         1,6         0,0           7 34/0/0/0/28       0,003       0,005      58/120  fila NAO CALIBRADA (WIN); fill atrav+1t
V2 r0 | S700                   1.312,0%    13.120,00    16,9%    2.677,50     4,90  40,3%     62     109,33     0,5      14.120,00     120    atrav+1t     A conta   3.3 [1-4]        27,4         1,6         0,0           7 34/0/0/0/28           —           —      58/120  fila NAO CALIBRADA (WIN)
V2 r0 | S.6atr                        —    14.502,00        —    3.490,00     4,16  58,1%     62     120,85     0,5              —     120       toque    B pregao           2        38,5         0,0         0,0           6 13/0/0/0/49       0,003       0,005      58/120  fila NAO CALIBRADA (WIN); fill toque
V2 r0 | S.6atr                 2.527,3%    25.273,50    21,8%    5.854,50     4,32  58,1%     62     210,61     0,5      26.273,50     120       toque     A conta   3.6 [2-5]        39,1         0,0         0,0           6 13/0/0/0/49           —           —      58/120  fila NAO CALIBRADA (WIN)
V2 r0 | S.6atr                        —    13.701,00        —    3.490,00     3,93  57,4%     61     114,17     0,5              —     120    atrav+1t    B pregao           2        38,6         1,6         0,0           6 13/0/0/0/48       0,003       0,006      59/120  fila NAO CALIBRADA (WIN); fill atrav+1t
V2 r0 | S.6atr                 2.327,1%    23.271,00    23,6%    5.854,50     3,97  57,4%     61     193,93     0,5      24.271,00     120    atrav+1t     A conta   3.6 [2-5]        39,5         1,6         0,0           6 13/0/0/0/48           —           —      59/120  fila NAO CALIBRADA (WIN)
```

## 4. Modo A e censura

```
HOLDOUT               V2 r0 | S700     toque      liquido     1,868 trades  19 contratos medios 1.6 recusadas 0 caixa min 380 censurada=False seq perdas B=3
HOLDOUT               V2 r0 | S700     atrav+1t   liquido     1,868 trades  19 contratos medios 1.6 recusadas 0 caixa min 380 censurada=False seq perdas B=3
HOLDOUT               V2 r0 | S.6atr   toque      liquido      -918 trades   3 contratos medios 1.7 recusadas 16 caixa min 82 censurada=True seq perdas B=3
HOLDOUT               V2 r0 | S.6atr   atrav+1t   liquido      -918 trades   3 contratos medios 1.7 recusadas 16 caixa min 82 censurada=True seq perdas B=3
IS (M1 conservador)   V2 r0 | S700     toque      liquido    14,546 trades  63 contratos medios 3.3 recusadas 0 caixa min 666 censurada=False seq perdas B=7
IS (M1 conservador)   V2 r0 | S700     atrav+1t   liquido    13,120 trades  62 contratos medios 3.3 recusadas 0 caixa min 666 censurada=False seq perdas B=7
IS (M1 conservador)   V2 r0 | S.6atr   toque      liquido    25,274 trades  62 contratos medios 3.6 recusadas 0 caixa min 898 censurada=False seq perdas B=6
IS (M1 conservador)   V2 r0 | S.6atr   atrav+1t   liquido    23,271 trades  61 contratos medios 3.6 recusadas 0 caixa min 898 censurada=False seq perdas B=6
```

## 5. Sensibilidade: o gap proxy do holdout contra o gap da série WIN@D (call real)

O call proxy (close da última barra contínua) difere do call real: |gap proxy − gap WIN@D| mediana 178 pts, máxima 1.150 pts, iguais em 6 de 38 dias (`DADOS_HOLDOUT.md`). Com o gap WIN@D (célula e execução iguais): o sinal do gap inverte em 2 dias (01-22 e 02-19), o conjunto de dias com gatilho troca em 2 dias (19 sinais nos dois casos), nenhum dia mantém gatilho com direção diferente.

```
sinais V2 com gap proxy: 19; com gap WIN@D: 19; dias com gatilho diferente: 2; dias com sinal do gap invertido: 2 ['2026-01-22', '2026-02-19']
dias de gatilho em ambos com DIRECAO diferente: 0
V2 r0 | S700      gap WIN@D: sinais 19 fills 19 liquido B 1,531 R$/trade 80.6 win 42.1% BE 32.8% p nulo 0.336 nulo medio 745 [-2147;3675] | A: liquido 592 recusadas 0 caixa min 162 censurada=False | pior -705 pts (1.01x)
V2 r0 | S.6atr    gap WIN@D: sinais 19 fills 19 liquido B 285 R$/trade 15.0 win 52.6% BE 51.3% p nulo 0.499 nulo medio 304 [-4131;4811] | A: liquido -918 recusadas 16 caixa min 82 censurada=True | pior -2215 pts (1.00x)
```

## 6. Poder estatístico

Alfa 0,05 unilateral, poder 0,80 (z = 1,645 + 0,842), n = 19 trades por célula:

```
V2 r0 | S700: holdout n=19 trades, sd por trade R$591; efeito minimo detectavel = R$337/trade (media) ou R$4,709 de excesso total sobre o nulo (sd do nulo R$1,894); efeito da IS (excesso sobre o nulo por trade) = R$153/trade; trades necessarios para detectar o efeito da IS = 92
V2 r0 | S.6atr: holdout n=19 trades, sd por trade R$698; efeito minimo detectavel = R$398/trade (media) ou R$6,879 de excesso total sobre o nulo (sd do nulo R$2,767); efeito da IS (excesso sobre o nulo por trade) = R$228/trade; trades necessarios para detectar o efeito da IS = 58
```

- Com ~19 trades por célula, o efeito mínimo detectável é R$337 por trade (S700) e R$398 (S.6atr), de 2 a 3 vezes o excesso da IS sobre o nulo (R$153 e R$228 por trade). O holdout, com 38 pregões, só detectaria um efeito 2 a 3 vezes maior que o medido na IS.
- Para detectar o excesso da IS com esse poder seriam necessários ~92 trades (S700) e ~58 (S.6atr), cerca de 180 e 115 pregões na taxa de 50% de dias com sinal.
- O p de 0,134 e 0,264 não distingue "efeito da IS" de "efeito zero": o holdout não tem poder para nenhum dos dois.
