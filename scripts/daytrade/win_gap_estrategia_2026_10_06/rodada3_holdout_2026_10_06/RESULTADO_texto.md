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
{{LADO}}
```

- Holdout: 38 pregões, 19 sinais (V2: a 1ª barra fechou contra o gap em metade dos dias), 19 fills, 0% sem fill nas duas premissas (a ordem a limite no close é tocada na barra M1 seguinte; `toque` e `atrav+1t` coincidem em M1).
- IS (mesma regra): 120 pregões, 62 a 63 sinais.
- Pior trade: S700 −705 pts (R$141 por contrato), S.6atr −2.215 pts (stop do dia = 2.215 pts).

## 3. Tabela padrão (`report.py`)

Holdout (`p adj` = 2 × p):

```
{{TAB_H}}
```

IS, mesma regra M1 conservadora:

```
{{TAB_IS}}
```

## 4. Modo A e censura

```
{{MODOA}}
```

## 5. Sensibilidade: o gap proxy do holdout contra o gap da série WIN@D (call real)

O call proxy (close da última barra contínua) difere do call real: |gap proxy − gap WIN@D| mediana 178 pts, máxima 1.150 pts, iguais em 6 de 38 dias (`DADOS_HOLDOUT.md`). Com o gap WIN@D (célula e execução iguais): o sinal do gap inverte em 2 dias (01-22 e 02-19), o conjunto de dias com gatilho troca em 2 dias (19 sinais nos dois casos), nenhum dia mantém gatilho com direção diferente.

```
{{SENS}}
```

## 6. Poder estatístico

Alfa 0,05 unilateral, poder 0,80 (z = 1,645 + 0,842), n = 19 trades por célula:

```
{{PODER}}
```

- Com ~19 trades por célula, o efeito mínimo detectável é R$337 por trade (S700) e R$398 (S.6atr), de 2 a 3 vezes o excesso da IS sobre o nulo (R$153 e R$228 por trade). O holdout, com 38 pregões, só detectaria um efeito 2 a 3 vezes maior que o medido na IS.
- Para detectar o excesso da IS com esse poder seriam necessários ~92 trades (S700) e ~58 (S.6atr), cerca de 180 e 115 pregões na taxa de 50% de dias com sinal.
- O p de 0,134 e 0,264 não distingue "efeito da IS" de "efeito zero": o holdout não tem poder para nenhum dos dois.
