# FEAT-001 — identidade-conta-corte-simulacao

> Plano de ação escrito pelo feature-agent, revisado (e corrigido quando necessário) pelo plan-reviewer.
> Status: `rascunho` → `em revisão` → `aprovado` → `executado` → `concluído`

**Status:** corrigido (tentativa 1/2 de correção pós-code-review concluída — ver seção 7; aguardando code-reviewer de novo)
**Run:** `blindagem-operacao-real` | **Plano original:** `C:\Users\Jeffe\.claude\plans\crie-um-plano-p-ra-gentle-papert.md` (seção "Lote 1 — Identidade da conta e corte da simulação", subitens 1.1–1.7, **mais o item 0.3 herdado de FEAT-000** — ver "Revalidação" e "Features adiadas" do EXEC-MAP)
**Tier:** T3 | **Wave:** 2 | **Isolamento:** worktree `../meta-FEAT-001`
**Branch:** `feat/blindagem-operacao-real-FEAT-001`

## 1. Problema / objetivo

Hoje o vocabulário de modo de corretora está fraturado em três grafias diferentes (`paper`/`manual`/`mt5` no CLI e no `<select>`, mas `paper`/`manual`/`broker` no `Broker.mode`/schema) — e é exatamente essa fratura que faz o botão "Iniciar" no dashboard emitir `--mode broker` para uma conta MT5 real, o argparse recusar, o processo morrer na hora, e o dashboard continuar mostrando "rodando" (crítico nº1 da revisão). Esta feature unifica o vocabulário em `manual`/`mt5`, tira `PaperBroker`/`ReplayFeed` de `src/` (viram test doubles), faz `LiveRuntime` recusar operar quando a conta e o broker instanciado divergem, corta os dois fallbacks silenciosos que hoje viram "paper" por baixo do capô, dá ao botão "Iniciar" uma prova de vida real do processo, e para de vazar defaults de simulação (capital fixo, disjuntor sempre nulo, `shares_per_lot` sem valor universal) para a conta real. Inclui, por herança de FEAT-000, a guarda que recusa `db_path == LIVE_DB_PATH` quando o broker é um test double — só dá para implementá-la agora que `PaperBroker` sai de produção.

**Estado atual (regra 6) — nada disto existe hoje:**
- `src/live/broker_mt5.py:84` — `MT5Broker.mode = "broker"`, divergente do `"mt5"` que CLI/dashboard/template usam. **Esta é a causa-raiz do crítico nº1.**
- `scripts/run_live.py:160-170,312` — `--mode` aceita `("paper","manual","mt5")` com `default="paper"`; `build()` tem `else: broker = PaperBroker(feed)` — fallback silencioso.
- `scripts/run_live.py:243-277` — `cmd_tickets`/`cmd_confirm` fazem `args.mode = "manual"` incondicionalmente, sem checar o modo real da conta.
- `src/dashboard/live_service.py:26-60` — `_build_runtime` tem `else: broker = PaperBroker(feed)`; `DEFAULT_CAPITAL = 1_000.0` hardcoded em `official_policy`/`BacktestConfig` independente do `initial_capital` real da conta; `risk_guard` nunca é passado (`status()` sempre reporta `disjuntor: None`).
- `src/dashboard/live_control.py` — `ProcessConfig` não tem campo `mt5_shares_per_lot`; `start()` nunca passa `--mt5-shares-per-lot`/`--mt5-symbol-map` para o processo filho (herda o default `1.0` do argparse, que a docstring de `MT5Broker` diz não ter valor universal); `start()` grava `pid`/`started_at` logo após `Popen`, sem checar se o processo sobreviveu.
- `src/journal/live_store.py:187-210` — `ensure_account` usa `ON CONFLICT(name) DO NOTHING`; se a conta já existe com modo diferente do pedido, a divergência é ignorada em silêncio.
- `src/journal/schema.sql:168` — `CHECK (mode IN ('paper','manual','broker'))`.
- `src/live/broker.py:83-149` — `PaperBroker` mora em `src/`.
- `src/live/feed.py:210-256` — `ReplayFeed` mora em `src/`.
- `src/live/runtime.py` — construtor não valida `db_path` contra broker test-double (item 0.3, adiado de FEAT-000); 8 pontos (`unfreeze`, `close_and_decide`, `execute_session`, `reconcile_pending_fills`, `reconcile_broker_cash`, `intraday_tick`, `status` ×2) chamam `store.load_account(conn, self.account_name)` sem checar se `account.mode == self.broker.mode`.
- `src/dashboard/templates/partials/operacao_body.html:127` — `<option value="paper">` ainda existe no `<select>`.

Delta desta feature: fechar todos os pontos acima.

## 2. Arquivos

**Escreve** (cria/edita):

*Produção:*
- `src/core/live_models.py` — novo `class BrokerMode(str, Enum)` (`MANUAL="manual"`, `MT5="mt5"`) — vocabulário canônico consumido pelo resto dos arquivos abaixo.
- `src/live/broker.py` — remove `PaperBroker` (vai para `tests/doubles.py`); `Broker` ganha `is_test_double: bool = False`; docstring/comentário de `mode` atualizado para `'manual' | 'mt5'`. **Também a docstring do módulo (linhas 12–24), que hoje enumera `PaperBroker` como implementação de `src/`.**
- `src/live/broker_mt5.py` — `MT5Broker.mode = "broker"` → `"mt5"` (`BrokerMode.MT5.value`).
- `src/live/feed.py` — remove `ReplayFeed` (vai para `tests/doubles.py`); **atualizar a linha 16 da docstring do módulo, que hoje lista `ReplayFeed` como implementação deste arquivo**.
- `src/live/runtime.py` — (a) guarda no `__init__`: recusa (`ValueError`) se `getattr(self.broker, "is_test_double", False)` e `Path(self.db_path).resolve() == Path(DB_PATH).resolve()` — **comparação por caminho RESOLVIDO, não por igualdade crua de objeto** (mesmo precedente de `scripts/run_live_sim.py::_ensure_disposable_sim_db`; com `==` puro, passar a mesma string/`Path` relativa driblaria a guarda, que é justamente o que o item 0.3 quer impedir). Ler `DB_PATH` do módulo em tempo de chamada (o monkeypatch de `tests/` depende disso); (b) novo método privado `_load_account(conn)` que chama `store.load_account` e recusa (`ValueError`, mensagem nomeando os dois modos) se `account.mode != self.broker.mode` — **devolve `None` quando a conta não existe, sem levantar**, porque os 8 call-sites dependem do ramo `if account is None` para o skip ("conta inexistente"); substitui os 8 call-sites de `store.load_account(conn, self.account_name)` por `self._load_account(conn)`.
- `src/journal/live_store.py` — (a) `ensure_account` passa a comparar o `mode` pedido com o da conta já existente e levanta `ValueError` na divergência (hoje ignora via `ON CONFLICT DO NOTHING`); (b) nova `LegacyPaperAccountError`, cuja mensagem **nomeia explicitamente as duas saídas que o plano original 1.1 exige do usuário — arquivar (renomear a conta) ou apagar** — e o nome da conta encontrada; (c) nova `_migrate_account_mode_vocabulary(conn, schema_path)` chamada no início de `ensure_tables`: se `live_accounts` já existe com o CHECK antigo (`'paper'`/`'broker'` no DDL de `sqlite_master`), rebuild da tabela — **recusa** (levanta `LegacyPaperAccountError`, não mexe em nada) se existir alguma linha com `mode='paper'` (não converte simulação em conta real em silêncio).
  **Ordem do rebuild (obrigatória, é a do plano original: "criar, copiar, dropar, renomear"):** `PRAGMA foreign_keys=OFF` → criar `live_accounts_new` com o DDL final (`_live_ddl` com o nome substituído) → `INSERT ... SELECT` copiando as linhas com `CASE WHEN mode='broker' THEN 'mt5' ELSE mode END` → `DROP TABLE live_accounts` → `ALTER TABLE live_accounts_new RENAME TO live_accounts` → `PRAGMA foreign_key_check` → `PRAGMA foreign_keys=ON`. **NÃO renomear a tabela antiga primeiro:** a partir do SQLite 3.25 `ALTER TABLE ... RENAME` reescreve as cláusulas `REFERENCES` das tabelas FILHAS (`live_positions`, `live_orders`, `live_intents`, …) para apontar ao nome novo — renomear `live_accounts`→`live_accounts_old` deixaria todas as filhas referenciando `live_accounts_old` e o banco silenciosamente corrompido. `PRAGMA foreign_keys` não pode ser alterado dentro de transação — `_connect` liga o pragma ANTES de chamar `ensure_tables`, então esta função tem de desligá-lo/religá-lo ela mesma, fora de qualquer `BEGIN`.
