# Rompimento de retângulo — executabilidade e economia (2026-09-16)

Território: EXECUTABILIDADE e ECONOMIA sob o desenho de execução fechado.
Não redefine lateralização/rompimento (isso é de outros agentes desta
rodada) — reusa a MESMA população que `rompimento_retangulo_fenomeno_
2026_09_16.py` mediu (417 rompimentos, IS, 129 pregões, 3,2/pregão —
conferido bit-a-bit neste script, `scripts/daytrade/rompimento_
executabilidade_economia_2026_09_16.py`, log em
`scratch/rompimento_executabilidade_economia_2026_09_16.log`).

## 1. Enumeração exaustiva das formas

Desenho fechado: `IntradayAction = Union[Enter, EnterLimit, Exit, AdjustStop,
AdjustTarget]` (`src/strategy/daytrade/base.py`) — **não existe ordem
STOP-DE-ENTRADA** (buy-stop/sell-stop) no motor inteiro. `Enter` (mercado)
levanta `EntradaAMercadoNaoSuportada` de propósito
(`src/backtest/intraday/machine.py:70,1233`). Uma limite de COMPRA só
descansa ABAIXO do preço corrente; uma de VENDA só ACIMA — é a mesma
conferência mecânica que `WinRetangulo`/`WdoRetangulo` já fazem antes de
armar.

| # | forma | executável | motivo mecânico |
|---|---|---|---|
| A1 | Retest completo na borda rompida (limite no nível exato) | **SIM** | após romper para alta, borda < preço corrente → compra abaixo é válida; após romper para baixa, borda > preço corrente → venda acima é válida |
| A2 | Retorno parcial (limite a 50% do caminho entre o preço de detecção e a borda) | **SIM** | mesmo lado de A1, nível ainda mais conservador |
| A3 | Escada de limites em várias profundidades de retração | **SIM em princípio** | cada degrau é uma A1/A2 individual; não medida nesta rodada |
| B | Perseguir o rompimento — limite mais LONGE na direção da continuação, à frente do preço | **NÃO** | exige compra ACIMA do mercado (alta) ou venda ABAIXO (baixa); não existe tipo de ação para isso — seria uma ordem STOP, ausente do motor |
| C | Reancorar a limite a cada barra, colada 1 tick atrás do preço, perseguindo a extensão | **mecanicamente sim, estruturalmente NÃO** | válida a cada instante isolado, mas degenera em preencher na 1ª reversão de 1 tick — ordem a mercado disfarçada, mesmo pecado do T1 do WDO F1 (já proibido por precedente) |
| D | Entrada a mercado no rompimento, ou alvo a mercado | **NÃO** | proibido pelo desenho fechado do projeto (regra explícita, não descoberta aqui) |
| E | Entrada na borda OPOSTA (fade completo através do retângulo) | **fora de escopo** | não é rompimento — é a estratégia IRMÃ já em produção/sombra (`win_retangulo`/`wdo_retangulo`), que entra no MEIO mirando a borda oposta |

Só A1 e A2 foram medidas. B, C, D, E ficam descartadas/fora de escopo pelo
motivo na tabela — não redescobrir.

## 2. Preenchimento e atraso (ttl_bars = minutos, feed M1 1:1)

WIN@ M1: 1 barra = 1 minuto exato (sem a armadilha "barra ≠ tempo" do tick do
WDO).

**A1 (retest completo na borda):**

| ttl | preenche | atraso mediano | atraso p90 |
|---|---|---|---|
| 5 min | 29,3% | 3,0 min | 5,0 min |
| 10 min | 41,0% | 4,0 min | 8,0 min |
| 20 min | 54,7% | 5,0 min | 15,0 min |
| 30 min | 59,7% | 6,0 min | 19,0 min |
| 60 min | 69,3% | 7,0 min | 35,0 min |
| 120 min | 76,3% | 9,0 min | 56,6 min |
| nunca (fim do pregão) | 18,5% dos 417 nunca retesta |  |  |

**A2 (retorno parcial 50%):** preenche muito mais rápido — 56,8% em 5 min,
84,4% em 60 min, atraso mediano 3 min, só 10,1% nunca preenche.

## 3. Economia crua contra o pedágio (7,5 pontos = R$1,50/contrato)

Só operações que PREENCHERAM (A1, n=340 de 417). Todas as leituras abaixo
têm o breakeven DENTRO do IC95% — nenhuma é distinguível de cara-ou-coroa:

