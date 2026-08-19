# FEAT-004 — feed-stop-execucao

> Plano de ação escrito pelo feature-agent, revisado (e corrigido quando necessário) pelo plan-reviewer.
> Status: `rascunho` → `em revisão` → `aprovado` → `executado` → `concluído`

**Status:** executado — aguardando code-review (ver §7, Registro de execução)
**Run:** `blindagem-operacao-real` | **Plano original:** `C:\Users\Jeffe\.claude\plans\crie-um-plano-p-ra-gentle-papert.md` (seção "Lote 4 — Feed, stop e execução", subitens 4.1–4.4, mais "Processo por lote")
**Tier:** T3 | **Wave:** 5 | **Isolamento:** worktree `../meta-FEAT-004`
**Branch:** `feat/blindagem-operacao-real-FEAT-004`

## 1. Problema / objetivo

Quatro furos independentes na fronteira feed/stop/execução da operação real,
todos verificados no código atual da worktree (HEAD pós-FEAT-003, `2ba5b29`):

- **4.1 — feed intradiário não é obrigatório.** `scripts/run_live.py::build()`
  resolve `feed = YFinanceFeed() if args.feed == "yfinance" else
  ParquetCloseFeed()` (linha 161) com `--feed` default `"parquet"` (linha
  375). O botão "Iniciar" do dashboard (`dashboard/live_control.py::start()`,
  linhas 267-280) monta o `argv` do processo supervisor **sem nunca passar
  `--feed`** — cai no default. `create_account()` (mesmo arquivo, linha 238)
  hardcoda `feed="parquet"` explicitamente. Resultado confirmado lendo os três
  caminhos: CLI sem `--feed`, botão do dashboard e criação de conta **todos**
  operam dinheiro real (`manual`/`mt5`) vendo o fechamento de ontem o dia
  inteiro — só quem digita `--feed yfinance` à mão escapa disso.
- **4.2 — stop dispara sobre dado velho.** `intraday_tick` (`runtime.py:1256-1339`)
  calcula `velhas = staleness_report(...)` e só usa isso para um `warn`
  genérico (linha 1300-1306); o laço que seguinte que chama
  `self.investment.on_intraday(ctx)` (linha 1318) não filtra por
  `velhas` — um stop cuja cotação está velha dispara e vende do mesmo jeito.
- **4.3 — stop duplica sob corretora manual.** `InvestmentRobot.on_intraday`
  (`live/robots.py:141-171`) reemite um `Intent` de `EXIT` a cada chamada
  enquanto `quote.price <= pos.current_stop` e a posição existir em
  `ctx.account.positions`. Sob `ManualBroker` (`live/broker.py:106-121`),
  `place()` deixa a ordem `SENT` sem preencher — a posição só sai quando um
  humano chama `confirm()`. `intraday_tick` (linhas 1316-1324) não verifica se
  já existe uma saída em voo para o ticker antes de gravar+enviar o intent
  seguinte: 5 chamadas de `intraday_tick` sobre o mesmo tick geram 5 `Intent`
  distintos, 5 `Order` distintas, todas `SENT` — confirmando o "5 ticks = 5
  ordens abertas de 100 ações cada" do plano original.
- **4.4 — quatro furos de execução, todos em `runtime.py`/`broker_mt5.py`:**
  - `_resolve_buy` (linhas 922-952) debita `account.cash -= custo` sem nunca
    comparar `custo` contra o caixa disponível — um fill pior que o planejado
    (gap, gordura de `plan_entry`, que reserva só ~0,22%) passa em silêncio.
  - `MT5Broker._send` (`broker_mt5.py:290-316`) faz
    `order.status = OrderStatus.FILLED` incondicionalmente — mesmo quando
    `result.volume < volume` pedido (fill parcial de verdade da corretora).
    `Order.is_terminal` (`core/live_models.py:222-224`) já exclui `PARTIAL`
    corretamente; o bug é só o `_send` nunca atribuir esse status.
  - `run_live.py::cmd_execute` (linhas 231-234) chama
    `rt.execute_session(clock.next_session(clock.session_date()))`
    **incondicionalmente** — rodado em `POST_CLOSE`, executa as intenções de
    D+1 contra as cotações de D (a sessão errada).
  - `_resolve_buy`/`_resolve_sell` (linhas 922-952, 845-877) nunca chamam
    `self._log(...)` num fill bem-sucedido — entrada e saída executadas hoje
    não geram nenhum evento nem notificação, os dois momentos mais
    importantes do dia com dinheiro real.

Esta feature corrige as quatro. Nenhuma mexe em `strategy/`/`robots.py`
(regra 6 do AGENTS.md): a trava de 4.3 vive no `runtime` (ciclo de vida de
ordem), a supressão de 4.2 é uma decisão de **execução** sobre dado
declaradamente velho (mesma classe do que já existe hoje como `warn`), não
uma regra de sinal nova.

## 2. Arquivos

**Escreve** (produção):
- `src/live/feed.py` — `MT5Feed` novo (`QuoteFeed`): lê `symbol_info_tick`
  do terminal MT5 já conectado (mesma fonte que `MT5Broker` usa para
  executar), import de `MetaTrader5` LAZY (mesmo padrão de `YFinanceFeed`
  neste arquivo e de `MT5Broker` em `broker_mt5.py`). Construtor ganha
  `now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc)`
  **[correção do plan-reviewer, ver §6 item 2]** — mesma convenção já
  usada por `ParquetCloseFeed` — porque `delay_seconds` é a idade REAL do
  tick (`now_fn() - tick.time`), nunca uma constante otimista, e sem
  relógio injetável a idade não é testável de forma determinística (só
  aproximada, com tolerância larga e instável). `symbol_for(ticker)`
  replica a tradução de `MT5Broker.symbol_for` (remove `.SA`, respeita
  `symbol_map` injetado) — duplicação pequena e deliberada (ver §5, riscos
  aceitos), mitigada porque `run_live.py::build()` (abaixo) passa o
  **mesmo** `symbol_map`/credenciais para os dois. Docstring da classe
  ganha um aviso explícito, no mesmo estilo das 4 ressalvas já
  documentadas no topo de `broker_mt5.py` (shares_per_lot/symbol_map/
  filling_type/comissão): `tick.time` é o horário do **SERVIDOR do
  terminal MT5**, não necessariamente UTC — corretoras costumam configurar
  o servidor MT5 num fuso proprio (ex.: GMT+2/GMT+3), deslocado de UTC por
  horas. Calcular `now_fn() - tick.time` sem calibrar esse offset pode
  **SUBESTIMAR** o atraso real (cotação parecendo mais fresca do que é) —
  exatamente a direção perigosa para o invariante desta feature (4.2: stop
  não pode disparar sobre dado velho). Ver risco novo em §5.
- `src/live/broker_mt5.py` — `MT5Broker._send`: `order.status` passa a ser
  `FILLED` só quando `order.filled_qty >= order.quantity`, senão `PARTIAL`
  (mesmo padrão já usado por `ManualBroker.confirm`, `live/broker.py:146`).
  Nenhuma outra linha do método muda.
- `scripts/run_live.py`:
  - `build()`: monta `broker` primeiro (branch `manual`/`mt5` já existente,
    inalterada); em seguida recusa (`ValueError`) `args.feed == "parquet"`
    para os dois modos reais (únicos que chegam até ali — o `else` já existe
    e recusa `--mode` desconhecido antes); monta `MT5Feed(symbol_map=...,
    **_mt5_credentials())` quando `args.feed == "mt5"`, senão `YFinanceFeed()`.
    `ParquetCloseFeed` deixa de ser importado neste arquivo (import morto).
  - `--feed`: choices ganham `"mt5"`; default muda de `"parquet"` para
    `"yfinance"` (fallback seguro sempre que o operador não escolher
    explicitamente).
  - `cmd_execute`: antes de chamar `execute_session`, checa
    `clock.phase() == SessionPhase.OPEN` (import local de
    `core.live_models.SessionPhase`, mesmo estilo de `from live import
    clock` já usado dentro da função); fora de `OPEN`, imprime o motivo e
    `sys.exit(1)` sem tocar o banco.
  - Docstring do módulo ganha uma nota curta sobre `--feed` (operação real
    exige `mt5`/`yfinance`, `parquet` é recusado).
