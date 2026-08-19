# FEAT-002 — saque-vira-recomendacao

> Plano de ação escrito pelo feature-agent, revisado (e corrigido quando necessário) pelo plan-reviewer.
> Status: `rascunho` → `em revisão` → `aprovado` → `executado` → `concluído`

**Status:** executado (CORRIGIDO pelo plan-reviewer — ver §6; correções SUBSTANTIVAS) — aguardando code-reviewer
**Run:** `blindagem-operacao-real` | **Plano original:** `C:\Users\Jeffe\.claude\plans\crie-um-plano-p-ra-gentle-papert.md` (seções: "Contexto", "Consequência que precisa ficar explícita", "Lote 2 — Saque vira recomendação; conciliação nunca inventa dinheiro" 2.1–2.4, "Processo por lote")
**Tier:** T3 | **Wave:** 3 | **Isolamento:** worktree `../meta-FEAT-002`
**Branch:** `feat/blindagem-operacao-real-FEAT-002`

## 1. Problema / objetivo

Hoje o saque é executado pela própria máquina: `_withdraw` liquida posição e move
`account.cash` sozinho, e `reconcile_broker_cash` credita qualquer saldo extra da
corretora como se fosse aporte — no modo MT5 isso faz o patrimônio "crescer" R$1.000
por saque sem ninguém ter depositado nada (o crítico nº2 da revisão). Esta feature
tira a máquina da decisão de mover dinheiro: `IntentKind.WITHDRAW` vira só uma
**recomendação** (grava + notifica), o humano executa o saque de verdade na
corretora e **confirma** depois (CLI `sacar` ou botão "Confirmar saque"), e a
conciliação de caixa vira detector puro — nunca mais um `account.cash +=` automático.

**Estado atual (regra 6):**
- `src/live/runtime.py:718-895` — `_withdraw`/`_withdraw_manual_step`/
  `_apply_liquidation_fill`/`_finish_withdrawal` executam o saque sozinhos (síncrono
  em corretora automática, em pernas sob `ManualBroker`) e mexem em `account.cash`.
- `src/live/runtime.py:539-564` — `execute_session` passos 2 e 4 chamam `_withdraw`.
- `src/live/runtime.py:1002-1043` — `reconcile_broker_cash` credita (`_apply_deposit`,
  linha 977) qualquer diferença POSITIVA como depósito automático.
- `src/dashboard/app.py:454-497` — `operacao_aportar` (POST `/operacao/aportar`,
  "Registrar aporte") **já existe e está pronto** — é o espelho que este plano
  reaproveita como padrão, não recria.
- Nada existe ainda para: recomendação nunca mover caixa, confirmação humana
  (`sacar`/`/operacao/sacar`), expiração de recomendação na virada do mês, ou
  `reconcile_broker_cash` como detector puro. **Delta: tudo isso.**

## 2. Arquivos

**Escreve** (cria/edita):
- `src/live/runtime.py` — remove execução automática de saque; helper novo
  `_expire_withdraw_advice` chamado por `close_and_decide` **e** por
  `execute_session` (antes de qualquer decisão de liquidez); log/notify da
  recomendação; `execute_session` para de executar saque (só registra o de
  liquidez); `reconcile_pending_fills` passa a restaurar estado antes de
  persistir `policy_state`; `reconcile_broker_cash` vira detector puro; novos
  métodos `confirm_withdrawal`/`_last_equity_before`; `status()` passa a mostrar
  recomendação de saque pendente por todo o mês (não só no dia seguinte à
  decisão) e a expor o `id` da intenção.
- `src/journal/live_store.py` — nova função `pending_withdraw_intents`; nova função
  `claim_intent` (transição de status ATÔMICA, `UPDATE ... WHERE id=? AND status=?`
  com `rowcount`); `stale_intents` passa a excluir `kind='withdraw'` (recomendação de
  saque não expira por dia).
- `src/core/live_models.py` — **[reviewer, escopo ampliado — ver §6 correção 2]**
  `Intent.is_immediate` passa a aceitar `WITHDRAW` com `execute_on == decided_on`.
  Uma linha + docstring; nenhum outro contrato do módulo é tocado.
- `scripts/run_live.py` — novo subcomando `sacar <valor> [--data ...]`.
- `src/dashboard/app.py` — nova rota `POST /operacao/sacar` ("Confirmar saque").
- `src/dashboard/templates/partials/operacao_body.html` — form "Confirmar saque"
  (reaproveita as classes CSS `.ops-deposit`/`.ops-deposit-form` já existentes — sem
  editar `pages.css`); ajuste de texto na seção "Intenções pendentes".
- `tests/test_live_runtime.py` — reescreve/remove os testes de saque automático,
  acrescenta os cenários novos (recomendação não move caixa, confirmação humana,
  expiração mensal, `reconcile_broker_cash` nunca credita, visibilidade da
  recomendação por vários dias).
- `tests/test_live_store.py` — testes novos para `pending_withdraw_intents`,
  `claim_intent` e para a exclusão de `WITHDRAW` em `stale_intents`; asserção nova
  no teste **já existente** `test_record_intent_aceita_excecoes_de_is_immediate`
  (linha 207) para o `WITHDRAW` same-day.
- `tests/test_run_live_cli.py` — testes novos para `cmd_sacar`.
- `tests/test_dashboard_app.py` — testes novos para `/operacao/sacar`.

**Só lê:**
- `src/backtest/withdrawal.py` — `WithdrawalPolicy`/`FloorSkim` (`on_close`,
  `on_liquidity_event`, `on_executed`, `state`/`restore`) — contrato consumido, não
  alterado (arquivo **intocado** por decisão explícita do plano original).
- `src/live/robots.py` — `WithdrawalRobot`/`LiveRobot` (adaptador já traduz
  `Intent`; não decide nada, regra 6).
- `src/dashboard/live_service.py` — `_build_runtime(mode, capital)` reaproveitado
  por `operacao_sacar` (precisa da política de saque de verdade, diferente de
  `operacao_aportar`, que não toca robô nenhum).
- `src/journal/schema.sql` — `live_withdrawals`/`live_deposits`/`live_intents` (schema
  já serve; nenhuma coluna nova necessária).
- `tests/doubles.py` — `PaperBroker`/`ReplayFeed` para os testes de runtime.

**Consome de outras features:** FEAT-001 — `BrokerMode`/`Broker.mode` canônico
(`"manual"`/`"mt5"`), dispatch explícito em `scripts/run_live.py::build`,
`LiveRuntime._load_account` recusando conta×broker divergente.
**Produz para outras features:** FEAT-003 consome o `runtime.py` pós-remoção do
saque executado — `close_and_decide`/`execute_session` sem os passos 2/4 antigos,
`reconcile_pending_fills` sem o ramo `WITHDRAW` **e agora com
`_restore_robot_state` antes de persistir `policy_state`** (relevante para o item
3.2 de FEAT-003, que acrescenta a chave `"investment"` a `_robot_state()`: sem a
restauração, o estado da estratégia seria apagado pelo mesmo caminho). Também
produz `store.claim_intent` (transição atômica de status) e o helper
`_expire_withdraw_advice`. **Registrar no checkpoint de revalidação da wave:**
`Intent.is_immediate` passou a aceitar `WITHDRAW` same-day.

## 2b. Premissas a montante (regra 17)

