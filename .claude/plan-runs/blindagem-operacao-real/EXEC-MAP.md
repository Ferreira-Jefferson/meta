# EXEC-MAP — `blindagem-operacao-real`

**Plano original:** `C:\Users\Jeffe\.claude\plans\crie-um-plano-p-ra-gentle-papert.md`
**Branch alvo:** `plan/blindagem-operacao-real` | **Paralelismo máximo:** 4 (execução, mas não usado — cadeia 100% sequencial) | **Janela de revisão:** 6 (não usada — todas as features são T3, gate individual)
**Objetivo global:** o robô `portfolio_dip2_hw40` passa a operar dinheiro real (manual/MT5) sem simulação no caminho de produção, sem movimentação de caixa decidida pela máquina, com disjuntor que dispara de fato, estado que sobrevive a restart, e nenhum caminho silencioso — mais cobertura de teste na estratégia campeã, hoje com zero.

**Comandos do projeto:** teste `./.venv/Scripts/python.exe -m pytest -q [arquivos]` | lint `n/a — sem ruff/flake8 instalado no venv` | typecheck `n/a — sem mypy; substituto: ./.venv/Scripts/python.exe -m py_compile <arquivos tocados>` | build `n/a — não há passo de build`
**Convenção de commit:** sem convenção estabelecida no histórico (2 commits só); adotado `feat(blindagem): [FEAT-ID] <descrição>` em português, curto, foco no porquê
**Custo de worktree neste projeto:** baixo — `.venv` (409MB) é compartilhado via caminho absoluto (`../meta/.venv/Scripts/python.exe`), nenhuma reinstalação por worktree; `db/*.sqlite` é gitignored e os testes usam `tmp_path`, então nenhum worktree depende de banco do repo principal

**PRE-GATE (regra 18)** — roda por feature, antes de qualquer code-reviewer:
`1. prova da feature (pytest -q nos arquivos declarados) | 2. lint n/a | 3. typecheck n/a — py_compile nos arquivos tocados | 4. escopo: git diff --name-only plan/blindagem-operacao-real...HEAD | 5. higiene (grep por print/TODO/FIXME novo, arquivo temporário)`

**Modelos (regra 20):** worker T1 `haiku` (não usado nesta run) | worker T2/T3 `sonnet` (herdado da sessão) | revisores `opus` | owner T3 `haiku`

**MODO DA RUN:** NORMAL — 6 features, todas T3 (dinheiro, schema, remoção de comportamento em `live/`), cadeia 100% sequencial por colisão física de arquivo (`src/live/runtime.py` é escrito por 5 das 6 features) e por dependência de conteúdo declarada pelo próprio plano ("Processo por lote" + "suíte inteira verde antes do lote seguinte").

**Agentes previstos:** 6 planners + 6 implementers (0 execuções contínuas — T3 nunca é contínuo) + 6 janelas de gate 1 (individuais, T3 não entra em lote) + 6 code-reviewers individuais + 6 owners (T3) + 6 hipótese-agents (etapa própria do processo do plano, coordenada pelo owner) = **36**, mais fixers sob demanda (rejeição de gate, correção de hipótese).
> Comparação honesta: no modelo por-sub-item (30+ itens do plano) seriam 30+ × ~2,7 ≈ 80+ agentes. Aqui são 36 fixos + fixers pontuais.
> O maior corte veio antes: os **~35 sub-itens numerados** do plano (0.1–0.3, 1.1–1.7, 2.1–2.4, 3.1–3.3, 4.1–4.4, 5.*) viraram **6 features** — uma por Lote — porque o próprio plano prescreve granularidade de lote no processo ("Processo por lote": implemento → hipóteses → revisor → corrijo, suíte verde antes do próximo). Regra 1 (o plano é fonte da verdade) prevalece aqui sobre a heurística padrão de dividir acima de 8 arquivos (FEAT-001 tem 12): dividir cada Lote em sub-features quebraria a coesão de prova que o autor do plano pediu explicitamente. Se, na prática, algum Lote se mostrar grande demais para um implementer (regra 13 — >3 arquivos não previstos, plano provando errado), ele escala e o Lote é fatiado ali, não antes.

## Itens já implementados (NO-OP)

