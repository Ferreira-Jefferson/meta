# FEAT-005 — cobertura-campea-e-menores

> Plano de ação escrito pelo feature-agent, revisado (e corrigido quando necessário) pelo plan-reviewer.
> Status: `rascunho` → `em revisão` → `aprovado` → `executado` → `concluído`

**Status:** CORRIGIDO — liberado para execução pelo plan-reviewer
**Run:** `blindagem-operacao-real` | **Plano original:** `C:\Users\Jeffe\.claude\plans\crie-um-plano-p-ra-gentle-papert.md` (seção "Lote 5 — Cobertura da campeã e menores", linhas 275-309, mais "Processo por lote")
**Tier:** T3 | **Wave:** 6 | **Isolamento:** worktree `../meta-FEAT-005`
**Branch:** `feat/blindagem-operacao-real-FEAT-005` (HEAD `d6d0197`, FEAT-004 já mergeada)
**Rigor:** REDUZIDO por decisão explícita do usuário — sem agente de hipóteses. Este planner é a única fonte de plano antes do gate 1; investigação abaixo é deliberadamente mais extensa que o padrão para compensar.

## 1. Problema / objetivo

`src/strategy/` e `src/backtest/engine_portfolio.py` — o motor que decide os
números do backtest de referência da campeã (`portfolio_dip2_hw40`) — têm
**zero teste direto** hoje (confirmado: `tests/test_backtest_engine.py` testa
só `backtest/engine.py`, o engine de ticker único; nenhum teste importa
`strategy.portfolio_dip2_hw40`, `strategy.h3_hysteresis` ou
`strategy.portfolio_satellite` fora de `LiveRuntime`, que os usa de forma
indireta/integrada). Esta feature fecha os dois maiores buracos e corrige
duas divergências reais encontradas em `engine_portfolio.py` durante a
investigação, deixadas passar até aqui porque nada testava o arquivo.

**Achado central desta investigação (regra 4/7 do AGENTS.md) — CORRIGIDO PELO
PLAN-REVIEWER:** o texto acima (versão original deste ACTION-PLAN) afirmava
que "o Lote 5 original suspeitava que `Exit` sem dado hoje NÃO reenfileira" e
que "o código real faz o OPOSTO do que o texto do plano descreve". **Isso é
falso — conferido linha a linha no plano original** (`crie-um-plano-p-ra-
gentle-papert.md`, linhas 307-309, seção "Menores da revisão"): o texto já
diz textualmente "`Exit` sem dado reenfileirado para o dia seguinte
(assimétrico com `Enter`, que é descartado — e é o 'executar tarde' que a
regra 7 proíbe)" — ou seja, o plano original **já identificava corretamente**
a direção exata do bug (Exit reenfileira, Enter descarta). Não há
contradição entre plano e código; esta investigação **confirma** o achado do
plano original com os números de linha exatos, e acrescenta duas coisas que
o original não tinha: (1) confirmação de que `live/runtime.py` **não** tem o
problema análogo — intents ao vivo expiram por `stale_intents`/regra 7 de
verdade (`runtime.py:751-758`), não há fila `pending` em memória lá; (2)
achado novo (fora do plano original): `engine.py` (motor de ticker único) tem
a MESMA assimetria (`engine.py:253` reenfileira `Exit` vs `engine.py:291`
descarta `Enter`) — ver premissa 7.

Confirmado por leitura direta nesta revisão: `engine_portfolio.py:351-357`
(`pending.append(act); continue` no ramo "ticker sem dado hoje" do laço de
`Exit`) vs `engine_portfolio.py:441-443` (`continue` puro no laço de
`Enter`). Reenfileirar significa que uma saída decidida no close de D pode
executar no open de D+2, D+3... se o ticker tiver um gap de dado — quebra o
contrato da regra 4 ("close[D] → open[D+1], nunca outro dia") e é exatamente
o "executar tarde" que a regra 7 proíbe, ainda que a regra 7 cite
`core/live_models.py` como exemplo — o princípio (decisão atrasada não
executa) é o mesmo e o `engine_portfolio.py` é o motor que MODELA o que o
live faz.

**Segundo achado de produção:** `entries_filled += 1`
(`engine_portfolio.py:459`) incrementa ANTES do teste de viabilidade
(`plan.is_feasible`, linha 464) — `entries_skipped` (`entries_attempted -
entries_filled`) nunca pode ser > 0. Confirmado por grep: **nenhum chamador
no repositório passa `entry_fill_mode` diferente de `"open"`** (o único
valor do `Literal["open"]`), então o bloco de métricas que usa esses três
contadores (linhas 571-577) é hoje código morto — o bug não altera nenhum
número reportado agora, mas fica ativo assim que alguém usar o parâmetro
(ele existe por um motivo, não é vestigial de nomenclatura).

**Investigação também revelou que boa parte do Lote 5 já está coberta** por
FEAT-001/002/003/004, que mexeram muito em `live/runtime.py` desde que o
plano foi escrito. Ver tabela de NO-OPs na seção 2b — isto reduz
substancialmente o escopo de dois dos quatro arquivos de teste pedidos pelo
plano original.

## 2. Arquivos

### Escreve (produção)

- `src/backtest/engine_portfolio.py`:
  - `exits_p` loop (linhas 351-357): remove `pending.append(act)` do ramo
    "ticker sem dado hoje" — passa a só `continue` (descarta), simétrico ao
    `enters_p` loop logo abaixo (linhas 442-443). Comentário novo explica o
    porquê (regra 4/7) e por que é seguro: a família `BuyTheDip` reavalia o
    alvo de rotação TODO mês (`on_bar` roda no month-end e recalcula `tgt`
    do zero a partir de `_scores`/`_dist_from_high`), então uma saída
    descartada por falta de dado simplesmente será re-decidida (ou não) no
    próximo rebalance mensal — não fica presa. Não requer estado novo, não
    muda a interface de `Strategy`.
  - Bloco de entrada (linhas 445-463): move `entries_filled += 1` para
    IMEDIATAMENTE DEPOIS do `if not plan.is_feasible: continue` (linha 464),
    nunca antes — só conta como "preenchida" a entrada que de fato virou
    posição.
- `src/core/models.py`:
  - `Trade.r_multiple` (linhas 108-115): `risk_per_share = self.entry_price
    * 0.15` vira `risk_per_share = self.entry_price * _DEFAULT_RISK_PCT`,
    com `_DEFAULT_RISK_PCT` um constante de módulo nova, documentada:
    espelha `core.config.BacktestConfig.stop_loss_pct` (mesmo valor, 0.15),
    com docstring explícita de que é uma aproximação — `Trade` não guarda o
    stop real usado na entrada (`Enter.initial_stop`), então se uma
    estratégia algum dia passar um stop customizado (nenhuma registrada
    hoje passa — verificado por grep, ver riscos), `r_multiple` fica
    impreciso para ela até `Trade` ganhar um campo de risco real (fora de
    escopo: exigiria mudar toda construção de `Trade` em `engine.py` E
    `engine_portfolio.py`, não só `core/models.py`). **Deliberadamente NÃO
    é uma correção funcional** — o valor numérico de `r_multiple` não muda
    para nenhum trade histórico; é só nomear o número mágico e travar a
    coerência com `BacktestConfig` via teste.
- `tests/doubles.py`: adiciona `_RecordingNotifier` (import `Notifier` de
  `live.notify`) — consolidação de um duplicata real encontrado nesta
  investigação (ver 2b). **CORREÇÃO PLAN-REVIEWER:** também adiciona
  `ScriptedStrategy` (dict indexado por data, semântica de
  `tests/test_live_runtime.py`) e `ScriptedStrategySequence` (fila de
  listas de ação por chamada, renomeada a partir de `_ScriptedStrategy` de
  `tests/test_live_robots.py`) — ver premissa 11 (a investigação original
  concluiu, errado, que não havia duplicata).
- `tests/test_live_robots.py`: remove a definição local de
  `_ScriptedStrategy` (linha 34), importa `ScriptedStrategySequence` de
  `tests.doubles` e troca as ~6 chamadas `_ScriptedStrategy(...)` pelo nome
  novo (mesmo comportamento, só o local onde a classe mora muda).
- `tests/test_strategy_champion.py` (**novo**).
- `tests/test_engine_portfolio.py` (**novo**).
- `tests/test_live_runtime.py`: remove a definição local de
  `_RecordingNotifier` (linha 1125) e de `ScriptedStrategy` (linha 44),
  passa a importar as duas de `tests.doubles` + 4 funções de teste novas
  (ver Passo 6).
- `tests/test_live_notify.py`: remove a definição local de
  `_RecordingNotifier` (linha 32, passa a importar de `tests.doubles`).
  Nenhuma outra mudança neste arquivo.