| # | Premissa | Como verificar | Origem |
|---|----------|----------------|--------|
| 1 | `Broker.mode` vale só `"manual"`/`"mt5"`; `BrokerMode` enum existe em `core/live_models.py` | `src/core/live_models.py:101-102` | FEAT-001 |
| 2 | `LiveRuntime._load_account` recusa operar quando `account.mode != self.broker.mode` | `src/live/runtime.py:368-388` | FEAT-001 |
| 3 | `WithdrawalRobot.on_close/on_liquidity/on_executed/state/restore` só traduzem `WithdrawalPolicy`, nunca decidem | `src/live/robots.py:195-228` | código existente |
| 4 | `store.record_withdrawal(conn, account_id, day, requested, executed, equity_before, fees_paid, liquidated)` mantém essa assinatura | `src/journal/live_store.py:778-794` | código existente |
| 5 | `app.py::operacao_aportar` (POST `/operacao/aportar`) já existe e está coberto por `tests/test_dashboard_app.py` — não recriar | `src/dashboard/app.py:454-497` | trabalho anterior a esta run |
| 6 | `dashboard/live_service._build_runtime(mode, capital)` monta `LiveRuntime` completo (com a política real via `official_policy`) sem conectar corretora nem exigir dado de mercado no `__init__` | `src/dashboard/live_service.py:26-56` | código existente |
| 7 | `/operacao/historico` já renderiza `requested`/`executed` lado a lado por saque (`historico.html:100-101`, alimentado por `live_store.withdrawals`) — a "Consequência" do plano original (mostrar recomendado vs. sacado) já é satisfeita por esta página existente, desde que `confirm_withdrawal` continue chamando `record_withdrawal` com esses dois valores corretos | `src/dashboard/templates/historico.html:97-101` | código existente |

**Premissas acrescentadas pelo plan-reviewer** (todas conferidas no worktree `../meta-FEAT-002`, HEAD `b6102f3`) — são os fatos de código em que as correções da §6 se apoiam:

| # | Premissa (FATO verificado, não suposição) | Onde | Consequência para esta feature |
|---|-------------------------------------------|------|-------------------------------|
| 8 | `Intent.is_immediate` é `kind == ADJUST_STOP or reason == "stop"` — **só isso** | `src/core/live_models.py:156-164` | uma recomendação de saque por liquidez (`kind=WITHDRAW`, `reason=policy.label`, `execute_on == decided_on`) **não** é imediata |
| 9 | `store.record_intent` **levanta `ValueError`** quando `not is_immediate and execute_on <= decided_on` | `src/journal/live_store.py:525-532` | o `record_intent` do passo de liquidez (hoje `runtime.py:562`) **já explode hoje**, antes desta feature — o plano só o preservava |
| 10 | `cmd_loop` trata `ValueError` como **fatal** (`sys.exit(1)`), decisão de FEAT-001 | `scripts/run_live.py:325-337` | o item 9 mata o supervisor na primeira rotação com saque pendente |
| 11 | `WithdrawalRobot.on_liquidity` emite `execute_on=ctx.session` (mesma barra), `reason=policy.label` | `src/live/robots.py:207-219` | confirma o formato da intent do item 9; `robots.py` continua **intocado** (regra 6) |
| 12 | `reconcile_pending_fills` faz `account.policy_state = self._robot_state()` **sem** `_restore_robot_state` antes | `src/live/runtime.py:971-972` | num processo novo isso **zera** `_paid_month`/`_pool`; sobrevive à remoção do ramo `WITHDRAW` (a linha está fora do `for`) |
| 13 | `unfreeze()` já faz o padrão certo (restaura → muta → persiste), com docstring explicando por quê | `src/live/runtime.py:398-414` | é o padrão a replicar no item 12, não uma invenção |
| 14 | `FloorSkim._requested` é um escalar **global** da política (não por-intent); `on_executed` faz `falta = _requested - executed` e zera | `src/backtest/withdrawal.py:249, 277, 294-300` | duas recomendações `PENDING` simultâneas corrompem a fila; a correção é garantir a **invariante de ordem** (expirar antes de decidir), nunca mexer em `_pool` a partir de `live/` |
| 15 | Ordem real do pregão em `run_once`: `OPEN → execute_session` (pode gerar recomendação por liquidez) **antes** de `POST_CLOSE → close_and_decide` (onde o plano punha a expiração) | `src/live/runtime.py:1105-1114` | no 1º pregão de um mês novo, a nova recomendação nasce antes de a antiga expirar → cenário do item 14 |
| 16 | `store.set_intent_status` é um `UPDATE ... WHERE id = ?` **sem** guarda de status | `src/journal/live_store.py:589-590` | "ler PENDING → decidir → gravar DONE" não é atômico; duplo-clique debita duas vezes |
| 17 | `CircuitBreaker` só veta `IntentKind.ENTER` (nunca saída, stop ou saque) | `src/live/runtime.py:461-470` e `651-655` | disjuntor acionado **não** deve bloquear `confirm_withdrawal` — é comportamento já correto, só falta teste |
| 18 | `status()["intencoes_pendentes"]` **não expõe `id`**; o template renderiza a tabela sem identificador | `src/live/runtime.py:1177-1180`; `partials/operacao_body.html:352-360` | sem `id` não há como vincular a confirmação a uma recomendação específica na UI |
| 19 | Seções reais do template: "Registrar aporte" em **258-280**, "Intenções pendentes" em **335-366** (a frase a ajustar é a 338) | `src/dashboard/templates/partials/operacao_body.html` | corrige os "~280"/"~338" do plano original |
| 20 | `_operacao_ctx(**extra)` aceita kwargs arbitrários e já é usado por `aporte_msg` | `src/dashboard/app.py:332-360` | `saque_msg` funciona sem tocar no helper |
| 21 | `data/raw` do worktree está **vazio**; `../meta/data/raw` tem os parquets | `ls` nos dois caminhos | confirma o passo 1 |

## 3. Passos