| Item do plano | Evidência |
|---------------|-----------|
| 0.1 — Commitar trabalho pendente de outra sessão | `git log` → commit `1a0ad66` "Reconcilia caixa MT5, registro manual de aporte e universo por robô" (18 arquivos, 907 linhas). Working tree limpo confirmado antes da criação da branch `plan/blindagem-operacao-real`. |
| 2.3 (parcial) — formulário "Registrar aporte" | `src/dashboard/app.py::operacao_aportar` (rota `POST /operacao/aportar`) já existe e está coberto por `tests/test_dashboard_app.py` (vindo do commit acima). FEAT-002 cobre só o espelho "Confirmar saque", não recria o aporte. |

## Features

| ID | Slug | Tier | Wave | **Depende de** | Planejamento | Escreve | Consome | Prova de conclusão | Isolamento | Status |
|----|------|------|------|----------------|--------------|---------|---------|--------------------|------------|--------|
| FEAT-000 | fundacao-db-separado | T3 | 1 | — | imediato (ESTÁVEL) | `src/core/config.py`, `src/journal/live_store.py`, `src/journal/schema.sql`, `src/live/runtime.py` (só o rename `DB_PATH`→`LIVE_DB_PATH`, sem guarda), `scripts/run_live_sim.py`, `scripts/migrate_live_db.py` (novo) | — | `pytest -q` (suíte inteira, baseline 249) com `LIVE_DB_PATH` como default de `_connect`/`live_journal`/`LiveRuntime` (P1-P3) + migração idempotente com integridade referencial (P4) + guarda do simulador acelerado (P6) | worktree | **CONCLUÍDA** (`62e7fbb`) |
| FEAT-001 | identidade-conta-corte-simulacao | T3 | 2 | FEAT-000 | concluído | *Produção (11):* `src/core/live_models.py`, `src/live/broker.py`, `src/live/broker_mt5.py`, `src/live/feed.py`, `src/live/runtime.py` (**+ a guarda `db_path=LIVE_DB_PATH` recusada quando o broker for test-double — herdada de FEAT-000, ver "Revalidação"**), `src/journal/live_store.py`, `src/journal/schema.sql`, `scripts/run_live.py`, `scripts/run_live_sim.py`, `src/dashboard/live_service.py`, `src/dashboard/live_control.py`, `src/dashboard/app.py`, `src/dashboard/templates/partials/operacao_body.html` · *Teste (novos):* `tests/doubles.py`, `tests/test_live_control.py`, `tests/test_run_live_cli.py` · *Teste (alterados, consequência mecânica de 1.1/1.4):* `tests/test_live_runtime.py`, `tests/test_live_store.py`, `tests/test_dashboard_app.py`, `tests/test_live_broker.py`, `tests/test_live_feed.py`, `tests/test_live_broker_mt5.py`, `tests/test_live_robots.py`, `tests/test_journal_live_store_history.py`, `tests/test_migrate_live_db.py` | FEAT-000: `LIVE_DB_PATH`, schema separado | `pytest -q` (suíte inteira, baseline 261 — blast radius maior que os arquivos nomeados) + cenário novo (modo divergente recusado, `--mode` desconhecido levanta, guarda por broker test-double recusa dublê e aceita caminho de produção, capital/disjuntor reais atravessando `get_status()`, prova de vida do processo) | worktree | **CONCLUÍDA** (`b6102f3`) |
| FEAT-002 | saque-vira-recomendacao | T3 | 3 | FEAT-001 | concluído | `src/live/runtime.py`, `src/journal/live_store.py`, `scripts/run_live.py`, `src/dashboard/app.py`, `src/dashboard/templates/partials/operacao_body.html`, `src/core/live_models.py` (**+ `Intent.is_immediate` aceita WITHDRAW same-day — bug pré-existente de FEAT-001 que só ativa com o comportamento desta feature**) | FEAT-001: enum de modo, dispatch explícito | `pytest -q` (suíte inteira) — tabela de 6 cenários × teste no ACTION-PLAN (duplo-clique, 2 PENDING coexistindo, restart apaga policy_state, saque>caixa sem clamp, disjuntor não bloqueia, valor≠recomendado) | worktree | **CONCLUÍDA** (`9ae5e8b`) |
| FEAT-003 | disjuntor-estado-skip-visivel | T3 | 4 | FEAT-002 | concluído | *Produção (6):* `src/live/runtime.py`, `src/live/riskguard.py` (**mantido — `unfreeze()` re-ancora; ver Revalidação**), `src/strategy/base.py`, `src/strategy/buy_the_dip.py` (**substitui `portfolio_dip2_hw40.py`: `_stateful_keys` mora na raiz da família e é herdado**), `src/live/robots.py` (**+ `InvestmentRobot` delega `state()`/`restore()`**), `src/journal/live_store.py` (**+ `last_equity` com `LIMIT 1`**) · *Teste (alterados):* `tests/test_live_runtime.py`, `tests/test_live_robots.py`, `tests/test_live_riskguard.py` | FEAT-002: `runtime.py` pós-refatoração do saque | `pytest -q` (suíte inteira, baseline 315 → 328 — blast radius maior que os arquivos nomeados) + 13 cenários novos (disjuntor diário dispara em crash intra-dia sobre painéis carregados e base do fecho anterior válida; `unfreeze()` destrava de verdade durante o pregão; `state()/restore()` sobrevive a restart no blackout de março; skip não silencioso, deduplicado e idempotente) | worktree | **CONCLUÍDA** (`2ba5b29`) |
| FEAT-004 | feed-stop-execucao | T3 | 5 | FEAT-003 | concluído (rigor reduzido: sem agente de hipóteses, decisão explícita do usuário) | `src/live/feed.py` (`MT5Feed` novo, `now_fn` injetável), `src/live/broker_mt5.py` (fill parcial → `PARTIAL`), `scripts/run_live.py` (`build()` recusa parquet em operação real, `--feed` ganha choice mt5/yfinance, `cmd_execute` recusa fora da fase OPEN), `src/dashboard/live_control.py` (correção de escopo: `feed="parquet"`→`"yfinance"`), `src/live/runtime.py` (stop suprimido sobre dado velho; 2ª trava de dedupe em `_sell` via `store.open_orders` — cobre o caminho cruzado stop-em-voo × decisão de saída do fecho seguinte; `_resolve_buy`/`_resolve_sell` notificam execução e alerta de caixa estourado, distinguindo PARCIAL/TOTAL) | FEAT-003: `runtime.py` pós-disjuntor/estado | `pytest -q` (suíte inteira, baseline 328 → 346) + 17 cenários novos, incluindo os 3 exigidos pelo gate 1 (dedupe cruzado stop×fecho, `MT5Feed.now_fn` injetável, notificação PARCIAL com `leaves_qty`) | worktree | **CONCLUÍDA** (`d6d0197`) |
| FEAT-005 | cobertura-campea-e-menores | T3 | 6 | FEAT-004 | concluído (rigor reduzido: sem agente de hipóteses) | *Novos:* `tests/test_strategy_champion.py` (9 funções), `tests/test_engine_portfolio.py` (9 funções) · *Produção:* `src/backtest/engine_portfolio.py` (fix: `Exit` sem dado descarta em vez de reenfileirar — elimina assimetria com `Enter`, regra 4/7; `entries_filled` só conta entrada realmente preenchida), `src/core/models.py` (`_DEFAULT_RISK_PCT` documentada) · *Consolidação:* `tests/doubles.py` (absorve `_RecordingNotifier`/`ScriptedStrategy` duplicados), `tests/test_live_robots.py`, `tests/test_live_notify.py` · *Alterados:* `tests/test_live_runtime.py` (+4 testes: `data_is_ready` falso, `execute_session` 2x mesma sessão, restart no ramo `risk_guard`) · *Correção pontual:* `scripts/debug_sim.py`, `scripts/screenshot_sim.py`, `scripts/screenshot_strategies.py` (URL morta `/strategies/sim/` → `/sim/`). `test_live_withdrawal_advice.py`/`test_live_account_mode.py` do plano original NÃO criados — confirmado que já estão cobertos por FEAT-001..004 (ver Revalidação) | FEAT-000..004: comportamento final de toda a stack live | `pytest -q` (suíte inteira, baseline 346 → 368) + Passo 3.5 obrigatório (capital final da campeã `DipTop1Portfolio`, 7 tickers watchlist oficial, byte-idêntico antes/depois do fix — bug nunca foi exercitado pelo histórico real) | worktree | **CONCLUÍDA** (`5798777`) |

