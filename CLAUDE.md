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

**Ordem do dono, 2026-09-08: teste SEMPRE com o capital mínimo para operar, a não ser que ele passe outro valor expressamente.** Nada de bateria "com folga" para separar geometria de censura — se o dono não tem o capital, a célula não descreve nenhum futuro possível e é só tempo de máquina gasto. Isso vale inclusive quando a janela sai censurada: uma linha censurada com o capital real informa mais (mostra que o robô morre de caixa) do que uma linha limpa com um capital que não existe.

Foi exatamente o que aconteceu na varredura do deslize: 10 das 24 células eram a R$5.000, "o único lugar onde T4/T6 podem ser lidos" — e foram canceladas por este motivo. Ler T4/T6 num capital indisponível responde uma pergunta que ninguém tem.

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

> **DESFECHO, 2026-09-09 — leia isto antes do resto da seção.** O deslize abaixo é real e continua medido, mas ele **não é mais o custo que o robô paga**: era consequência de um MECANISMO de execução, não uma constante do mercado. O `tp` nativo é gatilho varrido a mercado; trocá-lo por ordem-limite real parada no livro (`fatiar_saida_alvo=True`, commit `317e839`) faz o custo sumir por construção — derrapagem é "executou pior do que pedi", e limite recusa pior. Com isso o T2/S16 vira **+R$239.936,50 no IS (0/72 pregões sem trade) e +R$77.833,50 no OOS (0/51)**, contra −R$242,50 e −R$273,50 do alvo nativo. **Está ligado em produção.** O que continua valendo desta seção: a proibição do T1, os números do deslize (que explicam por que o alvo nativo é inviável), e a lista de scripts antigos viciados. O que NÃO vale mais: o veredito "T2/S16 não tem edge" e o parágrafo "rodar mais nada move a resposta" — ver a correção no fim da seção. O risco que a troca cria (o alvo perde o TP registrado na corretora; a fila REAL de saída nunca foi medida) está no item novo de `LICOES_DE_PRODUCAO.md`.

> **CONTINUA em _A base de fidelidade de execução_ (seção seguinte).** Trocar o alvo nativo por ordem-limite real resolveu o PREÇO da saída e criou na hora a pergunta seguinte, que ninguém tinha feito: *quem está na FRENTE dessa limite?* Até 2026-09-09 o motor respondia "ninguém" — dos dois lados da operação. As duas seções são o mesmo erro de modelo em dois pontos da mesma ordem.

**Ordem do dono, 2026-09-08: `profit_ticks=1` (T1) não entra em nenhuma medição do WDO F1 nem da família maker — nem como candidato, nem como baseline, nem como "linha de referência" numa tabela.** Não é preferência de parâmetro. É uma geometria que o motor sabe simular e a corretora não sabe executar.

**Isso vale para QUALQUER estratégia com `target_fills_as_maker=True`, não só o WDO F1 — inclusive `wdo_orb` (em produção).** Um alvo de 1 tick não entra como candidato nem em `alvo_ticks_fixo=1` nem em `alvo_multiplo` tão baixo que o alvo calculado chegue perto de 1 tick, mesmo que o robô use ordem-limite real (não `tp` nativo) — a razão hoje não é mais só o deslize do gatilho nativo (isso foi corrigido em 2026-09-09, ver a seção acima), é a FILA: um nível a 1 tick do preço de entrada é o nível mais disputado do livro, e a calibração real (`fidelidade.py`, fila 438/489) já mostra que até alvos normais penam pra preencher. Um agente que reencontrar essa restrição e achar "ah mas esse robô não é o WDO F1, e o alvo dele não é nativo" está errando — a proibição é sobre o RESULTADO (alvo de 1 tick não é executável de forma confiável), não sobre qual robô ou qual mecanismo gerou o número.

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

> **[SUPERADO em 2026-09-09 — vale só para o alvo NATIVO; ver o DESFECHO no topo da seção] T2/S16 não tem edge depois de cobrar o deslize.** A compensação do dono (pedir 3 ticks para receber 2) devolve o payoff, mas o gatilho anda junto e o win% cai para 89,9% (n=5.076) contra breakeven de 90,00% — o breakeven cai DENTRO do IC [89,07% ; 90,73%]. Ela não resgata: leva de "negativo mensurável" a "cara-ou-coroa em cima do zero".

> Um ótimo que mora exatamente no ponto onde o simulador é mais otimista que a realidade não é um ótimo. É o sintoma de um modelo incompleto.