| # | Ação | Arquivo(s) | Como sei que funcionou |
|---|------|-----------|------------------------|
| 1 | **Preparar ambiente da worktree (não é código):** copiar `data/raw/*.parquet` de `C:\Users\Jeffe\Documents\study\meta\data\raw` para o mesmo caminho nesta worktree — `data/raw` é gitignored (`.gitignore: data/raw/*.parquet`) e por isso ausente aqui; sem ele, `get_status()` → `LiveRuntime._load()` → `load_universe(WATCHLIST)` derruba `tests/test_dashboard_app.py` inteiro (confirmado: 6/61 falhando HOJE, antes de qualquer mudança minha, com `FileNotFoundError: WEGE3.SA`) | `data/raw/` (não rastreado) | `../meta/.venv/Scripts/python.exe -m pytest -q tests/test_dashboard_app.py` sai de 55/61 para 61/61 **antes** de eu tocar em qualquer código |
| 2 | Em `src/journal/live_store.py`, **três** funções: (a) `pending_withdraw_intents(conn, account_id) -> list[Intent]` (SELECT `status='pending' AND kind='withdraw'`, `ORDER BY id`); (b) `claim_intent(conn, intent_id, from_status: IntentStatus, to_status: IntentStatus) -> bool` — `UPDATE live_intents SET status=? WHERE id=? AND status=?`, devolve `cur.rowcount == 1`; docstring explica que é a **trava** contra duplo-clique/confirmação concorrente: quem recebe `False` perdeu a corrida e **não** pode mover dinheiro (`set_intent_status` continua existindo para as transições onde não há corrida); (c) em `stale_intents`, `AND kind != 'withdraw'` com comentário (recomendação de saque não expira por dia — expira na virada do mês, ver passo 6) | `src/journal/live_store.py` | Em `tests/test_live_store.py`: `test_pending_withdraw_intents_devolve_mais_antiga_primeiro`; `test_stale_intents_nunca_expira_recomendacao_de_saque` (WITHDRAW com `execute_on` no passado → `stale_intents` vazia); `test_claim_intent_so_transiciona_uma_vez` (1ª chamada `True` + status muda; 2ª chamada idêntica `False` + status **não** muda) |
| 3 | Em `src/core/live_models.py`: `Intent.is_immediate` passa a devolver `True` também para `kind == IntentKind.WITHDRAW and execute_on == decided_on`; docstring ganha o 3º caso, explicando que uma **recomendação** de saque por evento de liquidez nasce na mesma barra (o robô acabou de vender, o caixa está na mão — paridade com `on_liquidity_event` do engine, ver `robots.py:207-219`) e que isso **não** é look-ahead: ela não executa nada, só notifica um humano. Ajustar junto a mensagem de erro de `record_intent` (`live_store.py:529-531`), que hoje enumera "as duas exceções" | `src/core/live_models.py`, `src/journal/live_store.py` | **RED primeiro:** acrescento ao teste JÁ EXISTENTE `tests/test_live_store.py::test_record_intent_aceita_excecoes_de_is_immediate` um `WITHDRAW` com `execute_on == decided_on` e `reason="piso_55000_1.00pct_mes_min1000"` (o label real da política, nunca `"stop"`); confirmo que **falha com `ValueError`** antes do passo e passa depois. Sem este passo, o passo 8 mata o supervisor (premissas 9-11) |
| 4 | Em `src/live/runtime.py`: remover `_withdraw`, `_withdraw_manual_step`, `_apply_liquidation_fill`, `_finish_withdrawal` e o ramo `elif intent.kind == IntentKind.WITHDRAW` dentro de `reconcile_pending_fills`; remover o import de `liquidation_quantity` de `backtest.sizing` (só ele deixa de ser usado — `has_free_slot`/`initial_stop`/`plan_entry` continuam); atualizar a docstring de `reconcile_pending_fills`, que hoje dedica dois parágrafos ao caso WITHDRAW | `src/live/runtime.py` | `grep -n "_withdraw_manual_step\|_apply_liquidation_fill\|_finish_withdrawal\|def _withdraw(\|liquidation_quantity" src/live/runtime.py` vazio; `py_compile` limpo |
| 5 | **[reviewer — hipótese nº1, bloqueante]** Em `reconcile_pending_fills`, inserir `self._restore_robot_state(account.policy_state)` logo após o `_load_account` (antes do laço), replicando o padrão já documentado em `unfreeze()` (premissa 13). Comentário curto no lugar: sem isso, a linha `account.policy_state = self._robot_state()` do fim do método (que **não** é removida pelo passo 4 — está fora do `for`) grava, num processo recém-iniciado, uma `FloorSkim` virgem por cima do estado real, apagando `_paid_month`/`_pool`/`_requested` | `src/live/runtime.py` | **RED primeiro:** `test_reconcile_pending_fills_nao_apaga_estado_da_politica_de_saque` — grava `policy_state` com `_paid_month`/`_pool` não triviais, instancia um `LiveRuntime` **novo** (política virgem, como um `step` de cron), chama `reconcile_pending_fills()` **sem nenhuma intent EXECUTING**, recarrega a conta e afirma que `policy_state["withdrawal"]` está **idêntico**. Falha hoje (vem zerado) |
| 6 | **[reviewer — hipótese nº4, bloqueante]** Novo helper `_expire_withdraw_advice(self, conn, account, session) -> int` em `LiveRuntime`: lê `store.pending_withdraw_intents`; se vier **mais de uma**, `self._log(level="error", source="saque", ...)` com os ids (invariante quebrada tem de gritar, não passar batido); para cada recomendação cujo `(decided_on.year, decided_on.month) != (session.year, session.month)`: `store.claim_intent(conn, i.id, PENDING, EXPIRED)` — se devolver `False`, **pula** (outro processo já tratou) —, depois `self.withdrawal.on_executed(i, 0.0)` e `self._log(level="warn", source="saque", ...)` com `{"intent_id": i.id, "valor": i.amount}`. Devolve quantas expirou. Docstring registra a invariante que torna `on_executed` correto: `FloorSkim._requested` é um escalar global (premissa 14), então `live/` **não** pode creditar `_pool` na mão (regra 6) — o que `live/` garante é a **ordem**: nenhuma recomendação nova é decidida enquanto uma vencida ainda estiver `PENDING`, e é por isso que este helper roda em `close_and_decide` **e** em `execute_session` | `src/live/runtime.py` | Coberto pelos testes dos passos 7 e 8 (o helper não é chamado direto por ninguém de fora) |
| 7 | Em `close_and_decide`: logo após `self._restore_robot_state(...)` e **antes** de `self.withdrawal.on_close(...)`, chamar `self._expire_withdraw_advice(conn, account, session)`; no laço que grava `intents`, para cada `intent.kind == WITHDRAW` acrescentar `self._log(level="warn", source="saque", ...)` com o valor logo após `store.record_intent` (item 2.2 do plano original: `warn` porque `--notify-min-level` default é `warn`); acrescentar `"saques_expirados"` ao `StepReport.detail` | `src/live/runtime.py` | `test_saque_expira_na_virada_do_mes_e_devolve_valor_a_fila` (duas sessões em meses civis diferentes): a recomendação do mês 1 nunca confirmada vira `EXPIRED` no fecho do mês 2, `rt.withdrawal.policy._pool` reflete o valor devolvido, existe evento `warn`/`saque`. E `test_recomendacao_de_saque_gera_evento_warn_notificado`: `_RecordingNotifier` recebe o evento de nível `warn` com o valor (hoje a decisão de saque não notifica nada) |
| 8 | Reescrever `execute_session`: (a) apagar o passo "2. saque programado" inteiro (`for intent in saques: self._withdraw(...)`) e a lista `saques`; (b) **logo após o passo 1 (expiração por `stale_intents`) e antes de qualquer venda**, chamar `self._expire_withdraw_advice(conn, account, session)` — é isto que impede a recomendação de liquidez do 1º pregão do mês novo de coexistir com a do mês anterior (premissas 14-15); (c) o passo "4. saque por evento de liquidez" passa a **só** `store.record_intent(...)` + `self._log(level="warn", source="saque", ...)` com o valor — nenhuma execução, nenhuma `Order`; (d) renomear `done["saques"]` → `done["recomendacoes_saque"]` e acrescentar `done["saques_expirados"]`; (e) atualizar a docstring do módulo (seção "ABERTURA de D+1", linhas 24-28) e a de `execute_session` (que ainda cita `_withdraw`) | `src/live/runtime.py` | **RED primeiro, dois testes:** (1) `test_saque_recomendado_nao_move_caixa_nem_gera_ordem` — `execute_session` com recomendação PENDING deixa `account.cash`/posições intactos e `live_orders` vazia (hoje o dinheiro se move); (2) **`test_recomendacao_de_saque_por_liquidez_e_gravada_sem_matar_o_supervisor`** — força uma venda que credita caixa + `on_liquidity` devolvendo valor > 0, e afirma que `execute_session` **retorna normalmente** com `recomendacoes_saque == 1`, sem `ValueError`. Este 2º teste falha HOJE com `ValueError: look-ahead` (premissa 9) e é a prova do achado nº2 |
| 9 | Reescrever `reconcile_broker_cash` como detector puro: um ramo só — `abs(diff) > _DEPOSIT_TOLERANCE` → `self._log(level="warn", source="runtime", ...)` com o número, o sinal e a instrução ("se foi aporte seu, registre em /operacao; se foi saque seu, confirme em /operacao"), **nunca** `account.cash +=`; `StepReport` sempre com a chave `"diferenca"`; remover `_apply_deposit` (fica sem chamador) e ajustar a docstring do módulo/da função, que hoje descreve o crédito automático | `src/live/runtime.py` | Reescrevo `test_reconcile_broker_cash_credita_deposito_e_e_idempotente` → `test_reconcile_broker_cash_nunca_credita_so_avisa_pra_mais_ou_pra_menos`: diff de **+500** não muda `acc.cash`, `live_deposits` continua **vazia**, existe evento `warn`; `test_reconcile_broker_cash_encolhimento_nao_ajusta_so_avisa` e `test_reconcile_broker_cash_sem_saldo_externo_e_no_op_silencioso` continuam verdes; atualizo `test_run_once_aciona_reconcile_broker_cash_no_pre_open` (chave `"diferenca"`, `acc.cash` inalterado) |
| 10 | Novo `confirm_withdrawal(self, amount: float, session=None, intent_id: Optional[int] = None) -> StepReport`, nesta ordem exata: (1) `amount <= 0` → `StepReport("withdraw_reject", detail={"motivo": "valor inválido"})` sem abrir banco; (2) abre `store.live_journal`, `_load_account` (None → `withdraw_reject`), `_restore_robot_state`; (3) chama `self._expire_withdraw_advice(...)` **antes de escolher a recomendação** (nunca confirmar contra uma recomendação vencida); (4) `pendentes = store.pending_withdraw_intents(...)` — vazia → `withdraw_reject` motivo `"sem recomendação pendente"`, **sem tocar em caixa**; com `intent_id` → seleciona por id (não achou → reject); sem `intent_id` e `len == 1` → essa; sem `intent_id` e `len > 1` → **reject** listando os ids ("informe o intent_id"), nunca adivinhar a mais antiga; (5) **`if not store.claim_intent(conn, intent.id, PENDING, DONE): return withdraw_reject`** motivo `"recomendação já confirmada ou expirada"` — esta linha vem ANTES de qualquer mutação de caixa e é a trava anti-duplo-clique; (6) `equity_before = self._last_equity_before(conn, account.id, session)`; (7) `account.cash -= amount; account.external_cash += amount; account.withdrawn_total += amount` — **sem clamp e sem rejeitar por caixa insuficiente** (decisão do usuário, ver §5): se `account.cash` ficar negativo, `self._log(level="warn", source="saque", ...)` avisando que a divergência será apontada por `reconcile_broker_cash`; (8) `store.record_withdrawal(..., requested=intent.amount, executed=amount, equity_before=..., fees_paid=0.0, liquidated=[])`; (9) `self.withdrawal.on_executed(intent, amount)`; (10) `account.policy_state = self._robot_state()`, `store.save_account`, `self._log(level="info", source="saque", ...)`; (11) `StepReport("withdraw_confirm", session, detail={"intent_id", "recomendado", "confirmado", "caixa"})`. Helper `_last_equity_before(conn, account_id, session)`: último `equity` de `store.equity_series` com `date <= session`; **nenhuma linha** (conta nova) → cai em `account.cash` (sem posição, caixa É o equity) e loga `warn` se `account.positions` não estiver vazio | `src/live/runtime.py` | Cinco testes em `tests/test_live_runtime.py`: `test_confirm_withdrawal_debita_caixa_credita_externo_e_fecha_intent` (recomendação R$X, confirma R$Y, `cash -= Y`, `external_cash += Y`, `withdrawn_total += Y`, intent `DONE`, linha em `live_withdrawals` com `requested=X, executed=Y`); `test_confirm_withdrawal_sem_recomendacao_pendente_rejeita_sem_mexer_no_caixa`; **`test_confirm_withdrawal_duas_vezes_debita_uma_so_vez`** (mesma recomendação, duas chamadas: 2ª devolve `withdraw_reject` e `cash` é o mesmo da 1ª — falsifica a trava do item 5); **`test_confirm_withdrawal_valor_menor_devolve_falta_a_fila_e_maior_nao_devolve`** (Y<X → `policy._pool` cresce a diferença; Y>X → `_pool` não muda — documenta o `on_executed` existente); **`test_confirm_withdrawal_funciona_com_disjuntor_acionado`** (`risk_guard` congelado → confirmação passa; premissa 17, não exige código novo); e `test_confirm_withdrawal_acima_do_caixa_debita_mesmo_assim_e_avisa` (cash fica negativo, evento `warn`, **nenhuma** rejeição) |
| 11 | Ajustar `status()`: filtrar `pend` para excluir `kind == WITHDRAW` e concatenar com `store.pending_withdraw_intents(conn, account.id)` (todas as recomendações pendentes, de qualquer dia) em `intencoes_pendentes`; **acrescentar `"id": i.id` ao dict de cada item** (premissa 18 — sem ele a UI não consegue vincular a confirmação a uma recomendação específica, que é o que o passo 15 precisa) | `src/live/runtime.py` | `test_status_mostra_recomendacao_de_saque_pendente_varios_dias_depois` (recomendação com `decided_on` de N>1 dias atrás ainda aparece numa sessão bem posterior) **e** afirma que o item traz `id` não-nulo |
| 12 | Remover de `tests/test_live_runtime.py` os testes que só existiam para a execução automática: `test_saque_manual_liquidacao_fica_pendente_e_completa_apos_confirmacao` (494), `test_saque_manual_liquidacao_em_duas_pernas` (573), `test_saque_automatico_com_liquidacao_permanece_sincrono` (669); reescrever `test_withdrawal_flui_e_estado_sobrevive_a_restart` (368) para o fluxo novo — recomendação → `confirm_withdrawal` → **`LiveRuntime` novo** (processo novo) → política não repaga o mesmo mês —, e **sem a asserção condicional** que o plano original (Lote 5) marca como defeito (`if d2.year == d0.year and d2.month == d0.month:`): as datas passam a ser fixadas pelo teste | `tests/test_live_runtime.py` | `grep -n "_withdraw(\|_withdraw_manual_step\|_apply_liquidation_fill" tests/test_live_runtime.py` vazio; `grep -n "if d2.year ==" tests/test_live_runtime.py` vazio; `pytest -q tests/test_live_runtime.py -k "withdrawal or saque"` verde |
| 13 | Em `scripts/run_live.py`: `from datetime import date` no topo; `cmd_sacar(args)` → `build(args)`, `session = date.fromisoformat(args.data) if args.data else None`, `rt.confirm_withdrawal(args.valor, session, intent_id=args.intent_id)`, imprime o `StepReport`, `sys.exit(1)` se `action != "withdraw_confirm"`; subparser `sacar` com `valor: float` posicional, `--intent-id` (int, opcional) e `--data` (opcional). O `--intent-id` existe pelo mesmo motivo do `confirm <order_id>` que já existe: um `sacar` repetido (cron, dedo no Enter) não pode confirmar "o que estiver pendente" às cegas. Acrescentar a linha ao docstring do módulo, no bloco de exemplos (linhas 3-12) | `scripts/run_live.py` | Em `tests/test_run_live_cli.py` (fixture `isolated_db` já existe): `test_cmd_sacar_confirma_recomendacao_pendente_debita_caixa`, `test_cmd_sacar_sem_recomendacao_pendente_sai_com_erro` (`pytest.raises(SystemExit)`), `test_cmd_sacar_com_intent_id_errado_sai_com_erro_sem_mexer_no_caixa` |
| 14 | Em `src/dashboard/app.py`: rota `@app.post("/operacao/sacar")` `operacao_sacar`, espelhando `operacao_aportar` (parse de `amount`, guarda de conta inexistente, captura de `LegacyPaperAccountError`), lendo também `intent_id` do form (`_parse_optional_float` → int, ausente = `None`) e chamando `live_service._build_runtime(conta.mode, conta.initial_capital).confirm_withdrawal(amount, intent_id=intent_id)` — diferente de `operacao_aportar`, precisa da política real (`WithdrawalRobot.on_executed`); quando `report.action != "withdraw_confirm"`, renderiza `erro` com `report.detail["motivo"]`; quando confirma, `saque_msg = f"Saque de R$ {amount:.2f} confirmado."` via `_operacao_ctx(saque_msg=...)` (premissa 20) | `src/dashboard/app.py` | Em `tests/test_dashboard_app.py` (`isolated_journal`/`client`/`_create_account` já existem): `test_operacao_sacar_confirma_recomendacao_pendente_debita_caixa_e_credita_externo`, `test_operacao_sacar_sem_recomendacao_pendente_devolve_erro_sem_mexer_no_caixa`, `test_operacao_sacar_valor_invalido_nao_mexe_no_caixa`, `test_operacao_sacar_sem_conta_devolve_erro_sem_criar_saque`, `test_operacao_sacar_duplo_post_debita_uma_so_vez` (dois POSTs idênticos → 1 linha em `live_withdrawals`, caixa debitado uma vez) |
| 15 | Em `src/dashboard/templates/partials/operacao_body.html`: seção "Confirmar saque" logo **após** a de "Registrar aporte" (que termina na linha **280**), reaproveitando `class="ops-deposit stagger"`/`class="ops-deposit-form"` (sem CSS novo). Renderiza **um form por recomendação pendente** — `{% for i in s.intencoes_pendentes if i.tipo == "withdraw" %}` — com `<input type="hidden" name="intent_id" value="{{ i.id }}">` e `amount` **pré-preenchido** com `value="{{ '%.2f'|format(i.valor) }}"` (editável: confirmar valor diferente é legítimo, ver passo 10); sem nenhuma recomendação, a seção mostra a frase "Nenhuma recomendação de saque pendente." e nenhum form (nunca um botão que move dinheiro sem recomendação); `{% if saque_msg %}` para o banner de sucesso. Ajustar a frase da linha **338** ("valem para o próximo pregão") para ressalvar que a recomendação de saque fica na fila até ser confirmada ou expirar na virada do mês | `src/dashboard/templates/partials/operacao_body.html` | Os testes do passo 14 batem 200; `resp.text` contém "Confirmar saque", o `intent_id` da recomendação e o valor pré-preenchido; com zero recomendações contém "Nenhuma recomendação de saque pendente." e **não** contém `hx-post="/operacao/sacar"`; `grep -n 'name="intent_id"' src/dashboard/templates/partials/operacao_body.html` não vazio |
| 16 | Rodar a prova (§4) e varrer resquício do mecanismo antigo: `grep -rn "IntentKind.WITHDRAW" src/live/runtime.py` só aparece em contexto de registro/notificação/expiração, nunca de `Order`; `grep -rn "_apply_deposit" src/` vazio | — | `../meta/.venv/Scripts/python.exe -m pytest -q tests/test_live_store.py tests/test_live_runtime.py tests/test_run_live_cli.py tests/test_dashboard_app.py tests/test_live_robots.py` → exit 0 |