| geometria | n | win% | breakeven | R$/op líquido | IC95% do win% |
|---|---|---|---|---|---|
| 0,50L / 0,50L | 336 | 53,0% | 50,0% | +R$1,42 | [47,7 ; 58,3] |
| 0,80L / 0,50L (herdada da família) | 331 | 40,8% | 38,5% | +R$1,31 | [35,5 ; 46,1] |
| 150 pts simétrico | 338 | 52,4% | 50,0% | −R$0,08 | [47,1 ; 57,7] |
| 300 pts simétrico | 330 | 51,5% | 50,0% | +R$0,32 | [46,1 ; 56,9] |
| A2, 0,80L/0,50L | 368 | 37,8% | 38,5% | −R$2,10 | [32,8 ; 42,8] |

Nenhum número passa de ruído — nem o maior positivo (+R$1,42) nem o maior
negativo (−R$2,10) escapam do intervalo de confiança do breakeven.

## 4. Fila (proxy — WIN@ não tem `fidelidade.py` calibrada)

Revisitas ao nível de entrada nas 60 barras seguintes ao fill/nascimento:

| nível | n | revisitas mediana | p10 | p90 | fração com 0 revisitas |
|---|---|---|---|---|---|
| BORDA (A1, pós-retest) | 340 | 7,0 | 1,0 | 20,1 | 7,9% |
| MEIO (win_retangulo, pós-nascimento) | 434 | 6,0 | 0,0 | 18,0 | 15,4% |

**Achado contra-intuitivo, e a explicação provável:** a borda rompida é
revisitada TANTO OU MAIS que o meio — o oposto do que a intuição "rompeu e
foi embora" sugeria. A explicação mais provável não é "a borda tem fila
boa" — é que grande parte destes "rompimentos" (critério de morte:
fechamento além de 25% da largura por 3 barras) são rompimentos FRACOS que
voltam a chacoalhar perto do nível em vez de continuar (coerente com
MFE/MAE 0,92 < 1,09 do nulo, já medido no fenômeno). Ou seja, a métrica de
revisita aqui está CONFUNDIDA com falha de continuação, não é evidência
limpa de "nível barato de fila" no sentido do `win_retangulo` (onde o meio é
visitado porque o preço genuinamente oscila dentro de um range validado).
**Não tratar isto como "fila resolvida"** — é a mesma ordem de grandeza, mas
por um motivo que não sustenta a analogia.

## 5. Piso de capital

Pior perda medida por operação (geometrias 0,50L/0,50L e 0,80L/0,50L, mesmo
valor pois o pior caso tem o mesmo stop): **R$108,89** → piso sugerido
**R$208,89** (perda + margem crua R$100). Não inclui deslize de stop a
mercado (não calibrado para WIN@ nesta rodada).

## 6. Veredito

- **A1 (retest completo) é a forma recomendada para PERSEGUIR, não para
  ADOTAR ainda**: é a única mecanicamente limpa e com fila mensurável, mas
  0/5 geometrias testadas mostram edge que sobreviva ao IC95%. É "hipótese
  não refutada por falta de tentativa melhor", não "estratégia validada".
- **A2 (retorno parcial) deve ser ABANDONADA** como geometria 0,80L/0,50L:
  win% 37,8% abaixo do breakeven 38,5% (embora dentro do IC), preenche mais
  rápido mas entra num ponto mais frágil — pior risco/retorno que A1 na
  única geometria testada.
- **B, C, D são mecanicamente inexequíveis/proibidas** — não retestar.
- **E é a estratégia irmã já em produção — fora de escopo.**

## Perguntas abertas

1. A3 (escada de retração) nunca foi medida — pode capturar parte do fill
   rápido de A2 com o risco/retorno de A1.
2. A métrica de fila (seção 4) precisa de calibração real (como
   `fidelidade.py` fez para o WDO) antes de decidir; o proxy de revisitas
   está confundido com falha de continuação.
3. Nenhuma geometria testada usou o dado de "quem chega primeiro" para
   OTIMIZAR (todas vieram de fora — herdadas ou arbitrárias); um grid fino
   correria o risco de garimpar ruído, dado que nenhum ponto do espaço
   testado até aqui escapou do IC95% do breakeven.
4. Não foi testado condicionar a entrada por tamanho/força do rompimento
   (ex.: `barras_vivo`, largura) — pode ser território de outro agente
   (anatomia/preditores), mas se sobrar, é o próximo lugar a olhar.