- `scripts/debug_sim.py` (linha 17) e `scripts/screenshot_sim.py` (linha
  19): URL `http://127.0.0.1:8765/strategies/sim/{sim_id}` →
  `http://127.0.0.1:8765/sim/{sim_id}` — rota real confirmada em
  `dashboard/app.py:564` (`@app.get("/sim/{sim_id}")`); `/strategies/sim/`
  nunca existiu como rota (grep confirmado). Scripts de debug manual via
  Playwright, sem cobertura de pytest — a prova aqui é `grep`, não teste.
  **CORREÇÃO PLAN-REVIEWER:** o grep original não pegou um terceiro arquivo
  com o mesmo defeito — `scripts/screenshot_strategies.py:30` espera
  `page.wait_for_url("**/strategies/sim/**")` depois de submeter o
  formulário, mas o redirect real (`dashboard/app.py:298`,
  `RedirectResponse(url=f"/sim/{sim.id}", ...)`) nunca gera essa URL — o
  `wait_for_url` sempre estouraria o timeout de 15s. Adicionado ao Passo 7.

### Só lê

- `src/strategy/base.py` (`Strategy.state()`/`restore()`, `_stateful_keys`,
  `Enter`/`Exit`/`AdjustStop`/`OpenPosition` — já existentes).
- `src/strategy/buy_the_dip.py`, `src/strategy/h3_hysteresis.py`,
  `src/strategy/portfolio_satellite.py`, `src/strategy/portfolio_dip2_hw40.py`
  (hierarquia da campeã — nenhuma mudança, só teste direto).
- `src/core/calendar.py` (`is_month_end`), `src/core/earnings_calendar.py`
  (`blackout_series`/`is_earnings_blackout`) — usados para montar cenários
  sintéticos de blackout/month-end nos testes novos.
- `src/backtest/sizing.py`, `src/backtest/costs.py`, `src/backtest/withdrawal.py`
  (`plan_entry`, `initial_stop`, `FloorSkim` — já existentes, reusados).
- `src/live/runtime.py` (`_restore_robot_state`, `execute_session`,
  `confirm_withdrawal`, `reconcile_broker_cash`, `_expire_withdraw_advice` —
  já existentes, só teste novo).
- `src/live/notify.py` (`Notifier` — base para `_RecordingNotifier`).

### Correção de escopo em relação ao `EXEC-MAP.md`

| Item do `EXEC-MAP` | Realidade encontrada | Decisão |
|---|---|---|
| `tests/test_live_withdrawal_advice.py` (novo) | Todos os 5 cenários listados no Lote 5 já têm teste equivalente em `tests/test_live_runtime.py`, adicionado por FEAT-002: recomendação não move dinheiro (`test_saque_recomendado_nao_move_caixa_nem_gera_ordem`, linha 694), ignorada acumula na fila (`test_saque_expira_na_virada_do_mes_e_devolve_valor_a_fila`, linha 911), confirmação humana debita/credita (`test_confirm_withdrawal_debita_caixa_credita_externo_e_fecha_intent`, linha 803), expiração na virada de mês (mesmo teste da linha 911), conciliação MT5 nunca credita sozinha (`test_reconcile_broker_cash_nunca_credita_so_avisa_pra_mais_ou_pra_menos`, linha 1364). O ÚNICO cenário sem cobertura é a INTERAÇÃO específica "conciliação rodada logo após uma confirmação de saque não é lida como depósito" (nenhum teste de `reconcile_broker_cash` roda depois de um `confirm_withdrawal`). **Não crio arquivo novo** para 1 cenário — seria o anti-padrão "prova genérica"/arquivo cerimonial; adiciono a 1 função que falta em `tests/test_live_runtime.py`, no mesmo estilo dos testes de saque já lá (mesmo precedente de FEAT-004 com `live_control.py`: correção de escopo justificada por evidência, não invenção de trabalho). |
| `tests/test_live_account_mode.py` (novo) | Os 4 cenários listados já têm teste, todos de FEAT-001: modo divergente conta/broker recusado (`test_cmd_loop_valueerror_de_conta_broker_divergente_e_fatal`, `tests/test_run_live_cli.py:235`), `--mode` desconhecido levanta (`test_build_modo_desconhecido_levanta_valueerror`, `tests/test_run_live_cli.py:75`), `cmd_tickets`/`cmd_confirm` recusam conta não-manual (`test_cmd_tickets_recusa_conta_nao_manual`/`test_cmd_confirm_recusa_conta_nao_manual`, `tests/test_run_live_cli.py:184,198`), prova de vida detecta morte imediata (`test_start_processo_morre_na_hora_levanta_runtimeerror_sem_gravar_estado`, `tests/test_live_control.py:52`). **NO-OP total para este arquivo — nenhuma linha nova, em lugar nenhum.** |

## 2a. NO-OPs confirmados (não geram passo, listados para não serem reabertos)

| Item do Lote 5 original | Evidência de que já está resolvido |
|---|---|
| Assinatura condicional em `test_withdrawal_flui_e_estado_sobrevive_a_restart` | JÁ CORRIGIDA — `tests/test_live_runtime.py:516-531` usa `clock.sessions_between` filtrado para um bloco garantidamente no MESMO mês civil, com comentário explícito citando "defeito apontado no Lote 5 do plano original". Feature anterior (provavelmente FEAT-002) já tratou isto proativamente. |
| Stop intra-dia sob `ManualBroker` sem teste | JÁ COBERTO — `test_stop_intraday_nao_duplica_ordem_sob_corretora_manual`, `tests/test_live_runtime.py:351` (FEAT-004). |
| `data_is_ready` falso nunca testado | JÁ COBERTO — seção "FEAT-003: item 3.3 — skip por dado incompleto e visivel", `tests/test_live_runtime.py:1842-1942`, inclusive o caso fim-de-mês (nível `error`). |
| Disjuntor diário disparando em crash intra-dia | JÁ COBERTO — `test_disjuntor_dispara_em_crash_intradia_e_estado_sobrevive_a_restart`, `tests/test_live_runtime.py:1699` (FEAT-003). |
| `_restore_robot_state` ramo `investment` nunca exercitado | JÁ COBERTO — `test_estado_de_outro_robo_e_descartado_no_restore`, `tests/test_live_runtime.py:1588` (FEAT-003), e o teste de restart no blackout de março logo acima. **CORREÇÃO PLAN-REVIEWER: o ramo `risk_guard` TAMBÉM já está coberto**, não só `investment` — `test_disjuntor_dispara_em_crash_intradia_e_estado_sobrevive_a_restart` (`tests/test_live_runtime.py:1699`, FEAT-003) constrói um `rt2` NOVO (`LiveRuntime`+`CircuitBreaker` novos, mesmo banco), chama `rt2.reconcile_pending_fills()` — que chama `self._restore_robot_state(account.policy_state)` em `runtime.py:1240` — e afirma `rt2.risk_guard.is_frozen is True`. Isso já exercita o dispatch de `_restore_robot_state` para o ramo `risk_guard`, exatamente o cenário que este ACTION-PLAN (versão original) propunha recriar no Passo 6(b). **NO-OP total para esse item — item (b) removido do Passo 6** (ver Passo 6 corrigido). |
| `tests/doubles.py` "confirme que não sobrou duplicata" | PARCIALMENTE JÁ FEITO (FEAT-001: `PaperBroker`/`ReplayFeed`) mas **sobrou uma duplicata real**: `_RecordingNotifier` definida de forma idêntica em `tests/test_live_notify.py:32` E `tests/test_live_runtime.py:1125` (mesmos 2 métodos, mesmo comportamento). `_write_parquet`/`_sessions` — confirmado só 1 definição cada (`test_live_runtime.py`), sem duplicata. Vira Passo 1. **CORREÇÃO PLAN-REVIEWER: a conclusão original sobre `ScriptedStrategy` estava ERRADA** — a investigação rodou um grep estreito por `class ScriptedStrategy` (que não bate com `class _ScriptedStrategy`, prefixo `_`, de `tests/test_live_robots.py:34`) e concluiu "sem duplicata". As duas classes existem e têm semânticas DIFERENTES por desenho — exatamente como o **plano original já apontava** ("`ScriptedStrategy` (hoje duplicada com semânticas diferentes em `test_live_runtime.py` e `test_live_robots.py`)", linha 301). Isto não é redundância a remover, é um item do plano original que ficou de fora por engano — reaberto no Passo 1 (ver premissa 11). |

## 2b. Premissas a montante (regra 17)