> Cada passo é uma ação com efeito verificável, não um tema. Ordem executável: passo N só depende de 1..N-1. Dois pontos de ordem que **não** podem ser trocados: o passo 3 (`is_immediate`) precede o passo 8 (que grava a intent de liquidez) — invertido, o passo 8 não tem como ficar verde; e o passo 6 (helper de expiração) precede 7, 8 e 10, que são seus três chamadores. O passo 1 é pré-requisito de todos os passos de dashboard, por isso vem primeiro apesar de não ser código.

## 4. Prova de conclusão (uma só)

**Origem:** ⬜ comando/teste que já existe ☑ asserção nova em teste existente ⬜ teste novo (justifique por que 1 e 2 não servem) ⬜ estado observável

> Os 5 arquivos de teste já existem (`tests/test_live_runtime.py`, `tests/test_live_store.py`,
> `tests/test_run_live_cli.py`, `tests/test_dashboard_app.py`, `tests/test_live_robots.py`);
> esta feature acrescenta funções de teste novas e reescreve/remove um punhado de testes
> obsoletos dentro deles — nenhum harness/fixture novo é criado (reaproveita `_runtime`,
> `isolated_db`, `isolated_journal`, `_RecordingNotifier`, `_FakeCashBroker`,
> `_create_account` já existentes). `tests/test_live_robots.py` entra na prova porque o
> passo 3 escreve `core/live_models.py` e é lá que a semântica de `is_immediate` está
> assertada hoje (linhas 116/132/148/195) — o arquivo não é editado, só protegido.

