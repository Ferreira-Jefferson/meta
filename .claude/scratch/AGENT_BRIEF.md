# Brief para agentes de estratégia (robôs 1000-reais)

Você vai escrever **UM** arquivo de estratégia novo para o projeto `meta`. Seu robô deve
imitar a estrutura do `momentum_macro_gated` (o vencedor atual), variando **uma dimensão
específica** que será dada no prompt.

## Interface obrigatória (leia antes de codar)

Arquivos que definem o contrato:
- `src/strategy/base.py` — classe `Strategy`, dataclasses `Enter`, `Exit`, `AdjustStop`, `OpenPosition`
- `src/backtest/engine.py` — como o engine executa suas ações (D+1 open, stop intra-bar)
- `src/core/models.py` — enum `ExitReason`
- `src/core/calendar.py` — `is_month_end(index)`
- `src/core/earnings_calendar.py` — `blackout_series(index)` (opcional, use se pertinente)
- `src/strategy/momentum_macro_gated.py` — **referência de estilo e mecânica** (Selic gate obrigatório)

Regras que TODO robô nesta leva deve preservar:
1. **Selic gate**: se Selic acumulada em 63 pregões subiu > 0.005 %ad → sai de tudo (`ExitReason.IBOV_DEFENSIVO`).
   Copie a lógica de `_selic_tightening` do `momentum_macro_gated.initialize`.
2. **Ranking momentum 12-1** para score default (`close.shift(21)/close.shift(252) - 1`), a menos que seu prompt diga o contrário.
3. **Anti look-ahead**: só use dados até `date` (inclusive). Nunca `.shift(-N)`.
4. **top_n padrão = 3**, a menos que seu prompt peça diferente.
5. **Devolva ações declarativas** (`Enter`, `Exit`, `AdjustStop`) — não modifique estado interno de posição.
6. **`universe_tickers` como class attribute** — se seu robô muda o universo, declare como tupla:
   ```python
   class MyRobot(Strategy):
       universe_tickers = ("WEGE3.SA", "RADL3.SA", "VALE3.SA", "ITUB4.SA", ...)
   ```
   Sem esse atributo (ou `None`) o engine usa `WATCHLIST` default.

## O que você NÃO faz

- **Não** edite `registry.py`, `run_backtest.py`, `scheduler.py`. Vou compilar essas mudanças eu mesmo.
- **Não** rode backtests. Vou rodar tudo no final.
- **Não** escreva testes.
- **Não** invente indicadores custom — use os já em `src/core/indicators.py` (`sma`, `atr`, `ifr`, `rolling_high`, `rolling_low`, `bollinger_bands`, etc.).

## Formato de saída

1. Escreva o arquivo Python completo em `src/strategy/<nome_do_robo>.py`.
2. No fim da sua resposta, cole em um bloco ```md```:
   - Uma entrada `StrategyInfo` COMPLETA (chave, name, version="1.0", description, long_description, entry_rules, exit_rules, sizing_rules, params, factory) pronta pra colar em `registry.py`.
   - Uma linha `"<key>": <ClassName>,` pra colar em `scripts/run_backtest.py`.
   - **Uma frase** sobre qual hipótese específica está sendo testada e por que ela poderia bater `momentum_macro_gated`.

## Estilo

- Docstring do arquivo explicando a hipótese.
- Sem comentários redundantes.
- Português nos textos; snake_case nos identificadores.
- `from __future__ import annotations` no topo.
- Imports absolutos (`from strategy.base import ...`).

## Dados disponíveis (parquets já baixados)

Tickers com histórico completo desde 2010: `WEGE3.SA, RADL3.SA, VALE3.SA, ITUB4.SA, BBDC4.SA, BBAS3.SA, ITSA4.SA, MGLU3.SA, RENT3.SA, SUZB3.SA, B3SA3.SA`. Benchmark `^BVSP`. Macro: `selic`, `usd_brl`. Se seu robô precisar de universo custom, escolha entre esses.