| # | Premissa | Como verificar | Origem |
|---|----------|----------------|--------|
| 1 | `DipTop1Portfolio` (nome `portfolio_dip2_hw40`) é a campeã; hierarquia `BuyTheDip → DipTop1Hysteresis → PortfolioHysteresis → DipTop1Portfolio`; `on_bar` REAL usado é o de `DipTop1Hysteresis` (nem `PortfolioHysteresis` nem `DipTop1Portfolio` sobrescrevem `on_bar`) | `src/strategy/h3_hysteresis.py`, `src/strategy/portfolio_dip2_hw40.py`, `src/strategy/portfolio_satellite.py` (HEAD atual) | FEAT-003 (rename `portfolio_dip2_hw40.py` → família em `buy_the_dip.py`) |
| 2 | `_stateful_keys = ("_pending_rebalance",)` declarada na raiz (`BuyTheDip`), herdada sem redeclaração pela cadeia inteira | `src/strategy/buy_the_dip.py:24` | FEAT-003 |
| 3 | Campeã tem `satellite_pct=0.00` (herdado de `DipTop1Portfolio.__init__`) — satélites NUNCA se formam para ela; `test_strategy_champion.py` não precisa cobrir lógica de satélite (isso é `PortfolioHysteresis`, não a campeã) | `src/strategy/portfolio_dip2_hw40.py:22,30` | código existente |
| 4 | `live/runtime.py` NÃO tem fila `pending` em memória — intents ao vivo persistem em SQLite e expiram via `stale_intents`/regra 7 de verdade; o bug de reenfileiramento de `Exit` é isolado a `engine_portfolio.py` (backtest) | `src/live/runtime.py:724-810` (`execute_session` lê `store.pending_intents`, não fila em memória) | verificado nesta sessão |
| 5 | `entry_fill_mode` (`engine_portfolio.py:70`) não é passado por NENHUM chamador hoje (`Literal["open"]`, único valor possível) — o fix de `entries_filled` não muda nenhuma métrica reportada hoje, só corrige o contador para quando o parâmetro for usado | grep `entry_fill_mode` no repo inteiro → só a declaração e o uso interno | verificado nesta sessão |
| 6 | Nenhuma estratégia registrada passa `Enter(initial_stop=...)` custom — todas usam o default do engine (`config.stop_loss_pct=0.15`) — por isso `_DEFAULT_RISK_PCT` não muda o valor numérico de `r_multiple` de nenhum trade histórico | grep `initial_stop=` em `src/` → nenhum resultado | verificado nesta sessão |
| 7 | `engine.py` (ticker único) tem o MESMO comentário/comportamento "MFE/MAE usando close do dia" (`engine.py:195`) e a MESMA assimetria Exit-reenfileira/Enter-descarta (`engine.py:253` vs `291`) — ambos deliberados e simétricos entre os dois engines. Corrigir só `engine_portfolio.py` (Exit/Enter) sem tocar `engine.py` é aceitável porque só `engine_portfolio.py` está no escopo desta feature (`engine.py` não está listado no `EXEC-MAP`) e a campeã usa exclusivamente `engine_portfolio.py` — mas fica documentado como INCONSISTÊNCIA entre os dois engines após esta feature (risco registrado, não passo) | `src/backtest/engine.py:192-201,248-292` | verificado nesta sessão |
| 8 | `data/raw/*.parquet` está vazio/ausente nesta worktree — não é possível rodar uma verificação manual "capital final da campeã idêntico ao centavo antes/depois do fix" (scripts como `quick_ref_check.py` dependem desses arquivos) | `ls data/raw` → 0 arquivos | verificado nesta sessão |
| 9 | `_RecordingNotifier` em `test_live_notify.py:32` e `test_live_runtime.py:1125` são funcionalmente idênticas (mesmos 2 métodos, mesmo corpo) — consolidação é mecânica, sem risco de mudar comportamento de teste nenhum | leitura lado a lado nesta sessão | verificado nesta sessão |
| 10 | `Notifier` (`live/notify.py:93`) é `ABC` com `notify(level, source, message, payload=None)` — assinatura que `_RecordingNotifier` já implementa nos dois lugares | `src/live/notify.py:93-102` | código existente |
| 11 | `ScriptedStrategy` (`tests/test_live_runtime.py:44`, dict indexado por data) e `_ScriptedStrategy` (`tests/test_live_robots.py:34`, fila de listas de ação por chamada) são duas classes DIFERENTES com semânticas diferentes — não a mesma classe duplicada. O plano original (linha 301) já sabia disso e pediu consolidação em `tests/doubles.py` mesmo assim (sob nomes distintos, não fusão de comportamento). A conclusão da investigação original de que "não há duplicata" vinha de um grep que não bate com o prefixo `_` da segunda classe | leitura lado a lado nesta revisão: `tests/test_live_runtime.py:44-56` vs `tests/test_live_robots.py:34-53` | **verificado pelo plan-reviewer** — corrige premissa que a investigação original tinha errada |
| 12 | `data/raw/*.parquet` está **presente** no repositório principal (`C:\Users\Jeffe\Documents\study\meta\data\raw`, 77 tickers, incluindo os 7 do watchlist oficial + benchmark) — só está ausente NESTA worktree isolada (`../meta-FEAT-005`) porque `data/raw/*.parquet` é gitignored e `git worktree` só materializa arquivos versionados. A verificação byte-a-byte do capital da campeã ANTES/DEPOIS do Passo 3 (recomendada como opcional na versão original deste plano) é, portanto, **executável hoje** copiando os parquets do repo principal para a worktree — não depende de outro ambiente hipotético | `ls "C:\Users\Jeffe\Documents\study\meta\data\raw"` (77 arquivos) vs `../meta-FEAT-005/data/raw` (não existe); `.gitignore:6` → `data/raw/*.parquet` | **verificado pelo plan-reviewer** — eleva a verificação de "recomendada" para **obrigatória** (ver Passo 3 e Riscos, corrigidos) |
| 13 | `scripts/quick_ref_check.py` já existe e roda `run_portfolio_backtest` com os 7 tickers do watchlist oficial + `PortfolioHysteresis(confirm_months=2, redist_mode="pool")`, capital inicial R$1.000 — adaptável para `DipTop1Portfolio()` (a campeã real) trocando só a import e a linha de `strategy=` | `scripts/quick_ref_check.py:1-16` | **verificado pelo plan-reviewer** |

## 3. Passos