> **`Depende de` é o que agenda a run.** Cadeia linear: cada feature depende só da anterior. Não há wave com 2+ features — paralelismo real é zero nesta run (todas colidem em `src/live/runtime.py` ou em conteúdo). O rótulo de wave aqui é 1:1 com a ordem de execução.

**Fusões no fatiamento** (regra 7 — a prova define o corte, mas aqui a fusão é por **decisão explícita do plano**, não por prova compartilhada):

| Feature | Itens/tasks do plano que ela cobre | Por que foram fundidos |
|---------|------------------------------------|-------------------------|
| FEAT-000 | 0.1 (NO-OP), 0.2, 0.3 | plano define "Lote 0" como unidade única de fundação |
| FEAT-001 | 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7 | plano define "Lote 1" como unidade única ("mata o crítico nº 1"); processo por lote explícito na seção final do plano |
| FEAT-002 | 2.1, 2.2, 2.3 (delta: só "sacar"), 2.4 | plano define "Lote 2" como unidade única ("mata o crítico nº 2") |
| FEAT-003 | 3.1, 3.2, 3.3 | plano define "Lote 3" como unidade única |
| FEAT-004 | 4.1, 4.2, 4.3, 4.4 | plano define "Lote 4" como unidade única |
| FEAT-005 | tabela de testes do Lote 5 + "Menores da revisão" | plano define "Lote 5" como unidade única |

