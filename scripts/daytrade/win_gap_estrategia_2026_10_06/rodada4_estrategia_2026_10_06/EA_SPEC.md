# EA_SPEC — WIN gap / 1ª barra M5 contra o gap (V2 r0 com stop)

Especificação para o agente que vai escrever o EA em MQL5. Fonte da verdade da lógica: `src/strategy/daytrade/lab/win_gap_barra1.py` (classe `WinGapBarra1`, 17 testes em `tests/test_win_gap_barra1.py`). Números de referência: `RESULTADO.md` desta pasta e `EA_referencia_trades.csv` (um trade esperado por pregão). Este documento não tem código MQL5.

## 1. Instrumento, timeframe, relógio

- Mini-índice. Tester: `WIN$N` (contínuo, preço NÃO ajustado). Ao vivo: o contrato corrente (WINxNN). Gráfico M5.
- Relógio: todo horário abaixo é **hora do servidor MT5, que nesta corretora é o horário de Brasília** (os ticks gravados em `data/comparativo_win_2026/ticks` têm o relógio do servidor rotulado como UTC e o pregão abre às 09:00). Parametrize o deslocamento (`ServerGMTOffsetH`, default 0) se o servidor for outro; nada no EA pode assumir fuso além disso.
- 1 ponto = R$0,20 por contrato; tick = 5 pontos; lote mínimo = 1 contrato.

## 2. Definições do sinal (todas em barras M5 do gráfico)

Grade B3 do WIN (`data/b3_grade_horaria_win.csv`): leilão de abertura antes de 09:00 e formado entre 09:00 e 09:05; negociação contínua termina às **18:25** (17:55 antes de 2024-03-11 em horário de verão dos EUA); call de fechamento depois das 18:25.

| item | definição em MT5 |
|---|---|
| Barra 1 | a barra M5 do dia com `time == hoje 09:00`. Se a 1ª barra do dia não começa às 09:00 (ex.: 2026-07-31, abriu 12:34), **não opera o dia**. |
| Preço do leilão de D | `Open` da barra 1. (Em barras M5/M1 brutas do WIN$N o open da 1ª barra é o preço do leilão: igual ao `pre_preco_fechamento` do CSV de fases em 126/126 dias.) |
| Preço do call de D−1 | `Close` da última barra M5 do pregão anterior, a barra das 18:20 (equivalente: `Close` da barra M1 das 18:24). Em barras brutas essa barra contém o call: igual ao `pos_preco_fechamento` do CSV em 126/126 dias. |
| gap | `Open(barra 1) − Close(última barra de D−1)`, em pontos. Sessão anterior a no máximo 5 dias corridos; senão não opera. |
| Decisão | no **fecho da barra 1**, isto é, no primeiro tick com `time ≥ 09:05:00` (nova barra M5), lendo a barra de índice 1. Nunca antes. |
| Sinal | a barra 1 fecha **contra** o gap: `gap > 0` e `Close < Open` → **VENDA**; `gap < 0` e `Close > Open` → **COMPRA**. Corpo zero, gap zero ou `|gap| < 5` → sem sinal. A favor do gap → sem sinal. |
| Dia de vencimento | veja a seção 6. |

Uma operação por pregão, no máximo. Sem reentrada depois de stop.

Diferença conhecida para a referência: o simulador usou como "open da barra 1" o 1º negócio contínuo; o EA usa o preço do leilão. Muda o sinal em 1 de 120 pregões (2026-05-20: o EA opera uma compra que a referência não tem).

## 3. Ordens

