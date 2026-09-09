# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## AGENTS.md is the source of truth

Repo-wide rules for all IAs live in `AGENTS.md` (layer boundaries, `journal` schema policy, anti-look-ahead, frontend aesthetic, parallel-test contract, standard backtest table). Read it first — this file only adds Claude-specific operational context on top.

## "O Que Já Custou" — o registro vivo de produção

`LICOES_DE_PRODUCAO.md` is the second thing to read before touching execution, sizing, or measurement method. It is the register of errors that already cost real money — the 2026-08-28 incident that zeroed the account, plus the accumulated record — each with the invariant that survived it. Written to be portable across language/platform, so it says *what must be true*, not *which API to call*.

**Página publicada (leitura): https://claude.ai/code/artifact/9a682e56-04b6-4b70-8da3-c5d410076b9d**

Este registro é **vivo** — pedido do dono, 2026-08-28: "para sempre irmos melhorando os itens e aumentando a referência". Ele existe porque a estratégia vai ser portada para outra linguagem (a da Copa, que não é Python nem MetaTrader), e o código não leva o aprendizado junto — os modos de falha, sim.

**Quando adicionar um item.** Sempre que um bug custar dinheiro real, sempre que um erro de método invalidar uma medição, e sempre que uma auditoria achar uma lacuna. Não espere o dono pedir. Um achado que não vira item aqui está a um `/compact` de deixar de existir — foi exatamente o que aconteceu com a lista dos 27 achados da auditoria, que só existia nos relatórios dos subagentes e teve de ser recuperada do transcript (item 7.6 do próprio documento).

**Como escrever um item.** A forma é fixa e é o que dá valor ao arquivo:

1. **O que aconteceu**, com o número real que custou (R$, contagem, percentual). Sem número o item vira conselho genérico, e conselho genérico ninguém lê duas vezes.
2. **A regra** — o invariante que sobrou, escrito de forma que valha em qualquer corretora e qualquer linguagem.
3. Quando a regra depender da plataforma, transforme-a numa **pergunta a fazer à plataforma nova**, e acrescente a pergunta à lista da Parte 8 com a referência de volta ao item.

Fica de fora de propósito: hipótese de estratégia refutada (é resultado de pesquisa, mora na memória do projeto) e detalhe de API que não generaliza.

**Como atualizar a página.** O `.md` no repo é a FONTE; a página é a vista publicada. Depois de editar o markdown, republique **na mesma URL** — `Artifact` com `url: "https://claude.ai/code/artifact/9a682e56-04b6-4b70-8da3-c5d410076b9d"`. Publicar sem passar a `url` cria um artefato NOVO e deixa o link acima morto, que é o oposto do ponto de ele estar anotado aqui.

**Delegue a atualização, não a faça inline.** Editar `LICOES_DE_PRODUCAO.md` E republicar o artefato na mesma URL é um processo lento (ler o HTML publicado por inteiro é obrigatório antes de poder republicar — ver o fluxo de `Artifact`). Sempre que for adicionar/editar um item, dispare um subagente (`Agent`, pode rodar em background) com o achado já resumido (o que aconteceu, o número real, a regra, a pergunta pra Parte 8) para fazer as DUAS pontas — editar o `.md` e republicar o artefato — enquanto o agente principal responde ao dono imediatamente com o conteúdo do achado, sem esperar a atualização do documento terminar.

## Two products in one repo

The codebase is a **B3 trading robot** with two independent execution paths that share the same `strategy/` and `journal/`:

- **Swing / daily** — `strategy/*.py` (subclass of `strategy.base.Strategy`), decides once per session, runs on B3 stocks via `backtest/engine.py` or `live/runtime.py`.
- **Day trade / intraday** — `strategy/daytrade/lab/*.py` (subclass of `strategy.daytrade.base.IntradayStrategy`), decides bar-by-bar (M1 or tick), never carries overnight, runs on futures/stocks via `backtest/intraday/engine.py` or `live/intraday_runtime.py`.