- `src/journal/schema.sql` — `CHECK (mode IN ('paper','manual','broker'))` → `CHECK (mode IN ('manual','mt5'))`, com comentário apontando para `core.live_models.BrokerMode`.
- `scripts/run_live.py` — (a) `--mode` sem default (`None`), `choices=("manual","mt5")`; `--mt5-shares-per-lot` sem default (`None`); (b) `build()`: dispatch explícito (`manual`/`mt5`/`else: raise ValueError` cuja mensagem **nomeia os modos válidos e cobre também `mode is None`** — sem default, `run_live.py status` sem `--mode` cai aqui e o erro tem de dizer o que fazer); exige `mt5_shares_per_lot` não-`None` em modo `mt5`; (c) novo helper `_require_manual_account()` — lê o modo real da conta (`store.load_account`), recusa (mensagem + `SystemExit`) se a conta não existir ou se o modo não for `manual`, e **só então faz `args.mode = "manual"`** para o `build()` seguinte funcionar; `cmd_tickets`/`cmd_confirm` passam a usá-lo em vez de `args.mode = "manual"` incondicional. (d) **docstring do módulo** (é `description=__doc__` do argparse, sai em `--help`): remover a entrada `paper   PaperBroker ...` da seção "Modos de corretora" e a linha 3 do exemplo `init --mode paper`.
- `scripts/run_live_sim.py` — troca `from live.broker import PaperBroker` / `from live.feed import ReplayFeed` por `from tests.doubles import PaperBroker, ReplayFeed`; adiciona a raiz do repo (`parents[1]`, sem o `/src`) ao `sys.path` para o pacote `tests` resolver (comentário explicando que é uma exceção deliberada: este script simula com o MESMO test double que a suíte usa, nunca em produção real).
- `src/dashboard/live_service.py` — (a) `_build_runtime(mode, capital)`: dispatch explícito (`manual`/`mt5`/`else: raise ValueError`), **sem valor default para `mode`** (o default `"paper"` de hoje é metade do bug); (b) `get_status()`: carrega a conta uma vez, devolve `{"conta": ACCOUNT_NAME, "existe": False}` cedo se não existir (**mesma forma que `LiveRuntime.status()` já devolve nesse caso** — o template lê `s.existe`, mas manter a chave `conta` evita divergir de contrato entre os dois caminhos), senão usa `account.mode` e `account.initial_capital` reais (nunca `DEFAULT_CAPITAL`) para montar o runtime; (c) novo `_resolve_risk_guard()` — lê `dashboard.live_control.last_config()` e reconstrói o `CircuitBreaker` via `live_control._load_cli()._build_risk_guard(...)` (reuso, não duplica a lógica do CLI), passado a `LiveRuntime(risk_guard=...)`. `DEFAULT_CAPITAL` **permanece** (é o default do formulário de conta nova em `app.py`, uso legítimo e diferente do bug).
- `src/dashboard/live_control.py` (adicional ao item abaixo) — **memoizar `_load_cli()`** num módulo-cache (`_CLI_MODULE`). Hoje ele só roda no clique de "Iniciar"; a partir do `_resolve_risk_guard()` acima ele passaria a rodar em CADA `get_status()`, ou seja, a cada poll HTMX de `/operacao/fragment` — re-executar `scripts/run_live.py` inteiro (com todos os imports de topo) várias vezes por minuto numa página de leitura é custo gratuito e efeito colateral repetido de `sys.path.insert`.
- `src/dashboard/live_control.py` — (a) `ProcessConfig` ganha `mt5_shares_per_lot: Optional[float] = None`; (b) `create_account()` passa `mt5_shares_per_lot=config.mt5_shares_per_lot` no lugar do `1.0` hardcoded; (c) `start()`: recusa cedo (`RuntimeError`) se `mode == "mt5" and mt5_shares_per_lot is None`; inclui `--mt5-shares-per-lot` no `argv` quando `mode == "mt5"`; (d) prova de vida: após o `Popen`, aguarda `_STARTUP_GRACE_SECONDS` (constante de módulo, monkeypatchável em teste), consulta `proc.poll()` — se saiu com código != 0, lê a cauda de `db/live_process.log` (novo `_tail_log()`) e levanta `RuntimeError` com o erro real, sem gravar PID como "rodando".
- `src/core/live_models.py` (2ª mudança, além do enum) — comentário da linha 278 (`mode: str  # 'paper' | 'manual' | 'broker'` em `AccountState`) atualizado para `'manual' | 'mt5'`.
- `src/dashboard/app.py` — `operacao_iniciar`: default de `mode` vira `"manual"` (não `"paper"`); quando `mode == "mt5"`, exige também `mt5_shares_per_lot` no form (mesmo padrão do `confirmar_real` já existente), passa para `ProcessConfig`; **o `except RuntimeError` em volta de `live_control.start(cfg)` passa a `except (RuntimeError, ValueError)`** — `create_account()` agora pode levantar `ValueError` (divergência de modo em `ensure_account`), e sem isso o clique vira 500 em vez de mensagem na página.
- `src/dashboard/templates/partials/operacao_body.html` — remove `<option value="paper">`; `manual` vira a opção `selected` default; novo campo `mt5_shares_per_lot` dentro do bloco `#ops-mt5-confirm` (visível só quando `mode == mt5`).

*Testes (novos):*
- `tests/doubles.py` — `PaperBroker` (com `is_test_double = True`) e `ReplayFeed`, corpo idêntico ao que saiu de `src/live/broker.py`/`src/live/feed.py`, **exceto `PaperBroker.mode`** — ver a decisão obrigatória logo abaixo.
- `tests/test_live_control.py` — prova de vida do processo (1.6): `Popen` mockado que já saiu → `start()` levanta `RuntimeError` com a cauda do log, sem gravar estado; `Popen` mockado que sobrevive → `start()` grava PID normalmente.
- `tests/test_run_live_cli.py` — dispatch do `build()` (1.2): modo `manual`/`mt5` constroem o broker certo; modo desconhecido/ausente levanta `ValueError`; modo `mt5` sem `mt5_shares_per_lot` levanta `ValueError`; `cmd_tickets`/`cmd_confirm` recusam conta cujo modo real não é `manual` (1.5). Carrega o módulo via o mesmo truque de `importlib` que `dashboard.live_control._load_cli()` já usa. **Isolamento obrigatório do banco:** `_require_manual_account()` e `cmd_tickets`/`cmd_confirm` abrem `store.live_journal()` SEM `db_path`, e `build()` monta `LiveRuntime` com `db_path=None` — sem isolar, este arquivo de teste escreve no `db/live.sqlite` REAL. Usar as duas mesmas técnicas já documentadas em `tests/test_dashboard_app.py` (docstring do módulo, linhas 9–26): `monkeypatch.setattr(live_store.live_journal.__wrapped__, "__defaults__", (tmp_db,))` **e** `monkeypatch.setattr(live_runtime, "DB_PATH", tmp_db)`.

*Testes (alterados — todos por consequência mecânica do CHECK novo / da saída dos dublês de `src/`):*
- `tests/test_live_runtime.py`, `tests/test_live_broker.py`, `tests/test_live_feed.py` — imports dos dublês; ver passos 8 e 10.
- `tests/test_live_store.py`, `tests/test_dashboard_app.py` — asserções novas + fixtures com `mode="paper"`.
- `tests/test_live_broker_mt5.py` — `assert broker.mode == "broker"` (linha 427) vira `"mt5"`.
- `tests/test_migrate_live_db.py` — `mode="paper"` nas linhas 50, 348 e 357 (chamadas a `store.ensure_account`, que agora violam o CHECK) e o par de `INSERT` da origem legada nas linhas 295–303 + o comentário da linha 298 que cita `('paper','manual','broker')`. **Atenção ao teste `..._mode_invalido...` (linhas ~274–325):** ele depende de UMA linha da origem ser válida no destino e a outra não — com o CHECK novo, `'paper'` deixa de ser válida; o valor "válido" da origem tem de passar a `'manual'` (ou `'mt5'`) para o teste continuar provando o que provava.
- `tests/test_journal_live_store_history.py` — fixture da linha 19 (`mode="paper"`).
- `tests/test_live_robots.py` — linha 57 (`mode="paper"`). **Corrige a premissa 5 original deste plano**, que só conferiu import de `PaperBroker`/`ReplayFeed` e concluiu "não precisa de edição" — o arquivo não importa os dublês, mas cria conta com `mode="paper"`.

