# meta — Robô de Trade B3

Sistema de estudo, backtest e execução automatizada de estratégias para **ações à vista da B3**, com **diário rico de operações** e **dashboard Terminal Editorial**.

Fase 1 (este repo): **estudo em Python** com dados históricos gratuitos (Yahoo Finance).
Fase 2 (futuro): porta para **MetaTrader 5 / MQL5** para execução real.

## Robôs oficiais — o TOP-4 (v4)

Descoberta 2026-08-14 v4: o **filtro buy-the-dip** bate REF em capital em ambas janelas. Substituição completa do TOP-4 anterior.

| # | Robô | FULL (2010→hoje) | 3Y (últimos 3 anos) | Papel |
|---|------|------------------|---------------------|-------|
| 1 | **`buy_the_dip_5pct`** ⭐ CAMPEÃO | **R$ 10.267** · DD -47,7% | **R$ 1.327** · DD -45,3% | Dip 5% do 20d high |
| 2 | `buy_the_dip` (3%) | R$ 8.373 · DD -47,9% | R$ 1.259 · DD -46,8% | Balanceado |
| 3 | `hybrid_cadence_by_vol` | R$ 8.217 · DD -49,4% | R$ 1.232 · DD -46,7% | Cadência adaptativa por vol |
| 4 | `buy_the_dip_1pct` | R$ 8.066 · DD -49,2% | R$ 1.225 · DD -48,0% | Dip mínimo 1% |

**Descoberta chave:** filtrar entradas por dip (≥5% abaixo do máximo de 20 pregões) supera comprar-qualquer-preço-no-mês em **+22% capital FULL** e **+10% capital 3Y** vs REF anterior (`momentum_macro_gated`).

**Critério de ranking:** reavaliação apples-to-apples periódica. Histórico de mudanças:
- **v1**: `biweekly` → `candle_body_momentum` (por DD-priority holística)
- **v2**: `candle_body_momentum` → `correlation_gated` sob "lucro na frente"
- **v3**: `take_profit` removido — divergência de capital. TOP-5 vira **TOP-4**.
- **v4 (atual)**: substituição COMPLETA. Todos os 4 anteriores (`momentum_macro_*`) removidos; 4 novos (`buy_the_dip_*` + `hybrid_cadence_by_vol`) promovidos. Todos bateram o antigo REF em ambas janelas.

Regra atual: **candidato entra se bater REF (`buy_the_dip_5pct`) em ambas janelas E não excluído por não superar nenhum dos TOP-4**.

Refutados nesta longa jornada: `daily_pulse`, `reversal_boost`, `dual_horizon`, `biweekly`; `bank_sector`, `broad`, `broad_top5` (universo!=oficial); candles (`body_momentum` incluso); combos pyramid+takeprofit; variantes ATR (`trigger_1_5`, `max4`); chandelier trailing; vol_gate/equity_regulator; `take_profit`; gate refinements (hysteresis, dual_confirmation, soft_sizing); `selic_level_gate`; `buy_the_dip_weekly`; e todo o TOP-4 v3 (`momentum_macro_*`).

**Regra de promoção:** todo novo candidato precisa **bater `momentum_macro_gated` em ambas as janelas** (FULL + 3Y) com R$ 1.000 iniciais e lote fracionário. Rodar via `python scripts/run_experiments_1000.py`.

## Watchlist oficial — as três campeãs

O sistema opera **exclusivamente** sobre três ações da B3:

| Ticker | Setor | Papel na carteira |
|--------|-------|-------------------|
| **WEGE3** | Bens de capital / motores elétricos | Motor de crescimento, momentum consistente |
| **RADL3** | Farmácia (Raia Drogasil) | Defensivo com win rate alto |
| **VALE3** | Mineração / commodity | Diversifica correlação com o ciclo global |

Essas três não são escolha arbitrária — foram **validadas empiricamente** por dois experimentos:

1. **Análise cross-strategy de PnL agregado** (rodada inicial do projeto): PnL positivo consistente e melhor combinação de trades × win rate ao longo de 4 janelas × 4 estratégias.
2. **Experimento combinatorial 6→3** (2026-08-14): dentre C(6,3) = 20 trincas testadas com `momentum_macro_gated` (candidatos WEGE3, RADL3, VALE3, BBAS3, ITUB4, RENT3), a trinca `WEGE3/RADL3/VALE3` foi **1º lugar em ambas as janelas** (FULL 2010-2026 e últimos 3 anos), com margem robusta sobre a 2ª colocada.

Refutadas explicitamente por dados: expandir a carteira para bancos (`bank_sector`), universo largo (`broad`, 11 tickers) ou incluir MGLU3/B3SA3/SUZB3/BBDC4/ITSA4 — todas as variantes ficaram atrás do baseline em pelo menos uma janela, com destaque negativo para o setor bancário isolado (-81% vs baseline no FULL).

**Referência absoluta:** todo novo experimento é medido contra o `momentum_macro_gated` rodando sobre WEGE3/RADL3/VALE3. Uma variante só é promovida a candidato de produção se **bater essa referência em ambas as janelas** (FULL + últimos 3 anos) com R$ 1.000 iniciais e lote fracionário.

## Subir o projeto

Na raiz do repositório, um comando — funciona no PowerShell ou no cmd:

```
.\dev.bat
```

O script cuida sozinho de tudo, sempre idempotente:

1. Cria `.venv` se ainda não existir
2. Sincroniza dependências (só reinstala quando `requirements.txt` mudou)
3. Inicializa `db/journal.sqlite` se ausente
4. Baixa histórico de mercado se `data/raw/` estiver vazio
5. Sobe o dashboard em **http://127.0.0.1:8000** com hot-reload

`Ctrl+C` encerra uvicorn e workers do reloader — nada fica orfão.

## Rodar um backtest

```powershell
.\.venv\Scripts\python.exe scripts/run_backtest.py --strategy momentum_macro_gated --start 2010 --end 2024
```

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Estrutura

Feature-first: cada módulo em `src/` é autocontido, depende apenas de `core/`.

| Módulo         | Responsabilidade                                            |
|----------------|-------------------------------------------------------------|
| `core/`        | Config, dataclasses, indicadores (funções puras portáveis)  |
| `market_data/` | Ingestão via yfinance → Parquet + checagens de qualidade    |
| `strategy/`    | Regras de sinal isoladas (portáveis p/ MQL5)                |
| `backtest/`    | Engine event-driven customizado + custos + métricas         |
| `journal/`     | SQLite: trades, snapshots, enrichment automático            |
| `dashboard/`   | FastAPI + Jinja2 + HTMX + Plotly.js (Terminal Editorial)    |