**Onde mora a incerteza que ainda decide (2026-09-08).** O ponto de virada é mais apertado do que o veredito sugere. Contra win% 94,5% e perda de R$85,50 (16 ticks + 1 tick de deslize do stop + R$0,50), o T2/S16 fica no zero a zero com **deslize de 0,905 tick** — e o IC 95% do deslize medido (média 1,000, desvio 0,447, n=11) é **[0,700 ; 1,300]**, que ATRAVESSA esse ponto. Medido por sensibilidade: a 0,5t a mesma geometria dá **+R$137.618,50 com 0 de 72 pregões sem trade** (não censurada), a 1,0t dá −R$242,50 com 71 de 72 parados. Não é gradiente, é penhasco.

Consequência de método: **rodar mais janela, mais geometria ou mais capital não move a resposta** — o win% já tem n de cinco dígitos e IC de ±0,5pp. A incerteza inteira está do lado do custo, num n=11. A única medição que decide é acumular saídas por TP nativo no extrato (~40-50 levariam o IC a ~±0,14 tick), e **a sombra não serve para isso**: ela não manda ordem, então nunca preenche um TP de verdade. Essa medição só existe com dinheiro real, a uma expectativa conhecida de −R$0,45/trade — é decisão do dono, não tarefa a disparar.

> **CORREÇÃO, 2026-09-09 — o parágrafo acima estava certo sobre as três alternativas que listou e errado na conclusão, porque a lista estava incompleta.** Janela, geometria e capital de fato não moviam a resposta. A quarta alternativa, que ninguém tinha considerado, movia: **trocar o mecanismo de execução que GERA o custo**. Um número medido com rigor (n=11, direção inequívoca) foi tratado como constante da natureza quando era consequência de uma escolha de implementação — o alvo viajava como `tp` nativo, que a corretora varre a mercado. A pergunta que faltou não era *"quanto custa?"*, era ***"por que custa?"***. Com o alvo fatiado a pergunta do n=11 deixa de decidir qualquer coisa: aquele custo não é mais pago. Fica a lição de método, que é o que sobrevive: **antes de aceitar um custo medido como restrição, pergunte se ele é do mercado ou do caminho escolhido para chegar nele.** Um custo que só existe por causa do "como" é bug de implementação usando roupa de lei da natureza.

Consequências que continuam valendo:

1. O "padrão estrutural" da varredura de 250 células (*alvo=1 é o único regime saudável*) **descreve o motor antigo, não o mercado** — não cite como achado de estratégia. Aquela grade rodou sem cobrar o deslize e escolheu a célula que mais explorava a lacuna do modelo.
2. Toda comparação T1×T2 feita antes de 2026-09-08 está viciada no mesmo eixo. Inclusive a de 2026-09-04.
3. **Script de laboratório que monta `IntradayCostModel` na mão** com `target_fills_as_maker=True` não passa por `config_for` e fica com o alvo de graça — produz número otimista. Os 7 que faziam isso (`copa_lab.py`, `wdo_fillreal_study*.py`, `wdo_geo_*`…) foram apagados; não recrie o padrão.
4. **Os mesmos scripts que fogem de `config_for` também fogem da FILA** — nenhum deles passa por `backtest/intraday/fidelidade.py`, então rodam com `queue_ahead_qty=0.0` e `exit_queue_ahead_qty=0.0` (entrada E saída de graça). Somados os dois desvios, um número saído dali hoje é otimista em duas frentes independentes — e uma delas já se mostrou capaz de inverter o sinal do resultado.

## A base de fidelidade de execução — obrigatória em toda medição de robô maker

> **Mesma família do problema da seção acima, do outro lado da mesma ordem.** Lá o simulador dava um preço de saída que a corretora não dá; aqui ele dava uma FILA que a corretora não dá. Trocar o `tp` nativo por ordem-limite real resolveu o preço e criou imediatamente a pergunta seguinte: *quem está na FRENTE dessa limite?* Leia as duas juntas — a lição de método é a mesma, e desta vez o buraco vinha de um mês antes.

**A partir de 2026-09-09, nenhuma medição de robô maker vale sem declarar a premissa de preenchimento que usou.** Os números por símbolo moram em **`src/backtest/intraday/fidelidade.py`** (tabela por símbolo, no molde de `core/instruments.py`), `config_for` os lê sozinho (então backtest, sombra e produção herdam juntos, mesmo precedente do deslize do alvo nativo) e a tabela padrão carimba a premissa na linha — `fila 438/489`. Não digite fila na mão dentro de um script: se o número não veio de `fidelidade.py`, ele não foi calibrado contra execução real. Itens **3.8** (parâmetro opcional é parâmetro desligado), **4.20**, **4.21** e **4.22** de `LICOES_DE_PRODUCAO.md`.

### O que estava errado

Até 2026-09-09 o motor enchia ordem-limite no **PRIMEIRO TOQUE** do nível, **dos dois lados da operação**. No livro de verdade, o preço ter negociado no seu nível significa que alguém negociou ali — quase sempre com quem estava na **FRENTE** da fila. Tocar não é preencher.

Três buracos, todos fechados em 2026-09-09:

| buraco | desde quando | efeito na medição |
|---|---|---|
| `exit_queue_ahead_qty` (fila da **SAÍDA**) não existia | sempre | alvo maker preenchia de graça, no toque |
| `queue_ahead_qty` (fila da **ENTRADA**) existia desde 2026-08-26 e **nunca foi setado em lugar nenhum do repo** | 2026-08-26 → 2026-09-09 | ficou no default `0.0` por **um mês inteiro**; toda medição maker do período encheu entrada de graça |
| a fatia que estourava o prazo saía a **MERCADO** mas era **precificada como maker** | sempre | a saída mais cara do robô entrava na conta com o custo da mais barata |

**O do meio é o ponto mais importante desta seção**, e é o que tem de sobreviver à troca de linguagem/plataforma: **um parâmetro de realismo que existe mas nasce desligado é pior que não existir, porque dá a impressão de estar coberto.** Quem abrisse `machine.py` encontraria um modelo de fila implementado, documentado, com docstring longa — e concluiria (errado) que o backtest cobrava fila. Ninguém procura o que já achou. Um campo ausente ao menos provoca a pergunta; um campo presente em `0.0` encerra a pergunta.

### Os números: calibração contra execução real

Calibração do **WDO@** (contrato WDOV26), pregão de **2026-09-09**, `magic` 862399285. Método: `history_orders_get` dá o instante em que a ordem-limite entrou no livro e o instante em que preencheu ou foi cancelada; `copy_ticks_range` dá todo negócio do dia. **Q_frente = volume negociado NO PREÇO DA ORDEM entre os dois instantes.** Estimador **Kaplan-Meier**, porque a amostra é **censurada à direita** — ordem cancelada por prazo só informa "esperou pelo menos X", não quanto teria esperado.

| lado | n que esperaram | preencheram | censuradas | **KM mediana** | ingênua (só fills) |
|---|---|---|---|---|---|
| **ENTRADA** | 67 | 30 | 37 | **438** | 346 |
| **SAÍDA** | 25 | 8 | 17 | **489** | 374 |

**Lição de método destacável, vale muito além deste caso: estimar fila só com as ordens que preencheram é viés de sobrevivência, e ele só anda para um lado.** Ordem que preencheu é, por definição, ordem que **ganhou** a fila; a que enfrentou fila grande foi cancelada e sumiu da amostra. Corrigir a censura moveu **346→438** na entrada e **374→489** na saída — sempre para cima, nunca para baixo. Qualquer estatística do tipo "quanto se espera até X acontecer" carrega esse viés embutido se as que não aconteceram forem jogadas fora.

**Refinamento medido e REFUTADO — não refaça.** A hipótese era que só o volume do **agressor do lado contrário** consome a fila (uma compra parada no livro só anda quando alguém VENDE a mercado naquele nível), o que sugeriria descontar metade do volume da barra. No dia inteiro o fluxo é de fato equilibrado — 50,1% comprador / 50,1% vendedor. Mas **no nível da própria ordem, 99,3% do volume é do lado que executa contra nós**: a limite está na melhor oferta, então negócio naquele preço é por definição alguém agredindo a nossa ponta. **Descontar o volume inteiro da barra já estava certo.**

### A aferição contra o extrato — o motor errava o SINAL

O robô rodou de verdade em **2026-09-09, das 14:47 às 18:03**: **34 operações, líquido −R$102,00, −R$3,00 por operação**, **33,3% de preenchimento** (9 alvos preenchidos como limite contra 18 estouros de prazo) e 7 stops. Simulando o **mesmo trecho**, T2/S6, prazo 60:

| configuração | trades | R$/trade | fill% |
|---|---|---|---|
| **REAL (extrato)** | 34 | **−3,00** | 33,3 |
| motor **sem fila nenhuma** (até 2026-09-08) | — | **+3,82** | 97,8 |
| Q_ent=0, Q_saí=400 (chute) | 63 | −0,50 | 44,4 |
| **Q_ent=438, Q_saí=489 (adotado)** | 42 | **−3,48** | 44,1 |

O motor antigo não errava a magnitude: **errava o sinal.** Previa **+R$3,82** por operação num dia que deu **−R$3,00**, e previa 97,8% de fill num dia que deu 33,3%. Não é "otimista na margem" — é resposta de direção oposta, e era esse motor que produzia todos os números de robô maker do repo.

### As limitações, que fazem parte do achado

Registrar só a metade boa repetiria exatamente o erro que a seção documenta:

- **Um pregão só.** n=67 (entrada) e n=25 (saída) vêm de um único dia. A amostra da saída é pequena e **cada pregão real novo quase dobra ela** — recalibrar é barato e deve ser feito, não é tarefa opcional.
- **A contagem de operações ainda fica ~30% acima da real** (42 simuladas contra 34). Sobra otimismo em algum lugar que a fila sozinha não explica.
- **O par que melhor encaixa no dia (Q_saí=600) foi escolhido DEPOIS de ver o resultado — isso é ajuste, não validação.** Por isso o valor adotado é o **489 do Kaplan-Meier**, que é estimativa com método, e não o que melhor encaixa em n=34. Escolher o parâmetro que melhor reproduz a amostra já vista fabrica concordância em vez de medi-la, e concordância fabricada não sobrevive ao pregão seguinte.

A quarta limitação seria a mais séria se fosse verdade — a produção trocou de mecanismo no MESMO dia (`exit_ttl_bars` → sem prazo), e calibração medida sob um mecanismo raramente sobrevive à troca dele. Aqui sobrevive, e a subseção seguinte explica exatamente por quê e o que **não** sobrevive junto.

### Como a base se mantém viva — e o que a troca para "sem prazo" fez com ela

A calibração de 438/489 foi medida num robô que rodava **com** prazo na fatia de saída; a produção passou a rodar **sem** prazo no mesmo 2026-09-09 (`EXIT_TTL_BARS_SEM_PRAZO = 10**9`). A calibração continua valendo, e a razão é o que impede esta seção de envelhecer numa semana: **Q é propriedade do LIVRO, não do nosso robô.** Quantos contratos estão na frente da nossa ordem naquele preço não muda porque nós desistimos depois de 22 segundos. O prazo determinava apenas por quanto tempo a gente conseguia **observar** a fila.

E observar pouco era exatamente o problema: **17 das 25 ordens de saída de 2026-09-09 foram censuradas** — canceladas pelo prazo antes de sabermos qual era a fila delas. Foi isso que obrigou ao Kaplan-Meier. Sem prazo, essas mesmas observações correm até o preenchimento e viram **eventos**: a mesma quantidade de operações passa a produzir estimativa muito mais firme. **Tirar o prazo melhorou a mensurabilidade da fila, não piorou.**

O que de fato deixa de ser mensurável é a **derrapagem do estouro de prazo** — as 18 saídas a mercado daquele pregão eram a única observação com dinheiro real daquele caminho, e não haverá outra. Não é perda: o robô parou de pagar esse custo, e calibrar custo que não se paga mais é desperdício. É a seção do deslize do TP nativo um degrau adiante — lá, perguntar *por que* custa fez o custo sumir; aqui, o custo que sumiu leva junto a própria necessidade de medi-lo.

**O que passa a existir e nunca foi medido.** Estas três linhas estão **vazias**, e são a agenda de medição a partir do primeiro pregão sem prazo:

| o que medir | por que | linha de base |
|---|---|---|
| saídas no achatamento de fim de pregão | caminho NOVO; limitado entre stop e alvo, mas nunca medido | **nenhuma** |
| tempo de posição aberta (mediana / p90) | é o custo que **substituiu** a derrapagem: o motor não piramida, então enquanto a limite espera o robô não abre outra posição — paga em operações que não faz | **nenhuma** |
| posições que o pregão inteiro não pagou | é a cauda do desenho sem prazo | **nenhuma** |

**Como a calibração se refresca:** `scripts/daytrade/wdof1_calibra_fila_real_2026_09_09.py` reprocessa o extrato do terminal e devolve os números que `fidelidade.py` guarda. Cada pregão real novo quase dobra a amostra da saída (n=25), então rodar é barato e é devido, não opcional. **Mas curvas de regimes diferentes não se misturam numa estimativa só sem declarar o regime:** pregão COM prazo e pregão SEM prazo têm natureza de censura diferente — no primeiro a censura é imposta pelo relógio do robô e é maciça (17 de 25), no segundo ela quase desaparece. Somar os dois sem separar mistura duas populações e devolve um número que não descreve nenhuma das duas.

> **O invariante portável: quando você troca o mecanismo de execução, a calibração do LIVRO sobrevive, mas a calibração do MECANISMO morre junto — e o que a substitui começa sem linha de base.** Antes de tratar a primeira semana pós-troca como evidência, confirme que as métricas do mecanismo NOVO já têm amostra. Enquanto a coluna "linha de base" da tabela acima estiver vazia, o resultado do robô sem prazo é observação, não validação.

### A regra que fica (portável: vale em qualquer corretora e qualquer linguagem)