**Decisão obrigatória — `PaperBroker.mode` (o plano original não a fixa e sem ela a feature não compila em runtime):** o dublê continuar com `mode = "paper"` faz `ensure_account` violar o CHECK novo em ~20 testes de `tests/test_live_runtime.py` **e** em `scripts/run_live_sim.py` (que chama `rt.ensure_account()` com `PaperBroker`). Como o vocabulário canônico só tem `manual`/`mt5` e `PaperBroker` é o dublê de uma corretora AUTOMÁTICA (`supports_automation() → True`, ao contrário de `ManualBroker`), ele passa a declarar `mode = BrokerMode.MT5.value`, documentado na própria classe. Consequências a executar junto:
- `tests/test_live_runtime.py::_runtime` — o parâmetro `mode="paper"` (linha 88) e a chamada explícita `mode="paper"` (linha 570) passam a `mode="mt5"`; o `if mode == "manual"` do corpo continua igual.
- `tests/test_live_runtime.py:770` — a classe falsa de broker com `mode = "broker"` passa a `"mt5"` (ou `"manual"`, o que o teste daquele bloco exigir para não colidir com a guarda de divergência do passo 11).
- Nenhum teste hoje mistura dois modos sobre o MESMO `db_name` dentro do mesmo `tmp_path` (conferido: cada teste tem `tmp_path` próprio e `rt2` na linha 294 usa o mesmo modo), então a guarda de divergência do passo 11 não quebra nada retroativamente — **reconferir isso ao executar**, é a premissa que sustenta o passo 11.

**Só lê:**
- `src/core/config.py` — confirmar `LIVE_DB_PATH`, `BacktestConfig`, `WATCHLIST` (já existem, FEAT-000).
- `src/live/robots.py` — confirmar `WithdrawalRobot.policy` (atributo público, usado na prova do passo 14).
- `src/backtest/withdrawal.py` — confirmar `official_policy(initial_capital)`, `OFFICIAL_FLOOR_MULTIPLE = 55.0` e `FloorSkim.floor` (confirma que `floor` NÃO é persistido em `policy_state`, ver premissa 4).

**Consome de outras features:** FEAT-000 — `core.config.LIVE_DB_PATH`, `journal.live_store`/`live.runtime` já apontando para o banco separado, `scripts/migrate_live_db.py`.
**Produz para outras features:** vocabulário canônico `manual`/`mt5` (`BrokerMode`, `Broker.mode`, `account.mode`); `runtime.py` pós-corte de simulação (FEAT-002 reescreve o mesmo arquivo em cima disto); `tests/doubles.py` (FEAT-005 absorve `ScriptedStrategy`/`_write_parquet`/etc. nele).

## 2b. Premissas a montante (regra 17)

| # | Premissa | Como verificar | Origem |
|---|----------|----------------|--------|
| 1 | `core.config.LIVE_DB_PATH` existe e `journal.live_store._connect`/`live_journal` já o usam como default | `src/core/config.py:19`; `src/journal/live_store.py:133,156` | FEAT-000 |
| 2 | `live.runtime` importa `LIVE_DB_PATH as DB_PATH` — o NOME do atributo de módulo continua `DB_PATH` (usado por `tests/test_dashboard_app.py` via `monkeypatch.setattr(live_runtime, "DB_PATH", tmp)`) | `src/live/runtime.py:65`; `tests/test_dashboard_app.py:46` | FEAT-000 |
| 3 | `db/live.sqlite` nasce vazio (sem `live_accounts` migrada) — a conta `principal` real (modo `paper` no vocabulário antigo) só existe hoje em `db/journal.sqlite`, não migrada ainda (ação humana pendente, fora do escopo automatizado) | EXEC-MAP, "Revalidação", linha FEAT-000 CONCLUÍDA | FEAT-000 |
| 4 | `FloorSkim.state()`/`restore()` só persistem atributos privados (prefixo `_`); `self.floor` é público e NUNCA é restaurado — logo construir `official_policy` com o capital errado é um bug real de configuração, não mascarado por `restore()` | `src/backtest/withdrawal.py:146-164,236` | código existente |
| 5 | ~~Nenhum teste em `tests/test_live_robots.py` importa `PaperBroker`/`ReplayFeed` — mover essas classes não exige tocar aquele arquivo~~ **PREMISSA FALSA (plan-reviewer).** O grep original só cobriu import de dublê. `tests/test_live_robots.py:57` cria conta com `mode="paper"`, que o CHECK novo rejeita → o arquivo PRECISA de edição. O mesmo vale para `tests/test_journal_live_store_history.py:19`, `tests/test_migrate_live_db.py:50,348,357` e `tests/test_live_broker_mt5.py:427` | `grep -rn 'mode="paper"\|mode == "broker"' tests/` | corrigido pelo plan-reviewer |
| 5b | Todo consumidor do vocabulário antigo está coberto pela lista da seção 2 — o grep de fechamento não pode sobrar nada | `grep -rn "'paper'\|\"paper\"\|'broker'\|\"broker\"" src/ scripts/ tests/` devolve só prosa deliberada (nome `PaperBroker`, `name = "paper"` do dublê), nenhum valor de MODO | verificado pelo plan-reviewer |
| 6 | `pyproject.toml` tem `pythonpath = ["src"]` e `tests/__init__.py` existe — `from tests.doubles import ...` resolve de dentro de qualquer teste; `scripts/run_live_sim.py` precisa da RAIZ do repo (não só `src/`) no `sys.path` para o mesmo import funcionar de um script | `pyproject.toml:15-16`; `tests/__init__.py` | código existente + plano original (nota sobre `tests/doubles.py`) |
| 7 | Suíte verde antes desta feature: **261 testes** (baseline pós-FEAT-000, medido pelo orquestrador) | `EXEC-MAP.md`, linha "Comandos do projeto" | baseline informado no briefing |

## 3. Passos

> **RED antes de GREEN (T3):** cada teste novo/alterado abaixo é escrito e rodado ANTES da mudança de produção correspondente, e precisa falhar com o código atual (`BrokerMode` não existe, `MT5Broker.mode` ainda é `"broker"`, `PaperBroker` ainda está em `src/`, etc.). Colar a saída RED na seção 7.