| # | Ação | Arquivo(s) | Como sei que funcionou |
|---|------|-----------|------------------------|
| 1 | Em `tests/doubles.py`: adicionar `_RecordingNotifier(Notifier)` (import `from live.notify import Notifier`), corpo idêntico ao das duas cópias atuais (`self.calls: list[tuple] = []`, `notify()` faz `append`). Em `tests/test_live_notify.py`: remover a classe local (linha 32) e importar `from tests.doubles import _RecordingNotifier`. Em `tests/test_live_runtime.py`: remover a classe local (linha 1125) e importar do mesmo lugar. **[Inserido pelo plan-reviewer — ver premissa 11]** No mesmo passo, adicionar a `tests/doubles.py` `ScriptedStrategy` (corpo idêntico ao de `tests/test_live_runtime.py:44-56`: dict indexado por data) e `ScriptedStrategySequence` (corpo idêntico ao de `_ScriptedStrategy` em `tests/test_live_robots.py:34-53`, só renomeada — fila de listas de ação, `calls`/`initialized_with` gravados). Em `tests/test_live_runtime.py`: remover a classe local e importar `ScriptedStrategy` de `tests.doubles`. Em `tests/test_live_robots.py`: remover `_ScriptedStrategy` (linha 34) e trocar as ~6 chamadas `_ScriptedStrategy(...)` por `ScriptedStrategySequence(...)` importado de `tests.doubles` — comportamento idêntico, só nome e local | `tests/doubles.py`, `tests/test_live_notify.py`, `tests/test_live_runtime.py`, `tests/test_live_robots.py` | `pytest -q tests/test_live_notify.py tests/test_live_runtime.py tests/test_live_robots.py` continua verde (mesma contagem de testes de antes — mudança é só de onde as classes moram e o nome de uma delas, nenhum teste muda de comportamento) |
| 2 | Criar `tests/test_strategy_champion.py` com `DipTop1Portfolio` importado direto (`from strategy.portfolio_dip2_hw40 import DipTop1Portfolio`), um helper local `_panel(prices, dates)` (mesmo padrão de `_fabricate_ohlcv` em `test_backtest_engine.py`, duplicado deliberadamente — arquivo isola sua própria fixture, sem acoplar a outro teste), e 9 funções: (a) `test_momentum_12_1_ranqueia_por_variacao_shift21_menos_shift252` — 2 tickers com trajetórias de preço distintas, confirma que `_scores` ordena pelo de maior variação entre `close.shift(21)` e `close.shift(252)`; (b) `test_hysteresis_nao_rotaciona_abaixo_do_limiar_15pct` — held com score positivo, rank-1 novo com score < `held*1.15`, `on_bar` devolve `[]`; (c) `test_hysteresis_rotaciona_quando_bate_o_limiar` — rank-1 novo com score >= `held*1.15`, devolve `Exit(held, ROTATION_OUT)`; (d) `test_hysteresis_score_negativo_do_held_usa_formula_alternativa` — held com score <= 0, confirma o ramal `held_score + abs(held_score)*hysteresis` (`h3_hysteresis.py:62`); (e) `test_dip_gate_2pct_sobre_maxima_40_bloqueia_entrada_sem_dip` — `dist_from_high > -0.02` não gera `Enter`; entrando abaixo de -2% gera; (f) `test_selic_tightening_dispara_saida_defensiva_para_todas_posicoes` — injeta `strategy._selic_tightening` manualmente após `initialize()` (sem precisar fabricar `data/raw/selic.parquet` real — isola a lógica de despacho do gate, não o cálculo de aperto de Selic, que é dado externo) — `on_bar` no month-end devolve `Exit(IBOV_DEFENSIVE)` para toda posição aberta, `_pending_rebalance` fica `False`; (g) `test_blackout_adia_rebalance_e_executa_no_primeiro_pregao_limpo` — month-end em 31/mar (dentro da janela heurística `earnings_calendar.py:27`) devolve `[]` e seta `_pending_rebalance=True`; PRÓXIMO pregão (não month-end, `_pending_rebalance` ainda `True`) executa a lógica de rotação normalmente; (h) `test_state_e_restore_do_pending_rebalance` — `strategy.state() == {"_pending_rebalance": True/False}`; `restore({"_pending_rebalance": "true"})` coage para bool `True` (mesmo teste de coerção de `strategy/base.py:170-174`, aqui aplicado à classe REAL da campeã, não a um dublê); (i) `test_rotaciona_e_nao_entra_quando_novo_rank1_sem_dip` — hysteresis passa (Exit do held emitido) MAS o novo rank-1 tem `dist_from_high > -dip_pct` (sem dip) — `on_bar` devolve só `[Exit(held)]`, SEM `Enter` — carteira vai para caixa | `tests/test_strategy_champion.py` (novo, ~9 funções) | RED antes de GREEN (T3): todas as 9 falham hoje com `ModuleNotFoundError`/`ImportError` na primeira execução (arquivo não existe) — depois de escrito, `pytest -q tests/test_strategy_champion.py` → 9 passed |
| 3 | Em `src/backtest/engine_portfolio.py`: (a) no laço `exits_p` (linha ~354-357), trocar `pending.append(act); continue` por só `continue` — comentário novo citando regra 4/7 e a simetria com `enters_p`; (b) no laço `enters_p` (linha ~459), mover `entries_filled += 1` para depois de `if not plan.is_feasible: continue` | `src/backtest/engine_portfolio.py` | **RED antes de GREEN**, 2 testes em `tests/test_engine_portfolio.py` (ver Passo 5, itens (b) e (g)) — escritos e confirmados FALHANDO nesta ordem: primeiro rodar os testes contra o código ATUAL (sem o fix) e confirmar que falham pelo motivo semântico certo (exit executa em D+2 em vez de nunca; `entries_skipped==0` mesmo com uma entrada inviável), só então aplicar o fix e confirmar GREEN |
| 3.5 | **[Inserido pelo plan-reviewer — OBRIGATÓRIO, não opcional; ver premissa 12 e Riscos]** Verificação empírica do impacto do Passo 3(a) no capital histórico da campeã, ANTES de considerar a feature concluída: (1) copiar de `C:\Users\Jeffe\Documents\study\meta\data\raw\` (repo principal, fora desta worktree) os parquets dos 7 tickers do watchlist oficial (`WEGE3_SA`, `BRAP4_SA`, `RADL3_SA`, `CSMG3_SA`, `EMAE4_SA`, `KEPL3_SA`, `CXSE3_SA`) + o benchmark (`BOVA11_SA` ou `^BVSP`, conforme `core.config.BENCHMARK`) para `data/raw/` desta worktree; (2) adaptar `scripts/quick_ref_check.py` trocando `PortfolioHysteresis(confirm_months=2, redist_mode="pool")` por `DipTop1Portfolio()` (import de `strategy.portfolio_dip2_hw40`); (3) rodar o script ANTES de aplicar o Passo 3(a) (código atual, no commit anterior ou via `git stash`) e registrar `final_capital`; (4) aplicar o Passo 3(a); (5) rodar o script de novo e registrar `final_capital`; (6) comparar os dois números | dados copiados do repo principal (só leitura, nenhuma escrita fora desta worktree) + `scripts/quick_ref_check.py` adaptado | Os dois `final_capital` são **idênticos** → confirma a premissa de que o universo real (watchlist, 16 anos) nunca dispara o gap que o bug explora, registrar o número no Registro de execução. Se **divergirem**, a feature NÃO pode ser considerada concluída silenciosamente — aciona o Gatilho de escalação (a) da seção 5: parar e apresentar a divergência ao usuário antes de prosseguir, porque significaria que o fix muda um número já usado em decisões de watchlist/ranking (ver memórias `watchlist_champions.md`/`ranking_criterion.md`) |
| 4 | Em `src/core/models.py`: adicionar `_DEFAULT_RISK_PCT = 0.15` (constante de módulo, acima da classe `Trade`, com a docstring descrita na seção 2); trocar `risk_per_share = self.entry_price * 0.15` por `risk_per_share = self.entry_price * _DEFAULT_RISK_PCT` | `src/core/models.py` | 2 testes em `tests/test_engine_portfolio.py` (Passo 5, item (h)): `_DEFAULT_RISK_PCT == BacktestConfig().stop_loss_pct` (trava de coerência) + `r_multiple` calculado com valores conhecidos bate com a fórmula documentada — não é RED→GREEN (não há bug funcional, só nomeação), roda GREEN direto |
| 5 | Criar `tests/test_engine_portfolio.py` com um `_StubStrategy` local (mesmo padrão de `test_backtest_engine.py`, devolve `Enter`/`Exit` em datas fixas via `on_bar`) e um helper `_panel`. Funções: (a) `test_anti_look_ahead_sinal_do_close_executa_no_open_do_dia_seguinte` — `Enter` decidido no close de D executa exatamente no open de D+1 (nunca D, nunca D+2); (b) `test_exit_sem_dado_e_descartado_nao_executa_tarde` — ticker com gap de 1 dia logo após o `Exit` ser decidido: ANTES do fix (Passo 3a), `trade.exit_reason==ROTATION_OUT` e `exit_date==D+2` (executou tarde); DEPOIS do fix, a posição só fecha no fechamento forçado de fim de janela (`exit_reason==MANUAL`, `exit_date==`última data da janela) — nunca no dia do gap; (c) `test_stop_intrabar_executa_em_min_open_stop_no_gap_down` — dia com `open < stop < high`, `low <= stop`: `exec_price` (antes do slippage) é `min(open, stop)`, não `stop` puro; (d) `test_ordem_das_operacoes_na_barra` — cenário com stop E entrada agendada na MESMA barra: confirma que o stop libera caixa ANTES da entrada tentar usar esse caixa (sizing da entrada reflete o caixa PÓS-stop, não pré-stop); (e) `test_sizing_com_size_hint_1_0_usa_caixa_total_nao_dividido_por_slots` — `max_concurrent_positions=5`, uma única posição com `size_hint=1.0` consome o caixa inteiro (não `cash/5`); (f) `test_saque_simulado_executado_no_open_seguinte_com_taxas` — `FloorSkim` gera saque no close, executa no open seguinte, `BacktestResult.withdrawals` tem 1 `WithdrawalEvent` com `requested`/`executed`/`fees_paid` coerentes e `cash` reduzido; (g) `test_entries_filled_so_conta_entrada_realmente_preenchida` — 2 tentativas de `Enter`, uma com caixa suficiente e outra forçada inviável (caixa insuficiente para 1 lote) via `entry_fill_mode="debug"` (bypassa o `Literal` só em runtime, permitido pois Python não impõe `Literal`): `entries_attempted==2`, `entries_filled==1`, `entries_skipped==1`; (h) `test_r_multiple_usa_constante_documentada_e_bate_com_config` — `core.models._DEFAULT_RISK_PCT == BacktestConfig().stop_loss_pct` e um `Trade` manual com preços conhecidos bate a fórmula; (i) `test_mfe_mae_usa_apenas_close_nunca_high_low` — bar sintético com `high`/`low` bem distantes do `close`: `max_favorable_excursion`/`max_adverse_excursion` do trade refletem só variação de `close`, documentando (não mudando) o comportamento atual — mesmo padrão do comentário `"(1) MFE/MAE usando close do dia"` já explícito em `engine.py:195`, aqui travado por teste pela primeira vez para `engine_portfolio.py` | `tests/test_engine_portfolio.py` (novo, ~9 funções) | RED antes de GREEN nas partes (b) e (g) (dependem do Passo 3); GREEN direto nas partes (a),(c),(d),(e),(f),(h),(i) (comportamento já correto ou só documentação) — `pytest -q tests/test_engine_portfolio.py` → 9 passed no final |
| 6 | Em `tests/test_live_runtime.py`, adicionar 4 funções na seção final (nova região `# ---------- FEAT-005: cobertura de menores -------------------------`) — **[CORRIGIDO PELO PLAN-REVIEWER: item (b) da versão original (`test_restore_robot_state_restaura_risk_guard`) removido — REDUNDANTE. Já coberto por `test_disjuntor_dispara_em_crash_intradia_e_estado_sobrevive_a_restart` (`tests/test_live_runtime.py:1699`, FEAT-003), que exercita exatamente este cenário via `rt2.reconcile_pending_fills()` → `_restore_robot_state()` → `assert rt2.risk_guard.is_frozen is True` num `LiveRuntime`/`CircuitBreaker` novos. Ver premissa/NO-OP corrigidos na seção 2a]**: (a) `test_reconcile_broker_cash_apos_saque_confirmado_nao_vira_deposito` — `confirm_withdrawal` reduz `account.cash`; broker fake (`_FakeCashBroker`, já existe no arquivo) devolve o MESMO saldo já reduzido; `reconcile_broker_cash()` acha `diferenca≈0`, nenhuma linha em `live_deposits`; (b) `test_execute_session_chamada_duas_vezes_e_idempotente` — mesma sessão, chama `execute_session` duas vezes seguidas: segunda chamada não gera ordem/fill duplicado (`done["entradas"]==0`/`done["saidas"]==0` na segunda, `store.open_orders` sem duplicata); (c) `test_entrada_inviavel_por_caixa_insuficiente_notifica` — intent de `ENTER` com caixa menor que 1 lote, confirma evento `warn`/"nao cobre um lote" gravado (`_log` de `runtime.py:951`, hoje sem asserção); (d) `test_saque_multiplo_pendente_simultaneo_loga_invariante_quebrada` — corrompe `policy_state` manualmente para ter 2 intents `WITHDRAW` `PENDING` ao mesmo tempo, confirma evento `error`/"invariante quebrada" (`_log` de `runtime.py:1062`, hoje sem asserção) | `tests/test_live_runtime.py` | RED antes de GREEN só onde há comportamento a provar pela primeira vez (todas as 4 são cobertura pura, sem mudança de produção em `runtime.py` — cada uma é validada contra o código ATUAL antes de escrita, confirmando que passa; não há uma fase "falha, depois corrige" porque não há bug aqui, só ausência de asserção) — `pytest -q tests/test_live_runtime.py` → +4 testes, todos passed |
| 7 | Em `scripts/debug_sim.py` (linha 17) e `scripts/screenshot_sim.py` (linha 19): trocar `f"http://127.0.0.1:8765/strategies/sim/{sim_id}"` por `f"http://127.0.0.1:8765/sim/{sim_id}"`. **[Inserido pelo plan-reviewer]** Em `scripts/screenshot_strategies.py` (linha 30): trocar `page.wait_for_url("**/strategies/sim/**", timeout=15000)` por `page.wait_for_url("**/sim/**", timeout=15000)` — mesmo defeito (rota morta), pego pelo grep completo desta revisão, não pela investigação original | `scripts/debug_sim.py`, `scripts/screenshot_sim.py`, `scripts/screenshot_strategies.py` | **Estado observável** (sem runner de pytest para scripts Playwright manuais): `grep -n "127.0.0.1:8765\|strategies/sim" scripts/debug_sim.py scripts/screenshot_sim.py scripts/screenshot_strategies.py` não mostra mais `strategies/sim`, batendo com a rota real `@app.get("/sim/{sim_id}")` (`src/dashboard/app.py:564`) e o redirect `RedirectResponse(url=f"/sim/{sim.id}", ...)` (`src/dashboard/app.py:298`) |
| 8 | Rodar a prova (§4) inteira. `git diff --stat plan/blindagem-operacao-real...HEAD` mostra exatamente os arquivos das seções "Escreve" (§2) — nenhum a mais, `tests/test_live_withdrawal_advice.py` e `tests/test_live_account_mode.py` **NÃO** devem aparecer (correção de escopo documentada) | — | `../meta/.venv/Scripts/python.exe -m pytest -q` → exit 0, baseline 346 (FEAT-004) + ~9 (`test_strategy_champion.py`) + ~9 (`test_engine_portfolio.py`) + 4 (`test_live_runtime.py`, corrigido — item (b) removido, ver Passo 6) = **~368**, nenhuma contagem líquida perdida em `test_live_notify.py`/`test_live_robots.py` (consolidação dos Passos 1 é neutra em contagem) |