1. **Antes de tratar qualquer resultado de backtest maker como previsão, verifique qual premissa de preenchimento ele usou** — fila na entrada, fila na saída, e como a saída forçada por prazo é precificada — **e confirme que essa premissa foi calibrada contra execução real, com correção de censura.** Sem as três respostas, a linha da tabela é aritmética, não previsão.
2. **Um resultado de backtest que nunca foi aferido contra o extrato não é previsão, é hipótese.** A aferição é a única coisa que separa as duas, e custa um pregão de dado real — barato perto de um mês de números com o sinal trocado.
3. **Parâmetro de realismo nasce ligado e calibrado, ou não nasce.** Default zero num campo que modela atrito é o mesmo que não modelar, com o agravante de parecer modelado.
4. **Ao estimar "quanto se espera até X acontecer", conte também as que não aconteceram.** Kaplan-Meier ou equivalente; média sobre os sucessos é sempre otimista, e só para um lado.
5. **Separe o que é do LIVRO do que é do MECANISMO.** Calibração do livro (fila, liquidez no nível) sobrevive à troca do jeito de executar; calibração do mecanismo (derrapagem de um caminho específico, taxa de fill sob um prazo específico) morre junto com ele, e a métrica que a substitui nasce sem linha de base.

Na hora de portar a estratégia, o que viaja são essas cinco perguntas, não os números: a plataforma nova tem fila própria, então `fidelidade.py` é recalibrado lá do zero — o método é que é reaproveitável.

## O desenho de execução é FECHADO: nunca a mercado, nem na entrada nem no alvo

**Ordem do dono, 2026-09-10.** Toda medição deste projeto — backtest, sombra e produção — roda no mesmo desenho de execução. Ele não é parâmetro de busca; é o contorno de dentro do qual a busca acontece.

| ponta | como | por quê |
|---|---|---|
| **entrada** | `EnterLimit` (ordem-limite parada no livro) | `Enter` a mercado **não tem caminho de execução real** — `machine._entrar_a_mercado` levanta `EntradaAMercadoNaoSuportada` de propósito, porque simular o fill com o `open` da barra manda dinheiro real contra um preço inventado |
| **alvo** | ordem-limite real fatiada (`exit_split_unit`), sem prazo (`EXIT_TTL_BARS_SEM_PRAZO = 10**9`, nunca `None`) | o `tp` nativo é gatilho varrido a mercado: **R$55,00 de deslize contra R$95,00 de bruto teórico, 57,9%** (n=11, média −1,000 tick, 10 contra 0 a favor). Ver a seção do deslize do TP nativo |
| **níveis** | `anchor_exits_at_fill=True` | se o preço deslizou entre o sinal e o preenchimento, stop e alvo acompanham o preço realmente obtido |
| **stop** | **a mercado — exceção única** | proteção não espera fila. E ele não desliza como o alvo: medido em 5 de 5 saídas reais, nunca pior que o nível pedido |

**O que isso custou por não estar escrito aqui.** Em 2026-09-10 uma rodada inteira de cinco setups públicos (Wyckoff/SMC, IFR2, VWAP, Setup 123/Ross, Ondas de Wolfe), ~50 células, foi medida com entrada e alvo a mercado. A ORB também — a única candidata viva do projeto, a que produziu o primeiro veredito POSITIVO da investigação. **Nenhum daqueles números responde à pergunta que importava**, porque descrevem um robô que a corretora recusa. A proibição do alvo a mercado já estava documentada (seção do deslize do TP) e mesmo assim não foi aplicada; a da entrada não estava em lugar nenhum, existia só como uma exceção dentro do motor que só dispara em execução real.

**A lição de método, que é o que sobrevive à troca de plataforma:** o custo de execução não é um detalhe a acertar depois que a estratégia "funcionar" — ele determina **quais desenhos existem**. Antes de varrer parâmetro de estratégia, congele o desenho de execução e confirme que ele tem caminho real confirmado. Um backtest capaz de simular o que a produção proíbe é uma máquina de gastar tempo.

**Consequência prática ao converter um setup para maker:** o custo não aparece no R$/op, aparece no **volume**. Medido na ORB (1 mês, IS): a expectativa por operação ficou em R$86-106 contra R$109 da versão a mercado — praticamente igual — mas **24% a 67% dos pregões passam em branco** porque o preço não voltou até a limite. A taxa de não-preenchimento é o número que decide, não o líquido.

**E a ordem de entrada precisa de prazo.** Sem `ttl_bars` ela espera até o fim do pregão: medido um fill **269,7 minutos** depois do rompimento (rompeu 14:08, encheu 18:37). Isso não é o trade que a estratégia pediu, é uma ordem esquecida no livro que pegou o preço passando — e os fills atrasados foram justamente os piores resultados. Atenção: `ttl_bars` conta BARRAS, e em base de tick (barra degenerada, 1 negócio por barra) isso **não é tempo** — a base mede mediana de 336 barras/minuto, com p25 190 e p75 586. Calibre e reporte o atraso REALIZADO em minutos, nunca o prazo nominal.

## Como pesquisar uma ideia de estratégia — o método que funcionou (WIN, 2026-10-09)