| # | Ação | Arquivo(s) | Como sei que funcionou |
|---|------|-----------|------------------------|
| 1 | Adicionar `class BrokerMode(str, Enum)` (`MANUAL="manual"`, `MT5="mt5"`) com docstring explicando a fratura de vocabulário que ela fecha; atualizar o comentário de `AccountState.mode` (linha 278) | `src/core/live_models.py` | `python -c "from core.live_models import BrokerMode; print([m.value for m in BrokerMode])"` → `['manual', 'mt5']` |
| 2 | `CHECK (mode IN ('paper','manual','broker'))` → `CHECK (mode IN ('manual','mt5'))` + comentário apontando para `BrokerMode` | `src/journal/schema.sql` | `grep -n "CHECK (mode" src/journal/schema.sql` mostra só `'manual','mt5'` |
| 3 | `_migrate_account_mode_vocabulary(conn, schema_path)` + `LegacyPaperAccountError`, chamada no início de `ensure_tables`: detecta CHECK antigo via `sqlite_master.sql` (posicional, sem depender de `row_factory`), recusa se houver linha `mode='paper'`, senão rebuild **na ordem criar-novo → copiar → dropar-antiga → renomear**, com `PRAGMA foreign_keys` desligado durante e `PRAGMA foreign_key_check` antes de religar (ver seção 2 para o porquê de NUNCA renomear a antiga primeiro), convertendo `'broker'→'mt5'` no `SELECT` | `src/journal/live_store.py` | testes novos em `tests/test_live_store.py`: (a) tabela com CHECK antigo + linha `mode='broker'` + uma `live_positions` filha apontando para ela → após `ensure_tables`, a linha vira `mode='mt5'`, inserir `mode='paper'` novo levanta `IntegrityError`, **`PRAGMA foreign_key_check` volta vazio e o DDL de `live_positions` em `sqlite_master` ainda diz `REFERENCES live_accounts`** (é isto que pega o rebuild feito na ordem errada); (b) tabela com CHECK antigo + linha `mode='paper'` → `ensure_tables` levanta `LegacyPaperAccountError` citando o nome da conta e as opções arquivar/apagar, tabela intacta |
| 4 | `ensure_account`: após o `INSERT ... ON CONFLICT DO NOTHING`, comparar `mode` pedido com `account.mode` carregado; levantar `ValueError` na divergência | `src/journal/live_store.py` | teste novo em `tests/test_live_store.py`: `ensure_account(mode="manual")` seguido de `ensure_account(mode="mt5")` no mesmo nome levanta `ValueError`; fixture `_account()` (linha 59) corrigida para `mode="manual"` |
| 5 | `MT5Broker.mode = "broker"` → `"mt5"`; **`tests/test_live_broker_mt5.py:427` (`assert broker.mode == "broker"`) → `"mt5"`** | `src/live/broker_mt5.py`, `tests/test_live_broker_mt5.py` | `pytest -q tests/test_live_broker_mt5.py` verde; `python -c "from live.broker_mt5 import MT5Broker; assert MT5Broker.mode == 'mt5'"` |
| 6 | Criar `tests/doubles.py` com `PaperBroker` (corpo movido de `live/broker.py`, ganha `is_test_double = True` e `mode = BrokerMode.MT5.value` — ver "Decisão obrigatória" na seção 2) e `ReplayFeed` (corpo movido de `live/feed.py`) | `tests/doubles.py` (novo) | `python -c "from tests.doubles import PaperBroker, ReplayFeed; print(PaperBroker.is_test_double, PaperBroker.mode)"` → `True mt5` |
| 7 | Remover `PaperBroker` de `src/live/broker.py` (+ docstring do módulo e comentário de `Broker.mode`); `Broker` ganha `is_test_double: bool = False`; remover `ReplayFeed` de `src/live/feed.py` (+ linha 16 da docstring) | `src/live/broker.py`, `src/live/feed.py` | `grep -rn "class PaperBroker\|class ReplayFeed" src/` vazio; `grep -rn "'paper'\|'broker'" src/live/ src/core/ src/journal/` sem nenhum valor de MODO sobrando |
| 8 | Atualizar imports de `PaperBroker`/`ReplayFeed` em `tests/test_live_broker.py`, `tests/test_live_feed.py`, `tests/test_live_runtime.py` para `from tests.doubles import ...` (mantendo `Broker`/`ManualBroker` importados de `live.broker`, e `ParquetCloseFeed`/`YFinanceFeed`/`QuoteFeed`/`staleness_report` de `live.feed`) | `tests/test_live_broker.py`, `tests/test_live_feed.py`, `tests/test_live_runtime.py` | os 3 arquivos importam sem `ModuleNotFoundError`; suíte desses 3 arquivos continua com a MESMA contagem de testes de antes |
| 8b | **Migrar todas as contas de teste do vocabulário antigo** (consequência mecânica do CHECK): `tests/test_live_runtime.py:88,570` (`mode="paper"`→`"mt5"`) e `:770` (broker falso `mode="broker"`), `tests/test_dashboard_app.py:60`, `tests/test_live_robots.py:57`, `tests/test_journal_live_store_history.py:19`, `tests/test_migrate_live_db.py:50,295-303,348,357` (inclusive o comentário da linha 298 e a escolha do modo "válido" da origem legada — ver seção 2) | os 6 arquivos de teste acima | `grep -rn 'mode="paper"\|mode="broker"' tests/` vazio; `pytest -q` sem nenhum `IntegrityError: CHECK constraint failed` |
| 9 | Atualizar `scripts/run_live_sim.py`: import de `PaperBroker`/`ReplayFeed` de `tests.doubles`; adicionar raiz do repo ao `sys.path` | `scripts/run_live_sim.py` | `python -m py_compile scripts/run_live_sim.py` ok **e** o teste existente `tests/test_migrate_live_db.py` (que faz `from run_live_sim import SIM_DB, _ensure_disposable_sim_db`) continua verde — é ele que exercita o import de verdade, não um `exec()` manual |
| 10 | `LiveRuntime.__init__`: logo após resolver `self.db_path`, recusar (`ValueError`) se o broker é dublê **e** `Path(self.db_path).resolve() == Path(DB_PATH).resolve()` | `src/live/runtime.py` | testes novos em `tests/test_live_runtime.py`: (a) `LiveRuntime(broker=PaperBroker(...), db_path=None)` com `live_runtime.DB_PATH` monkeypatchado levanta `ValueError`; (b) o MESMO caminho passado como `str`/`Path` relativo também levanta (prova que a comparação é por caminho resolvido); (c) `LiveRuntime(broker=ManualBroker(), db_path=live_runtime.DB_PATH)` NÃO levanta. **Ajuste obrigatório em teste existente:** `test_db_path_default_e_live_db_path` (linhas 102–138) hoje instancia `PaperBroker` com `db_path=None` — exatamente o cenário que a guarda passa a recusar; trocar por `ManualBroker()` (o teste é sobre a resolução do default, não sobre o broker) |
| 11 | Novo `_load_account(self, conn)`: chama `store.load_account`, devolve `None` se a conta não existe (preserva os 8 ramos de skip) e recusa (`ValueError`) se `account.mode != self.broker.mode`; substituir os 8 call-sites (`unfreeze`, `close_and_decide`, `execute_session`, `reconcile_pending_fills`, `reconcile_broker_cash`, `intraday_tick`, `status` ×2) por `self._load_account(conn)` | `src/live/runtime.py` | testes novos em `tests/test_live_runtime.py`: (a) cria conta com `ManualBroker` (`mode="manual"`), instancia um SEGUNDO `LiveRuntime` com `PaperBroker` (`mode="mt5"`) sobre o MESMO `db_path`/`account_name` e chama `close_and_decide` e `status()` → `ValueError` nos dois; (b) sobre banco vazio, `status()` do mesmo runtime continua devolvendo `{"existe": False}` (prova que `_load_account` não transformou "conta ausente" em exceção) |
| 12 | `--mode` sem default, `choices=("manual","mt5")`; `--mt5-shares-per-lot` sem default; `build()`: dispatch explícito `manual`/`mt5`/`else: raise ValueError` (mensagem nomeando os modos válidos, cobrindo `None`); exige `mt5_shares_per_lot` não-`None` em modo `mt5` | `scripts/run_live.py` | teste novo em `tests/test_run_live_cli.py` (com o isolamento de banco descrito na seção 2): `build(Namespace(mode="broker", ...))` e `build(Namespace(mode=None, ...))` levantam `ValueError`; `build(Namespace(mode="mt5", mt5_shares_per_lot=None, ...))` levanta `ValueError`; `build(Namespace(mode="manual", ...))` devolve runtime com `broker.mode == "manual"` e `build(Namespace(mode="mt5", mt5_shares_per_lot=1.0, ...))` com `broker.mode == "mt5"` |
| 13 | `_require_manual_account()`: lê o modo real da conta via `store.load_account`, levanta `SystemExit` com mensagem clara se a conta não existir ou se o modo não for `manual`, e só então faz `args.mode = "manual"`; `cmd_tickets`/`cmd_confirm` passam a usá-lo | `scripts/run_live.py` | teste novo em `tests/test_run_live_cli.py`: conta criada com `mode="mt5"`; `pytest.raises(SystemExit)` em `cmd_tickets(args)` e `cmd_confirm(args)`, e a mensagem capturada cita o modo real da conta; nenhum `Order`/evento gravado no banco isolado depois da recusa |
| 14 | `dashboard/live_service.py`: dispatch explícito em `_build_runtime(mode, capital)` (sem default de `mode`, raise no modo desconhecido); `get_status()` devolve `{"conta": ACCOUNT_NAME, "existe": False}` cedo sem conta; usa `account.mode`/`account.initial_capital` reais; novo `_resolve_risk_guard()` lendo `live_control.last_config()` via `live_control._load_cli()._build_risk_guard` (com `_load_cli()` memoizado) | `src/dashboard/live_service.py`, `src/dashboard/live_control.py` | testes novos em `tests/test_dashboard_app.py`, **os dois passando por `get_status()`** (ver "Correção da prova do 1.7" na seção 4): (a) conta criada com `initial_capital=50_000.0`; espião em `live_service._build_runtime` que guarda o runtime devolvido; após `live_service.get_status()`, `rt.config.initial_capital == 50_000.0` e `rt.withdrawal.policy.floor == 50_000.0 * OFFICIAL_FLOOR_MULTIPLE` (nunca `1_000.0`/`55_000.0`); (b) com `live_control._STATE_PATH` monkeypatchado e uma config salva com `daily_loss_limit=0.05`, `live_service.get_status()["disjuntor"]` não é `None` |
| 15 | `ProcessConfig` ganha `mt5_shares_per_lot`; `create_account()`/`start()` passam o valor adiante (fim do `1.0` hardcoded); `start()` recusa cedo (`RuntimeError`) se `mode == "mt5"` e o campo for `None`, e inclui `--mt5-shares-per-lot` no argv; prova de vida do processo: após `_STARTUP_GRACE_SECONDS`, **`proc.poll() is not None` (processo já saiu — qualquer código, inclusive 0) → `RuntimeError` com a cauda de `db/live_process.log` via `_tail_log()`, sem gravar estado** | `src/dashboard/live_control.py` | `tests/test_live_control.py` (com `_STATE_PATH`/`_LOG_PATH` monkeypatchados para `tmp_path` e `_STARTUP_GRACE_SECONDS=0`): `Popen` mockado com `poll()` devolvendo 1 → `start()` levanta `RuntimeError` contendo um trecho gravado no log, e `_read_state()` continua `None`; `Popen` mockado com `poll()` devolvendo `None` → `start()` grava PID; `ProcessConfig(mode="mt5", mt5_shares_per_lot=None)` → `RuntimeError` antes de qualquer `Popen`; `ProcessConfig(mode="mt5", mt5_shares_per_lot=2.0)` → `"--mt5-shares-per-lot"` presente no argv capturado |
| 16 | `app.py::operacao_iniciar`: default `mode` vira `"manual"`; exige `mt5_shares_per_lot` no form quando `mode == "mt5"`; `except` passa a cobrir `ValueError` além de `RuntimeError` | `src/dashboard/app.py` | teste novo em `tests/test_dashboard_app.py`: com o banco isolado VAZIO (a rota só lê o form quando não há conta), POST `/operacao/iniciar` com `mode=mt5`, `confirmar_real=1`, sem `mt5_shares_per_lot` → 200 com a mensagem de erro pedindo o campo e `live_control.start` (monkeypatchado com um espião) NUNCA chamado |
| 17 | Remover `<option value="paper">`; `manual` vira `selected` default; novo campo `mt5_shares_per_lot` dentro de `#ops-mt5-confirm` | `src/dashboard/templates/partials/operacao_body.html` | `grep -n 'value="paper"' src/dashboard/templates/partials/operacao_body.html` vazio; `grep -n "mt5_shares_per_lot" src/dashboard/templates/partials/operacao_body.html` presente |
| 18 | Rodar a suíte inteira (blast radius maior que os arquivos nomeados no EXEC-MAP — `core/live_models.py`/`live/broker.py`/`live/feed.py` são importados amplamente) | — | `../meta/.venv/Scripts/python.exe -m pytest -q` → exit 0, **≥ 261 testes** (baseline) e nenhuma regressão fora dos arquivos desta feature |