> **Ordem executável.** 1 (doubles) é independente, pode rodar em qualquer
> ponto antes do 8. 2 (`test_strategy_champion.py`) é independente de 3/4/5
> (arquivo/módulo diferente). 3 (fix `engine_portfolio.py`) antes de 5
> (os testes (b)/(g) de `test_engine_portfolio.py` precisam do fix para
> fechar GREEN — mas são ESCRITOS e confirmados RED antes do fix, então na
> prática 3 e 5 andam entrelaçados: escreve o teste RED, aplica o fix,
> confirma GREEN, seguindo a MESMA disciplina de FEAT-004). **3.5 (verificação
> obrigatória do capital da campeã, inserida pelo plan-reviewer) roda
> IMEDIATAMENTE ANTES e IMEDIATAMENTE DEPOIS do fix do Passo 3(a) —
> intercalada com ele, não depois de tudo, senão o "antes" já não existe
> mais para comparar.** 4 (fix `core/models.py`) antes da parte (h) de 5. 6
> é independente de 2-5 (arquivo diferente, sem dependência de dado). 7 é
> totalmente independente. 8 fecha.

## 4. Prova de conclusão (uma só)

**Origem:** ⬜ comando/teste que já existe ☑ asserção nova em teste existente
(Passo 6, 4 funções em `test_live_runtime.py`) + teste novo (Passos 2 e 5,
dois arquivos novos — únicos caminhos possíveis: `strategy/` e
`engine_portfolio.py` nunca tiveram teste, não há o que reusar) ⬜ estado
observável (só o Passo 7, script de debug, que fica FORA desta prova única
por não ter runner de pytest — ver nota abaixo)

```
../meta/.venv/Scripts/python.exe -m pytest -q
```

> **Prova é a suíte inteira**, mesmo precedente de FEAT-001/003/004: o
> blast radius passa dos arquivos novos — `core/models.py` é importado por
> TODO trade em TODA estratégia (`r_multiple`/`_DEFAULT_RISK_PCT`),
> `engine_portfolio.py` é o motor da campeã, e a consolidação de
> `_RecordingNotifier` toca dois arquivos de teste existentes
> (`test_live_notify.py`, `test_live_runtime.py`) que precisam continuar
> verdes.
>
> **O Passo 7 (URL morta em `debug_sim.py`/`screenshot_sim.py`) fica fora da
> prova de pytest** — são scripts de debug manual via Playwright contra um
> servidor rodando, sem suite automatizada. A verificação é o `grep` citado
> no Passo 7, registrado separadamente no Registro de execução.
>
> Nenhum harness/fixture pesado novo: `test_strategy_champion.py` e
> `test_engine_portfolio.py` reusam o padrão já estabelecido em
> `test_backtest_engine.py` (`_StubStrategy`/`_fabricate_ohlcv`, adaptado
> localmente em cada arquivo novo, sem import cruzado entre arquivos de
> teste).

**Teste de falsificação (obrigatório) — cenário de feature quebrada × teste que o pega:**