```
../meta/.venv/Scripts/python.exe -m pytest -q tests/test_live_store.py tests/test_live_runtime.py tests/test_run_live_cli.py tests/test_dashboard_app.py tests/test_live_robots.py
```

**O que essa prova garante:** cobre os três pilares do Lote 2 — (a) recomendação de
saque nunca move dinheiro nem gera ordem (`test_saque_recomendado_nao_move_caixa_nem_gera_ordem`),
(b) confirmação humana move dinheiro corretamente, **uma vez só**, e fecha a
recomendação (`test_confirm_withdrawal_*`, testes de CLI/dashboard), (c)
`reconcile_broker_cash` nunca mais credita sozinho
(`test_reconcile_broker_cash_nunca_credita_so_avisa_pra_mais_ou_pra_menos`) — mais os
achados do planejamento e da revisão: expiração mensal devolve o valor à fila,
recomendação fica visível no painel por todo o mês, o saque por liquidez **não** mata
o supervisor, e um restart não apaga o estado da política.

**Teste de falsificação (obrigatório) — seis cenários de feature quebrada, cada um com
o teste que o pega:**

| Cenário quebrado | Teste que falha |
|------------------|-----------------|
| `execute_session`/`close_and_decide` voltam a debitar `account.cash` ou gerar `Order` para um `WITHDRAW` | `test_saque_recomendado_nao_move_caixa_nem_gera_ordem` |
| a recomendação por evento de liquidez volta a ser recusada por look-ahead (supervisor morre no `cmd_loop`) | `test_recomendacao_de_saque_por_liquidez_e_gravada_sem_matar_o_supervisor` |
| `reconcile_pending_fills` volta a persistir `policy_state` sem restaurar (restart → saque duplicado no mês seguinte) | `test_reconcile_pending_fills_nao_apaga_estado_da_politica_de_saque` |
| a confirmação deixa de ser atômica (duplo-clique debita duas vezes) | `test_confirm_withdrawal_duas_vezes_debita_uma_so_vez` + `test_operacao_sacar_duplo_post_debita_uma_so_vez` |
| `reconcile_broker_cash` volta a creditar divergência positiva | `test_reconcile_broker_cash_nunca_credita_so_avisa_pra_mais_ou_pra_menos` |
| `confirm_withdrawal` move dinheiro sem recomendação `PENDING` correspondente | `test_confirm_withdrawal_sem_recomendacao_pendente_rejeita_sem_mexer_no_caixa` |

**RED antes de GREEN:** obrigatório (T3). Cada teste novo é escrito e confirmado
FALHANDO contra o código anterior à mudança do seu passo. Os quatro RED que **importam**
(porque falham por motivos diferentes, não por `AttributeError` de método que ainda não
existe) estão marcados na tabela de passos como "**RED primeiro**": passos 3, 5, 8 e o
`test_confirm_withdrawal_duas_vezes_debita_uma_so_vez` do passo 10. Se algum deles
passar antes da mudança, o teste está testando a coisa errada e tem de ser reescrito
antes de seguir.

## 5. Riscos e gatilhos de escalação

### Riscos ATIVOS (mitigados no plano)

- ~~**Duplo-confirmação não é idempotente**~~ → **[reviewer, hipótese nº5]** a
  "paridade com `/operacao/aportar`" **não se sustenta**: aportar é `+=` idempotente na
  intenção do usuário (aportar duas vezes é aportar duas vezes), saque é liquidar UMA
  recomendação específica exatamente uma vez. Mitigado no passo 10 item (5): a transição
  `PENDING → DONE` passa por `store.claim_intent` (`UPDATE ... WHERE id=? AND status=?`,
  `rowcount == 1`) **antes** de qualquer mutação de caixa. Quem perde a corrida recebe
  `withdraw_reject` e não move nada.
- ~~**Mais de uma recomendação `PENDING` simultânea**~~ → **[reviewer, hipótese nº4]** o
  cenário é **real**, não hipotético: `run_once` roda `execute_session` (OPEN) **antes**
  de `close_and_decide` (POST_CLOSE), então no 1º pregão de um mês novo uma recomendação
  por liquidez nasce antes de a do mês anterior expirar. Mitigado em três camadas: (a)
  `_expire_withdraw_advice` roda no início de `execute_session`, de `close_and_decide` e
  de `confirm_withdrawal`; (b) confirmação e expiração operam por **id de intent**, nunca
  por "a mais antiga"; (c) se duas `PENDING` ainda assim coexistirem, sai evento `error`
  e `confirm_withdrawal` **recusa** em vez de adivinhar.
- **Caixa insuficiente na confirmação** — `confirm_withdrawal` NÃO rejeita nem faz clamp
  ao caixa disponível, mesmo que `account.cash` fique negativo. **Decisão do usuário,
  registrada aqui de propósito para ninguém "consertar" depois:** o sistema só precisa
  saber quanto o dono pretende sacar; qualquer divergência real com o saldo da corretora
  é capturada por `reconcile_broker_cash` (item 2.4, mesmo lote), não por uma trava aqui.
  O comportamento antigo (`_finish_withdrawal` fazia `min(want, account.cash)`) morre
  junto com o método.

### Riscos CONHECIDOS (aceitos, sem passo no plano)

- **`reconcile_broker_cash` vira `warn` recorrente** enquanto a divergência não for
  resolvida — 1 evento por pregão (só PRE_OPEN), sem deduplicação. Deduplicar exigiria
  ler `live_events` ou guardar estado (inútil no caminho `step`/cron, que é processo
  novo a cada chamada); a cadência de 1×/dia não justifica o custo. Aceito.