- `src/dashboard/live_control.py` — **[correção de escopo, ver tabela
  abaixo]** `create_account()` (linha 238): `feed="parquet"` →
  `feed="yfinance"`. Consequência mecânica do item acima: com o `build()`
  recusando `parquet` para contas reais, o valor hardcoded quebraria a
  criação de conta pelo botão do dashboard se não for corrigido junto.
- `src/live/runtime.py`:
  - `intraday_tick` (bloco do stop, linhas ~1316-1324): calcula
    `exit_em_andamento` (tickers com `Intent` de `EXIT` `PENDING`/
    `EXECUTING`, via `store.intents_by_status` já existente — sem função
    nova em `live_store.py`) ANTES do laço; para cada intent de
    `on_intraday`, se `intent.ticker in velhas` → suprime com evento
    `error`+notificação (nunca executa sobre cotação velha, 4.2); senão se
    `intent.ticker in exit_em_andamento` → pula sem gravar nem enviar
    (4.3, repetição da MESMA sessão de intraday_tick); senão segue o fluxo
    atual (grava, envia, loga `warn` se "done").
  - **`_sell` (linhas 832-843) — [correção do plan-reviewer, SUBSTANTIVA,
    ver §6 item 1]:** segunda camada de trava, mais geral que a de
    `intraday_tick` acima. ANTES de `self._place(...)`, consulta
    `store.open_orders(conn, account.id)` (já existente, usada por
    `cmd_tickets`) e filtra por `o.ticker == pos.ticker and o.side ==
    OrderSide.SELL`; se já existir uma ordem de venda não-terminal para o
    mesmo ticker, NÃO chama `_place` — loga `warn` ("saída de {ticker}
    descartada: já existe ordem aberta #{id} para o mesmo papel — venda
    não duplicada"), marca a intent atual `CANCELLED` e devolve
    `"rejected"`. Motivo: o `exit_em_andamento` de `intraday_tick` só
    protege contra o MESMO `on_intraday` repetindo dentro da mesma sessão
    — não protege o caso em que um stop intra-dia de ONTEM ficou `SENT`
    sem confirmação humana (posição continua em `account.positions`
    porque `_resolve_sell` só remove a posição quando `filled_qty > 0`) e
    HOJE `close_and_decide`/`execute_session` decide uma saída por OUTRO
    motivo (rotação, fim de mês) para o MESMO ticker — o robô
    (`InvestmentRobot.on_close`) não enxerga ordens em voo, só
    `account.positions` (regra 6: robô não conhece ciclo de vida de
    ordem), então pode legitimamente decidir sair de novo. Sem esta
    segunda trava, `execute_session` chamaria `_sell` de novo e enviaria
    uma SEGUNDA ordem de venda para a mesma posição enquanto a primeira
    ainda está `SENT` — se um humano confirmar as duas, vende o dobro do
    que tem (mesma classe de bug do 4.3 original, por um caminho
    diferente). Colocar a trava em `_sell` (chamado por `execute_session`
    E por `intraday_tick`) fecha os dois caminhos com uma única mudança,
    em vez de duplicar a checagem nos dois call-sites.
  - `_resolve_buy` (linhas 922-952): depois de calcular `custo`, se
    `custo > account.cash` → evento `error`+notificação ANTES do débito
    (não impede nem desfaz o fill, só alerta — o fill já aconteceu de
    verdade); ao final, evento `info`+notificação "entrada executada"
    (4.4a, 4.4d). **[correção do plan-reviewer, ver §6 item 3]** a
    mensagem distingue fill total de fill PARCIAL
    (`order.status == OrderStatus.PARTIAL`): quando parcial, o texto diz
    "ENTRADA PARCIAL" e inclui `order.leaves_qty` (quantidade que não
    entrou) — sem isso a notificação de um fill parcial fica idêntica à de
    um fill total, e ninguém saberia que falta agir sobre o restante.
  - `_resolve_sell` (linhas 845-877): ao final (branch de fill, não a
    branch `pending`/`rejected`), evento `info`+notificação "saída
    executada" (4.4d), com a MESMA distinção PARTIAL/FILLED do item
    acima ("SAÍDA PARCIAL" + `order.leaves_qty` quando aplicável).

**Só lê:**
- `src/journal/live_store.py` — `intents_by_status`, `open_orders`
  (já existentes, reusados sem alteração).
- `src/core/live_models.py` — `OrderStatus.PARTIAL`, `Order.is_terminal`,
  `IntentKind`, `IntentStatus`, `SessionPhase.OPEN` (já existentes).
- `src/live/clock.py` — `phase()` (já existente, assinatura
  `phase(now: datetime | None = None) -> SessionPhase`).
- `src/live/robots.py`, `src/strategy/*` — nenhuma mudança; `on_intraday`
  continua emitindo o Intent, a trava/supressão fica inteiramente no
  runtime (regra 6).

**Testes alterados** (nenhum arquivo de teste novo):
- `tests/test_live_feed.py` — 5 funções novas (4 do escopo original + 1 do
  plan-reviewer): `MT5Feed`: lê tick e declara atraso real (com `now_fn`
  injetado, ver §6 item 2); `symbol_for`; falha de conexão devolve dict
  vazio + on_error; import lazy; **novo:** `now_fn` injetável torna a
  idade determinística.
- `tests/test_live_broker_mt5.py` — 2 funções novas (fill parcial vira
  `PARTIAL`; fill total continua `FILLED`).
- `tests/test_run_live_cli.py` — `_args()` (helper, linha 55-62): default
  `feed="parquet"` → `feed="yfinance"` (senão TODOS os testes existentes que
  usam esse helper com `mode="manual"/"mt5"` quebram na guarda nova de
  `build()` — consequência mecânica, não escopo novo). 4 funções novas
  (`build` recusa `parquet` em `manual`/`mt5`; `build` monta `MT5Feed` quando
  `--feed mt5`; `cmd_execute` recusa fora da fase `OPEN`; `cmd_execute` não
  recusa dentro da fase `OPEN`).
- `tests/test_live_runtime.py` — 4 funções novas (2 do escopo original + 2
  do plan-reviewer): stop suprimido sobre cotação velha; stop não duplica
  sob `ManualBroker` em 5 ticks; **novo:** saída de fecho não duplica
  ordem com stop já em voo (§6 item 1); fill cujo custo excede o caixa
  dispara `error` sem desfazer + entrada/saída executadas notificam +
  **novo:** fill parcial notifica como parcial (§6 item 3) — as duas
  últimas cabem na mesma função de teste ampliada ou em funções irmãs, a
  critério do feature-agent, desde que os cenários da tabela de
  falsificação (§4) fiquem cada um com seu próprio assert.
- `tests/test_live_control.py` — **nenhuma edição.** Duas funções já
  existentes (`test_start_processo_sobrevive_grava_pid`,
  `test_start_mt5_inclui_shares_per_lot_no_argv`) exercitam
  `live_control.start()` → `create_account()` → `cli.build()` com
  `mode="manual"`/`"mt5"` e servem de prova de regressão do item
  `live_control.py` acima (ver §4).

**Correção de escopo em relação ao `EXEC-MAP.md`:**

| Arquivo | EXEC-MAP | Realidade | Justificativa |
|---|---|---|---|
| `src/dashboard/live_control.py` | ausente | **Escreve (adicionado)**, 1 linha | `create_account()` hardcoda `feed="parquet"` (linha 238). Assim que `run_live.py::build()` passa a recusar `parquet` para contas reais (item 4.1, dentro do escopo já previsto), essa linha quebra a criação de conta pelo botão "Iniciar" do dashboard — o próprio caminho que o item 4.1 do plano original cita explicitamente ("botão do dashboard, criação de conta"). Mudança mecânica de um valor de string, sem campo novo em `ProcessConfig`, sem HTML novo — não é o mesmo tipo de mudança que adicionar um seletor de feed na UI (isso sim seria escopo novo, fora desta feature). |

**Consome de outras features:** FEAT-003 — `runtime.py` pós-disjuntor/estado:
`_observe_risk`/`intraday_tick` já carregam painéis e observam o disjuntor
intra-dia; `_robot_state()`/`_restore_robot_state()` já têm a forma atual.
Esta feature não toca nenhuma dessas linhas, só o bloco do stop dentro de
`intraday_tick` e os `_resolve_*` de execução.
**Produz para outras features:** FEAT-005 testa o estado final de
`runtime.py`/`engine_portfolio.py` — nenhuma API pública muda de nome ou
assinatura aqui (só comportamento interno + `Order.status` ganhando um
valor que já existia no enum).

## 2b. Premissas a montante (regra 17)

| # | Premissa | Como verificar | Origem |
|---|----------|----------------|--------|
| 1 | `intraday_tick` já carrega painéis (`_load` com `try/except`), restaura estado e observa o disjuntor via `_observe_risk(..., may_anchor=False)`; nada disso muda nesta feature | `src/live/runtime.py:1256-1339` (HEAD atual) | FEAT-003 |
| 2 | `staleness_report(quotes, now, max_age)` devolve só os tickers estragados (`dict[str, float]`, ticker→idade); `velhas` já é calculado no início de `intraday_tick` antes do laço de stop | `src/live/feed.py:212-226`, `src/live/runtime.py:1284` | código existente |
| 3 | `store.intents_by_status(conn, account_id, status)` devolve `list[Intent]`; nenhuma paginação, custo aceitável (poucas intents abertas por conta) | `src/journal/live_store.py:639-649` | código existente |
| 4 | `ManualBroker.place()` deixa a ordem `SENT` sem preencher (`filled_qty=0`); `_resolve_sell`/`_resolve_buy` então marcam a `Intent` como `EXECUTING` — é esse estado que o dedupe de 4.3 detecta | `src/live/broker.py:106-121`, `src/live/runtime.py:856-864` | código existente |
| 5 | `OrderStatus.PARTIAL` já existe no enum e `Order.is_terminal` já o exclui corretamente (`{FILLED, CANCELLED, REJECTED}`) — o bug de 4.4 é só `broker_mt5.py` nunca atribuir esse valor | `src/core/live_models.py:192-199, 222-224` | código existente |
| 6 | `ManualBroker.confirm` já usa o padrão `FILLED if filled_qty == quantity else PARTIAL` (`live/broker.py:146`) — a correção de `broker_mt5.py` só replica um padrão já estabelecido, não inventa um novo | `src/live/broker.py:146` | código existente |
| 7 | `run_once()` já só chama `execute_session` dentro de `if fase == SessionPhase.OPEN` (`runtime.py:1357-1360`) — o bug de 4.4c (execução fora de hora) é exclusivo do caminho manual `cmd_execute`, não do supervisor automático; por isso a correção fica só em `run_live.py`, não em `runtime.py::execute_session` | `src/live/runtime.py:1343-1372` | código existente — **decisão de design**, ver §5 |
| 8 | `dashboard/live_control.py` nunca chama `execute_session`/`cmd_execute` diretamente (grep confirmado); o único caminho que usa `execute_session` fora do supervisor automático é a CLI | grep em `src/dashboard/` | verificado nesta sessão |
| 9 | `ProcessConfig` (`dashboard/live_control.py:87-96`) não tem campo `feed`; `start()` monta o `argv` do processo filho sem nunca incluir `--feed` (linhas 267-280) — por isso o default do argparse é quem decide, e mudar o default (item 4.1) já cobre o caminho do botão "Iniciar" sem tocar `start()` | `src/dashboard/live_control.py:87-96, 230-243, 267-280` | verificado nesta sessão |
| 10 | `scripts/run_live_sim.py` monta seu próprio `ReplayFeed` diretamente (`tests/doubles`), nunca passa por `run_live.py::build()` — mudar `build()`/`--feed` não afeta o simulador acelerado | `scripts/run_live_sim.py:63,152` | verificado nesta sessão |
| 11 | `_mt5_credentials()` (`run_live.py:134-146`) devolve `dict(login=..., password=..., server=..., path=...)` — mesmos nomes de parâmetro do construtor de `MT5Broker`; `MT5Feed` é desenhado para aceitar os mesmos nomes | `scripts/run_live.py:134-146`, `src/live/broker_mt5.py:86-97` | código existente |
| 12 | `tests/test_run_live_cli.py::_args()` (helper compartilhado, linha 55-62) é usado por praticamente todos os testes deste arquivo com `mode="manual"` default e `feed="parquet"` hardcoded — mudar o default de `build()` sem corrigir este helper quebra ~8 testes hoje verdes | `tests/test_run_live_cli.py:55-118` | verificado nesta sessão |
| 13 | `tests/test_live_control.py` tem 2 testes (`test_start_processo_sobrevive_grava_pid`, `test_start_mt5_inclui_shares_per_lot_no_argv`) que chamam `live_control.start()` completo (não mockam `create_account`) — hoje verdes com `feed="parquet"` hardcoded; ficam RED assim que o passo 3 (guarda em `build()`) entrar sem o passo 4 (fix em `live_control.py`) | `tests/test_live_control.py:68-82, 117-131` | verificado nesta sessão — é a prova de regressão do item `live_control.py` |
| 14 | Nenhum teste hoje verde assere contagem EXATA de `notifier.calls`/`recent_events` num cenário que passe por um fill de ENTER/EXIT bem-sucedido (grep dirigido); os únicos `len(notifier.calls) ==`/`len(eventos) ==` existentes estão em `test_skip_por_dado_incompleto_...` (`ScriptedStrategy({})`, nunca gera Enter/Exit) — os `_log` novos de 4.4d não colidem com contagem exata nenhuma | `tests/test_live_runtime.py:1601-1682` | verificado nesta sessão |

## 3. Passos

| # | Ação | Arquivo(s) | Como sei que funcionou |
|---|------|-----------|------------------------|
| 1 | Em `src/live/feed.py`: classe nova `MT5Feed(QuoteFeed)` — construtor `(symbol_map=None, login=None, password=None, server=None, path=None, on_error=None, now_fn=lambda: datetime.now(timezone.utc))` **(`now_fn` acrescentado pelo plan-reviewer, ver §6 item 2 — mesma convenção de `ParquetCloseFeed`, obrigatório para a idade do tick ser testável de forma determinística)**; `symbol_for(ticker)` (remove `.SA`, respeita `symbol_map`); `_connect(mt5)` idêntico em espírito a `MT5Broker.connect()` (idempotente, `self._connected`); `quotes(tickers)` faz import lazy de `MetaTrader5`, conecta, e para cada ticker chama `mt5.symbol_select`+`mt5.symbol_info_tick`, usa `tick.last` (ou midpoint bid/ask como fallback) como preço, `delay_seconds` = `now_fn() - tick.time` (idade REAL, nunca constante); erro por ticker cai em `on_error` sem propagar (mesmo padrão de `YFinanceFeed`). Docstring da classe ganha o aviso de fuso do servidor MT5 (§5, risco novo) | `src/live/feed.py` | **RED primeiro:** 5 testes em `tests/test_live_feed.py` (4 do escopo original + 1 novo do plan-reviewer): le tick e declara atraso real com `MetaTrader5` fake via `monkeypatch.setitem(sys.modules, ...)`, mesma técnica de `test_live_broker_mt5.py::fake_mt5`, usando `now_fn` injetado para assert EXATO de `delay_seconds == now_fn() - tick.time` (não aproximado); `symbol_for` remove sufixo/respeita map; falha de conexão devolve `{}` + chama `on_error`; import nunca no topo do módulo, mesmo padrão de `test_yfinance_feed_nao_importa_yfinance_no_topo_do_modulo`; **novo:** `test_mt5feed_now_fn_injetavel_permite_idade_deterministica` — dois `tick.time` diferentes com o MESMO `now_fn` fixo provam que a idade é calculada (não uma constante) e independe do relógio real da máquina rodando o teste — falham hoje com `AttributeError: module 'live.feed' has no attribute 'MT5Feed'` |
| 2 | Em `src/live/broker_mt5.py::_send`: mover `order.filled_qty = int(round(filled_volume * self._shares_per_lot))` para ANTES da atribuição de `order.status`, e trocar `order.status = OrderStatus.FILLED` por `order.status = (OrderStatus.FILLED if order.filled_qty >= order.quantity else OrderStatus.PARTIAL)` — mesmo padrão de `ManualBroker.confirm` (`broker.py:146`) | `src/live/broker_mt5.py` | **RED primeiro:** `test_place_fill_parcial_vira_partial_nao_filled` (novo, `tests/test_live_broker_mt5.py`) — pede `quantity=2`, MT5 devolve `volume=1.0` (fill de metade); hoje `order.status == FILLED`, depois `== PARTIAL` e `not order.is_terminal`. `test_place_fill_total_continua_filled` (novo) — mesmo cenário com fill completo, continua `FILLED` (não regride o caminho feliz) |
| 3 | Em `scripts/run_live.py`: reordenar `build()` para montar `broker` primeiro (branches `manual`/`mt5` inalteradas, `else` de modo desconhecido inalterado); logo depois, `if args.feed == "parquet": raise ValueError(...)` (mensagem cita o modo e sugere `mt5`/`yfinance`); `feed = MT5Feed(symbol_map=(json.loads(args.mt5_symbol_map) if args.mt5_symbol_map else None), **_mt5_credentials()) if args.feed == "mt5" else YFinanceFeed()`. Remover import de `ParquetCloseFeed` (não usado mais), importar `MT5Feed`. `--feed`: `choices=("parquet", "yfinance", "mt5")`, `default="yfinance"`. Nota curta na docstring do módulo sobre a exigência | `scripts/run_live.py` | **RED primeiro:** em `tests/test_run_live_cli.py`, corrigir `_args()` (`feed="parquet"` → `feed="yfinance"`, ver premissa 12) e adicionar `test_build_recusa_feed_parquet_em_operacao_real` (`mode="manual"` e `mode="mt5"`, ambos levantam `ValueError`; hoje não levantam) e `test_build_monta_mt5feed_quando_pedido` (`feed="mt5", mode="mt5"` → `isinstance(rt.feed, MT5Feed)`; hoje seria `ParquetCloseFeed`) |
| 4 | Em `src/dashboard/live_control.py::create_account` (linha 238): `feed="parquet"` → `feed="yfinance"` | `src/dashboard/live_control.py` | **Prova de regressão via teste já existente** (não novo): `tests/test_live_control.py::test_start_processo_sobrevive_grava_pid` e `::test_start_mt5_inclui_shares_per_lot_no_argv` — ambos chamam `live_control.start()` → `create_account()` → `cli.build()`. Sem este passo (só o passo 3 aplicado), os dois ficam RED (`ValueError` de `build()` propagando por `create_account`); com os dois passos juntos, voltam a `PASSED` |
| 5 | Em `scripts/run_live.py::cmd_execute`: antes de `print(rt.execute_session(...))`, importar `from core.live_models import SessionPhase` (local, ao lado do `from live import clock` já existente na função) e checar `if clock.phase() != SessionPhase.OPEN:` → imprime mensagem explicando o motivo (rodar fora de `OPEN` executaria as intenções de D+1 contra cotações de D) e `sys.exit(1)`, sem chamar `build()`'s efeitos colaterais além do já feito, sem tocar o banco além do que `build()` já faz (nenhum) | `scripts/run_live.py` | **RED primeiro:** `test_cmd_execute_recusa_fora_da_fase_open` (novo, `tests/test_run_live_cli.py`) — `monkeypatch.setattr(clock, "phase", lambda *a, **k: SessionPhase.POST_CLOSE)`, espera `pytest.raises(SystemExit)`; hoje não levanta. `test_cmd_execute_no_fase_open_nao_recusa` (novo) — mesmo monkeypatch com `SessionPhase.OPEN`, sem conta criada (`execute_session` devolve `execute_skip` normalmente), NÃO levanta `SystemExit` |
| 6 | Em `src/live/runtime.py::intraday_tick`: antes do laço de `on_intraday`, calcular `exit_em_andamento = {i.ticker for i in (store.intents_by_status(conn, account.id, IntentStatus.PENDING) + store.intents_by_status(conn, account.id, IntentStatus.EXECUTING)) if i.kind == IntentKind.EXIT}`. Dentro do laço, para cada `intent`: se `intent.ticker in velhas` → `self._log(conn, account.id, "error", "feed", f"stop de {intent.ticker} suprimido: cotacao atrasada {int(velhas[intent.ticker])}s (feed {self.feed.name}) -- nao executa sobre dado velho")` e `continue` (não grava, não envia); senão se `intent.ticker in exit_em_andamento` → `continue` (não grava, não envia — já existe saída em voo); senão segue o fluxo atual (`store.record_intent` + `self._sell(...)` + `warn` se `"done"`). **[correção do plan-reviewer, SUBSTANTIVA, §6 item 1]** ADICIONALMENTE, em `_sell` (linhas 832-843, chamado por ESTE laço E por `execute_session`): ANTES de `self._place(...)`, filtrar `store.open_orders(conn, account.id)` por `o.ticker == pos.ticker and o.side == OrderSide.SELL`; se já existir uma ordem de venda não-terminal para o ticker, não chamar `_place`, logar `warn` e marcar a intent `CANCELLED`/retornar `"rejected"` — trava independente da de `intraday_tick` acima, que fecha o caso em que a saída duplicada vem de `execute_session` (rotação decidida no fecho) enquanto um stop de ONTEM ainda está `SENT` sem confirmação manual (posição continua em `account.positions`, o robô não vê ordens em voo) | `src/live/runtime.py` | **RED primeiro, quatro testes em `tests/test_live_runtime.py`** (2 do escopo original + 2 novos do plan-reviewer): `test_stop_intraday_suprimido_sobre_cotacao_velha` — posição aberta via `_runtime()` (mode mt5/PaperBroker), cotação abaixo do stop mas com `ts` de ~10.000s atrás (`ReplayFeed.set(..., ts=...)`); hoje `tick.detail["stops"] == 1` e a posição fecha; depois, `stops == 0`, posição continua aberta, evento `error` gravado, notifier chamado com nível `error`. `test_stop_intraday_nao_duplica_ordem_sob_corretora_manual` — posição aberta via `_runtime(..., mode="manual")`, confirmada manualmente (`rt.broker.confirm` + `reconcile_pending_fills`), depois cotação fresca abaixo do stop e **5 chamadas seguidas** de `intraday_tick`; hoje `len(store.open_orders(...))` conta 5 ordens de venda; depois, 1. **novo:** `test_saida_de_fecho_nao_duplica_ordem_com_stop_ja_em_voo` — posição com stop disparado via `intraday_tick` sob `ManualBroker` (ordem `SENT`, não confirmada, posição continua aberta); no fecho seguinte, o robô decide EXIT de novo para o MESMO ticker por outro motivo (`ScriptedStrategy` forçando `Exit`); hoje `execute_session` chama `_sell` de novo e `len(store.open_orders(...))` conta 2 ordens de venda para o ticker; depois, 1 (a segunda é recusada, intent marcada `CANCELLED`, evento `warn` registrado) |
| 7 | Em `src/live/runtime.py::_resolve_buy`: depois de `custo = preco * order.filled_qty + order.fees`, se `custo > account.cash` → `self._log(conn, account.id, "error", "runtime", f"entrada em {intent.ticker} custou R$ {custo:.2f}, acima do caixa disponivel (R$ {account.cash:.2f})", {"custo": round(custo,2), "caixa": round(account.cash,2)})` ANTES de `account.cash -= custo` (não impede o débito — o fill já aconteceu). No final do método (branch de fill aplicado, antes do `return "done"`), `self._log(conn, account.id, "info", "runtime", f"entrada executada: ...")`. Em `_resolve_sell`, no final da branch de fill aplicado (antes do `return "done"`), `self._log(conn, account.id, "info", "runtime", f"saida executada: ...")`. **[correção do plan-reviewer, §6 item 3]** as duas mensagens verificam `order.status == OrderStatus.PARTIAL` e, quando verdadeiro, trocam o texto para "ENTRADA PARCIAL"/"SAÍDA PARCIAL" incluindo `order.leaves_qty` (quantidade que não entrou/saiu) — sem isso um fill parcial (já hoje alcançável via `ManualBroker.confirm`, e após o passo 2 também via MT5) soaria idêntico a um fill total na notificação, escondendo que falta agir sobre o restante | `src/live/runtime.py` | **RED primeiro, três testes** (2 do escopo original + 1 novo): `test_fill_com_custo_acima_do_caixa_dispara_alerta_sem_desfazer` — broker fake que preenche a um preço muito acima do usado por `plan_entry` (ex.: 100x); hoje nenhum evento/notificação sobre o estouro de caixa; depois, evento `error` mencionando o custo, `account.cash` fica negativo (não é impedido) e a posição É criada normalmente (fill real não se desfaz). `test_entrada_e_saida_executadas_notificam` — fluxo padrão de `_runtime()` (entrada via `execute_session`, saída via stop intra-dia); hoje `notifier.calls` não tem nenhuma entrada `info`/"runtime" mencionando "entrada"/"saida"; depois, tem as duas. **novo:** `test_fill_parcial_notifica_como_parcial_com_quantidade_restante` — `ManualBroker.confirm(order, filled_qty=metade, ...)` seguido de `reconcile_pending_fills`; hoje a notificação (se existisse) seria igual à de fill total; depois, o texto contém "PARCIAL" e o `leaves_qty` correto |
| 8 | Rodar a prova (§4) inteira. `git diff --stat plan/blindagem-operacao-real...HEAD` tem de mostrar **exatamente** os 5 arquivos de produção da §2 (`live/feed.py`, `live/broker_mt5.py`, `scripts/run_live.py`, `dashboard/live_control.py`, `live/runtime.py`) + os 4 arquivos de teste — nenhum a mais | — | `../meta/.venv/Scripts/python.exe -m pytest -q` → exit 0, **328 passed** (baseline) **+ 15 novos** (5 feed + 2 broker_mt5 + 4 run_live_cli + 4 runtime; `test_live_control.py` sem função nova, só regressão) = **343** |

> **Ordem executável.** 1 (MT5Feed) antes de 3 (run_live.py importa/usa
> `MT5Feed`). 2 (broker_mt5) é independente, pode rodar em qualquer ordem
> antes do passo 8. 3 antes de 4 (o fix de `live_control.py` só faz sentido
> depois que `build()` já recusa `parquet`; testar 4 sem 3 não prova nada).
> 5 é independente de 1-4 (mesmo arquivo `run_live.py`, função diferente,
> sem dependência de dado). 6 e 7 são independentes entre si e de 1-5 (mesmo
> arquivo `runtime.py`, métodos diferentes: `intraday_tick` vs
> `_resolve_buy`/`_resolve_sell`) — mantidos em passos separados só para
> isolar a prova de cada um, não por dependência real. 8 fecha.

## 4. Prova de conclusão (uma só)

**Origem:** ⬜ comando/teste que já existe ☑ asserção nova em teste existente
(parte, `live_control.py` via 2 testes já existentes — regressão, sem editar
nada) + teste novo (maioria, comportamento novo, sem cenário anterior)
⬜ estado observável

```
../meta/.venv/Scripts/python.exe -m pytest -q
```

> **Prova PROMOVIDA** da linha do `EXEC-MAP.md`
> (`pytest -q tests/test_live_runtime.py tests/test_live_broker_mt5.py`) para
> a **suíte inteira**, mesmo precedente de FEAT-001/FEAT-003. Motivo: o
> blast radius passou dos dois arquivos nomeados — `scripts/run_live.py`
> (CLI, 3 funções tocadas) e `src/dashboard/live_control.py` (correção de
> escopo) entram na superfície, e `tests/test_live_control.py` (regressão
> sem edição) e `tests/test_run_live_cli.py` (helper compartilhado corrigido)
> precisam estar dentro da prova para não ficar cego a uma quebra. Continua
> sendo **uma** prova: um comando, um exit code.
>
> Nenhum arquivo de teste novo, nenhum harness/fixture novo: reaproveita
> `_runtime`, `_write_parquet`, `_RecordingNotifier`, `ScriptedStrategy`
> (`tests/test_live_runtime.py`), `fake_mt5`/`_symbol_info`/`_tick`/
> `_order_send_result` (`tests/test_live_broker_mt5.py`), `_args`/`cli`/
> `isolated_db` (`tests/test_run_live_cli.py`), e a técnica de
> `monkeypatch.setitem(sys.modules, "MetaTrader5", ...)` já estabelecida.

**Teste de falsificação (obrigatório) — cenário de feature quebrada × teste que o pega:**

| Cenário quebrado | Teste que falha |
|------------------|-----------------|
| operação real volta a aceitar `--feed parquet` (ou o default volta a ser `parquet`) | `test_build_recusa_feed_parquet_em_operacao_real` |
| `MT5Feed` some ou para de existir | `test_build_monta_mt5feed_quando_pedido` + os 5 testes de `tests/test_live_feed.py` |
| botão "Iniciar" do dashboard volta a criar conta com `feed="parquet"` | `test_start_processo_sobrevive_grava_pid` / `test_start_mt5_inclui_shares_per_lot_no_argv` (existentes) voltam a falhar assim que a guarda de `build()` estiver presente |
| stop volta a disparar sobre cotação velha | `test_stop_intraday_suprimido_sobre_cotacao_velha` |
| stop volta a duplicar ordem sob `ManualBroker` (5 ticks = 5 ordens) | `test_stop_intraday_nao_duplica_ordem_sob_corretora_manual` |
| **[novo]** saída decidida no fecho duplica ordem enquanto um stop de ontem ainda está `SENT`/não confirmado | `test_saida_de_fecho_nao_duplica_ordem_com_stop_ja_em_voo` |
| **[novo]** `MT5Feed` calcula idade a partir de constante/relógio real (não testável, não determinístico) | `test_mt5feed_now_fn_injetavel_permite_idade_deterministica` |
| fill parcial no MT5 volta a virar `FILLED` (resto nunca reconciliado) | `test_place_fill_parcial_vira_partial_nao_filled` |
| fill total deixa de marcar `FILLED` (regressão do caminho feliz) | `test_place_fill_total_continua_filled` |
| **[novo]** fill parcial notifica como se fosse fill total (esconde quantidade não executada) | `test_fill_parcial_notifica_como_parcial_com_quantidade_restante` |
| `cmd_execute` volta a rodar fora da fase `OPEN` | `test_cmd_execute_recusa_fora_da_fase_open` |
| guarda de `cmd_execute` bloqueia também dentro da fase `OPEN` (falso positivo) | `test_cmd_execute_no_fase_open_nao_recusa` |
| fill com custo acima do caixa deixa de alertar | `test_fill_com_custo_acima_do_caixa_dispara_alerta_sem_desfazer` |
| entrada/saída executadas voltam a não notificar nada | `test_entrada_e_saida_executadas_notificam` |

**RED antes de GREEN:** obrigatório (T3). Os 15 testes novos + os 2
existentes de `test_live_control.py` são verificados FALHANDO antes da
mudança correspondente. Um falha por `AttributeError` (passo 1, `MT5Feed`
ainda não existe — motivo trivial mas válido, contrato novo); os demais
falham por motivo **semântico** (comportamento realmente errado: parquet
aceito quando deveria recusar, stop disparando/duplicando quando não
deveria — inclusive a duplicação cruzada fecho×stop —, `FILLED` quando
deveria ser `PARTIAL`, execução fora de fase, ausência de log/notificação,
ausência de alerta de caixa, notificação de parcial idêntica à de total).

**Se a prova falhar:** o trabalho está inteiro na worktree, nada foi
mesclado. Nenhuma migração de schema nesta feature (todos os arquivos
tocados são código, não DDL). Reverter é `git checkout -- .` na worktree.
Falha em teste que era verde ANTES desta feature — em especial os 2 de
`tests/test_live_control.py` sem o passo 4, ou qualquer teste de
`tests/test_run_live_cli.py` sem a correção do `_args()` (premissa 12) — é
sinal de que os passos 3/4 não foram aplicados juntos, não de que o teste
esteja errado.

## 5. Riscos e gatilhos de escalação

### Riscos ATIVOS (mitigados no plano)

- **`MT5Feed.symbol_for` duplica a lógica de `MT5Broker.symbol_for`** —
  aceito deliberadamente (não extraído para função compartilhada) para não
  mexer na assinatura pública já testada de `MT5Broker` fora do escopo desta
  feature. Mitigação: `run_live.py::build()` é o único lugar que constrói os
  dois, e passa o **mesmo** `symbol_map`/credenciais para ambos — a
  duplicação nunca diverge em produção, só no código-fonte.
- **`MT5Feed` não foi validado contra um terminal MT5 real** — mesma
  ressalva já documentada para `MT5Broker` (`broker_mt5.py`, topo do
  arquivo) e repetida na docstring de `run_live.py`: teste primeiro com
  volume mínimo, observando o terminal ao vivo.
- **[risco novo, plan-reviewer] `tick.time` do MT5 é o relógio do
  SERVIDOR do terminal, não necessariamente UTC** — corretoras
  frequentemente configuram o servidor MT5 num fuso próprio (ex.:
  GMT+2/GMT+3), deslocado de UTC por horas. `delay_seconds = now_fn() -
  tick.time` (passo 1) assume implicitamente que os dois lados estão no
  mesmo referencial; se o servidor estiver ADIANTADO em relação a UTC, a
  conta pode dar um número BAIXO (ou até negativo, truncado para perto de
  zero) mesmo com uma cotação de fato antiga — a cotação PARECE fresca
  quando não é, exatamente a direção perigosa para o invariante desta
  feature (4.2: stop nunca dispara sobre dado velho). Mitigação parcial
  nesta feature: `now_fn` injetável (passo 1) torna o CÁLCULO testável e
  auditável; a CALIBRAÇÃO do offset servidor↔UTC continua sendo tarefa do
  operador antes de operar volume relevante — mesma categoria dos 4 itens
  já sem valor universal documentados no topo de `broker_mt5.py`
  (shares_per_lot/symbol_map/filling_type/comissão), agora um 5º item da
  mesma família, e deve ser citado ali. Não bloqueia esta feature (é
  documentação + testabilidade, não redesenho), mas é um risco ATIVO, não
  um mero "não validado contra terminal real" genérico.
- **[risco novo, plan-reviewer] `MT5Broker.connect()` e `MT5Feed._connect()`
  chamam `mt5.initialize()` de forma independente** — cada objeto tem seu
  próprio `self._connected`, nenhum sabe da conexão do outro; no primeiro
  ciclo (`_buy`/`_sell` e `intraday_tick` do mesmo `run_once`), os dois
  chamam `mt5.initialize()` uma vez cada, ainda que o pacote `MetaTrader5`
  mantenha estado de conexão a nível de processo (não por objeto). A
  própria docstring de `MT5Broker.connect()` alerta que chamar
  `initialize()` sem necessidade "é, na prática de alguns terminais, um
  jeito de perder estado de ordens em voo à toa" — o mesmo texto que já
  motivou a idempotência de `MT5Broker`. Aceito como risco de validação
  contra terminal real (mesmo item acima), não como bug de lógica: é uma
  chamada extra, não repetida em loop.
- **Alerta de custo > caixa (4.4a) não impede nem desfaz o fill** —
  intencional: uma execução real já aconteceu, não há como "cancelar" depois
  do fato. Mesma filosofia de `reconcile_broker_cash` (detector puro, nunca
  decide).
- **`cmd_execute`'s guarda de fase vive só em `run_live.py`, não em
  `runtime.py::execute_session`** — decisão deliberada (ver premissa 7):
  `run_once()` já só chama `execute_session` dentro da fase `OPEN`, então o
  bug real está isolado no caminho manual da CLI. Colocar a guarda em
  `execute_session()` exigiria um parâmetro `now` novo e editar os 8
  call-sites diretos de `tests/test_live_runtime.py` (que hoje chamam sem
  `now`, dependendo do relógio real) — blast radius desproporcional ao
  defeito real, que é só a CLI.
- **Dedupe de 4.3 usa `PENDING` + `EXECUTING`** — `PENDING` é defesa em
  profundidade (não deveria ocorrer na prática para um stop intra-dia, que
  avança direto para `EXECUTING`/`DONE`/`REJECTED` na mesma chamada, ver
  premissa 4), mas é uma checagem barata (mesma query, um status a mais) que
  fecha qualquer lacuna que a análise não tenha antecipado.
- **[risco novo, plan-reviewer] Dedupe de 4.3 tinha um segundo caminho
  aberto: saída decidida no FECHO (rotação) duplicando um stop intra-dia
  de ONTEM ainda `SENT`/não confirmado** — coberto agora pela trava em
  `_sell` (§6 item 1), não pela trava original de `intraday_tick` (que só
  vê repetições do PRÓPRIO `on_intraday` na mesma sessão). Registrado
  aqui porque é a mesma classe de bug do 4.3 original por um caminho que a
  análise inicial do plano não cobria.

### Riscos CONHECIDOS (aceitos, sem passo no plano)

- **Duas instâncias escrevendo `policy_state`/gravando ordens
  concorrentemente** — risco já registrado em FEAT-001/003, não aumentado
  nem corrigido aqui.
- **`_resolve_buy`/`_resolve_sell` agora geram mais eventos/notificações
  por pregão** — aceito como o próprio objetivo do item 4.4d; se o volume de
  eventos incomodar no operacional real, é ajuste de `--notify-min-level`
  (já existente), não bug desta feature.
- **`YFinanceFeed` como novo default (era `parquet`)** — troca o "silêncio
  perigoso" por um feed com 15min de atraso conhecido e documentado; ainda
  não é `MT5Feed` (atraso ~0) a menos que o operador passe `--feed mt5`
  explicitamente. Aceito: o plano pede "recusar parquet", não "forçar mt5
  sempre" (nem todo operador mt5 necessariamente quer cotação via o mesmo
  terminal que executa). **[precisão adicionada pelo plan-reviewer]** Nota
  importante para o operacional: pelo botão "Iniciar" do dashboard
  especificamente, isso não é uma escolha do operador — `live_control.
  start()` (premissa 9) NUNCA inclui `--feed` no `argv` do processo filho,
  então uma conta `mt5` criada pelo dashboard SEMPRE sobe com
  `YFinanceFeed` (15min), nunca com `MT5Feed`, mesmo sendo o feed
  preferido para esse modo; só quem invocar `scripts/run_live.py loop
  --feed mt5` manualmente (fora do dashboard) chega no `MT5Feed`. Isso
  permanece fora do escopo desta feature (um seletor de feed na UI é
  mudança de UI/`ProcessConfig`, explicitamente cortada na tabela de
  "correção de escopo" da §2) — registrado aqui só para a decisão ficar
  honesta, não para gerar um passo novo.