| Cenário quebrado | Teste que falha |
|------------------|-----------------|
| Momentum 12-1 ranqueia errado (ex.: usa `shift(0)` em vez de `shift(21)`) | `test_momentum_12_1_ranqueia_por_variacao_shift21_menos_shift252` |
| Histerese rotaciona sem bater os 15% (ou nunca rotaciona) | `test_hysteresis_nao_rotaciona_abaixo_do_limiar_15pct` + `test_hysteresis_rotaciona_quando_bate_o_limiar` |
| Fórmula de score negativo do held quebra (ex.: usa a mesma fórmula do score positivo) | `test_hysteresis_score_negativo_do_held_usa_formula_alternativa` |
| Gate de dip 2%/40 pregões deixa de bloquear entrada sem dip | `test_dip_gate_2pct_sobre_maxima_40_bloqueia_entrada_sem_dip` |
| Gate de Selic para de sair defensivamente | `test_selic_tightening_dispara_saida_defensiva_para_todas_posicoes` |
| Blackout deixa de adiar, ou nunca executa o rebalance adiado | `test_blackout_adia_rebalance_e_executa_no_primeiro_pregao_limpo` |
| `state()`/`restore()` de `_pending_rebalance` perde o valor ou o tipo | `test_state_e_restore_do_pending_rebalance` |
| "Rotaciona e não entra" volta a forçar entrada sem dip (ou nunca sai do held) | `test_rotaciona_e_nao_entra_quando_novo_rank1_sem_dip` |
| `Enter`/`Exit` decidido no close executa fora do open de D+1 | `test_anti_look_ahead_sinal_do_close_executa_no_open_do_dia_seguinte` |
| `Exit` volta a reenfileirar sobre dado faltante (executa tarde) | `test_exit_sem_dado_e_descartado_nao_executa_tarde` |
| Stop intrabar deixa de usar `min(open, stop)` num gap down | `test_stop_intrabar_executa_em_min_open_stop_no_gap_down` |
| Ordem das operações na barra inverte (entrada não vê caixa liberado pelo stop) | `test_ordem_das_operacoes_na_barra` |
| `size_hint=1.0` volta a dividir por slots livres | `test_sizing_com_size_hint_1_0_usa_caixa_total_nao_dividido_por_slots` |
| Saque simulado do engine para de registrar `WithdrawalEvent`/taxas | `test_saque_simulado_executado_no_open_seguinte_com_taxas` |
| `entries_filled` volta a contar entrada inviável como preenchida | `test_entries_filled_so_conta_entrada_realmente_preenchida` |
| `_DEFAULT_RISK_PCT` diverge de `BacktestConfig.stop_loss_pct` (drift silencioso) | `test_r_multiple_usa_constante_documentada_e_bate_com_config` |
| MFE/MAE passam a usar high/low sem decisão explícita (mudança silenciosa) | `test_mfe_mae_usa_apenas_close_nunca_high_low` |
| Conciliação de caixa MT5 volta a confundir saque confirmado com depósito | `test_reconcile_broker_cash_apos_saque_confirmado_nao_vira_deposito` |
| `execute_session` chamado 2x duplica ordem/fill | `test_execute_session_chamada_duas_vezes_e_idempotente` |
| Entrada inviável por caixa para de notificar | `test_entrada_inviavel_por_caixa_insuficiente_notifica` |
| Duas recomendações de saque `PENDING` simultâneas passam batido | `test_saque_multiplo_pendente_simultaneo_loga_invariante_quebrada` |

**RED antes de GREEN:** obrigatório (T3). Confirmado RED nas partes com
correção de produção real: Passo 3a (`test_exit_sem_dado_e_descartado_nao_executa_tarde`
falha hoje com `exit_reason==ROTATION_OUT`/`exit_date==D+2` em vez de
`MANUAL`/fim-de-janela) e Passo 3b (`test_entries_filled_so_conta_entrada_realmente_preenchida`
falha hoje com `entries_skipped==0`). As demais ~22 funções são cobertura
pura sobre comportamento já correto (`ModuleNotFoundError` nos dois arquivos
novos antes de existirem conta como RED trivial, mesmo padrão aceito em
FEAT-004 para contratos novos) — nenhuma delas exige mudança de produção.

**Se a prova falhar:** nenhuma migração de schema nesta feature. Reverter é
`git checkout -- .` na worktree. Falha num teste que era verde ANTES desta
feature (ex.: `test_live_notify.py` depois da consolidação do Passo 1, ou
qualquer teste de `test_live_runtime.py` que dependia da classe local
`_RecordingNotifier` por um detalhe de import) é sinal de que a
consolidação do Passo 1 não foi aplicada nos dois arquivos junto — não de
que o teste esteja errado.

## 5. Riscos e gatilhos de escalação

### Riscos ATIVOS (mitigados no plano)

- **Fix de `Exit`/`Enter` toca o motor de referência (`engine_portfolio.py`)
  que decide os números do backtest de referência da campeã** (`data/raw/`
  vazio NESTA worktree isolada, ver premissa 8 — mas presente no repo
  principal, ver premissa 12). **CORREÇÃO PLAN-REVIEWER:** a versão original
  deste risco citava "premissa 6/7" como mitigação — **citação errada**:
  premissa 6 é sobre `Enter.initial_stop` customizado e premissa 7 é sobre a
  simetria com `engine.py`, nenhuma das duas fala de gaps no watchlist. A
  evidência real de que o watchlist oficial (7 tickers) está sem gaps é a
  memória `yfinance_gap_filling.md` (auditoria de 2026-08-17, um dia antes
  desta feature) — não verificada de novo nesta sessão porque `data/raw`
  está ausente nesta worktree. Depender só de uma memória de outra sessão
  para um fix que toca o motor de referência da campeã não é rigor
  suficiente quando a verificação real é barata e está ao alcance: **o
  Passo 3.5 (inserido por esta revisão) torna essa comparação OBRIGATÓRIA,
  não recomendada** — os parquets dos 7 tickers + benchmark existem no
  repo principal (`C:\Users\Jeffe\Documents\study\meta\data\raw`, fora
  desta worktree isolada) e podem ser copiados sem nenhuma chamada de rede
  (ver premissa 12). Se o Passo 3.5 confirmar `final_capital` idêntico
  antes/depois, o risco fica mitigado por PROVA, não por inferência. Se
  divergir, aciona o Gatilho de escalação (a) abaixo — não é opcional
  seguir em frente com uma divergência não explicada.
- **Inconsistência nova entre `engine.py` e `engine_portfolio.py`** — depois
  desta feature, só o engine de portfólio descarta `Exit` sem dado; o de
  ticker único continua reenfileirando (`engine.py:253`). Aceito: `engine.py`
  não está no `EXEC-MAP` desta feature (nenhuma estratégia candidata hoje
  usa `run_backtest` de ticker único para produção — é usado por
  experimentos antigos/históricos, ver `strategy/discovery.py`), e corrigir
  os dois exigiria dobrar o escopo de testes. Registrado para decisão futura
  do usuário (uma FEAT-006 focada em consistência entre engines, se
  desejado).
- **`entry_fill_mode="debug"` no teste (g) do Passo 5 bypassa o `Literal`
  em runtime** — Python não impõe `Literal` fora de type-checkers; é uma
  forma legítima de exercitar código que hoje é morto por falta de
  chamador, sem inventar um chamador novo em produção. Se o code-reviewer
  preferir, alternativa é expandir o `Literal` para incluir um segundo
  valor real (ex. `"debug_metrics"`) — decisão de nomenclatura, não de
  comportamento; deixada para o gate se for levantada.

### Riscos CONHECIDOS (aceitos, sem passo no plano)

- **MFE/MAE calculado só por `close`** (`_DEFAULT_RISK_PCT`-adjacente, mas
  item distinto) — comportamento DELIBERADO e SIMÉTRICO entre `engine.py` e
  `engine_portfolio.py` (mesmo comentário nos dois). Não é corrigido nesta
  feature: mudar para `high`/`low` alteraria `max_favorable_excursion`/
  `max_adverse_excursion` de TODO trade histórico do sistema — decisão de
  produto/precisão analítica que extrapola "menor", e exigiria tocar
  `engine.py` (fora do escopo declarado desta feature) para os dois
  engines continuarem consistentes. Documentado e travado por teste
  (`test_mfe_mae_usa_apenas_close_nunca_high_low`) para a mudança, se algum
  dia acontecer, ser deliberada e não silenciosa.
- **`r_multiple` continua impreciso para uma estratégia hipotética que
  passe `Enter.initial_stop` customizado** — nenhuma registrada hoje faz
  isso (premissa 6), mas se uma passar a fazer, o número fica errado até
  `Trade` ganhar um campo de risco real (mudança maior, fora de escopo).
- **`entry_fill_mode` continua sem nenhum chamador real** — o fix do Passo
  3b só evita que o contador MINTA quando/se alguém um dia passar um valor
  diferente de `"open"`; não há plano para usar o parâmetro nesta feature.

### Gatilhos de escalação