They are deliberately kept apart: `IntradayStrategy` does not inherit from `Strategy`, so `strategy.discovery.discover_strategies()` never picks up a day trade robot for the daily podium (different instrument, capital, risk — incomparable). Each has its **own registry**:
- Daily: **auto-discovery** (`strategy/discovery.py`) — every concrete `Strategy` in `strategy/` is a candidate; the podium is computed from the journal by `scheduler.refresh_champion_rankings()`.
- Day trade: **explicit list** in `strategy/daytrade/registry.py` — order in that dict IS the podium.

The same live process (`scripts/run_live.py --slot swing|daytrade`) dispatches to the right runtime.

## Layer boundaries (from AGENTS.md — non-negotiable)

```
orchestration:  scheduler.py, live/, dashboard/       → may import anything
feature:        market_data, strategy, backtest,      → may import ONLY core/
                journal, market_data_intraday
core:           core/                                 → imports nothing from project
```

- Features do **not** import each other. If feature A needs data from feature B, it goes through a `core/` dataclass or through the SQLite journal.
- **Signal logic in `strategy/` must be pure** (OHLCV in → decisions out, no I/O, no DB). Reason: it will be ported to MQL5.
- **`live/` decides nothing.** The robot that trades real money is literally the same `Strategy` / `IntradayStrategy` instance the backtest runs. If `live/` adds a filter, rounding, or "safety" stop of its own, the backtest stops describing production and the validation history becomes fiction.
- **No look-ahead.** Decision at `close[D]` executes at `open[D+1]` (daily) or `open[bar t+1]` (intraday). This is enforced by the engine, not the strategy.

## Journal is the most valuable asset

When you add a new feature to the entry/exit snapshot, you MUST update **all four** places in sync — `tests/test_live_journal_rationale.py` fails if they diverge:
1. `signal_snapshots` table (backtest — `journal/schema.sql` via migration)
2. `live_signal_snapshots` table (real ops — same migration)
3. `core.models.MarketSnapshot`
4. `journal.live_store._SNAPSHOT_COLUMNS`

There are **two SQLite files on purpose** — `db/journal.sqlite` (backtest) and `db/live.sqlite` (live ops, tables prefixed `live_`) — so a long backtest thread in `dashboard/app.py` doesn't compete for the same file lock as a real-order write.

## Commands

