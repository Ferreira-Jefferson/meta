# WinGapBarra1.mq5 — como usar

Port da classe `src/strategy/daytrade/lab/win_gap_barra1.py`. Especificação e números: `scripts/daytrade/win_gap_estrategia_2026_10_06/rodada4_estrategia_2026_10_06/` (`EA_SPEC.md`, `RESULTADO.md`, `EA_referencia_trades.csv`).

## O que faz
- gap = preço do leilão de hoje (open da 1ª barra M5, 09:00) − preço do call de ontem (close da última barra M5 de ontem, 18:20).
- Se a 1ª barra M5 (09:00–09:05) fecha **contra** o gap, manda uma ordem **limite** no close dela, no sentido da barra (gap de alta e barra de baixa = venda; gap de baixa e barra de alta = compra). A ordem vale até 09:35.
- Stop de 1.200 pts no servidor, sem alvo. Zera a mercado às 18:20 (17:50 no regime antigo da B3), nunca dentro do call.
- Não opera a 1ª sessão depois de um vencimento (rolagem do WIN$N). Uma operação por pregão, sem reentrada.
- **Sempre 1 contrato** (v1.01). O aumento automático pelo saldo foi removido em 06/10/2026: no replay de 2022–2026 ele quebrou a conta em 3 de 5 anos, contra 1 de 5 com 1 contrato fixo (`scripts/daytrade/win_gap_estrategia_2026_10_06/rodada10_contratos/`).
- Todos os inputs já vêm com a regra adotada. Sem portão de capital/margem.

## Testador do MT5
- Símbolo **WIN$N**, gráfico M5 (o EA lê M5 sozinho).
- Período **2026-04-06 a 2026-10-05**.
- Modelo: **Todos os ticks com base em ticks reais**. Conta NETTING.
- Depósito R$1.000.
- Comissão R$0,50 por contrato (ida e volta) e deslize de ~1 tick no stop e no zeramento, como no simulador.
- Os ticks reais só existem a partir de 2026-02-20.
- Se o servidor não estiver em horário de Brasília, ajuste `ServerGMTOffsetH`.

## Números que o teste deve reproduzir (1 contrato, stop 1200, sem alvo)
Referência do simulador a tick, 120 pregões elegíveis, 63 sinais:

| medida | valor |
|---|---|
| sinais / ordens preenchidas | 63 / 62 |
| saídas | 24 stops, 38 zeramentos |
| win% | 50,0% |
| ganho médio / perda média | R$379 / R$202 |
| líquido | R$5.464 (R$88,1 por trade) |
| pior trade | −R$242 |
| maior sequência de perdas | 6 |
| MaxDD (curva por trade) | R$1.268 |

Tolerâncias: 60 a 66 trades; win% 50% ± 6 pp; líquido R$4.400 a R$6.600; MaxDD ≤ R$1.900; mesmo lado e mesma entrada em ≥ 90% dos pregões de `EA_referencia_trades.csv`; nenhuma posição aberta depois de 18:24:30; nenhuma ordem de entrada ativa depois de 09:35.

Alternativa dentro do mesmo platô: `StopPts = 700` (1 contrato: R$4.786, 62 trades, win 40,3%, MaxDD R$892).

Diferença conhecida: o EA usa o preço do leilão como open da barra 1; o simulador usava o 1º negócio contínuo. Muda o sinal em 1 de 120 pregões (2026-05-20, em que o EA opera uma compra que a referência não tem). Os dias 2026-04-15, 06-17 e 08-12 (rolagem) e 07-31 (abertura fora das 09:00) ficam sem ordem.

## Limites do resultado
A janela do teste é a mesma onde a pista nasceu (descoberta, não validação). A fila do WIN não está calibrada. Holdout 2025-12-19..2026-02-19 deu R$168/trade em 19 trades, com p 0,134 (sem poder estatístico).