Escalarei se: **(a)** o Passo 3.5 (obrigatório, ver premissa 12) mostrar
QUALQUER divergência no `final_capital` da campeã entre antes/depois do
fix do Passo 3(a) — sinal de que o watchlist real tem (ou passou a ter) um
gap que o bug explora, e o fix mudaria um número já usado nas decisões de
watchlist/ranking deste projeto (`watchlist_champions.md`/
`ranking_criterion.md`) sem aviso; **(b)** ~~o plan-reviewer discordar da
correção de escopo que elimina `test_live_withdrawal_advice.py`/
`test_live_account_mode.py` como arquivos~~ — **RESOLVIDO nesta revisão:**
o plan-reviewer conferiu por amostragem os 9 testes citados como
equivalentes (linhas exatas em `test_live_runtime.py`/`test_run_live_cli.py`/
`test_live_control.py`) e confirma que a correção de escopo é válida, não
está evitando trabalho necessário — gatilho encerrado, não bloqueia; **(c)**
algum teste hoje verde quebrar por causa da consolidação de
`_RecordingNotifier`/`ScriptedStrategy`/`_ScriptedStrategy` (Passo 1, este
último ampliado pelo plan-reviewer — ver premissa 11) por um motivo não
previsto nas premissas 9/11; **(d)** os ~22 testes novos (9+9+4, após a
remoção do item redundante do Passo 6) não fecharem RED→GREEN em 2 rodadas
de pre-gate; **(e)** o Passo 3.5 (verificação obrigatória do capital da
campeã, inserida pelo plan-reviewer) não puder ser executado por algum
motivo não previsto (ex.: os 7 parquets do watchlist não existirem mais no
repo principal) — nesse caso a feature NÃO pode fechar como se a verificação
tivesse sido feita; o gap fica registrado e escalado, não assumido como
"provavelmente ok".

---

## Correções do plan-reviewer

Revisão feita com leitura direta do código (`engine_portfolio.py`,
`core/models.py`, `engine.py`, `strategy/buy_the_dip.py`,
`strategy/h3_hysteresis.py`, `strategy/portfolio_dip2_hw40.py`,
`strategy/portfolio_satellite.py`, `live/runtime.py`, `core/config.py`,
`backtest/sizing.py`, `market_data/loader.py`, `dashboard/app.py`,
`scripts/quick_ref_check.py`, `scripts/screenshot_strategies.py`,
`tests/test_live_runtime.py`, `tests/test_live_robots.py`,
`tests/test_live_notify.py`, `tests/test_backtest_engine.py`), do
`AGENTS.md`, do plano original (linhas 275-309) e do `EXEC-MAP.md`.

1. **[Seção 1, "Achado central"]** A afirmação de que "o Lote 5 original
   suspeitava que `Exit` sem dado hoje NÃO reenfileira" e que "o código real
   faz o OPOSTO do que o texto do plano descreve" é **falsa** — o plano
   original (linhas 307-309) já descrevia a direção correta do bug (`Exit`
   reenfileira, `Enter` descarta) e já a classificava como violação da regra
   7. Corrigido para deixar claro que esta investigação CONFIRMA o achado
   original com linhas exatas, sem inventar uma contradição que não existe.
   Os dois bugs de produção em si (assimetria Exit/Enter, `entries_filled`
   contado cedo demais) foram **confirmados como reais** por leitura direta
   — os dois fixes propostos estão corretos e na direção certa (descartar >
   reenfileirar, por regra 4/7; contar só entrada de fato preenchida).
2. **[Passo 3 → novo Passo 3.5, OBRIGATÓRIO]** A versão original tratava a
   verificação "capital final da campeã idêntico ao centavo antes/depois do
   fix" como recomendação opcional, alegando que `data/raw/` não está
   disponível em nenhum ambiente acessível. **Falso**: os 77 parquets
   (incluindo os 7 do watchlist oficial + benchmark) existem no repo
   principal (`C:\Users\Jeffe\Documents\study\meta\data\raw`), só ausentes
   NESTA worktree isolada (gitignored, `git worktree` não materializa). A
   comparação é barata (7 arquivos, um script já existente adaptado) e
   decide exatamente a pergunta que mais importa nesta feature: se o fix
   muda um número já usado nas decisões de watchlist/ranking do projeto.
   Promovida a passo obrigatório com instruções concretas (copiar os
   parquets, adaptar `quick_ref_check.py` para `DipTop1Portfolio()`, rodar
   antes/depois, comparar). Sem essa correção, um fix "correto" poderia
   mudar os números do campeão em silêncio — exatamente o risco que o
   usuário pediu para não deixar passar.
3. **[Riscos]** Citação quebrada corrigida: a mitigação apontava para
   "premissa 6/7", que não falam de gaps no watchlist (falam de
   `initial_stop` customizado e da simetria com `engine.py`). Substituída
   por referência à nova premissa 12 e ao Passo 3.5.
4. **[Passo 6, item (b) removido]** `test_restore_robot_state_restaura_risk_guard`
   era redundante — `test_disjuntor_dispara_em_crash_intradia_e_estado_sobrevive_a_restart`
   (`tests/test_live_runtime.py:1699`, já existente, de FEAT-003) já exercita
   exatamente esse cenário via `reconcile_pending_fills()` →
   `_restore_robot_state()`, com um `LiveRuntime`/`CircuitBreaker` NOVOS
   confirmando `is_frozen is True` após restauração. Passo 6 passa de 5 para
   4 funções; contagem total da prova ajustada de ~369 para ~368.
5. **[Passo 1 ampliado + novo arquivo `tests/test_live_robots.py`]** A
   investigação original concluiu, incorretamente, que `ScriptedStrategy`
   não tinha duplicata (grep estreito por `class ScriptedStrategy` não bate
   com `class _ScriptedStrategy`, prefixo `_`, de `tests/test_live_robots.py:34`).
   As duas classes existem, com semânticas diferentes, exatamente como o
   **plano original já apontava** — item do plano original que tinha ficado
   de fora por engano, não redundância. Reaberto: Passo 1 agora também
   consolida as duas em `tests/doubles.py` (nomes distintos:
   `ScriptedStrategy` e `ScriptedStrategySequence`), com import atualizado
   em `tests/test_live_robots.py`.
6. **[Passo 7 ampliado]** `scripts/screenshot_strategies.py:30` tem o mesmo
   defeito de rota morta (`page.wait_for_url("**/strategies/sim/**")`, que
   nunca bate porque o redirect real é `/sim/{sim.id}`) que os dois scripts
   já cobertos pelo plano — não pego pelo grep original. Adicionado ao Passo
   7 e à lista de arquivos "Escreve".

**Natureza das correções:** SUBSTANTIVAS — a correção 2 insere um passo novo
com efeito real (decide se o fix é seguro para os números do campeão, não
só estilo/nomenclatura), a correção 4 remove um passo de prova (muda a
contagem da prova de conclusão), e a correção 5 reabre escopo que tinha sido
fechado por engano. As correções 1, 3 e 6 são mais próximas de pontuais
(framing/citação/arquivo esquecido), mas o conjunto como um todo altera a
prova de conclusão e a lista de arquivos — tratar o lote de correções como
substantivo.

**Observações não-bloqueantes:** o `test_execute_session_chamada_duas_vezes_e_idempotente`
(Passo 6) e o `test_reconcile_broker_cash_apos_saque_confirmado_nao_vira_deposito`
(Passo 6) são cobertura genuinamente nova (confirmado por grep — nenhum teste
hoje combina esses dois cenários); nenhuma correção necessária aí. O restante
dos NO-OPs (stop intraday, disjuntor intra-dia, `data_is_ready`, ramo
`investment` de `_restore_robot_state`, 4 dos 5 cenários de saque, os 4
cenários de `test_live_account_mode.py`) foi conferido por amostragem linha a
linha e bate com o que o plano afirma — não é trabalho evitado.

**Tier:** mantido T3 (correto — toca `engine_portfolio.py`/`core/models.py`,
motor de referência do backtest da campeã, e schema/contrato não muda, mas o
risco de mudar métricas históricas justifica T3 mesmo sem migração).

**Próxima ação:** feature-agent re-lê o plano corrigido (em particular o
Passo 3.5, obrigatório e intercalado com o Passo 3, e o Passo 1/6/7
ampliados) e executa — sem nova revisão.

---

## Registro de execução

**Status:** executado — todos os 8 passos concluídos na ordem do plano
corrigido, commits atômicos por passo em
`feat/blindagem-operacao-real-FEAT-005` (worktree `../meta-FEAT-005`).

### Passo 1 — consolidação de duplos de teste
`_RecordingNotifier` (antes duplicada em `test_live_notify.py:32` e
`test_live_runtime.py:1125`) e `ScriptedStrategy`/`ScriptedStrategySequence`
(renomeada de `_ScriptedStrategy`, `test_live_robots.py:34`) movidas para
`tests/doubles.py`. `pytest -q tests/test_live_notify.py tests/test_live_runtime.py
tests/test_live_robots.py` → **88 passed** (mesma contagem de antes, nenhum
comportamento mudou). Imports não usados removidos (`Notifier`, `Strategy`
em `test_live_runtime.py`).