## 4. Prova de conclusão (uma só)

**Origem:** ⬜ comando/teste que já existe ☑️ asserção nova em teste existente ☑️ teste novo (justificado abaixo) ⬜ estado observável

**Justificativa do teste novo:** a maior parte da prova são asserções novas em arquivos que já existem (`test_live_runtime.py`, `test_live_store.py`, `test_dashboard_app.py`, `test_live_broker_mt5.py`). Só dois arquivos são criados, e só porque não há nada a estender: `scripts/run_live.py` e `dashboard/live_control.py` não tinham arquivo de teste dedicado antes desta feature.

**Correção da prova do 1.7 (plan-reviewer):** a versão original testava `live_service._build_runtime("manual", 50_000.0).config.initial_capital == 50_000.0` — isto é, chamava o helper com o capital certo passado à mão. **Essa asserção passaria com a feature quebrada:** um `get_status()` que continuasse chamando `_build_runtime(mode, DEFAULT_CAPITAL)` não seria pego por ela, e o vazamento do default de simulação para a conta real (o item 1.7 inteiro) sobreviveria com a prova verde. A prova passa a atravessar `get_status()` com um espião sobre `_build_runtime` (passo 14a).

```
../meta/.venv/Scripts/python.exe -m pytest -q
```

Executado a partir da worktree `../meta-FEAT-001`. Esperado: **todos os testes verdes** (baseline 261 + os testes novos desta feature; a contagem final nunca pode ser < 261 — teste sumido é regressão, não simplificação), incluindo especificamente:
- `tests/test_live_runtime.py` — mode divergente recusado em `close_and_decide`/`status()`; conta ausente continua devolvendo skip (não exceção); guarda test-double recusa dublê (inclusive com caminho equivalente não-idêntico) e aceita broker de produção.
- `tests/test_live_store.py` — `ensure_account` recusa divergência de modo; rebuild do CHECK renomeia `broker→mt5` **sem repontuar as FKs das tabelas filhas**; rebuild recusa quando há `mode='paper'`, com mensagem que nomeia arquivar/apagar.
- `tests/test_run_live_cli.py` (novo) — `--mode` desconhecido/ausente levanta; `mt5` sem `shares_per_lot` levanta; `cmd_tickets`/`cmd_confirm` recusam (`SystemExit`) conta não-manual.
- `tests/test_live_control.py` (novo) — prova de vida do processo detecta saída imediata; `--mt5-shares-per-lot` chega ao argv; `mt5` sem o valor é recusado antes do `Popen`.
- `tests/test_dashboard_app.py` — capital/piso reais atravessando `get_status()`; disjuntor não-nulo; validação de `mt5_shares_per_lot` na rota.
- `tests/test_live_broker.py`, `tests/test_live_feed.py` — continuam verdes após a relocação para `tests/doubles.py`.
- `tests/test_live_broker_mt5.py`, `tests/test_live_robots.py`, `tests/test_journal_live_store_history.py`, `tests/test_migrate_live_db.py` — continuam verdes sob o vocabulário novo.

**O que essa prova garante:** que o vocabulário de modo é único e canônico ponta a ponta (schema, broker, CLI, dashboard, template), que nenhum modo desconhecido cai silenciosamente em `PaperBroker`, que uma conta e um broker divergentes nunca operam juntos, que um dublê nunca abre o banco de produção (item 0.3 herdado), que o botão "Iniciar" não mente sobre um processo morto, e que a página de status não vaza defaults de simulação para uma conta real — resolvendo o crítico nº1 da revisão.

**Teste de falsificação (obrigatório) — um cenário por requisito, todos pegos por esta prova:**

| Requisito | Feature quebrada assim… | …e quem pega |
|---|---|---|
| 1.1 vocabulário | `MT5Broker.mode` continua `"broker"` | `test_live_broker_mt5.py` (assert direto) **e** o guard do passo 11 (conta `mt5` vs broker `broker` → não bate) |
| 1.1 rebuild | rebuild feito com `ALTER TABLE RENAME` primeiro | passo 3(a): `sqlite_master` de `live_positions` passaria a dizer `REFERENCES live_accounts_old` |
| 1.1 conta legada | migração converte `paper→manual` em silêncio | passo 3(b): esperava `LegacyPaperAccountError`, não recebe exceção |
| 1.2 fallback | `else: PaperBroker(feed)` mantido em `run_live.py`/`live_service.py` | passos 12/14: `build(mode="broker")` devolveria runtime em vez de levantar |
| 1.3 divergência | `_load_account` continua chamando `store.load_account` cru | passo 11(a): nenhuma exceção onde se espera `ValueError` |
| 1.4 dublês | `PaperBroker` fica em `src/` | passo 7 (grep) + import de `tests.doubles` falha em 4 arquivos |
| 1.5 CLI mentindo | `args.mode = "manual"` incondicional | passo 13: `cmd_tickets` sobre conta `mt5` terminaria normal, sem `SystemExit` |
| 1.6 prova de vida | `start()` grava PID logo após `Popen` | passo 15: `_read_state()` traria PID em vez de `None` e nenhum `RuntimeError` |
| 1.7 capital | `get_status()` segue passando `DEFAULT_CAPITAL` | passo 14(a) via espião: `floor` viria `55_000.0` em vez de `2_750_000.0` |
| 1.7 disjuntor | `risk_guard` continua nunca passado | passo 14(b): `status()["disjuntor"]` seria `None` |
| 1.7 shares/lote | `create_account`/`start` mantêm `1.0` hardcoded | passo 15: `--mt5-shares-per-lot` ausente do argv capturado |
| 0.3 herdado | guarda ausente, ou comparando `==` cru | passo 10(a) e 10(b): dublê construiria sobre `DB_PATH` sem levantar |

**RED antes de GREEN:** obrigatório (T3) — cada teste novo do passo 3 em diante é escrito e rodado contra o código ATUAL antes da mudança correspondente; saída RED colada na seção 7.

## 5. Riscos e gatilhos de escalação