Destilado de um dia inteiro de pesquisa sobre a escada WIN M15: ~30 rodadas e centenas de hipóteses. O método mata ideia ruim em horas, e o que sobrevive a ele também sobreviveu ao Testador do MT5. A v4.1 bateu ano a ano, R$11.074 contra R$11.459 do Python. Siga a ordem.

**1. Gerar hipóteses: autópsia alternada, 10 ruins → 10 bons → bons × ruins, escalando.**

| passo | como | por que funciona |
|---|---|---|
| 10 dias **ruins** | Sorteie 1 por faixa do período de escolha, nunca escolha a dedo. Use 1 subagente por dia, com ficha padrão e as perguntas de `PERGUNTAS_DE_OPERACAO.md`, e cruze as fichas. | Subagentes separados leem cada dia sem contaminar um ao outro. O sorteio por faixa evita juntar só dias pitorescos. |
| 10 dias **bons**, mesmo pacote | Mesma ficha, mesmas perguntas. | **Ruins sozinhos acham o que é COMUM, não o que é DIFERENTE.** "Tarde", "dia esgotado" e "volume baixo" apareceram em 8 de 10 ruins e igualmente nos bons. Sem o grupo de controle eles virariam regra falsa. |
| cruzar **bons × ruins** | Só vira hipótese o que aparece num grupo e não no outro. | Transforma traço frequente em diferença, que é a única coisa que pode separar operações. |
| escalar | Hipótese que sobreviveu → nova rodada de 10/10 com o pacote ampliado (dias anteriores, semana, gaps, H1/H4, dólar). | Cada rodada parte do que a anterior não explicou. |

Cuidados que custaram rodadas:
- **O pacote de cada dia é cortado na hora da decisão.** H1 e diário do próprio dia vazaram o futuro uma vez.
- **Agentes convergindo NÃO é evidência.** Já aconteceu de 4 de 10 apontarem "compressão" e o teste mostrar o oposto.
- **A autópsia GERA hipóteses, não aprova nada.** Até hoje nenhuma hipótese dela passou no passo 2. O valor dela é produzir perguntas boas e descartar rápido.

**2. Testar: só depois de congelar a definição.**
- **Escrever a régua antes de olhar o resultado.** Limiar, janela e lado ficam fixos. Escolher depois de ver é ajuste, não teste.
- **Três períodos, cada um com um papel.**
  - Escolha (IS, 2022–set/25): só ele pode ser usado para decidir qualquer coisa.
  - Confirmação (OOS, out/25–out/26): mesmo sinal e p<0,10.
  - Virgem (out–dez/21): nunca tocado. Serve de último aviso: num caso os pesos que valiam no IS **inverteram** ali (correlação −0,50).
- **Nulo e múltiplos testes.**
  - Compare com o acaso por embaralhamento **por dia**, porque velas do mesmo dia não são independentes.
  - Aplique Benjamini-Hochberg q=0,10 sobre todos os testes da rodada.
  - Mão menor sempre reduz a queda, então compare com sortear a mesma quantidade de trades em 1 contrato.
- **Bloco 0 (`PERGUNTAS_DE_OPERACAO.md`): em que condições a conclusão foi tirada?** Controle por hora, lado, volatilidade e trimestre. Quase todo "achado" de hoje era o horário ≥15h disfarçado.
- **Os cinco usos (dono).** Toda informação é testada como: entrada, aviso de não entrar, tamanho da mão, stop e alvo. "Piora bastante" também é informação.

**3. Decidir: painel completo e critério do dono.**
- **O painel completo:** total, pior queda, fator de recuperação, fator de lucro, acerto, pior mês, % meses positivos, Sharpe, nos três períodos.
- **O critério:** só muda se o acerto subir bastante E recuperação e o resto melhorarem, com no máximo uma pequena queda de lucro. Sem melhora evidente, não muda.

**Lições que valem para qualquer estratégia:**
- **Achado do mercado em geral não se transfere para dentro de uma estratégia.**
  - "RSI ≤ 30 continua caindo" é verdade no WIN M15, mas nunca acontece num sinal da escada.
  - Rompimento da faixa da 1ª hora e máxima de 10 dias, bons no mercado, ficam piores dentro dela.
  - Meça sempre no **resultado da própria operação**.
- **Alvo simétrico curto não mede estratégia de cauda.** Na escada, os 10% melhores trades fazem 174% do lucro. Qualquer medida de "acerto em ±1 ATR" erra o que importa. Alvo limitado sobe o acerto e corta 40% do lucro.
- **Pesos aprendidos sobre muitas perguntas não sobrevivem à troca de regime.** A correlação dos pesos entre períodos ficou entre 0,02 e −0,29. Contagem simples, com sinal fixado de antemão, é mais robusta que peso estimado.
- **Regra de estratégia é resposta; pergunta é universal.** O arquivo de perguntas não carrega gabarito de estratégia. A resposta "não" é tão válida quanto "sim".