**Dev loop (auto-bootstraps venv, deps, DB, market data, then runs the dashboard on http://127.0.0.1:8000):**
```
.\dev.bat                    # dashboard survives; live robots survive too
.\dev.bat --kill-robots      # also kills run_live.py processes on Ctrl+C
```

**Tests (always parallel — see AGENTS.md § "A suíte roda em PARALELO"):**
```
.\.venv\Scripts\python.exe -m pytest                              # full suite (~35s)
.\.venv\Scripts\python.exe -m pytest tests/test_gremah.py         # one file
.\.venv\Scripts\python.exe -m pytest tests/test_gremah.py::test_x # one test
.\.venv\Scripts\python.exe -m pytest -n0                          # force serial (debugging only)
```
`pyproject.toml` fixes `-n auto --dist load`. New tests must use `tmp_path` (no shared file paths) and must not depend on execution order — otherwise you get flaky failures under xdist.

**Backtest one strategy:**
```
.\.venv\Scripts\python.exe scripts/run_backtest.py --strategy buy_the_dip_5pct --start 2010 --end 2024
```

**Live operation:**
```
.\.venv\Scripts\python.exe scripts/run_live.py --slot swing    init --capital 50000 --mode mt5 --strategy liqflop
.\.venv\Scripts\python.exe scripts/run_live.py --slot swing    loop --seconds 60
.\.venv\Scripts\python.exe scripts/run_live.py --slot daytrade --strategy gremah loop --seconds 5
```
Default `--execution-mode` is `shadow` (journals everything, sends no orders). See `DEPLOY.md` for the NSSM service + Windows-only rationale.

**Parameter sweeps / exploratory scripts** live in `scripts/daytrade/` and `scripts/`. Follow the parallelism pattern in `scripts/daytrade/gremah_defesa_corte_sweep_2026_09_03.py`: `ProcessPoolExecutor` with `submit`/`as_completed` (never `pool.map`), one `redirect_stdout` per unit, `flush=True` on every print, and **stream each unit's result as it finishes** — never wait for the whole sweep to speak.

## Standard backtest table — do not invent columns

Every day trade script must print results through `backtest/intraday/report.py`: call `linha_de_resultado()` then `tabela()`. The 12 base columns (`variante`, `retorno`, `líquido R$`, `MaxDD %`, `MaxDD R$`, `lucro/DD`, `win%`, `trades`, `R$/dia`, `trd/dia`, `capital final`, `pregões`) are fixed and always in that order. Anything a specific run needs goes into the `extras` dict — **after** the base, never in place of it. Numbers use BR decimals (comma). Reasons for the two non-obvious choices (`lucro/DD` instead of annualized Calmar; nocional capital blanks capital-dependent columns) are documented in the module.

## Capital inicial: sempre o mínimo real do instrumento

Every backtest / sweep starts from the **real** minimum cash to operate the instrument, never a round test value like "R$50k so it doesn't zero." A generic capital silently changes how many lots fit and whether the capital gate lets a session trade at all, which flips which geometry "wins."

**Regra por instrumento (2 lotes / 2× buffer de margem — `CAPITAL_MINIMO_EM_LOTES = MARGIN_BUFFER_FUTUROS = 2.0`):**

| Instrumento | Fórmula | Onde |
|---|---|---|
| Ação B3 | `preço_atual × 100 × 2` (2 lotes padrão) | `strategy.daytrade.base.capital_minimo_brl(preco)` |
| Mini-índice (WIN) | `margem × 2` = **R$100 × 2 = R$200** | `contracts_from_capital(cash, margin=100)` |
| Mini-dólar (WDO) | `margem × 2` = **R$150 × 2 = R$300** | `contracts_from_capital(cash, margin=150)` |

**Sizing de ENTRADA REAL usa `contracts_from_capital_com_reserva`, não `contracts_from_capital`** (2026-08-28, depois do incidente que zerou a conta). Ela empilha `RESERVA_CAIXA_SEGURANCA = 1.25` por cima do buffer — 20% do caixa nunca entra na conta de quantos contratos cabem. Na prática: **WIN R$250, WDO R$375**.

### O piso de capital é indicação de PARTIDA, nunca condição de continuidade

Esta é a confusão que já custou uma medição inteira, e ela reaparece toda vez que um agente novo lê a tabela acima. **Três números, três empregos diferentes — nunca os trate como um só:**

| Número | WDO@ | O que é | Quando vale |
|---|---|---|---|
| `margem` | R$150 | O que a corretora cobra para segurar 1 contrato | **Sempre.** É o piso de SOBREVIVÊNCIA |
| `× MARGIN_BUFFER_FUTUROS` (2,0) | R$300 | Folga para cobrir uma troca de lado em conta NETTING | Ao ESCALAR (2º contrato em diante) |
| `× RESERVA_CAIXA_SEGURANCA` (1,25) | **R$375** | Reserva pós-incidente | Ao ESCALAR, e como indicação de PARTIDA |

**A regra (decisão do dono, 2026-09-08):** a pilha de segurança governa **escalar**, não **sobreviver**.

- **R$375 responde "quanto preciso para começar com folga?"** — é o que o painel mostra e checa **uma vez**, quando o dono clica em "Iniciar operação" (`dashboard.robot_view._capital_minimo_do_robo`). Depois disso não é mais observado.
- **Manter/abrir o 1º contrato exige só a margem crua** (R$150). Abaixo dela quem recusa é a corretora, e não faz sentido o motor recusar antes.
- **Abrir o 2º, 3º… exige a pilha inteira.** Foi exposição AGREGADA — dois contratos simultâneos num caixa de R$300 — que zerou a conta em 2026-08-28. Essa proteção fica intacta.

Quem faz essa conta é `strategy.daytrade.base.contracts_from_capital_operacional`, e o motor (`IntradaySessionMachine._cap_capital_atual`) chama ela. **Não reintroduza `contracts_from_capital_com_reserva` no caminho de recusa por entrada** achando que é mais seguro: até 2026-09-08 era assim, e o efeito era que um único stop de R$80 sobre um caixa que começou nos R$375 de partida derrubava o caixa para R$299 e calava o robô **em silêncio, para sempre**.

**Corolário na hora de LER um backtest — vale para qualquer robô, não só os de futuro:** antes de tratar um `líquido` como veredito, olhe **quantos trades** e **quantos pregões sem trade** a janela teve. Uma janela em que o robô parou de operar está **censurada**: ela mede a restrição que o parou, não a estratégia. O caso real: WDO F1 no OOS deu "−R$76, win 50%" — parecia edge negativo, eram 2 trades em 51 pregões e 50 pregões de silêncio depois do primeiro stop. E quando o capital inicial é exatamente o piso, comparar IS com OOS não é validação: é comparar dois sorteios sobre quais foram as primeiras operações. Ver item 6.15 de `LICOES_DE_PRODUCAO.md`.

Use `config_for(..., preco_atual=preco_ref)` para ação e `contracts_from_capital(cash, margin_per_contract, buffer=2.0)` para futuro — nunca digitar o número na mão. `enforce_capital_minimo` fica no default do perfil (ligado para ação) pelo mesmo motivo: desligar mede geometria isolada do caixa, que é outra pergunta. A tabela de saída sempre mostra o capital usado (a coluna, ou implícito em `capital final − líquido R$`).

## O motor COBRA o deslize do TP nativo — e isso apagou o edge do WDO F1

**Ordem do dono, 2026-09-08: `profit_ticks=1` (T1) não entra em nenhuma medição do WDO F1 nem da família maker — nem como candidato, nem como baseline, nem como "linha de referência" numa tabela.** Não é preferência de parâmetro. É uma geometria que o motor sabe simular e a corretora não sabe executar.

**O número.** O `tp` nativo (o que viaja amarrado no request da entrada) não fica *resting* no livro: a corretora o executa como gatilho varrido a mercado. População completa de operação real do robô — 3 pregões, reconstruída do histórico de DEALS+ORDENS do terminal, **n=11 saídas por alvo nativo**:

| deslize (ticks) | 0 | −1 | −2 |
|---|---|---|---|
| n | 1 | 9 | 1 |

média −1,000 · mediana −1,0 · desvio 0,447 · **10 contra a posição, 0 a favor** (sob moeda justa, p ≈ 0,001). R$55,00 de deslize contra R$95,00 de bruto teórico — 57,9%. Item 4.8 de `LICOES_DE_PRODUCAO.md`.

O **stop** foi medido separado e **não desliza igual**: n=2 do robô (0 e +1 tick, a favor) + 3 saídas manuais (0 tick) — em 5 de 5 nunca pior que o nível pedido. Ele continua pagando só `slippage_ticks`; não empilhe os dois.

**Como o motor cobra** (desde 2026-09-08): `IntradayCostModel.target_slippage_ticks` + `costs.apply_deslize_alvo_nativo()`, aplicado em `machine._close_position` **só no alvo maker NÃO fatiado** — a saída fatiada posiciona ordens-limite reais no livro e continua pagando zero. `config_for` liga sozinho (`DESLIZE_ALVO_NATIVO_TICKS = 1.0`) quando `target_fills_as_maker=True`, então backtest, sombra e produção herdam junto; passe `target_slippage_ticks=0.0` explícito para reproduzir o motor antigo e outro número para medir sensibilidade (n=11 é pouco — o forte da amostra é a direção, não a magnitude). A tabela padrão carimba `desliz.alvo 1,0t` na linha, porque duas linhas com o mesmo `líquido R$` e premissas de deslize diferentes não são comparáveis.

**O que a cobrança fez com o robô.** Com alvo de 2 ticks (T2, produção) o ganho por vitória cai de R$9,50 para **R$4,50** e o breakeven sobe de **90,00% para 95,00%** — contra o stop de 16 ticks. Medido nas duas janelas congeladas, capital real R$375 (`scripts/daytrade/wdof1_deslize_alvo_is_oos_2026_09_08.py`):

| janela | geometria | líquido R$ | win% | trades | pregões s/ trade | caixa mín |
|---|---|---|---|---|---|---|
| IS (72) | T2/S16 **sem** deslize | +347.548,50 | 94,2% | 19.893 | 0/72 | 370,00 |
| IS | T2/S16 **com** deslize | **−242,50** | 93,3% | 165 | **71/72** | 132,50 |
| IS | T3/S16 com deslize (dono) | −229,00 | 88,0% | 158 | **70/72** | 146,00 |
| IS | T4/S16 com deslize | −244,00 | 83,3% | 108 | **70/72** | 131,00 |
| OOS (51) | T2/S16 **sem** deslize | +143.214,50 | 94,5% | 9.635 | 0/51 | 290,00 |
| OOS | T2/S16 **com** deslize | **−273,50** | 94,1% | 407 | **49/51** | 101,50 |
| OOS | T3/S16 com deslize (dono) | −237,00 | 89,2% | 1.784 | **37/51** | 121,00 |

Nas DUAS janelas, cobrar o deslize tira o robô do ar em poucos pregões partindo do capital real. A expectativa por trade, a 1 contrato, sai de **+R$4,27 (T2 sem deslize)** para **−R$0,45 (T2 com deslize)** e **−R$0,09 (T3, a compensação do dono)**.

As linhas com deslize estão **censuradas** (70-71/72 e 37-49/51 pregões sem trade, `caixa_mín` abaixo da margem crua de R$150) — o líquido delas mede o portão de capital, não o edge. O que mede edge é o win% contra o breakeven, e ele é **invariante ao deslize** (o gatilho não muda, só o preço de saída), então vale o win% de n grande da linha não-censurada: **94,5% (n=9.635), IC 95% [94,04% ; 94,96%] — o breakeven de 95,00% fica FORA do intervalo, acima dele** (z = −2,15).

> **T2/S16 não tem edge depois de cobrar o deslize.** A compensação do dono (pedir 3 ticks para receber 2) devolve o payoff, mas o gatilho anda junto e o win% cai para 89,9% (n=5.076) contra breakeven de 90,00% — o breakeven cai DENTRO do IC [89,07% ; 90,73%]. Ela não resgata: leva de "negativo mensurável" a "cara-ou-coroa em cima do zero".

> Um ótimo que mora exatamente no ponto onde o simulador é mais otimista que a realidade não é um ótimo. É o sintoma de um modelo incompleto.

Consequências que continuam valendo:

1. O "padrão estrutural" da varredura de 250 células (*alvo=1 é o único regime saudável*) **descreve o motor antigo, não o mercado** — não cite como achado de estratégia. Aquela grade rodou sem cobrar o deslize e escolheu a célula que mais explorava a lacuna do modelo.
2. Toda comparação T1×T2 feita antes de 2026-09-08 está viciada no mesmo eixo. Inclusive a de 2026-09-04.
3. **7 scripts antigos de laboratório montam `IntradayCostModel` na mão** (`copa_lab.py`, `f8_win_lacuna_execucao_sweep.py`, `wdo_fillreal_study*.py`, `wdo_geo_sweep.py`, `wdo_geo_grid_rolling_market_sweep.py`, `wdo_grid_reload_f1_lab.py`) com `target_fills_as_maker=True` — eles **não** passam por `config_for` e continuam com o alvo de graça. Rodar um deles hoje produz número otimista de novo.

## Testes rodam em paralelo — sempre

`pyproject.toml` fixa `-n auto --dist load` (pytest-xdist). Suite inteira mede 92s serial → 35s paralela nesta máquina, e o ciclo "mede → decide → mede de novo" é o trabalho: suite lenta é o gargalo do projeto. **Todo teste novo obedece duas condições, senão o paralelismo quebra em falha intermitente:**

1. **Sem caminho de arquivo fixo compartilhado.** `tmp_path` sempre. Dois workers ao mesmo tempo pegariam o mesmo arquivo.
2. **Sem dependência de ordem entre testes.** `--dist load` distribui teste-a-teste; ordem de coleta ≠ ordem de execução.

Mesmo espírito para **sweeps de parâmetro**: `ProcessPoolExecutor` com `submit`/`as_completed` (nunca `pool.map`, que trava resultado pronto atrás de unidade lenta), `redirect_stdout` por unidade, `flush=True` em todo print, cada unidade imprime a linha DELA assim que termina — resumo ordenado vem depois. Ver `scripts/daytrade/gremah_defesa_corte_sweep_2026_09_03.py` e `scripts/daytrade/sweep_copa.py`.

## Front-end: HTMX + Terminal Editorial

FastAPI + Jinja2 templates in `src/dashboard/templates/` (partials in `partials/`) + HTMX for partial swaps + Plotly.js. **No SPA framework.** All templates inherit from `base.html`. Colors from `static/css/tokens.css` — never hardcode. Fonts: JetBrains Mono (data/numbers), Instrument Serif (headlines). When creating/editing a template, invoke the `frontend-design` skill.

## Windows-specific gotchas

- Shell is PowerShell; use `.\.venv\Scripts\python.exe`, not `./venv/bin/python`.
- No TA-Lib (C dependency, painful on Windows) — indicators live in `core/indicators.py` as pure `(pd.Series, ...) -> pd.Series` functions.
- Live ops require Windows because `MetaTrader5` Python only talks to a locally-running MT5 terminal via Windows IPC — see `DEPLOY.md`.
- `dev.bat` explicitly cleans up port 8000 in a loop because uvicorn `--reload`'s master + spawned child both bind the socket.
- **Saldo do MT5 (Rico) não é confiável como fonte de capital.** `MT5Broker.account_risk_state()`/`cash_balance()` chamam `mt5.account_info()` direto no terminal, mas a Rico confirmou que esse saldo não é sincronizado com o saldo real da corretora — pode aparecer um número muito menor (ou maior) que o dinheiro de verdade na conta, sem que nada esteja errado. Por isso o sizing e o gate de capital usam o valor **digitado pelo dono no painel** (`available_cash` / `capital` do slot em `db/live_process.json`), nunca o número que vem do MT5 — sincronizar é manual, 1x/dia quando o dono decide. Não trate `equity`/`balance`/`margin_free` baixos vindos do MT5 como sinal de conta zerada ou de motivo para o robô não entrar.

## What NOT to do (from AGENTS.md)

- Medir `profit_ticks=1` (T1) no WDO F1 / família maker — nem como baseline (ver seção do deslize de TP).
- Comparar um número medido **antes** de 2026-09-08 com um medido depois sem checar o aviso `desliz.alvo` da linha: são modelos de custo diferentes.
- Ler um `líquido` de backtest sem antes conferir **trades** e **pregões sem trade**: janela onde o robô parou é censurada.
- Tratar o piso de capital cheio (R$375 no WDO@) como condição de continuidade — ele é indicação de PARTIDA.
- Add dependencies without justification (project weight matters).
- Use TA-Lib.
- Swap SQLite for another DB in this phase.
- Introduce React/Vue/any SPA framework — HTMX solves it.
- Put multiple strategies in one file — **one strategy per file** in `strategy/` (this is what makes auto-discovery work).