**Justificativa de tier** (obrigatória):

| ID | Tier | Por quê |
|----|------|---------|
| FEAT-000 | T3 | migration/schema (`db/live.sqlite` novo, rebuild de conexão) |
| FEAT-001 | T3 | schema (`CHECK` de `live_accounts` via rebuild de tabela), remove comportamento existente (`PaperBroker`/`paper` mode saem de `src/`) |
| FEAT-002 | T3 | dinheiro/crédito direto (saque, `account.cash`), remove comportamento existente (`_withdraw*` no `live/`) |
| FEAT-003 | T3 | disjuntor de risco sobre dinheiro real + persistência de estado; corrige comportamento que "nunca disparou" (remoção/substituição de lógica existente) |
| FEAT-004 | T3 | execução de ordem com dinheiro real (stop, fill, custo > caixa) |
| FEAT-005 | T3 | toca `engine_portfolio.py` (motor que decide números do backtest de referência) e corrige assimetria Enter/Exit que a regra 7 do `AGENTS.md` proíbe — efeito direto em execução ao vivo, não só teste |

**Execução contínua** (regra 5): **nenhuma** — T3 nunca é contínuo (veto absoluto da regra 5/16). Todas as 6 features usam planner e implementer como agentes distintos.

| ID | Execução | Por quê |
|----|----------|---------|
| FEAT-000..005 | worker novo | T3 — veto absoluto à execução contínua |

**Status possíveis:** pendente → planejando → plano em revisão → executando → hipóteses → em code review → CONCLUÍDA (`<hash>`) | rejeitada (N/2) | escalada | NO-OP

## Waves

```
WAVE 0 [orquestrador]  fundação compartilhada — nada além do commit 1a0ad66 já feito; sem boilerplate extra a criar
WAVE 1                 FEAT-000
WAVE 2                 FEAT-001 (aguarda FEAT-000)
WAVE 3                 FEAT-002 (aguarda FEAT-001)
WAVE 4                 FEAT-003 (aguarda FEAT-002)
WAVE 5                 FEAT-004 (aguarda FEAT-003)
WAVE 6                 FEAT-005 (aguarda FEAT-004)
```

### WAVE 0 — fundação (executada pelo orquestrador)

- [x] Commit do trabalho pendente de outra sessão (`1a0ad66`) — confirmado pelo usuário ("commit o que está unstashed")
- [x] Branch de trabalho `plan/blindagem-operacao-real` criada a partir de `master`
- [ ] Nenhum boilerplate/contrato compartilhado adicional — o plano não define artefato agregador novo que preceda as 6 features

## Serializações e o porquê

| Features | Motivo da serialização |
|----------|-------------------------|
| FEAT-001 depois de FEAT-000 | consome `LIVE_DB_PATH` e schema separado |
| FEAT-002 depois de FEAT-001 | escrevem `src/live/runtime.py` e `src/journal/live_store.py` em comum; FEAT-002 consome o vocabulário de modo de FEAT-001 |
| FEAT-003 depois de FEAT-002 | escrevem `src/live/runtime.py` em comum (FEAT-003 reescreve `close_and_decide`/`intraday_tick` que FEAT-002 acabou de alterar) |
| FEAT-004 depois de FEAT-003 | escrevem `src/live/runtime.py` em comum (execução depende do disjuntor/estado já corrigidos) |
| FEAT-005 depois de FEAT-004 | a prova de FEAT-005 é o comportamento final de toda a stack — testar antes seria testar código que ainda vai mudar |

Nenhuma serialização é "por capacidade" — é 100% dependência real ou colisão física, então `[max-parallel]=4` nunca é exercitado nesta run.

## Pontos de colisão resolvidos