| item | valor |
|---|---|
| Entrada | ordem **limite**: `ORDER_TYPE_BUY_LIMIT` (compra) ou `SELL_LIMIT` (venda) no `Close` da barra 1, arredondado a múltiplo de 5. Enviada no primeiro tick `≥ 09:05:00`. |
| Validade | `ORDER_TIME_SPECIFIED`, `expiration = hoje 09:35:00` (6 barras M5 = 30 minutos). Passou disso sem encher: a ordem morre, sem trade no dia. Nunca ordem de entrada sem prazo. |
| Stop | no **servidor**, no campo `sl` da própria ordem: `entrada ∓ StopPts` (default 1.200 pts; compra: abaixo; venda: acima). Executa a mercado quando atravessado. O stop é a única saída a mercado, além do flatten. |
| Alvo | **nenhum no default** (a escolha é "sem alvo"). Se um alvo for ativado (`AlvoPts` ou `AlvoR`): NÃO usar o campo `tp` da posição (o TP nativo é varrido a mercado e perde 1 tick); depois do preenchimento enviar uma ordem **limite** oposta (SELL_LIMIT / BUY_LIMIT) no preço `entrada ± alvo`, tamanho da posição, e cancelá-la ao zerar. |
| Breakeven (opcional, `BeR`, default desligado) | depois de uma excursão favorável de `BeR × StopPts` medida só com ticks posteriores ao fill, mover o `sl` para `entrada ± 5`. |
| Tipo de preenchimento | `ORDER_FILLING_RETURN`. Conta netting (uma posição por símbolo). |
| Magic | um número próprio; o EA só mexe em ordens/posições com ele. |

Tamanho (`Lotes`, default **0 = automático pelo saldo**, a mesma função da produção: o menor entre a escada de risco e o teto por margem, margem R$100, teto 5 contratos):

| saldo (R$) | contratos |
|---|---|
| < 100 | 0 (não opera) |
| 100 a 799 | 1 |
| 800 a 2.399 | 2 |
| 2.400 a 6.666 | 3 |
| 6.667 a 16.666 | 4 |
| ≥ 16.667 | 5 |

(o teto por margem adicional é `floor(saldo / 250)`, que nunca aperta antes da escada nesses degraus). Com `Lotes > 0` o tamanho é fixo (use `Lotes = 1` para comparar com `EA_referencia_trades.csv`). O saldo é lido no momento do envio da ordem.

## 4. Fim do dia

- `FlattenHora = 18:20:00` (servidor): no primeiro tick com `time ≥ 18:20:00`, fechar a posição a mercado e apagar ordens pendentes. Nunca depois de 18:24:30. O call começa às 18:25 e **nunca** é negociado; se a posição ainda existir às 18:25 é erro.
- A ordem de entrada não chega até aí (expira às 09:35).
- Regime antigo da B3 (17:55): `FlattenHora = 17:50` (a grade mudou o fim do contínuo; parametrize `FimContinuoMin`, 565 minutos depois das 09:00 no regime atual, 535 no antigo; flatten = fim − 5 min).
- Referência da simulação: o simulador a tick zerou no último tick do contínuo (18:24:59); o motor em M5, às 18:15. A diferença de horário muda cerca de R$1 por contrato por trade em mediana (soma de −R$67 por contrato nos 62 trades comuns).

## 5. Parâmetros (inputs) e defaults

| input | default | nota |
|---|---|---|
| `StopPts` | **1200** | alternativa dentro do mesmo platô: 700 (menor risco por trade e melhor lucro/DD) |
| `AlvoPts` / `AlvoR` | 0 / 0 (sem alvo) | grade testada na rodada 4 |
| `BeR` | 0 (desligado) | |
| `RecuoPts` | 0 | limite no close da barra 1 |
| `TtlBarras` | 6 | validade da entrada |
| `GapMinPts` | 5 | `|gap| ≥ 1 tick` |
| `Lotes` | 0 | 0 = automático por saldo |
| `AberturaHora`, `AberturaMin` | 9, 0 | |
| `FimContinuoMin` | 565 | minutos desde a abertura |
| `FlattenHora` | 18:20 | |
| `EvitarVencimento` | true | seção 6 |
| `ServerGMTOffsetH` | 0 | |

## 6. Rolagem do contrato (WIN$N)