### Passo 2 — `tests/test_strategy_champion.py` (novo, 9 funções)
RED trivial (arquivo não existia) → GREEN direto nas 9 (nenhuma delas
depende de fix de produção — cobertura pura da campeã real, `DipTop1Portfolio`).
`pytest -q tests/test_strategy_champion.py` → **9 passed**. Cobre: score
momentum 12-1 (fórmula independente, calculada à mão a partir dos preços
crus, não reaproveitando o cálculo do código), histerese 15% (rotaciona/não
rotaciona/ramo score negativo — este último com valores desenhados para
DIVERGIR entre a fórmula correta e a fórmula errada, ver comentário no
teste), gate de dip 2%/janela 40, saída defensiva por Selic, blackout com
execução no próximo pregão limpo, `state()`/`restore()` de
`_pending_rebalance`, e "rotaciona mas não entra sem dip".

### Passo 3.5 — verificação empírica do capital da campeã (obrigatória, inserida pelo plan-reviewer)
Parquets dos 7 tickers do watchlist oficial + benchmark (`^BVSP` →
`_BVSP.parquet`) copiados do repo principal
(`C:\Users\Jeffe\Documents\study\meta\data\raw`) para
`../meta-FEAT-005/data/raw` (gitignored, não versionado, script de
verificação rodado a partir de fora do repo — scratchpad — para não sujar o
escopo do diff).

**Achado colateral não previsto pelo plano:** a última linha (`2026-08-18`)
de **todos os 8 parquets copiados** vinha com `open=high=low=volume=0` e só
`close` preenchido — artefato do pipeline de dados para o pregão do dia
corrente (dado ainda incompleto no momento da cópia), não um bug desta
feature. Rodar o comparativo até essa data literal produzia um trade
fantasma (`CSMG3.SA`, stop a preço 0.0, -100% de perda) que mascarava
qualquer efeito real do fix. Corrigido usando `end="2026-08-17"` (último
pregão com dado completo em todos os tickers) — mudança registrada aqui
como desvio, não uma alteração de escopo do fix em si.

Resultado com `DipTop1Portfolio()` real, 7 tickers, R$1.000 iniciais,
`2010-01-01` → `2026-08-17`:

| | `final_capital` | trades |
|---|---|---|
| **ANTES** do fix (Passo 3a) | R$ 73.701,3877 | 33 |
| **DEPOIS** do fix (Passo 3a) | R$ 73.701,3877 | 33 |

**IDÊNTICO ao centavo (10 casas decimais coincidentes).** O watchlist real
nunca dispara o gap de dado que o bug do Exit reenfileirado explorava —
confirma a mitigação do risco por PROVA, não por inferência de memória
antiga. Nenhum gatilho de escalação acionado (não houve divergência).

### Passos 3/4 — fix de produção (`engine_portfolio.py`, `core/models.py`)
`tests/test_engine_portfolio.py` escrito ANTES do fix e rodado contra o
código do HEAD anterior (commit `c1cf616`/`359d301`, antes do fix):

```
tests\test_engine_portfolio.py .F....FF.                                 [100%]
FAILED tests/test_engine_portfolio.py::test_exit_sem_dado_e_descartado_nao_executa_tarde
  AssertionError: assert <ExitReason.ROTATION_OUT> == <ExitReason.MANUAL>
FAILED tests/test_engine_portfolio.py::test_entries_filled_so_conta_entrada_realmente_preenchida
  assert 2 == 1   (entries_filled contava a entrada inviável)
FAILED tests/test_engine_portfolio.py::test_r_multiple_usa_constante_documentada_e_bate_com_config
  ImportError: cannot import name '_DEFAULT_RISK_PCT' from 'core.models'
3 failed, 6 passed in 0.82s
```

Após aplicar o fix (Passo 3a: `Exit` sem dado descarta em vez de
reenfileirar; Passo 3b: `entries_filled += 1` movido para depois do teste
de viabilidade; Passo 4: `_DEFAULT_RISK_PCT` nomeando o `0.15` de
`Trade.r_multiple`):

```
tests\test_engine_portfolio.py .........                                 [100%]
9 passed in 0.59s
```

RED→GREEN real confirmado para as 3 partes que dependiam do fix; as outras
6 funções já passavam antes (cobertura pura de comportamento correto
preexistente: anti-look-ahead D+1, stop intrabar em gap down, ordem das
operações na barra — stop libera caixa antes da entrada usar, sizing
`size_hint=1.0`, saque simulado via `FloorSkim` com taxas reais, MFE/MAE
usando só `close`).

### Passo 6 — 4 funções novas em `tests/test_live_runtime.py`
Sem fix de produção (cobertura pura). `pytest -q tests/test_live_runtime.py`
→ **53 passed** (49 pré-existentes + 4 novas: conciliação de caixa MT5 após
saque confirmado não vira depósito; `execute_session` chamado 2x é
idempotente; entrada inviável por caixa insuficiente notifica; 2 intents
WITHDRAW `PENDING` simultâneas loga o `error` "invariante quebrada").

### Passo 7 — URL morta `/strategies/sim/` em 3 scripts de debug
`grep -n "127.0.0.1:8765\|strategies/sim" scripts/debug_sim.py
scripts/screenshot_sim.py scripts/screenshot_strategies.py` → nenhuma
ocorrência de `strategies/sim` remanescente (rota real confirmada:
`/sim/{sim_id}` em `dashboard/app.py:564`, redirect real em
`dashboard/app.py:298`). Terceiro arquivo (`screenshot_strategies.py`,
achado do plan-reviewer) também corrigido.

### Passo 8 — PRE-GATE

| # | Checagem | Resultado |
|---|----------|-----------|
| 1 | Prova de conclusão: `../meta/.venv/Scripts/python.exe -m pytest -q` | **368 passed, 1 warning, 11.98s** — exit 0. Bate exatamente a previsão do plano (346 baseline FEAT-004 + 9 + 9 + 4 = 368) |
| 2 | Lint | N/A — nenhum linter (ruff/flake8/pylint) configurado no repo (`pyproject.toml`/`requirements.txt` conferidos) |
| 3 | Typecheck | N/A — nenhum mypy/typecheck configurado no repo |
| 4 | Escopo: `git diff --name-only plan/blindagem-operacao-real...HEAD` | 11 arquivos, **idêntico** à lista "Escreve" da seção 2 do plano — nenhum a mais; `test_live_withdrawal_advice.py`/`test_live_account_mode.py` **não aparecem** (correção de escopo confirmada) |
| 5 | Higiene: `print`/`console.log`/`TODO`/`FIXME` novos no diff | Nenhum (grep no diff completo — únicos matches são falsos-positivos em comentários PT-BR: "TODO mês" = "every month") |

### Desvios do plano
1. **Passo 3.5:** usado `end="2026-08-17"` em vez do último dia literal do
   parquet (`2026-08-18`) — a última linha de TODOS os 8 parquets copiados
   veio com OHLC zerado (artefato de pipeline para o pregão corrente, dado
   incompleto), o que geraria um trade fantasma (stop a preço 0) mascarando
   o resultado real da comparação. Não é uma mudança de escopo do fix, é a
   escolha da janela de comparação para isolar o efeito do fix do ruído de
   um dado incompleto.
2. Script de verificação do Passo 3.5 escrito no diretório de scratchpad
   (fora do repo), não em `scripts/`, para não introduzir um arquivo fora
   da lista "Escreve" do plano — evita falha no PRE-GATE item 4 (escopo).

### Arquivos realmente tocados
`src/backtest/engine_portfolio.py`, `src/core/models.py`, `tests/doubles.py`,
`tests/test_live_notify.py`, `tests/test_live_robots.py`,
`tests/test_live_runtime.py`, `tests/test_strategy_champion.py` (novo),
`tests/test_engine_portfolio.py` (novo), `scripts/debug_sim.py`,
`scripts/screenshot_sim.py`, `scripts/screenshot_strategies.py` — idêntico
à seção 2 do plano.

## Prova de conclusão (resultado final)

```
../meta/.venv/Scripts/python.exe -m pytest -q
368 passed, 1 warning in 11.98s
```

Exit 0. Todos os testes de falsificação da tabela da seção 4 verificados
(RED confirmado nos 3 cenários que dependiam do fix de produção antes de
aplicá-lo; as demais ~22 funções cobrem comportamento correto preexistente
sem depender de mudança de produção).

**Achado a destacar para o usuário:** o capital final da campeã
(`DipTop1Portfolio`, watchlist oficial de 7 tickers, R$1.000 iniciais,
janela FULL) **não mudou** com o fix do Passo 3 — R$73.701,3877 idêntico
antes/depois, ao centavo. O bug de reenfileiramento do `Exit` era real e
violava a regra 4/7 do AGENTS.md, mas nunca foi exercitado pelo histórico
real do watchlist (nenhum gap de dado nos 7 tickers nessa janela). Nenhum
número já usado em decisões de watchlist/ranking (`watchlist_champions.md`/
`ranking_criterion.md`) precisa ser revisto por causa desta feature.

Pronto para code-review.