- **Taxas/IR cobrados pela corretora no saque não são rastreados**: `record_withdrawal`
  recebe `fees_paid=0.0` e `liquidated=[]`, porque nesta arquitetura quem vende e quem
  paga taxa é o humano, fora do sistema. Fora do escopo do Lote 2.
- **Processo fora do ar por 2+ meses** faz `FloorSkim` perder a acumulação de "sessões"
  do mês (`_sessions` conta pregões observados). `backtest/withdrawal.py` é **intocável**
  por decisão explícita do plano original — registrado, não corrigido.
- **Não há lembrete periódico** de recomendação pendente: a notificação sai uma vez, no
  momento da decisão. Quem não vê o alerta depende do painel `/operacao`.
- **Não há caminho manual para "vendi uma posição na corretora para levantar o saque"** —
  exigiria reconciliação de posição, fora do escopo deste lote.
- **`data/raw` ausente na worktree** (passo 1): gap pré-existente do ambiente, não do
  código; bloqueia os testes de dashboard se não for resolvido primeiro.
- **Comentário desatualizado em `schema.sql`** (~304-311, descreve `mt5_reconciliation`
  como se creditasse automaticamente): `schema.sql` não está na lista de arquivos desta
  feature; cosmético, `origin` não tem `CHECK`. Não corrigido para não ampliar escopo.

### Gatilhos de escalação

Escalarei se: precisar mudar contrato de `backtest/withdrawal.py`, `live/robots.py` ou
`dashboard/live_service.py` (não só ler — `core/live_models.py` já está autorizado pelo
reviewer, ver §6 correção 2); se a correção do passo 3 quebrar algum teste de
`tests/test_live_robots.py` (sinal de que a semântica de `is_immediate` é mais carregada
do que a revisão apurou); ou se `data/raw` da `meta/` principal também estiver incompleto
(passo 1 sem solução).

## 6. Correções do plan-reviewer

**VEREDICTO: CORRIGIDO (liberado para execução).** Natureza: **SUBSTANTIVAS**.
Passos 13 → 16. Nenhuma nova revisão: o feature-agent re-lê e executa.

Base da revisão: worktree `../meta-FEAT-002`, HEAD `b6102f3` (FEAT-001), árvore limpa.
Todas as premissas 8-21 da §2b foram verificadas no código, não inferidas.

| # | O que estava errado | Correção aplicada | Motivo |
|---|---------------------|-------------------|--------|
| 1 | `reconcile_pending_fills` sobrescreve `account.policy_state` com o estado em memória **sem** `_restore_robot_state` antes (`runtime.py:971`). O passo 3 antigo removia só o ramo `WITHDRAW` — a linha ofensora fica **fora** do laço e sobrevivia intacta | **Passo 5 novo** (restaurar antes de persistir, padrão de `unfreeze()`), com RED obrigatório: `test_reconcile_pending_fills_nao_apaga_estado_da_politica_de_saque` | Hipótese nº1. Num processo novo (cron `step`, restart do supervisor) isso apaga `_paid_month`/`_pool` → a política recomenda o **mesmo mês de novo** → saque duplicado de verdade. É o furo mais caro dos cinco e não seria pego por nenhum teste do plano original |
| 2 | `core/live_models.py` estava em "Só lê", mas a recomendação de saque por liquidez (`kind=WITHDRAW`, `execute_on == decided_on`, `reason=label`) **não** é `is_immediate` → `record_intent` levanta `ValueError` → `cmd_loop` trata como fatal e **mata o supervisor** | **Passo 3 novo** (estende `is_immediate` p/ `WITHDRAW` same-day) + `core/live_models.py` movido para "Escreve" + teste `test_recomendacao_de_saque_por_liquidez_e_gravada_sem_matar_o_supervisor` no passo 8 | Hipótese nº2. **Ampliação de escopo autorizada e registrada, não escalada:** o plano original já prescreve o timing same-day ("`on_liquidity` … antecipa a *data* da recomendação para um dia de rotação, preservando a paridade de timing com o backtest"), então fechar o buraco é completar a letra do plano, não inventar arquitetura. Sem colisão: a run é 100% sequencial e nenhuma feature seguinte escreve `core/live_models.py` (FEAT-005 escreve `core/models.py`, arquivo diferente). **Ação para o orquestrador: acrescentar `src/core/live_models.py` à coluna "Escreve" de FEAT-002 no `EXEC-MAP.md`.** O bug é PRÉ-EXISTENTE (`runtime.py:562` já chama `record_intent` assim hoje) — o plano só o preservava |
| 3 | Passo 7 antigo era mudo sobre o que fazer quando a confirmação excede o caixa | Passo 10 item (7): **sem clamp, sem rejeição**, debita mesmo deixando `cash` negativo + evento `warn`; registrado em §5 como decisão do usuário, com o teste `test_confirm_withdrawal_acima_do_caixa_debita_mesmo_assim_e_avisa` | Hipótese nº3, decisão do usuário já tomada. Explicitado no plano **e** no bloco de riscos justamente para que um code-reviewer futuro não "conserte" isso adicionando uma trava. A divergência real é papel de `reconcile_broker_cash` (2.4, mesmo lote) |
| 4 | Expiração só em `close_and_decide` (POST_CLOSE), mas `run_once` roda `execute_session` (OPEN) **antes** — no 1º pregão de um mês novo nasce uma recomendação de liquidez com a do mês anterior ainda `PENDING`; como `FloorSkim._requested` é escalar **global**, a expiração tardia credita ao pool o valor da recomendação **nova**, corrompendo a fila | Expiração extraída para o helper **`_expire_withdraw_advice` (passo 6 novo)**, chamado em `close_and_decide` (7), no início de `execute_session` (8) e em `confirm_withdrawal` (10); expiração e confirmação passam a operar **por id de intent**; >1 `PENDING` vira evento `error` e recusa de confirmação em vez de chute | Hipótese nº4. A correção preserva a regra 6 (`live/` não credita `_pool` na mão — só garante a **ordem** que torna `on_executed` correto), e a docstring do helper registra essa invariante para quem vier depois |
| 5 | §5 declarava "duplo-clique: mitigação nenhuma, por paridade com `/operacao/aportar`" | Passo 2 ganha `store.claim_intent` (`UPDATE … WHERE id=? AND status=?`, `rowcount==1`); passo 10 item (5) faz o claim **antes** de qualquer mutação de caixa; testes `test_confirm_withdrawal_duas_vezes_debita_uma_so_vez` e `test_operacao_sacar_duplo_post_debita_uma_so_vez` | Hipótese nº5. A paridade era falsa: aportar é `+=` idempotente na intenção; saque é liquidar UMA recomendação exatamente uma vez. "Ler estado → decidir → gravar" sem trava é exatamente a classe de bug que esta feature existe para eliminar |
| 6 | CLI `sacar <valor>` e o form do dashboard confirmavam "o que estiver pendente", sem vínculo com uma recomendação | `--intent-id` no CLI (passo 13) e `<input type="hidden" name="intent_id">` no form (passo 15); `confirm_withdrawal` ganha o parâmetro e **recusa** quando há >1 pendente sem id | Mesmo padrão do `confirm <order_id>` que já existe. Um `sacar` repetido por cron/script deixa de mover dinheiro sem decisão humana explícita a cada vez |
| 7 | Form de saque sem valor pré-preenchido; `status()` não expõe `id` da intenção | Passo 11 acrescenta `"id"` ao item de `intencoes_pendentes`; passo 15 pré-preenche `amount` com o valor recomendado (editável) e renderiza um form por recomendação; sem recomendação, **nenhum** form | Reduz erro de digitação e torna impossível um botão de saque existir sem recomendação por trás |
| 8 | Nenhum teste sobre disjuntor × saque, nem sobre confirmar valor ≠ recomendado | Passo 10: `test_confirm_withdrawal_funciona_com_disjuntor_acionado` e `test_confirm_withdrawal_valor_menor_devolve_falta_a_fila_e_maior_nao_devolve` | Nenhum dos dois exige código novo (`CircuitBreaker` já só veta `ENTER`; `on_executed` já só devolve `falta>0` à fila) — os testes **documentam** comportamento correto que hoje ninguém protege |
| 9 | `_last_equity_before` sem fallback para conta sem nenhuma linha em `equity_series` | Passo 10: fallback explícito para `account.cash` (sem posição, caixa É o equity) + `warn` se houver posição | Conta nova confirmando o primeiro saque não pode quebrar nem gravar `equity_before` inventado |
| 10 | Prova de conclusão sem falsificação por cenário; RED genérico ("todos os testes dos passos 4-12") | §4 reescrita: tabela de 6 cenários quebrados × teste que os pega; RED restrito aos 4 que falham por motivo **semântico** (passos 3, 5, 8 e o duplo-clique do 10), não por `AttributeError` | Um RED que falha só porque o método ainda não existe não prova nada. Os 4 marcados falham contra código que **existe e está errado** |
| 11 | `tests/test_live_robots.py` fora da prova, embora o passo 3 escreva `core/live_models.py` | Acrescentado ao comando da §4 (arquivo protegido, não editado) | É onde a semântica de `is_immediate` está assertada hoje (linhas 116/132/148/195); conferido que nenhuma dessas asserções quebra com a mudança |
| 12 | Números de linha do template errados ("~280", "~338"); riscos fora de escopo não registrados | Corrigidos para 258-280 / 335-366 (premissa 19); §5 reorganizada em "ATIVOS (mitigados)" × "CONHECIDOS (aceitos)", com taxas/IR, ≥2 meses fora do ar, ausência de lembrete periódico, venda manual para levantar caixa e fadiga de alerta do `reconcile_broker_cash` todos registrados | Pontual; e o que é fora de escopo tem de ficar escrito no plano, não sumir |
| 13 | Reescrita de `test_withdrawal_flui_e_estado_sobrevive_a_restart` não dizia o que fazer com a asserção condicional que o próprio plano original (Lote 5) aponta como defeito | Passo 12 exige datas fixadas pelo teste e `grep -n "if d2.year ==" … ` vazio como prova | O teste que deveria provar "estado sobrevive a restart" é justamente onde o assert às vezes não roda — deixá-lo condicional depois de reescrever o fluxo inteiro seria manter a feature sem prova |