- **Lista de arquivos maior que a linha do EXEC-MAP — RESOLVIDO pelo plan-reviewer.** O planner reportou 7 arquivos a mais; a revisão encontrou **mais 4** que ele não viu (`tests/test_live_broker_mt5.py`, `tests/test_migrate_live_db.py`, `tests/test_journal_live_store_history.py`, `tests/test_live_robots.py` — todos criam conta com `mode="paper"` ou assertam `mode == "broker"`). Total real: 23 arquivos. Todos são consequência MECÂNICA e inevitável de 1.4 ("PaperBroker/ReplayFeed saem de `src/`") e 1.1 ("CHECK canoniza para manual/mt5") — sem tocá-los, os imports quebram ou os fixtures violam o CHECK novo. Nenhum item além de 1.1–1.7 + a guarda 0.3 herdada. **A linha de FEAT-001 no `EXEC-MAP.md` foi corrigida para a lista real** (divergência de estimativa, não de escopo). Como toda a run é 100% sequencial, nenhum desses arquivos colide com feature concorrente.
- **Rebuild de schema em produção.** `_migrate_account_mode_vocabulary` só é exercitado por teste contra bancos em `tmp_path`; `db/live.sqlite` real (fora da worktree) pode já ter sido tocado por FEAT-000/testes manuais com o CHECK antigo. A função foi desenhada para ser segura mesmo assim (recusa alto em vez de converter `paper`, e só renomeia `broker→mt5` que é correção de rótulo sobre uma conta já real) — mas nunca roda contra o banco real dentro desta feature (fora do escopo automatizado, mesma fronteira que `scripts/migrate_live_db.py` já respeita).
- **`official_policy`/capital real não é observável em nenhum campo de `status()` hoje** (confirmado lendo `runtime.py::status()` — nenhum campo expõe `floor`/`initial_capital` diretamente). A prova do passo 14 testa isso no nível de unidade (`_build_runtime(...).config.initial_capital`), não via HTTP — é a forma mais forte de prova disponível sem inventar um campo novo em `status()` (fora de escopo desta feature).
- **`run_live_sim.py --keep` sobre um banco de simulação antigo passa a falhar** (novo, plan-reviewer). Um `db/live_sim.sqlite` de rodada anterior tem a conta `simulacao` com `mode='paper'`; a partir desta feature, qualquer `_connect` a ele levanta `LegacyPaperAccountError`. Sem `--keep` (o default) o arquivo é apagado no início e o problema não existe. Comportamento aceitável e coerente com 1.1 (não converter simulação em silêncio) — **registrar na mensagem da exceção que apagar o banco de simulação é a saída para esse caso**, para o usuário não confundir com a conta real.
- **A guarda 0.3 muda o comportamento de um teste já existente.** `tests/test_live_runtime.py::test_db_path_default_e_live_db_path` (escrito em FEAT-000) usa `PaperBroker` + `db_path=None` — exatamente o caso que a guarda passa a recusar. Trocado por `ManualBroker` no passo 10; não é perda de cobertura (o teste é sobre a resolução do default de `db_path`, não sobre o tipo de broker), e o cenário original vira o teste POSITIVO da guarda.
- Escalarei se: `_migrate_account_mode_vocabulary` precisar lidar com um `db/live.sqlite` real já populado (não é o caso hoje, confirmado pela premissa 3); ou se `tests/test_migrate_live_db.py` exigir mudança de SEMÂNTICA (e não só de rótulo de modo) para continuar provando o que provava — nesse caso a feature estaria alterando o contrato de FEAT-000, o que é decisão do orquestrador.

**Itens fora de escopo, registrados na rodada de correção pós-code-review (não corrigidos — decisão maior ou fora da fronteira desta feature):**
- `PaperBroker.mode` virar `"mt5"` apaga o marcador que distinguia contas de simulação de contas reais para o FUTURO — exigiria mudança de schema/decisão maior.
- Ausência de lock de "dono" do processo/conta — dois supervisores podem operar a mesma conta ao mesmo tempo, nada nesta feature impede isso.
- A prova de vida do processo (`live_control.start`) cobre só os primeiros segundos do start — não há heartbeat de vida contínua nem reciclagem de PID detectada depois disso.
- A guarda do dublê (item 0.3 herdado) só protege `LIVE_DB_PATH` — outros bancos reais como `db/journal.sqlite` não têm guarda equivalente.
- `get_status()` pode quebrar com 500 se faltar `data/raw/*.parquet` ou se `db/live_process.json` estiver em formato antigo/malformado — só `LegacyPaperAccountError` foi tratada nesta rodada, não essas outras causas de exceção.
- O disjuntor exibido no painel reflete o arquivo de config do dashboard (`live_control.last_config()`), não necessariamente o estado real da conta quando o processo foi iniciado fora do dashboard (ex.: via CLI direta).

## 6. Correções do plan-reviewer

**Natureza: SUBSTANTIVAS.** Duas correções mudam abordagem (ordem do rebuild de tabela, prova do 1.7), várias inserem passo novo. O plano corrigido está liberado para execução — não há segunda revisão.

| # | O que estava errado | Correção aplicada | Motivo |
|---|---------------------|-------------------|--------|
| 1 | **Premissa 5 falsa.** "`tests/test_live_robots.py` não precisa de edição" — o grep só cobriu import de dublê | Premissa marcada como falsa; arquivo incluído na seção 2 e no passo 8b, junto de `tests/test_journal_live_store_history.py`, `tests/test_migrate_live_db.py` e `tests/test_live_broker_mt5.py` | `tests/test_live_robots.py:57` cria conta com `mode="paper"` → `IntegrityError` sob o CHECK novo. 4 arquivos que o planner não viu quebrariam a suíte |
| 2 | **`PaperBroker.mode` ficava `"paper"`.** O plano movia a classe sem decidir o modo | Decisão fixada na seção 2: `mode = BrokerMode.MT5.value` (dublê de corretora automática), com as consequências listadas (`_runtime` linha 88/570, broker falso da linha 770) | Sem isso a feature nem roda: `ensure_account` violaria o CHECK em ~20 testes de `test_live_runtime.py` e em `scripts/run_live_sim.py` |
| 3 | **Rebuild na ordem errada.** `ALTER TABLE ... RENAME` primeiro | Sequência trocada para criar-novo → copiar → dropar-antiga → renomear, com `foreign_keys=OFF` + `foreign_key_check`; passo 3(a) ganha asserção sobre o DDL de `live_positions` | SQLite ≥3.25 reescreve as cláusulas `REFERENCES` das tabelas filhas ao renomear — a versão original repontuaria `live_positions/orders/intents` para `live_accounts_old` e corromperia o banco em silêncio. A ordem corrigida é a que o **plano original** pede ("criar, copiar, dropar, renomear") |
| 4 | **Prova do 1.7 não falsificava o bug.** `_build_runtime("manual", 50_000)` chamado à mão | Passo 14(a) reescrito: espião sobre `_build_runtime`, asserção depois de `get_status()`; justificativa registrada na seção 4 | A asserção original passaria com `get_status()` continuando a mandar `DEFAULT_CAPITAL` — ou seja, o item 1.7 inteiro poderia ficar quebrado com a prova verde |
| 5 | **Guarda 0.3 comparava `self.db_path == DB_PATH` cru** | Passa a comparar `Path(...).resolve()` nos dois lados; passo 10(b) prova com caminho equivalente não-idêntico | Igualdade crua é driblada por string/caminho relativo — exatamente o que a guarda existe para impedir. Precedente no repo: `run_live_sim._ensure_disposable_sim_db` |
| 6 | **Teste existente quebraria em silêncio.** `test_db_path_default_e_live_db_path` usa `PaperBroker` + `db_path=None` | Ajuste explícito no passo 10 (trocar por `ManualBroker`) e registro no risco | É literalmente o cenário que a guarda nova recusa; sem o ajuste, a suíte fica vermelha e o executor "conserta" adivinhando |
| 7 | **`_load_account` sem contrato para conta ausente** | Passo 11: devolve `None` sem levantar; prova 11(b) cobre isso | Os 8 call-sites dependem do ramo `if account is None` para o skip; um `_load_account` que levantasse trocaria "conta inexistente" por crash do supervisor |
| 8 | **`tests/test_run_live_cli.py` sem isolamento de banco** | Isolamento obrigatório documentado na seção 2 (as duas técnicas de `test_dashboard_app.py`) | `cmd_tickets`/`build()` abrem `live_journal()`/`DB_PATH` sem argumento — o teste escreveria no `db/live.sqlite` REAL |
| 9 | **`--mode` sem default deixava buracos** | Passo 12: erro nomeia os modos válidos e cobre `mode is None`; passo 13: `_require_manual_account()` só seta `args.mode="manual"` DEPOIS de validar, e o teste usa `pytest.raises(SystemExit)` | Sem default, `run_live.py status` sem `--mode` cai no `else` — o erro tem de ser acionável, não `ValueError` genérico. E "erro claro" não é asserção |
| 10 | **Prova de vida só checava código != 0** | Passo 15: `proc.poll() is not None` (qualquer código) | O plano original pede "checar que o PID vive **e** que não saiu com código != 0" — um processo que sai com 0 na hora também é falha de subida |
| 11 | **`_load_cli()` passaria a rodar a cada poll** | Memoização exigida em `live_control` (seção 2 + passo 14) | `_resolve_risk_guard()` é chamado por `get_status()`, que é chamado por `/operacao/fragment` em polling — re-executar `run_live.py` inteiro várias vezes por minuto |
| 12 | **`operacao_iniciar` só capturava `RuntimeError`** | Passa a capturar `(RuntimeError, ValueError)` | `create_account()` agora pode levantar `ValueError` (divergência de modo) → o clique viraria 500 em vez de mensagem na página |
| 13 | **Vocabulário antigo sobrando em prosa** | Seção 2 lista: docstring do módulo `run_live.py` (é `--help`), `core/live_models.py:278`, docstring+comentário de `live/broker.py`, linha 16 de `live/feed.py` | 1.1 pede vocabulário ÚNICO; um `--help` que ainda oferece `--mode paper` é a mesma fratura que causou o crítico nº1 |
| 14 | **Mensagem da `LegacyPaperAccountError` não especificada** | Deve nomear a conta e as duas opções (arquivar ou apagar) | Fidelidade ao 1.1: "reporta e **pede decisão explícita** do usuário (arquivar ou apagar)" |
| 15 | **`{"existe": False}` divergindo de `LiveRuntime.status()`** | `get_status()` devolve `{"conta": ACCOUNT_NAME, "existe": False}` | Dois caminhos para o mesmo contrato de template não podem ter shapes diferentes |
| 16 | **Prova do passo 9 era um `exec()` manual** | Trocado por "`tests/test_migrate_live_db.py` continua verde" (o arquivo já importa `run_live_sim`) | Regra 7: prova existente vence prova inventada |
| 17 | **Falsificação em um parágrafo genérico** | Tabela requisito × cenário quebrado × quem pega, incluindo o item 0.3 herdado | T3 exige que cada requisito tenha um cenário de quebra nomeado; 0.3 herdado precisava de prova própria, não "de passagem" |