Memórias com os números: `escada_autopsia_*`, `banco_perguntas_pesos_refutado_*`, `estrategia_perguntas_v1_*`, `feedback_todo_teste_vira_aviso_mao_stop_alvo`, `feedback_sem_melhora_evidente_nao_muda`.

## Bases de dados versionadas

`data/*` fica fora do git (dezenas de GB), com duas exceções versionadas para a pesquisa rodar em outra máquina:
- **`data/win_sem_leiloes/`** (14 MB): WIN$N M1 auditado, sem leilões, com IS, OOS e virgem. É a base de `scripts/daytrade/topos_fundos/dados.py`.
- **`data/wdo-mt5/`** (47 MB): WDO@D M1 de 5 anos.

O resto é regenerável da fonte, e o `.gitignore` explica cada caso.

## Testes rodam em paralelo — sempre

`pyproject.toml` fixa `-n auto --dist load` (pytest-xdist). Suite inteira mede 92s serial → 35s paralela nesta máquina, e o ciclo "mede → decide → mede de novo" é o trabalho: suite lenta é o gargalo do projeto. **Todo teste novo obedece duas condições, senão o paralelismo quebra em falha intermitente:**

1. **Sem caminho de arquivo fixo compartilhado.** `tmp_path` sempre. Dois workers ao mesmo tempo pegariam o mesmo arquivo.
2. **Sem dependência de ordem entre testes.** `--dist load` distribui teste-a-teste; ordem de coleta ≠ ordem de execução.

Mesmo espírito para **sweeps de parâmetro**: `ProcessPoolExecutor` com `submit`/`as_completed` (nunca `pool.map`, que trava resultado pronto atrás de unidade lenta), `redirect_stdout` por unidade, `flush=True` em todo print, cada unidade imprime a linha DELA assim que termina — resumo ordenado vem depois. Ver `scripts/daytrade/gremah_defesa_corte_sweep_2026_09_03.py`.

## Base histórica do WDO — 5 anos, M1, `WDO@D`

`C:\Users\Jeffe\Documents\study\meta\data\wdo-mt5\WDO@D_M1_202109290900_202609291020.csv` — 2021-09-29 a 2026-09-29, M1, ~698 mil barras, TSV com cabeçalho `<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>` (exportado do MT5). Use esta base para qualquer backtest de robô WDO que precise de mais de 2 meses de histórico — ela substitui puxar contrato único fresco do MT5 (que tem o problema de liquidez/rolagem já documentado abaixo) ou a série `data/raw_intraday/WDO_A_.parquet` (que está em UTC, não BRT, e teve saltos de dado achados perto do meio-dia em alguns pregões).

**Por que `@D` (ajuste por diferença) e não `@` (sem ajuste) ou `@N` (proporcional) — decisão do dono, 2026-09-29:** o ajuste por diferença preserva a distância em PONTOS entre os preços através das trocas de contrato, que é exatamente o que importa pro stop e pro trailing de um robô medido em pontos (como o `wdo_ribbon_mm34`). A série sem ajuste (`WDO@`) tem degraus artificiais no dia da virada de contrato — um salto de preço que não é movimento de mercado nenhum, e que já causou saltos de 14-34 pontos irreais no meio de um pregão numa investigação anterior (`WDO_A_.parquet`, mesma raiz do problema). A série com ajuste proporcional (`WDO@N`) mantém a distância percentual, não a distância em pontos — distorce levemente o tamanho de cada movimento, o que atrapalha qualquer lógica calibrada em pontos absolutos (stop, alvo, filtros de range).

**Cuidado ao ler com `MetaTrader5.copy_rates_range` para `WDO@D` (achado 2026-09-29):** pedir uma janela de tempo ESTREITA (poucas horas) às vezes devolve barras de um horário completamente diferente do pedido — comportamento inconsistente da API pra este símbolo específico. Correção que funcionou: buscar o DIA INTEIRO (`copy_rates_range` com range de 24h) e filtrar depois com `.loc[]` no DataFrame, nunca confiar num range estreito direto da API pra este símbolo.

## Front-end: HTMX + Terminal Editorial

FastAPI + Jinja2 templates in `src/dashboard/templates/` (partials in `partials/`) + HTMX for partial swaps + Plotly.js. **No SPA framework.** All templates inherit from `base.html`. Colors from `static/css/tokens.css` — never hardcode. Fonts: JetBrains Mono (data/numbers), Instrument Serif (headlines). When creating/editing a template, invoke the `frontend-design` skill.

## Windows-specific gotchas