## 7. Registro de execução

> Preenchido pelo feature-agent após executar.

**Passos executados:** 16/16
**Commits:**
- `64abe3d` feat(blindagem): FEAT-002 passos 2-5 - store de saque, is_immediate WITHDRAW, remove execucao automatica
- `9059422` feat(blindagem): FEAT-002 passos 6-8 - expiracao de recomendacao e saque vira recomendacao pura
- `c0ef1e7` feat(blindagem): FEAT-002 passo 9 - reconcile_broker_cash vira detector puro
- `d25e0b4` feat(blindagem): FEAT-002 passos 10-11 - confirm_withdrawal e status() com recomendacao de saque
- `58fc88c` test(blindagem): FEAT-002 passo 12 - remove testes de saque automatico, reescreve estado-sobrevive-a-restart
- `209d979` feat(blindagem): FEAT-002 passo 13 - CLI 'sacar' confirma recomendacao de saque
- `020358f` feat(blindagem): FEAT-002 passo 14 - rota POST /operacao/sacar confirma recomendacao de saque
- `441784f` feat(blindagem): FEAT-002 passo 15 - template ganha secao "Confirmar saque"

(passo 1 não gerou commit — cópia de `data/raw/*.parquet` para a worktree, gitignored)

**Relatório do PRE-GATE (regra 18) — input obrigatório do code-reviewer:**
```
1. prova      ../meta/.venv/Scripts/python.exe -m pytest -q tests/test_live_store.py
              tests/test_live_runtime.py tests/test_run_live_cli.py
              tests/test_dashboard_app.py tests/test_live_robots.py
              → exit 0, 99/99 passing
2. lint       n/a: projeto não tem linter configurado (sem ruff/flake8 no repo)
3. typecheck  py_compile em todos os arquivos tocados (scripts/run_live.py,
              src/core/live_models.py, src/dashboard/app.py,
              src/journal/live_store.py, src/live/runtime.py,
              tests/test_dashboard_app.py, tests/test_live_runtime.py,
              tests/test_live_store.py, tests/test_run_live_cli.py) → ✅ todos OK
4. escopo     git diff --name-only plan/blindagem-operacao-real...HEAD →
              10 arquivos, todos declarados na seção 2 (nenhum fora do previsto)
5. higiene    grep por TODO/FIXME/console.log/print de debug introduzidos → só
              ocorrências de "todo" em prosa portuguesa (falso positivo); sem
              arquivo temporário; sem dependência nova não usada; nenhum
              marcador TEMP-RED-CHECK sobrevivente (usados só durante os RED
              dos passos 5, 8 e 10, revertidos antes do commit)
Rodadas até fechar: 1 (correção de pre-gate não consome tentativa do gate 2)
```

**Evidência da prova de conclusão:**
```
$ ../meta/.venv/Scripts/python.exe -m pytest -q tests/test_live_store.py tests/test_live_runtime.py tests/test_run_live_cli.py tests/test_dashboard_app.py tests/test_live_robots.py
........................................................................ [ 72%]
...........................                                              [100%]
============================== warnings summary ===============================
..\meta\.venv\Lib\site-packages\fastapi\testclient.py:1
  ...StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated...
99 passed, 1 warning in 4.93s
```

RED confirmado nos 4 pontos marcados como "RED primeiro" no plano — evidência capturada contra o código genuinamente anterior (não `AttributeError` de método inexistente):
- **Passo 3** (`is_immediate` WITHDRAW same-day): `test_record_intent_aceita_excecoes_de_is_immediate` — RED real
  `ValueError: look-ahead: execute_on (2026-08-14) <= decided_on (2026-08-14)...` antes da mudança; GREEN depois.
- **Passo 5** (`reconcile_pending_fills` restaura estado antes de persistir): RED capturado
  temporariamente removendo a linha `self._restore_robot_state(...)` — `AssertionError` comparando
  `policy_state["withdrawal"]` esperado (`_paid_month=[2030,1]`, `_pool` não-zero) contra o zerado
  (`_paid_month=None`, `_pool=0.0`) que o bug produz; GREEN com a linha restaurada.
- **Passo 8** (dois testes): RED capturado com `git checkout b6102f3 -- src/live/runtime.py
  src/core/live_models.py` (código genuinamente anterior à feature, mantendo `live_store.py` em
  HEAD para os helpers novos existirem) —
  `test_saque_recomendado_nao_move_caixa_nem_gera_ordem`: `AssertionError: assert 1 == 0` (saque
  ainda executava, `execu.detail["saques"] == 1`);
  `test_recomendacao_de_saque_por_liquidez_e_gravada_sem_matar_o_supervisor`:
  `ValueError: look-ahead: execute_on (2030-01-03) <= decided_on (2030-01-03)...` (achado nº2 da
  revisão, supervisor morreria via `cmd_loop`). Ambos GREEN após restaurar o código do passo 3-9 e
  aplicar a reescrita do passo 8.
- **Passo 10** (`test_confirm_withdrawal_duas_vezes_debita_uma_so_vez`): RED capturado substituindo
  temporariamente a trava `store.claim_intent(...)` por uma variante ingênua (busca a intent por id
  em TODAS, ignora status, marca DONE sem checagem atômica) — `AssertionError: assert 'withdraw_confirm'
  == 'withdraw_reject'` (2ª confirmação seguinte debitava de novo); GREEN com `claim_intent` restaurado.

**Desvios (triviais, com plano atualizado):**
- Passo 10: `_last_equity_before` recebe o objeto `AccountState` já carregado (não `account_id`) —
  evita um reload redundante do mesmo registro dentro da mesma transação; `confirm_withdrawal` já
  tinha a conta em mãos e ela não muda de identidade entre a leitura e a chamada do helper.
- Passo 12: as três remoções de teste e a reescrita de `test_withdrawal_flui_e_estado_sobrevive_a_restart`
  foram feitas junto do passo 8 (a suíte já estava quebrada pela mudança de `execute_session`) em vez
  de esperar a ordem estrita do plano — sem efeito no resultado, só na ordem de commits (passo 12 ficou
  em commit próprio, depois dos passos 9-11, mas o conteúdo bate com o que o plano descreve).