| Arquivo / comportamento | Features envolvidas | Tipo | Resolução |
|--------------------------|----------------------|------|-----------|
| `src/live/runtime.py` | FEAT-000, FEAT-001, FEAT-002, FEAT-003, FEAT-004 | física | serializadas na ordem do plano (Lote 0→4); nenhuma roda em paralelo |
| `src/journal/schema.sql` | FEAT-000, FEAT-001 | física | serializadas (FEAT-000 cria a separação, FEAT-001 faz o rebuild do `CHECK`) |
| `src/journal/live_store.py` | FEAT-000, FEAT-001, FEAT-002, FEAT-003 | física | serializadas; FEAT-000/001/002 já CONCLUÍDAS. FEAT-003 só ACRESCENTA `last_equity` (leitura pura, sem schema, sem migração) — FEAT-004/005 não escrevem este arquivo |
| `src/live/robots.py` / `src/strategy/{base,buy_the_dip}.py` | FEAT-003 (única) | — | nenhuma outra feature da run escreve estes arquivos (verificado na coluna "Escreve" de FEAT-000..005) |
| gatilho `is_month_end` / rotação de carteira | FEAT-003, FEAT-005 | semântica | FEAT-005 só escreve teste sobre o comportamento que FEAT-003 corrigiu — depende, não colide |

## Features adiadas (planejamento just-in-time — regra 17)

| ID | Motivo do adiamento | Destrava quando | Premissa a confirmar no destravamento |
|----|----------------------|------------------|------------------------------------------|
| FEAT-001 | consome `LIVE_DB_PATH`/schema cuja forma FEAT-000 define | FEAT-000 CONCLUÍDA | caminho de `LIVE_DB_PATH` em `core/config.py`, nome da função de migração |
| FEAT-002 | consome enum de modo e dispatch explícito que FEAT-001 define | FEAT-001 CONCLUÍDA | nomes do enum (`manual`/`mt5`), assinatura de `Broker.mode` |
| FEAT-002 (CONCLUÍDA, `9ae5e8b`) | Saque nunca mais é executado pela máquina — vira recomendação (intent + notificação `warn`), confirmação humana via CLI `sacar --intent-id` ou dashboard "Confirmar saque", vinculada a um id específico. `reconcile_broker_cash` é detector puro (nunca credita). `Intent.is_immediate` (core/live_models.py) passou a aceitar WITHDRAW same-day — mudança de escopo justificada, sem regressão em ADJUST_STOP/stop. Expiração de recomendação vencida agora persiste `policy_state` corretamente em qualquer ponto que dispare (bug corrigido só na 2ª rodada de review). Riscos registrados como fora de escopo: taxas/IR do saque não rastreadas; processo fora do ar 2+ meses perde acumulação de sessões em `backtest/withdrawal.py` (intocável); sem lembrete periódico de recomendação pendente; sem caminho para "vendi posição na corretora para levantar o saque"; fadiga de alerta do `reconcile_broker_cash` (warn idêntico todo pregão sem dedupe). | FEAT-003 (mesmo `runtime.py`), FEAT-005 (testes de cobertura da campeã referenciam o estado final) | nenhuma premissa quebrada — vocabulário de modo e `Broker.mode` usados exatamente como FEAT-002 assumia. FEAT-003 deve estar ciente de que `_expire_withdraw_advice` já roda em 3 pontos (`close_and_decide`, `execute_session`, `confirm_withdrawal`) antes de tocar na ordem de `execute_session`/disjuntor. |
| FEAT-003 | ataca `runtime.py` que FEAT-002 acabou de reescrever (saque) | FEAT-002 CONCLUÍDA | shape de `close_and_decide` e de `execute_session` pós-remoção do saque executado |
| FEAT-004 | ataca `runtime.py` pós-disjuntor/estado | FEAT-003 CONCLUÍDA | assinatura de `observe()`/`intraday_tick`, chave `"investment"` em `_robot_state` |
| FEAT-005 | prova depende do comportamento final de toda a stack | FEAT-004 CONCLUÍDA | nenhuma API nova além do que FEAT-000..004 já fixaram |

## Revalidação (por fechamento de feature)

> Preenchido no checkpoint que roda a cada feature concluída.