- Shell is PowerShell; use `.\.venv\Scripts\python.exe`, not `./venv/bin/python`.
- No TA-Lib (C dependency, painful on Windows) — indicators live in `core/indicators.py` as pure `(pd.Series, ...) -> pd.Series` functions.
- Live ops require Windows because `MetaTrader5` Python only talks to a locally-running MT5 terminal via Windows IPC — see `DEPLOY.md`.
- `dev.bat` explicitly cleans up port 8000 in a loop because uvicorn `--reload`'s master + spawned child both bind the socket.

## What NOT to do (from AGENTS.md)

- **Medir qualquer estratégia com entrada `Enter` (a mercado) ou alvo a mercado** — o desenho de execução é fechado, ver a seção "O desenho de execução é FECHADO". Já custou ~50 células e a única candidata viva do projeto.
- **Deixar a ordem-limite de entrada sem prazo** (`ttl_bars=None`): ela espera até o fim do pregão e preenche horas depois do sinal (medido: 269,7 min). E **nunca traduza prazo em barras para prazo em tempo sem calibrar** — em base de tick são ~336 barras/minuto.
- **Ligar `anchor_exits_at_fill` numa estratégia que entra a mercado e achar que cobriu**: a flag é lida só no caminho de preenchimento de `EnterLimit`, então é no-op silencioso para `Enter` (item 4.23 de `LICOES_DE_PRODUCAO.md`).
- **Reportar win% de uma geometria alvo/stop sem o nulo ao lado.** O nulo nominal é `stop/(alvo+stop)` — que é exatamente o breakeven a custo zero. E quando o payoff realizado foge do nominal, o nulo certo passa a ser o **breakeven empírico** `perda_média/(ganho_médio+perda_média)`. Conferência: `R$/op > 0` e `win% > breakeven empírico` são a MESMA afirmação — se as duas leituras discordam no seu relatório, o nulo está no lugar errado. Itens 6.22 e 6.23.
- **Ler o veredito de uma grade sem confirmar que cada eixo mexeu em alguma coisa.** Três grades desta rodada tinham eixo morto (item 6.25) — a de 6 células da ORB era de ~3, porque o múltiplo do alvo devolveu win% idêntico (48,61%, os mesmos 35 acertos em 72) nas quatro células com corte de tempo.
- Medir `profit_ticks=1` (T1) no WDO F1 / família maker — nem como baseline (ver seção do deslize de TP). **Vale para qualquer robô com `target_fills_as_maker=True`, inclusive `wdo_orb`** — não testar `alvo_ticks_fixo=1` nem `alvo_multiplo` baixo o bastante pra chegar perto de 1 tick, mesmo com alvo em ordem-limite real (o problema hoje é fila, não só o deslize do `tp` nativo).
- Comparar um número medido **antes** de 2026-09-08 com um medido depois sem checar o aviso `desliz.alvo` da linha: são modelos de custo diferentes.
- Ler um `líquido` de backtest sem antes conferir **trades** e **pregões sem trade**: janela onde o robô parou é censurada.
- Tratar o piso de capital cheio (R$375 no WDO@) como condição de continuidade — ele é indicação de PARTIDA.
- Ler um número de backtest **maker** medido **antes de 2026-09-09** como previsão: até essa data entrada E saída enchiam de graça no primeiro toque, e o motor chegou a errar o SINAL do resultado (+R$3,82/op previsto contra −R$3,00 realizado). Confira a premissa de fila carimbada na linha.
- Digitar `queue_ahead_qty` / `exit_queue_ahead_qty` na mão num script — o número vem de `backtest/intraday/fidelidade.py`, que é o único lugar calibrado contra extrato real.
- Escolher parâmetro de fila por "qual encaixa melhor no dia que eu já vi" (foi por isso que Q_saí=600 foi descartado a favor do 489 do Kaplan-Meier): encaixar depois de ver é ajuste, não calibração.
- Estimar fila — ou qualquer tempo-até-evento — só com as ordens que **preencheram**: é viés de sobrevivência, e ele só anda para um lado (346→438 e 374→489 ao corrigir).
- Criar parâmetro de realismo com default que o desliga e considerar o assunto coberto: `queue_ahead_qty` nasceu em 2026-08-26 e viciou um mês de medição justamente por parecer implementado.
- Somar pregões COM prazo e SEM prazo numa estimativa de fila só, sem declarar o regime: a natureza da censura é outra (17 de 25 censuradas com prazo, quase nenhuma sem) e o número resultante não descreve nenhum dos dois.
- Tratar a primeira semana do robô SEM prazo como validação: as três métricas do mecanismo novo (achatamento de fim de pregão, tempo de posição aberta, posições que o pregão não pagou) ainda têm linha de base VAZIA.
- Add dependencies without justification (project weight matters).
- Use TA-Lib.
- Swap SQLite for another DB in this phase.
- Introduce React/Vue/any SPA framework — HTMX solves it.
- Put multiple strategies in one file — **one strategy per file** in `strategy/` (this is what makes auto-discovery work).