## 7. Registro de execução

> Preenchido pelo feature-agent após executar.

**Passos executados:** 19/19 (1–18 + 8b)

**RED (T3, obrigatório — capturado ANTES de qualquer mudança de produção):**
Todos os testes novos/alterados da seção 3 foram escritos primeiro (incluindo
`tests/doubles.py`, que já referencia `core.live_models.BrokerMode` — ainda
inexistente). Rodando `pytest -q --continue-on-collection-errors` contra o
código de produção ORIGINAL (antes do passo 1):
```
ERROR tests/test_live_broker.py
ERROR tests/test_live_feed.py
ERROR tests/test_live_runtime.py
  ImportError: cannot import name 'BrokerMode' from 'core.live_models'
FAILED tests/test_dashboard_app.py::test_operacao_aportar_credita_caixa_e_grava_deposito
FAILED tests/test_dashboard_app.py::test_operacao_aportar_valor_invalido_nao_mexe_no_caixa
FAILED tests/test_dashboard_app.py::test_get_status_usa_capital_real_da_conta_atraves_de_build_runtime
FAILED tests/test_dashboard_app.py::test_get_status_disjuntor_nao_nulo_quando_ha_config_salva
FAILED tests/test_dashboard_app.py::test_operacao_iniciar_mt5_sem_shares_per_lot_pede_campo_sem_iniciar
FAILED tests/test_live_broker_mt5.py::test_supports_automation_true_e_metadados
FAILED tests/test_live_store.py::test_ensure_account_recusa_divergencia_de_modo
FAILED tests/test_live_store.py::test_migrate_vocabulario_rebuild_converte_broker_em_mt5_sem_repontuar_fks
FAILED tests/test_live_store.py::test_migrate_vocabulario_recusa_quando_ha_conta_paper
FAILED tests/test_run_live_cli.py::test_build_modo_desconhecido_levanta_valueerror
FAILED tests/test_run_live_cli.py::test_build_modo_ausente_levanta_valueerror
FAILED tests/test_run_live_cli.py::test_build_mt5_sem_shares_per_lot_levanta_valueerror
FAILED tests/test_run_live_cli.py::test_build_mt5_com_shares_per_lot_monta_mt5_broker
FAILED tests/test_run_live_cli.py::test_cmd_tickets_recusa_conta_nao_manual
FAILED tests/test_run_live_cli.py::test_cmd_confirm_recusa_conta_nao_manual
ERROR tests/test_live_control.py (×4 — _STARTUP_GRACE_SECONDS ainda não existe)
15 failed, 211 passed, 1 warning, 7 errors in 3.94s
```
(2 testes novos de `test_live_runtime.py` — guarda 0.3 e `_load_account` — só
foram adicionados na rodada seguinte, junto da implementação de `runtime.py`;
ficaram RED isoladamente antes do passo 10/11, confirmado à parte.)

**Commits:**
- `dfeaa5c` vocabulario canonico de modo (BrokerMode manual/mt5) — passo 1+2
- `f52f765` rebuild do CHECK de mode + ensure_account recusa divergencia — passo 3+4
- `3d1e926` MT5Broker.mode vira "mt5" (era "broker") — passo 5
- `5d7d968` PaperBroker/ReplayFeed saem de src/, viram tests/doubles.py — passo 6+7+8+8b
- `c0ff78f` run_live_sim.py importa de tests.doubles — passo 9
- `5d84ce8` runtime.py recusa dublê sobre banco de produção e conta/broker divergentes — passo 10+11
- `a64a213` run_live.py --mode sem default, dispatch explícito, recusa CLI manual — passo 12+13
- `346a2a1` get_status() usa capital/disjuntor reais da conta — passo 14
- `9c256ce` testa prova de vida do processo e mt5_shares_per_lot — passo 15
- `0635c94` formulário "Iniciar" sem modo paper, exige lote MT5 — passo 16+17

**Relatório do PRE-GATE (regra 18) — input obrigatório do code-reviewer:**
```
1. prova      ✅ ../meta/.venv/Scripts/python.exe -m pytest -q → exit 0, 281 passed
              (baseline 261 + 20 testes novos desta feature; nenhum teste sumiu)
2. lint       n/a — sem ruff/flake8 instalado no venv
3. typecheck  n/a — sem mypy; py_compile nos 22 arquivos .py tocados → todos OK
4. escopo     git diff --name-only plan/blindagem-operacao-real...HEAD → 25 arquivos,
              TODOS previstos na seção 2 (ver "Desvios" sobre a contagem "23" do EXEC-MAP)
5. higiene    grep por TODO/FIXME/print/console.log/breakpoint no diff → só 1 falso-positivo
              ("todos", português, não é o marcador TODO); nenhum arquivo temporário;
              nenhuma dependência nova em requirements.txt
Rodadas até fechar: 1
```

**Evidência da prova de conclusão:**
```
$ ../meta/.venv/Scripts/python.exe -m pytest -q
........................................................................ [ 25%]
........................................................................ [ 51%]
........................................................................ [ 76%]
.................................................................        [100%]
281 passed, 1 warning in 7.28s
```

**Desvios (triviais, com plano atualizado):**
- **Contagem de arquivos "23" vs. lista real de 25.** O EXEC-MAP resume "Total real: 23 arquivos", mas a lista detalhada da seção 2 deste próprio ACTION-PLAN (Produção 13 + Testes novos 3 + Testes alterados 9) já somava 25. Os 25 arquivos tocados nesta execução são exatamente os 25 nomeados na seção 2 — nenhum arquivo fora do previsto. Tratado como divergência de contagem na narrativa do EXEC-MAP, não como desvio de escopo.
- **Worktree sem `data/raw/*.parquet`.** `db`/dados de mercado são gitignored (`data/raw/*.parquet`) e só existiam no repo principal (`../meta`), não no worktree `../meta-FEAT-001`. Vários testes de `test_dashboard_app.py` (inclusive 2 já existentes, não escritos por esta feature) chamam `_operacao_ctx()` → `live_service.get_status()` → `LiveRuntime.status()` → `_load_universe()`, que precisa dos parquets do WATCHLIST para não levantar `FileNotFoundError`. Copiados os `.parquet` do repo principal para o worktree (comando `cp`, arquivos permanecem gitignored, nenhum commit) — sem isso, a RED baseline já mostrava esses 2 testes falhando por ausência de dado, não por causa da feature. Registrar para o orquestrador: outras features/worktrees desta run podem precisar do mesmo passo manual se tocarem rotas que chamam `get_status()`.
- **Mensagem de `LegacyPaperAccountError`** ajustada de "ARQUIVE"/"APAGUE" (maiúsculo) para "arquivar"/"apagar" (minúsculo) para casar com a asserção do teste — mesma informação, só forma de palavra.

**Desvios relevantes para features seguintes:** o `data/raw/*.parquet` ausente no worktree (ver acima) pode afetar FEAT-002..005 se algum teste novo dessas features também atravessar `get_status()`/`_load_universe()` — vale o orquestrador propagar o mesmo `cp` (ou decidir uma solução permanente, tipo symlink) para os próximos worktrees da run.

**Arquivos realmente tocados (25, idênticos à seção 2):**
`scripts/run_live.py`, `scripts/run_live_sim.py`, `src/core/live_models.py`, `src/dashboard/app.py`, `src/dashboard/live_control.py`, `src/dashboard/live_service.py`, `src/dashboard/templates/partials/operacao_body.html`, `src/journal/live_store.py`, `src/journal/schema.sql`, `src/live/broker.py`, `src/live/broker_mt5.py`, `src/live/feed.py`, `src/live/runtime.py`, `tests/doubles.py` (novo), `tests/test_dashboard_app.py`, `tests/test_journal_live_store_history.py`, `tests/test_live_broker.py`, `tests/test_live_broker_mt5.py`, `tests/test_live_control.py` (novo), `tests/test_live_feed.py`, `tests/test_live_robots.py`, `tests/test_live_runtime.py`, `tests/test_live_store.py`, `tests/test_migrate_live_db.py`, `tests/test_run_live_cli.py` (novo).