| Feature fechada | Desvio reportado | Dependente afetada | Decisão |
|-------------------|--------------------|-----------------------|----------|
| FEAT-005 (CONCLUÍDA, `5798777`) | ÚLTIMA feature do run. Fix real de produção em `engine_portfolio.py`: `Exit` sem dado passou a descartar (em vez de reenfileirar), eliminando assimetria com `Enter` que violava o espírito da regra 4/7 do AGENTS.md ("executar tarde é pior que não executar" — reenfileirar o Exit é o análogo de executar tarde). **Verificação obrigatória (Passo 3.5, inserida pelo gate 1) confirmada de forma independente pelo code-reviewer com dados fora da worktree**: capital final da campeã `DipTop1Portfolio` (7 tickers do watchlist oficial, R$1.000, janela até 2026-08-17) ficou byte-idêntico antes/depois do fix — o bug nunca foi exercitado pelo histórico real, nenhuma memória de watchlist/ranking precisa revisão por causa desta feature. `entries_filled`/`entries_skipped` confirmado código morto hoje (só populado quando `entry_fill_mode != "open"`, nenhum chamador usa outro valor). `tests/doubles.py` absorveu a segunda cópia de `_RecordingNotifier`/`ScriptedStrategy` que a Revalidação de FEAT-001 achava já resolvida (não estava — grep anterior não pegou o prefixo `_`). **Achado não-bloqueante fora do escopo desta feature, mas relevante para o projeto**: o code-reviewer notou, ao reproduzir o cálculo de forma independente, que o capital real da campeã já mudou entre a execução da feature e a revisão (R$73.701,39/33 trades → R$166.505,54/26 trades) por revisão retroativa de `adj_close` pelo provedor de dados (mecanismo de detecção `_frame_digest`/`universe_fingerprint` já existe no projeto) — não é causado por esta feature, mas sugere que pode valer a pena re-rodar o ranking oficial se isso ainda não tiver acontecido recentemente. | nenhuma (última feature da run) | nenhuma premissa quebrada. Run "blindagem-operacao-real" fecha aqui — ver FASE 3/Cobertura do plano original. |
| FEAT-000 (gate 1, antes de fechar) | plan-reviewer escalou: guarda "recusa `db_path` quando broker é test-double" (item 0.3) pressupõe `PaperBroker` já fora de produção, o que só acontece em FEAT-001 (1.2/1.4) — dependência circular com a própria feature seguinte | FEAT-001 | **re-mapear** (decisão do usuário: opção A). FEAT-000 entrega só a separação do banco (rename `DB_PATH`→`LIVE_DB_PATH`, WAL, migração, guarda do simulador). A guarda por broker test-double vira requisito explícito de FEAT-001 (linha acima já atualizada) — não é NO-OP nem item perdido, só remarcado. |
| FEAT-001 (gate 1, plano) | Lista de arquivos 11 maior que a estimativa da linha original (7 apontados pelo planner + 4 achados na revisão: `tests/test_live_broker_mt5.py`, `tests/test_live_robots.py`, `tests/test_journal_live_store_history.py`, `tests/test_migrate_live_db.py`). Todos criam conta com `mode="paper"` ou assertam `mode == "broker"` | nenhuma (run 100% sequencial) | **linha de FEAT-001 corrigida acima.** Divergência puramente de "arquivo esquecido na estimativa": zero item novo além de 1.1–1.7 + a guarda 0.3 herdada; é consequência mecânica de 1.1 (CHECK/enum de modo) e 1.4 (dublês saem de `src/`). Prova promovida de 3 arquivos para a suíte inteira pelo mesmo motivo. |
| FEAT-000 (CONCLUÍDA, `62e7fbb`) | Nenhum desvio relevante para dependentes. `db/live.sqlite` nasce **vazio** após o merge — `db/journal.sqlite` continua com o histórico até alguém rodar `python scripts/migrate_live_db.py` na máquina (ação humana, fora do escopo automatizado). Migração agora exige `--force` explícito se o destino já tiver `live_accounts` sem marcador de migração (protege contra colisão silenciosa de conta). | FEAT-001 (consome `LIVE_DB_PATH`/schema) | nenhuma premissa afetada — `LIVE_DB_PATH` em `core/config.py`, `scripts/migrate_live_db.migrate()` e o schema separado existem exatamente na forma que FEAT-001 assumia. Planejamento de FEAT-001 liberado. |
| FEAT-003 (CONCLUÍDA, `2ba5b29`) | `unfreeze()` re-ancora as bases do disjuntor usando `datetime.now(timezone.utc).date()` (mesma expressão de `run_once`), não `clock.session_date()` — furo real achado no gate 2 (rejeição 1/2): a data errada fazia o "botão de pânico" recongelar sozinho em menos de um minuto durante o pregão. `intraday_tick` carrega painéis e recusa observar sem eles; base do fecho anterior só é aceita com data exata e valor `> 0`; âncora mensal só é fixada pelo caminho de fecho. `Strategy.state()`/`restore()` sobrevive a restart (`_pending_rebalance`), com coerção de tipo e carimbo de robô. Skip de dado incompleto gera evento+notificação deduplicado por sessão, escalando para `error` em fim de mês, com ordem "já decidido" antes de "dado pronto" (evita alarme falso no gap-flapping conhecido do yfinance). | FEAT-004 (mesmo `runtime.py`), FEAT-005 (testes de cobertura referenciam o estado final) | nenhuma premissa quebrada — `intraday_tick`/`_robot_state`/`unfreeze()` mantêm assinatura pública. FEAT-004 deve saber que `_observe_risk` já roda no ciclo intra-dia antes de mexer na ordem de execução/stop. Risco conhecido (não corrigido, pré-existente): dois processos escrevendo `policy_state` concorrentemente — superfície aumentada por `intraday_tick` escrever a cada minuto, sem lock de processo único em lugar nenhum da run. |
| FEAT-003 (gate 1, plano) | Lista de arquivos de produção passou de 4 para 6. **`src/live/riskguard.py` MANTIDO em "Escreve"** — o planner o havia removido alegando que `CircuitBreaker` já estava pronta; o plan-reviewer confirmou que `unfreeze()` não re-ancora `_daily_ref_equity`/`_monthly_ref_equity`, e isso deixa de ser inofensivo no instante em que `intraday_tick` passa a chamar `observe()` a cada minuto (o tick seguinte ao destravamento recongela na hora — o botão de pânico documentado vira inoperante durante o pregão). Mudança é **aditiva**: `unfreeze(session=None, patrimonio=None)`, zero nome público novo, zero teste existente de `tests/test_live_riskguard.py` editado. `src/strategy/portfolio_dip2_hw40.py` → `src/strategy/buy_the_dip.py` (`_stateful_keys` na raiz da família, herdado por toda a cadeia até a campeã). `src/live/robots.py` e `src/journal/live_store.py` adicionados. Prova promovida de `tests/test_live_runtime.py` para a suíte inteira pelo mesmo motivo de FEAT-001 (blast radius: `strategy/base.py` é base de todos os robôs, `test_live_riskguard.py` guarda o contrato de `unfreeze` e ficava fora da prova antiga). | nenhuma (run 100% sequencial); FEAT-004 continua consumindo `intraday_tick`/`_robot_state` com as mesmas assinaturas públicas | **linha de FEAT-003 corrigida acima.** Zero item novo além de 3.1–3.3: as adições são consequência mecânica de fazer o disjuntor observar intra-dia (painéis carregados antes de observar, base do fecho anterior com limite de idade e piso `> 0`, âncora do mês só pelo caminho de fecho, dedupe do alerta de skip). Gatilho de escalação "não mudar a API de `CircuitBreaker`" foi **explicitamente derrubado no ACTION-PLAN** — necessidade de engenharia, não decisão de política; mesmo precedente de `core/live_models.py` em FEAT-002. |
| FEAT-004 (CONCLUÍDA, `d6d0197`) | Rigor reduzido (sem hipótese-agent): gate 1 compensou com 3 correções substantivas — (1) dedupe de stop também no caminho cruzado (stop intra-dia em voo/`SENT` não confirmado × decisão de saída do fecho seguinte), via nova trava em `_sell` que checa `store.open_orders` antes de `_place` (não só o dedupe dentro do mesmo `intraday_tick`); (2) `MT5Feed` com `now_fn` injetável + aviso na docstring de que `tick.time` é hora do **servidor** MT5, tipicamente deslocada de UTC — calibração errada pode subestimar o atraso real; (3) notificação de fill distingue PARCIAL (com `order.leaves_qty`) de TOTAL. `build()` recusa `--feed parquet` em operação real; `cmd_execute` recusa fora da fase OPEN; alerta de custo>caixa não desfaz o fill (já aconteceu de verdade) — é só sinalização, não decisão de negócio (regra 6 preservada, confirmado no gate 2). Bug de escopo fora do EXEC-MAP original encontrado e corrigido pelo próprio planner: `live_control.py::create_account` hardcodava `feed="parquet"`, o que quebraria o botão "Iniciar" do dashboard assim que a recusa de parquet entrasse em vigor. Riscos registrados como fora de escopo (não corrigidos): `mt5.initialize()` chamado independentemente por broker e feed (2x); fill parcial não tem reconciliação automática do restante (consistente com IOC do MT5, mas fica explícito); botão "Iniciar" do dashboard nunca passa `--feed`, então conta `mt5` criada por ele sempre sobe com `YFinanceFeed`, nunca `MT5Feed`. | FEAT-005 (testes de cobertura referenciam o estado final de `runtime.py`) | nenhuma premissa quebrada — `intraday_tick`/`_sell`/`_resolve_buy`/`_resolve_sell` mantêm assinatura pública, só ganharam checagens internas. FEAT-005 deve saber que a superfície de notificação cresceu (fill parcial/total, custo>caixa, stop suprimido) — se for testar notificações da campeã, esses casos já têm cobertura própria aqui, não precisam ser reabertos. |
| FEAT-001 (CONCLUÍDA, `b6102f3`) | Vocabulário canônico `BrokerMode.MANUAL`/`BrokerMode.MT5` fixado; `Broker.mode` agora vale `"manual"` ou `"mt5"` (nunca mais `"paper"`/`"broker"`). `PaperBroker`/`ReplayFeed` vivem só em `tests/doubles.py`. `LiveRuntime` recusa `db_path=LIVE_DB_PATH` quando `broker.is_test_double` for `True` (comparação por `Path.resolve()`). Conta `principal` legada em `paper` seguirá bloqueando qualquer conexão até decisão humana (apagar linha ou `UPDATE` consciente do `mode`) — `LegacyPaperAccountError` agora tratada com mensagem amigável no dashboard. Riscos registrados como fora de escopo (não corrigidos): `PaperBroker.mode="mt5"` apaga o marcador sim/real para o futuro; sem lock de "dono" do processo/conta (dois supervisores podem operar a mesma conta); prova de vida cobre só o início do processo, não heartbeat contínuo; guarda do dublê protege só `LIVE_DB_PATH`, não outros bancos reais; `get_status()` pode 500 se faltar parquet ou `live_process.json` malformado; disjuntor exibido reflete o arquivo de config do dashboard, não necessariamente o estado real da conta (isso é território de FEAT-003, item 3.2 — persistência de estado). | FEAT-002 (consome enum de modo/dispatch), FEAT-003 (vai mexer no mesmo `runtime.py` e no disjuntor exibido) | nenhuma premissa quebrada para FEAT-002 — `BrokerMode.MANUAL.value == "manual"`, `Broker.mode` é a assinatura assumida. FEAT-003 deve estar ciente do risco "disjuntor exibido != estado real" ao desenhar a persistência de estado (item 3.2), não é um bloqueio, é contexto a considerar no planejamento. |