**Desvios relevantes para features seguintes:** nenhum além do já registrado no plano (§2:
`Intent.is_immediate` passou a aceitar `WITHDRAW` same-day; `reconcile_pending_fills` restaura estado
antes de persistir `policy_state`; `store.claim_intent` novo). `execute_session` não gera mais a chave
`"saques"` no `StepReport.detail` — quem consumia essa chave (nenhum código de produção fora dos testes
removidos consumia) precisa passar a olhar `"recomendacoes_saque"`/`"saques_expirados"`.
`reconcile_broker_cash` não gera mais a chave `"deposito"` — sempre `"diferenca"` (positiva ou negativa).

**Arquivos realmente tocados:** `scripts/run_live.py`, `src/core/live_models.py`,
`src/dashboard/app.py`, `src/dashboard/templates/partials/operacao_body.html`,
`src/journal/live_store.py`, `src/live/runtime.py`, `tests/test_dashboard_app.py`,
`tests/test_live_runtime.py`, `tests/test_live_store.py`, `tests/test_run_live_cli.py` —
idêntico à lista "Escreve" da seção 2, nenhuma divergência.

## 8. Definition of Done

- [x] Todos os passos da seção 3 executados
- [x] Prova de conclusão executada com evidência colada na seção 7
- [x] **PRE-GATE verde nos 5 itens**, com relatório na seção 7
- [x] Nenhum arquivo fora da seção 2 tocado (ou desvio justificado)
- [x] Testes da feature verdes; nada skipado
- [x] Sem `TODO`/código comentado/log de debug
- [x] Commits atômicos na convenção do projeto
- [ ] `code-reviewer` aprovou

## 9. Correção pós-rejeição do code-reviewer (tentativa 1/2)

**Issues bloqueantes corrigidas (3):**

| # | Issue | Correção | Arquivo |
|---|-------|----------|---------|
| 1 | `confirm_withdrawal` expirava a recomendação vencida por dentro de `_expire_withdraw_advice` (que muda `self.withdrawal` **só em memória**, via `on_executed(intent, 0.0)`), e os `return StepReport("withdraw_reject", ...)` que seguiam saíam **antes** de `account.policy_state = self._robot_state()`/`store.save_account` (que só rodavam no caminho de sucesso, mais abaixo). Repro do revisor confirmado: banco ficava com `_requested` antigo, evento dizia "volta pra fila", dinheiro sumia da fila. | `_expire_withdraw_advice` (`src/live/runtime.py:755-807`) agora persiste `account.policy_state`/`store.save_account` **dentro de si mesma**, sempre que `expiradas > 0` — mesmo padrão de `unfreeze()` (restaura → muta → persiste). Não depende mais de nenhum chamador lembrar de persistir depois de expirar. | `src/live/runtime.py` |
| 2 | Cobertura zero da expiração mensal e da notificação da recomendação — só havia menção em docstring, nenhum teste (`grep` confirmado pelo revisor). | 3 testes novos em `tests/test_live_runtime.py`: `test_saque_expira_na_virada_do_mes_e_devolve_valor_a_fila` (via `execute_session`, duas sessões em meses civis diferentes — derivadas do calendário real por `_pregao_e_pregao_do_mes_seguinte()`, não hardcodadas — confere `policy_state` do BANCO); `test_recomendacao_de_saque_gera_evento_warn_notificado` (`_RecordingNotifier` confirma o evento `warn`/`saque` de `close_and_decide`); `test_confirm_withdrawal_expira_recomendacao_vencida_e_persiste_policy_state` (reprodução exata da issue 1 — RED confirmado contra o código anterior à correção: `_requested` ficava `5000.0` em vez de `0.0` no banco). | `tests/test_live_runtime.py` |
| 3 | Bomba-relógio de calendário: `_create_withdraw_intent`/`_create_account_com_recomendacao` gravavam `decided_on=date(2026, 8, 3)` hardcodado, enquanto a rota `/operacao/sacar` e o CLI `sacar` (sem `--data`) confirmam contra `clock.session_date()` = hoje — a partir de 2026-09-01 a recomendação de teste passaria a estar vencida e os testes de confirmação quebrariam só por causa do calendário. | `decided_on`/`execute_on` agora derivados de `clock.session_date().replace(day=1)` / `clock.next_session(...)` — mesmo relógio que o código sob teste usa — nunca mais vencida no momento em que o teste roda, em qualquer mês. Mesmo padrão já usado em `test_withdrawal_flui_e_estado_sobrevive_a_restart` (passo 12). Import `date` do `datetime` removido de ambos os arquivos (ficou sem uso). | `tests/test_dashboard_app.py`, `tests/test_run_live_cli.py` |

**Issues não-bloqueantes corrigidas (2 de 3 — baratas):**
- `scripts/run_live_sim.py:174`: lia a chave obsoleta `"saques"` (sempre 0 em silêncio); agora lê `"recomendacoes_saque"` (nome real exposto por `execute_session` desde a execução original desta feature) e o rótulo impresso deixa de dizer "executados" (saque nunca mais é executado pela máquina).
- `src/journal/live_store.py:639-648`: `set_intent_payload` confirmado sem nenhum chamador (`grep -rn "set_intent_payload"` só achava a própria definição) e com docstring referenciando `_withdraw_manual_step` (já removido) — removida.
- `tests/test_live_runtime.py:576` (linha original apontada pelo revisor; deslocou para 589 após a inserção do helper de datas): `assert execu.detail.get("saques", 0) == 0` era assertiva morta (chave inexistente, nunca falharia) — removida; a asserção de `recomendacoes_saque` ao lado já prova o que importa.

**PRE-GATE (regra 18) da correção:**
```
1. prova (suite completa, nao so os 5 arquivos da prova original)
   ../meta/.venv/Scripts/python.exe -m pytest -q
   → 315 passed, 1 warning (baseline 312 + 3 testes novos), exit 0
2. lint       n/a: projeto nao tem linter configurado
3. typecheck  py_compile em src/live/runtime.py, tests/test_live_runtime.py,
              tests/test_dashboard_app.py, tests/test_run_live_cli.py,
              scripts/run_live_sim.py, src/journal/live_store.py → OK
4. escopo     git diff --name-only plan/blindagem-operacao-real...HEAD →
              11 arquivos (os 10 da execucao original + scripts/run_live.py,
              ja presente desde entao), todos dentro da secao 2 do plano;
              esta rodada de correcao tocou so os 6 arquivos autorizados no
              briefing do fixer (src/live/runtime.py, tests/test_live_runtime.py,
              tests/test_dashboard_app.py, tests/test_run_live_cli.py,
              scripts/run_live_sim.py, src/journal/live_store.py)
5. higiene    grep por TODO/FIXME/console.log/debug no diff da correcao →
              nenhum; nenhum arquivo temporario; nenhuma dependencia nova
Rodadas ate fechar: 1
```

**RED confirmado antes da correção (issue 1):** `test_confirm_withdrawal_expira_recomendacao_vencida_e_persiste_policy_state`
rodado com `git checkout -- src/live/runtime.py` (código genuinamente anterior à
correção, mantendo os testes novos): `AssertionError: assert 5000.0 == 0.0` em
`withdrawal_state["_requested"]` — reproduz exatamente o furo apontado pelo
revisor. GREEN após a correção de `_expire_withdraw_advice`.

**Commits da correção:**
- `67e6be7` fix(blindagem): FEAT-002 persiste policy_state ao expirar recomendacao de saque
- `e565cbe` test(blindagem): FEAT-002 cobre expiracao mensal do saque e notificacao warn
- `9bbe7df` fix(blindagem): FEAT-002 remove bomba-relogio de mes civil nas fixtures de saque
- `d5cd56d` chore(blindagem): FEAT-002 corrige chave obsoleta do saque no simulador

**Arquivos tocados nesta correção:** `src/live/runtime.py`, `tests/test_live_runtime.py`,
`tests/test_dashboard_app.py`, `tests/test_run_live_cli.py`, `scripts/run_live_sim.py`,
`src/journal/live_store.py` — idêntico à lista de escopo do briefing do fixer, nenhum
arquivo fora do previsto.

**Aguardando novo `code-reviewer` (tentativa 1/2 concluída).**