---

## 7b. Rodada de correção pós-code-review (tentativa 1/2)

> Preenchido pelo fixer. Corrige APENAS os itens bloqueantes do code-reviewer + os achados do agente de hipóteses combinados numa lista única (ver briefing) — nenhum refactor de passagem.

**Itens corrigidos:**

1. **Bloqueante nº1 (code-reviewer) — botão "Iniciar" morto numa conta mt5 existente.** `operacao_body.html`: form de RETOMADA ganha o campo `mt5_shares_per_lot` visível (pré-preenchido com `config_anterior.mt5_shares_per_lot`) quando `s.modo == "mt5"`. `app.py::operacao_iniciar`: quando o form não traz o valor (ou vem vazio), tenta `live_control.last_config()` antes de declarar erro. Teste novo: `test_operacao_iniciar_retoma_conta_mt5_existente_com_shares_per_lot_do_form` + `..._via_last_config` em `tests/test_dashboard_app.py`.
2. **`mt5_shares_per_lot` aceitava 0/negativo** nas 3 validações (`scripts/run_live.py::build`, `dashboard/live_control.py::start`, `dashboard/app.py::operacao_iniciar`) — trocado `is None` por `is None or <= 0` nas três, mesma mensagem de erro. Testes novos em `tests/test_run_live_cli.py`, `tests/test_live_control.py`, `tests/test_dashboard_app.py`.
3. **`scripts/migrate_live_db.py` não recusava conta `paper` na ORIGEM** (aberta via `ATTACH ... mode=ro`, nunca passa por `ensure_tables`/`_migrate_account_mode_vocabulary`). Nova `LegacySourceAccountError`: recusa ANTES de copiar se `live_accounts` da origem tiver linha com `mode` fora de `('manual','mt5')`, nomeando a(s) conta(s). Teste novo `test_migrate_recusa_quando_origem_tem_conta_paper`; o teste de divergência genérica (`test_migrate_reporta_divergencia_e_levanta_incompleto`) foi realocado de `live_accounts.mode` inválido para `live_intents.kind` inválido, para não colidir com a checagem nova e continuar provando o relatório linha-a-linha em qualquer tabela.
4. **Mensagem de `LegacyPaperAccountError` prometia "arquivar (renomear)"** como solução — não funciona (o CHECK novo rejeita pelo VALOR de `mode`, não pelo nome). Texto corrigido em `src/journal/live_store.py`: nomeia as saídas reais (apagar a linha, ou UPDATE manual consciente de `mode`). Nenhum mecanismo novo de "arquivamento" implementado (só o texto). Teste existente `test_migrate_vocabulario_recusa_quando_ha_conta_paper` ajustado para as novas asserções.
5. **`LegacyPaperAccountError` subia como 500 cru no dashboard.** Capturada especificamente (não `except Exception`) em `_operacao_ctx`, `operacao_iniciar`, `operacao_aportar` (renderizam `operacao_body.html` com banner de erro) e `operacao_historico` (sem banner próprio — devolve texto simples, 200). Teste novo `test_operacao_com_conta_legada_paper_devolve_pagina_com_mensagem_sem_500`.
6. **Divergência de modo no loop virava retry silencioso infinito.** `scripts/run_live.py::cmd_loop` ganha `except ValueError` ANTES do `except Exception` genérico: loga/notifica em nível `error` e `sys.exit(1)` — não continua tentando. Outras exceções (rede, dado) continuam com retry normal, comportamento inalterado. Testes novos `test_cmd_loop_valueerror_de_conta_broker_divergente_e_fatal` e `test_cmd_loop_outros_erros_continuam_com_retry` (contraste).
7. **`time.sleep(2.0)` síncrono bloqueava o event loop do dashboard.** `app.py::operacao_iniciar` (já `async def`) troca a chamada direta a `live_control.start(cfg)` por `await asyncio.to_thread(live_control.start, cfg)`.
8. **Mensagem de `LegacyPaperAccountError` não mencionava a saída de SIMULAÇÃO.** Corrigido junto do item 4: menciona `db/live_sim.sqlite` como a saída mais simples quando a conta legada é do banco de simulação, não da conta real.
9. **`_migrate_account_mode_vocabulary` não limpava `live_accounts_new` órfã e rodava `foreign_key_check` depois do commit.** (a) `DROP TABLE IF EXISTS live_accounts_new` antes de recriar. (b) `PRAGMA foreign_key_check` movido para ANTES do `commit()`, com `conn.rollback()` explícito em caso de violação (antes: violação só era reportada DEPOIS de o schema novo já estar gravado, sem desfazer nada). Testes novos `test_migrate_vocabulario_rebuild_limpa_live_accounts_new_orfa` e `test_migrate_vocabulario_rebuild_aborta_antes_do_commit_se_fk_invalida` em `tests/test_live_store.py`.

**Itens fora de escopo** (registrados na seção 5, não corrigidos nesta rodada): `PaperBroker.mode="mt5"` apagando o marcador simulação/real para o futuro; ausência de lock de dono do processo/conta; prova de vida cobrindo só os primeiros segundos (sem heartbeat contínuo); guarda do dublê só protegendo `LIVE_DB_PATH`; `get_status()` podendo quebrar por `data/raw/*.parquet` ausente ou `live_process.json` malformado; disjuntor do painel refletindo o config do dashboard, não necessariamente o estado real de um processo iniciado fora dele.

**PRE-GATE (regra 18) desta rodada:**
```
1. prova      ✅ ../meta/.venv/Scripts/python.exe -m pytest -q → exit 0, 292 passed
              (281 baseline pré-correção + 11 testes novos desta rodada)
2. lint       n/a — sem ruff/flake8 instalado no venv (mesma situação da 1ª rodada)
3. typecheck  n/a — sem mypy; py_compile nos 10 arquivos .py tocados → todos OK
4. escopo     git diff --name-only feat/blindagem-operacao-real-FEAT-001 → 11 arquivos:
              10 já listados na seção 2 original + scripts/migrate_live_db.py
              (citado explicitamente no item 3 desta correção — permitido pelo
              briefing: "escopo = arquivos já listados no ACTION-PLAN + os
              citados aqui")
5. higiene    grep por TODO/FIXME/print(debug)/console.log/breakpoint no diff
              da correção → nenhum; nenhum arquivo temporário; nenhuma
              dependência nova em requirements.txt
Rodadas até fechar: 1
```

**Evidência da prova de conclusão (pós-correção):**
```
$ ../meta/.venv/Scripts/python.exe -m pytest -q
........................................................................ [ 24%]
........................................................................ [ 49%]
........................................................................ [ 73%]
........................................................................ [ 98%]
....                                                                     [100%]
292 passed, 1 warning in 7.39s
```
(o único warning é `StarletteDeprecationWarning` de `httpx`/`starlette.testclient`, pré-existente, não relacionado a esta correção.)

**Commits desta rodada:**
- `1e7af80` fix(blindagem): FEAT-001 corrige mensagem de LegacyPaperAccountError e rebuild de live_accounts (itens 4, 8, 9)
- `f67bd20` fix(blindagem): FEAT-001 migrate_live_db.py recusa conta paper na origem (item 3)
- `76d87f3` fix(blindagem): FEAT-001 run_live.py valida shares_per_lot e encerra loop em ValueError fatal (itens 2 CLI, 6)
- `e78dbee` fix(blindagem): FEAT-001 live_control.start recusa mt5_shares_per_lot <= 0 (item 2 dashboard)
- `105cb87` fix(blindagem): FEAT-001 conserta botão "Iniciar" morto em conta mt5 e outros gaps do dashboard (bloqueante nº1, itens 2 app, 5, 7)

**Arquivos tocados nesta rodada de correção (11):** `scripts/migrate_live_db.py`, `scripts/run_live.py`, `src/dashboard/app.py`, `src/dashboard/live_control.py`, `src/dashboard/templates/partials/operacao_body.html`, `src/journal/live_store.py`, `tests/test_dashboard_app.py`, `tests/test_live_control.py`, `tests/test_live_store.py`, `tests/test_migrate_live_db.py`, `tests/test_run_live_cli.py` — todos já listados na seção 2 original, exceto `scripts/migrate_live_db.py`, citado explicitamente no briefing desta correção (item 3).

## 8. Definition of Done

- [x] Todos os passos da seção 3 executados
- [x] Prova de conclusão executada com evidência colada na seção 7
- [x] **PRE-GATE verde nos 5 itens**, com relatório na seção 7
- [x] Nenhum arquivo fora da seção 2 tocado (ou desvio justificado)
- [x] Testes da feature verdes; nada skipado
- [x] Sem `TODO`/código comentado/log de debug
- [x] Commits atômicos na convenção do projeto
- [ ] `code-reviewer` aprovou