## Colisões detectadas no gate 1 (lote)

> N/a nesta run — nenhum gate 1 roda em lote (todas T3, individuais).

## Lacunas do plano

| Lacuna | Tratamento |
|--------|------------|
| Sem lint/typecheck instalado no venv | pre-gate usa `py_compile` como substituto mínimo de sintaxe; registrado como `n/a` justificado, não escalado |
| Nome exato do script de migração (0.2) | decisão trivial, resolvida pelo planner de FEAT-000: `scripts/migrate_live_db.py` |
| Convenção de commit | sem padrão forte no repo; adotado `feat(blindagem): [FEAT-ID] <descrição>`, decisão trivial |

## Cobertura do plano original

> Preenchido no encerramento (FASE 3).

| Item/seção do plano | Feature | Status |
|------------------------|-----------|--------|
| Lote 0 (0.1–0.3) | FEAT-000 | ✅ (`62e7fbb`) — 0.3 (guarda por broker) remarcado para FEAT-001, ver Revalidação |
| Lote 1 (1.1–1.7) | FEAT-001 | ✅ (`b6102f3`) — 0.3 herdado de FEAT-000 também entregue |
| Lote 2 (2.1–2.4) | FEAT-002 | ✅ (`9ae5e8b`) |
| Lote 3 (3.1–3.3) | FEAT-003 | ✅ (`2ba5b29`) |
| Lote 4 (4.1–4.4) | FEAT-004 | ✅ (`d6d0197`) |
| Lote 5 (tabela + menores) | FEAT-005 | ✅ (`5798777`) — `test_live_withdrawal_advice.py`/`test_live_account_mode.py` do texto original não criados como arquivos separados: 4/5 e 4/4 cenários já cobertos por FEAT-001/002/004, ver Revalidação |