O WIN vence na quarta-feira mais próxima do dia 15 dos meses pares (fev, abr, jun, ago, out, dez); se o 15 é quarta, é ele. No WIN$N a série troca de contrato nesse dia e o gap `call D−1 → leilão D` vira um degrau de contratos diferentes (medido: 3.350 a 4.415 pts contra |gap| mediano de 500).

- `EvitarVencimento = true`: **não opera a primeira sessão em ou depois do vencimento** (cobre o vencimento em feriado). Implementação: se existe um vencimento `V` com `ontem_sessão < V ≤ hoje`, pula o dia.
- O dia seguinte à rolagem é normal (o call de D e o leilão de D+1 estão no mesmo contrato) e opera.
- Ao vivo, trocar o símbolo operado para o contrato novo após o vencimento; o gap do 1º dia do contrato novo usa o call do contrato novo.
- No período de referência as rolagens foram 2026-04-15, 06-17 e 08-12 (o EA não pode ter ordem nesses dias). 2026-07-31 também não opera (1ª barra fora das 09:00).

## 7. Números que o tester deve reproduzir aproximadamente

Tester: símbolo WIN$N, M5, **todos os ticks reais**, 2026-04-06 a 2026-10-05, depósito R$1.000 (para a referência por contrato use `Lotes = 1`), comissão R$0,50 por contrato (ida e volta), deslize do stop e do flatten de ~1 tick (5 pts) como no simulador.

Os ticks reais só existem a partir de 2026-02-20. Em 3 dias do período a fonte de ticks tem buracos (2026-05-06 09:16-09:23, 2026-08-10 10:00-10:08, 2026-09-24 sem ticks antes das 09:14): o EA pode operar neles; esses dias **não estão** na referência.

Referência, **1 contrato, `StopPts = 1200`, sem alvo**, simulador a tick (120 pregões elegíveis; 63 sinais):

| medida | valor |
|---|---|
| sinais / ordens preenchidas | 63 / 62 (1,6% sem fill) |
| saídas | 24 stops, 38 flatten |
| win% (líquido > 0) | 50,0% |
| ganho médio / perda média | R$379 / R$202 |
| líquido total | **R$5.464** (R$88,1 por trade) |
| pior trade | −R$242 (stop de 1.200 pts = R$240 + custos) |
| maior sequência de perdas | 6 |
| MaxDD (curva por trade) | R$1.268 |
| por mês | abr R$1.613 · mai R$632 · jun R$446 · jul R$562 · ago R$2.004 · set R$690 · out (1-5) −R$483 |

Alternativa `StopPts = 700` (1 contrato): 63 / 62 sinais/fills, 34 stops, 28 flatten, win 40,3%, ganho médio R$389, perda média R$134, líquido **R$4.786** (R$77,2 por trade), pior −R$142, sequência 7, MaxDD R$892.

Com sizing automático a partir de R$1.000 (tabela da seção 3): simulador a tick **+R$15.103,50** em 62 trades (1 a 5 contratos, média 3,6; MaxDD R$6.771; caixa mínimo MtM ~R$466); classe no motor sobre barras brutas M5, **+R$17.783,50** em 63 trades. Aqui o caixa compõe e qualquer diferença de trade muda os contratos dos seguintes, então espere dispersão maior que a por contrato.

Tolerâncias sugeridas para considerar o EA "reproduzindo": mesmo lado e mesmo preço de entrada em ≥ 90% dos pregões de `EA_referencia_trades.csv` (coluna `celula = S1200 | none`); número de trades 60 a 66; win% 50% ± 6 pp; líquido por contrato R$4.400 a R$6.600; MaxDD por contrato ≤ R$1.900; nenhuma posição aberta depois de 18:24:30; nenhuma ordem de entrada ativa depois de 09:35.

## 8. Itens que o EA não faz

Sem filtro de volume do call, sem filtro de gap mínimo além de 1 tick, sem segunda entrada, sem alvo no default, sem lote proporcional ao risco por trade além da tabela da seção 3. Nenhuma trava não pedida.