- **[risco novo, plan-reviewer] Fill PARCIAL não gera nenhuma tentativa de
  reconciliar o restante não executado** — `_resolve_buy`/`_resolve_sell`
  marcam a `Intent` `DONE` assim que `filled_qty > 0`, independente de
  `order.status` ser `PARTIAL` ou `FILLED` (não há checagem de
  `order.is_terminal` nesse ponto); `reconcile_pending_fills` só revisita
  intents em `EXECUTING`, então uma vez `DONE` o restante nunca mais é
  tocado automaticamente. Para `MT5Broker` isso é consistente com
  `ORDER_FILLING_IOC` (immediate-or-cancel: o que não preencheu na hora
  não vai preencher depois, não há "resto" para reconciliar de verdade);
  para `ManualBroker.confirm` com fill parcial relatado por um humano, o
  restante fica simplesmente perdido a menos que o operador note a
  notificação "PARCIAL" (§6 item 3) e decida manualmente abrir uma NOVA
  ordem para a diferença. Aceito como o escopo literal do item 4.4b
  original ("vira PARTIAL, não FILLED" — não "reconcilia o resto
  automaticamente"); mitigado o suficiente por esta feature ao tornar a
  notificação explícita sobre o que faltou (§6 item 3), mas registrado
  aqui para não ser lido como "PARTIAL implica retomada automática".

### Gatilhos de escalação

Escalarei se: **(a)** `MT5Feed` precisar de qualquer estado/objeto
compartilhado de verdade com `MT5Broker` (não só mesma credencial/símbolo) —
sinal de que a duplicação deliberada do risco ativo acima não é mais
sustentável; **(b)** a guarda de `cmd_execute` precisar se estender para
`execute_session()` em si (ex.: se o plan-reviewer entender que o caminho
automático via `run_once` também tem um buraco que a premissa 7 não cobriu)
— mudaria a assinatura pública e o blast radius de teste; **(c)** algum teste
hoje verde em `tests/test_dashboard_app.py` quebrar por causa do fix em
`live_control.py` (não previsto pela premissa 9, mas não auditado linha a
linha); **(d)** os 15 testes novos não fecharem RED→GREEN em 2 rodadas de
pre-gate.

## 6. Correções do plan-reviewer

Revisão feita em fluxo de rigor reduzido (sem agente de hipóteses nesta
run — decisão explícita do usuário). As 4 correções abaixo vieram de
procurar ativamente cenários adversariais que a ausência do agente de
hipóteses deixaria passar, focados nos quatro invariantes centrais do
Lote 4 (feed obrigatório, stop nunca sobre dado velho, stop nunca
duplica, execução sinalizada corretamente).

1. **[SUBSTANTIVA] Dedupe de stop duplicado (4.3) cobria só metade do
   problema.** O passo 6 original só protegia `intraday_tick` contra
   repetir o PRÓPRIO `on_intraday` na mesma sessão (via `exit_em_andamento`
   checado antes de gravar/enviar). Isso não protege o caminho cruzado:
   um stop intra-dia de ontem fica `SENT` sem confirmação sob
   `ManualBroker` (posição continua em `account.positions`, porque
   `_resolve_sell` só remove a posição quando `filled_qty > 0`); no fecho
   seguinte, `InvestmentRobot.on_close` não enxerga ordens em voo (regra
   6 — o robô só vê `account.positions`, não ciclo de vida de ordem) e
   pode legitimamente decidir EXIT de novo por outro motivo (rotação, fim
   de mês); `execute_session` chamaria `_sell` outra vez e enviaria uma
   SEGUNDA ordem de venda para a mesma posição — mesma classe de bug do
   4.3 original ("5 ticks = 5 ordens"), por um caminho que a análise
   original não cobria. Corrigido movendo uma segunda trava para dentro
   de `_sell` (primitiva compartilhada por `execute_session` E
   `intraday_tick`): antes de `_place`, verifica `store.open_orders` por
   ticker+`SELL` não-terminal e recusa duplicar. Novo teste:
   `test_saida_de_fecho_nao_duplica_ordem_com_stop_ja_em_voo`.
2. **[SUBSTANTIVA] `MT5Feed` sem relógio injetável e sem aviso sobre fuso
   do servidor MT5.** O passo 1 original calculava `delay_seconds = now -
   tick.time` sem `now_fn` injetável (impossível testar de forma
   determinística) e sem registrar que `tick.time` é o horário do
   SERVIDOR do terminal MT5 — que corretoras comumente configuram em
   fuso próprio, deslocado de UTC por horas. Sem calibrar esse offset, a
   idade calculada pode SUBESTIMAR o atraso real (cotação parecendo mais
   fresca do que é) — a direção perigosa para o invariante 4.2 (stop
   nunca dispara sobre dado velho). Corrigido: `MT5Feed` ganha `now_fn`
   injetável (mesma convenção de `ParquetCloseFeed`) e a docstring passa
   a registrar o risco como um 5º item da família "sem valor universal"
   já documentada em `broker_mt5.py`. Novo teste:
   `test_mt5feed_now_fn_injetavel_permite_idade_deterministica`. Risco
   residual (calibração do offset servidor↔UTC) registrado em §5 — exige
   validação humana contra terminal real, não é resolvível só com código.
3. **[SUBSTANTIVA] Notificação de fill não distinguia PARCIAL de TOTAL.**
   O passo 7 original notificava "entrada/saída executada" sem checar
   `order.status`. Como fill parcial já é alcançável HOJE via
   `ManualBroker.confirm` (e após o passo 2 também via `MT5Broker`), a
   notificação ficaria idêntica para os dois casos — escondendo
   exatamente a informação que o item 4.4b desta mesma feature passou a
   detectar corretamente (`PARTIAL` vs `FILLED`). Corrigido: as duas
   mensagens agora citam "PARCIAL" + `order.leaves_qty` quando
   `order.status == PARTIAL`. Novo teste:
   `test_fill_parcial_notifica_como_parcial_com_quantidade_restante`.
4. **[PONTUAL, documentação] Riscos registrados sem passo de código
   novo, para a decisão ficar honesta (não altera comportamento):** (a)
   `MT5Broker.connect()` e `MT5Feed._connect()` chamam `mt5.initialize()`
   de forma independente — aceitável, mas citado explicitamente dado o
   próprio aviso de `broker_mt5.py` sobre chamadas repetidas; (b) fill
   PARCIAL não tem reconciliação automática do restante (`Intent` vira
   `DONE` assim que `filled_qty > 0`, independente de `is_terminal`) —
   consistente com IOC do MT5, mas registrado para não ser lido como
   "PARTIAL implica retomada automática"; (c) o botão "Iniciar" do
   dashboard nunca passa `--feed`, então uma conta `mt5` criada por ele
   sempre sobe com `YFinanceFeed`, nunca `MT5Feed` — fora de escopo
   (seletor de feed na UI é mudança à parte, já cortada na tabela de
   "correção de escopo"), mas deixado explícito.

**Natureza das correções:** SUBSTANTIVAS (itens 1-3 mudam abordagem,
inserem passo de verdade e trocam/ampliam prova — item 1 em especial
generaliza a trava de um call-site específico para uma primitiva
compartilhada). Item 4 é documentação pura, sem efeito em código ou
prova.

**Contagem de testes atualizada:** 15 novos (5 `test_live_feed.py` + 2
`test_live_broker_mt5.py` + 4 `test_run_live_cli.py` + 4
`test_live_runtime.py`), antes 12 — baseline 328 + 15 = **343**.

**Tier:** mantido T3 — nenhuma correção muda a natureza da feature
(execução de ordem com dinheiro real), só fecha lacunas dentro do mesmo
escopo já T3.

## 7. Registro de execução

Executado em worktree `../meta-FEAT-004`, branch `feat/blindagem-operacao-real-FEAT-004`,
a partir de `2ba5b29`. 5 commits atômicos, um por passo (2 e 3 fundidos por
tocarem o mesmo arquivo/objetivo — feed obrigatório + `cmd_execute` só na
fase `OPEN` — ambos em `scripts/run_live.py`):

| Commit | Passo(s) | Conteúdo |
|---|---|---|
| `cd96952` | 1 | `MT5Feed` (`src/live/feed.py`) com `now_fn` injetável |
| `f5c662e` | 2 | `MT5Broker._send` fill parcial vira `PARTIAL` |
| `2b84cd5` | 3, 4, 5 | `build()` recusa `--feed parquet`, monta `MT5Feed`; `live_control.create_account` feed→`"yfinance"`; `cmd_execute` recusa fora da fase `OPEN` |
| `6300a1d` | 6 | `intraday_tick` suprime stop sobre cotação velha + dedupe `exit_em_andamento`; `_sell` recusa 2ª ordem de venda com uma já aberta |
| `eb5dcec` | 7 | `_resolve_buy`/`_resolve_sell` notificam entrada/saída executada, alerta de caixa estourado, distinção PARCIAL/TOTAL |

### RED → GREEN dos 3 testes centrais que o plan-reviewer acrescentou

**`test_mt5feed_now_fn_injetavel_permite_idade_deterministica`** (`tests/test_live_feed.py`)
- RED: `git stash` isolado em `src/live/feed.py` (mantendo o teste novo) →
  `pytest -q tests/test_live_feed.py` → `ImportError: cannot import name
  'MT5Feed' from 'live.feed'` (1 error na coleta).
- GREEN: `git stash pop` (restaura `MT5Feed`) → `pytest -q
  tests/test_live_feed.py` → `17 passed in 0.50s` (era 12 antes desta
  feature).

**`test_saida_de_fecho_nao_duplica_ordem_com_stop_ja_em_voo`** (`tests/test_live_runtime.py`)
- RED (antes do passo 6): `pytest -q tests/test_live_runtime.py -k
  saida_de_fecho_nao_duplica` → `AssertionError: venda duplicada -- a 2a
  saida deveria ter sido recusada / assert 2 == 1` (2 ordens de venda
  abertas para o mesmo ticker — a trava de `_sell` ainda não existia).
- GREEN (depois do passo 6): mesmo comando → `1 passed` (roda junto com os
  outros 2 testes de stop: `3 passed in 1.67s`).

**`test_fill_parcial_notifica_como_parcial_com_quantidade_restante`** (`tests/test_live_runtime.py`)
- RED (antes do passo 7): `pytest -q tests/test_live_runtime.py -k
  fill_parcial_notifica_como_parcial` → `AssertionError: fill parcial
  deveria notificar como PARCIAL, nao como fill total / assert [] ` (nenhuma
  notificação "PARCIAL" existia — `_resolve_buy` não notificava nada).
- GREEN (depois do passo 7): mesmo comando → `1 passed` (roda junto com os
  outros 2 testes de notificação: `3 passed in 1.27s`).

Os demais 14 testes novos (2 `MT5Broker` fill parcial, 4 `run_live.py` CLI,
2 stop restantes de `test_live_runtime.py`, 2 execução restantes de
`test_live_runtime.py`, mais os 4 restantes de `test_live_feed.py`) seguiram
o mesmo protocolo RED→GREEN passo a passo (capturado no terminal durante a
execução, não reproduzido aqui por brevidade — cada um falhou por motivo
SEMÂNTICO antes da mudança correspondente, nunca por erro de digitação no
teste). Os 3 testes já existentes de `tests/test_live_control.py`
(`test_start_processo_morre_na_hora_...`, `test_start_processo_sobrevive_...`,
`test_start_mt5_inclui_shares_per_lot_no_argv`) ficaram RED assim que o
passo 3 (guarda em `build()`) entrou sem o passo 4 (fix em
`live_control.py`) — confirmado (3 failed) antes de aplicar o passo 4, e
voltaram a `PASSED` imediatamente depois (nota: são 3, não os 2 que a
premissa 13 do plano antecipava — mesma causa raiz, mesmo fix de 1 linha).

### PRE-GATE

1. **Prova de conclusão** (`../meta/.venv/Scripts/python.exe -m pytest -q`,
   rodado no worktree): `346 passed, 1 warning in 29.55s`. O warning é o
   `StarletteDeprecationWarning` pré-existente do `fastapi.testclient`, sem
   relação com esta feature. (Nota: a suíte só chegou a rodar completa após
   copiar `data/raw/*.parquet` do repo principal para o worktree — esse
   diretório é gitignorado e cada worktree precisa da própria cópia; sem
   isso, 12 testes de `tests/test_dashboard_app.py`, fora do escopo desta
   feature, falhavam por `FileNotFoundError` em qualquer commit, inclusive
   antes desta feature — confirmado rodando a mesma suíte na branch-base.)
2. **Lint:** nenhum linter (ruff/flake8) configurado no projeto
   (`pyproject.toml` não declara nenhum) nem instalado no venv — não
   aplicável.
3. **Typecheck/compilação:** `python -m py_compile` nos 9 arquivos tocados
   (5 produção + 4 teste) → `COMPILE OK`, sem erro. `mypy` não está
   instalado no projeto — typecheck estático não aplicável, compilação
   cobre a checagem sintática disponível.
4. **Escopo:** `git diff --name-only plan/blindagem-operacao-real...HEAD` →
   exatamente os 9 arquivos previstos na §2 (`scripts/run_live.py`,
   `src/dashboard/live_control.py`, `src/live/broker_mt5.py`,
   `src/live/feed.py`, `src/live/runtime.py`,
   `tests/test_live_broker_mt5.py`, `tests/test_live_feed.py`,
   `tests/test_live_runtime.py`, `tests/test_run_live_cli.py`) — nenhum a
   mais, nenhum a menos.
5. **Higiene:** sem `print()` de debug (o único `print(` novo é em
   `cmd_execute`, mensagem de usuário da CLI — mesmo padrão de
   `cmd_init`/`cmd_status`/etc. já existentes no arquivo), sem `TODO`/
   `FIXME` novo, `git status --short` limpo (nada não commitado), nenhuma
   dependência nova em `requirements.txt`.

### Desvios

- **Contagem de testes novos: 17, não 15** (baseline 328 + 17 = **346**,
  não 343 como a aritmética da §6 previa). Causa: o plano explicitamente
  permitiu, no item de `test_live_runtime.py` da seção "Testes alterados",
  combinar os 3 cenários do passo 7 (alerta de caixa; entrada/saída
  notificam; fill parcial notifica) "na mesma função de teste ampliada OU
  em funções irmãs, a critério do feature-agent" — optei por 3 funções
  irmãs separadas (uma por cenário) em vez de comprimir em 1, pela mesma
  razão que already vale para o passo 6 (cada cenário de falsificação com
  seu próprio assert, sem acoplar setup de cenários não relacionados). Isso
  é uma escolha explicitamente autorizada pelo texto do plano, não um
  desvio de escopo — registrado aqui só porque muda a contagem final
  declarada em §6.
- **3 testes de `tests/test_live_control.py` ficaram RED (não 2)** quando o
  passo 3 entrou sem o passo 4 — a premissa 13 do plano antecipava 2
  (`test_start_processo_sobrevive_grava_pid`,
  `test_start_mt5_inclui_shares_per_lot_no_argv`); na prática
  `test_start_processo_morre_na_hora_levanta_runtimeerror_sem_gravar_estado`
  também quebrou, pela mesma causa raiz (`create_account()` chama
  `cli.build()` com `feed="parquet"` ANTES do `Popen`, então qualquer
  `start()` — inclusive o cenário "processo morre na hora" — já levanta
  `ValueError` de `build()` antes de chegar no `RuntimeError` esperado).
  Nenhuma edição extra necessária: o mesmo fix de 1 linha (passo 4) corrigiu
  os 3. Nenhum arquivo de teste editado (conforme o plano determinava).
- **`data/raw/*.parquet` ausente no worktree** (gitignorado, não
  compartilhado entre worktrees) causava 12 falhas em
  `tests/test_dashboard_app.py` por `FileNotFoundError` — confirmado como
  gap de ambiente pré-existente (reproduzido também rodando a suíte
  ANTES desta feature, no mesmo worktree) e resolvido copiando os
  parquets do repo principal (`../meta/data/raw/`) para o worktree antes
  de rodar a prova de conclusão final. Nenhum código de produção nem teste
  foi alterado por causa disso.
- Nenhum outro desvio: nenhum arquivo fora do previsto foi tocado; nenhuma
  divergência de arquitetura/contrato encontrada durante a execução.

### Prova de conclusão (resultado final)

```
../meta/.venv/Scripts/python.exe -m pytest -q
346 passed, 1 warning in 29.55s
```
