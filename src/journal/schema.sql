-- Schema do diário automatizado.
-- Cada backtest é uma "run"; cada trade pertence a uma run.
--
-- `run_kind` distingue a origem da run para o ranking automático não se
-- contaminar com simulações avulsas:
--   'ad_hoc'       - simulação manual disparada pelo usuário no dashboard
--                    ou por script exploratório (default).
--   'champion_full'- run oficial do ranking automático, janela FULL
--                    (2010-01-01 -> última data comum).
--   'champion_5y'  - run oficial do ranking automático, janela 5 anos
--                    (últimos 5 anos -> última data comum).
--   'champion_1y'  - run oficial do ranking automático, último ano-calendário
--                    COMPLETO (ex.: 2025-01-01 -> 2025-12-31 enquanto 2026
--                    não fechar) -- não é uma janela móvel de 365 dias.
-- Ver scheduler.refresh_champion_rankings().

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name      TEXT    NOT NULL,
    strategy_version   TEXT    NOT NULL,
    period_start       TEXT    NOT NULL,
    period_end         TEXT    NOT NULL,
    initial_capital    REAL    NOT NULL,
    final_capital      REAL,
    cagr               REAL,
    sharpe             REAL,
    sortino            REAL,
    max_drawdown       REAL,
    calmar             REAL,
    win_rate           REAL,
    profit_factor      REAL,
    trades_count       INTEGER,
    benchmark_cagr     REAL,
    neg_years          INTEGER,
    run_kind           TEXT    NOT NULL DEFAULT 'ad_hoc',
    -- Impressão digital do dado de entrada (ver market_data.loader.universe_fingerprint).
    -- Detecta run stale quando o provedor revisa closes ajustados sem mover a
    -- última data — comparar só `period_end` deixa métrica velha no pódio.
    data_fingerprint   TEXT,
    created_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_runs_kind ON runs(run_kind);

CREATE TABLE IF NOT EXISTS trades (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                   INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    ticker                   TEXT    NOT NULL,
    strategy_name            TEXT    NOT NULL,
    strategy_version         TEXT    NOT NULL,
    entry_date               TEXT    NOT NULL,
    entry_price              REAL    NOT NULL,
    quantity                 INTEGER NOT NULL,
    capital_allocated        REAL    NOT NULL,
    exit_date                TEXT,
    exit_price               REAL,
    exit_reason              TEXT    NOT NULL DEFAULT 'open',
    holding_days             INTEGER,
    fees_total               REAL    NOT NULL DEFAULT 0,
    slippage_total           REAL    NOT NULL DEFAULT 0,
    pnl_brl                  REAL,
    pnl_pct                  REAL,
    r_multiple               REAL,
    max_favorable_excursion  REAL    NOT NULL DEFAULT 0,
    max_adverse_excursion    REAL    NOT NULL DEFAULT 0,
    status                   TEXT    NOT NULL DEFAULT 'open'
);

CREATE INDEX IF NOT EXISTS idx_trades_run     ON trades(run_id);
CREATE INDEX IF NOT EXISTS idx_trades_ticker  ON trades(ticker);
CREATE INDEX IF NOT EXISTS idx_trades_status  ON trades(status);

CREATE TABLE IF NOT EXISTS signal_snapshots (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id                    INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    moment                      TEXT    NOT NULL CHECK (moment IN ('entry','exit')),
    close                       REAL,
    volume                      REAL,
    volume_vs_avg20             REAL,
    mm20                        REAL,
    mm50                        REAL,
    mm200                       REAL,
    mm50_over_mm200_pct         REAL,
    days_since_cross            INTEGER,
    ifr14                       REAL,
    atr14                       REAL,
    historical_vol_30d          REAL,
    distance_from_52w_high_pct  REAL,
    distance_from_52w_low_pct   REAL,
    ibov_close                  REAL,
    ibov_mm200                  REAL,
    ibov_above_mm200            INTEGER,
    ibov_trend_strength         REAL,
    correlation_with_ibov_60d   REAL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_trade ON signal_snapshots(trade_id);

CREATE TABLE IF NOT EXISTS market_regime_daily (
    date                    TEXT    PRIMARY KEY,
    ibov_close              REAL,
    ibov_mm50               REAL,
    ibov_mm200              REAL,
    regime                  TEXT,
    vix_proxy               REAL,
    active_positions_count  INTEGER
);

CREATE TABLE IF NOT EXISTS notes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id      INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    tag_type      TEXT    NOT NULL,
    tag_value     TEXT    NOT NULL,
    generated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_notes_trade ON notes(trade_id);
CREATE INDEX IF NOT EXISTS idx_notes_type  ON notes(tag_type);

CREATE TABLE IF NOT EXISTS equity_curve (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id   INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    date     TEXT    NOT NULL,
    equity   REAL    NOT NULL,
    benchmark REAL
);

CREATE INDEX IF NOT EXISTS idx_equity_run ON equity_curve(run_id);

-- ============================================================================
-- Diário da OPERAÇÃO REAL (live_*)
-- ============================================================================
-- As tabelas acima descrevem backtest (simulação). As tabelas `live_*` abaixo
-- descrevem dinheiro de verdade: a conta que opera, as posições que a
-- corretora confirmou, as decisões do robô e as ordens que tentam cumpri-las.
--
-- FEAT-000: estas tabelas continuam definidas AQUI (fonte única de verdade
-- do DDL, extraída por `journal.live_store._live_ddl`), mas fisicamente
-- passam a viver em um arquivo `.sqlite` SEPARADO do backtest —
-- `db/live.sqlite` (`core.config.LIVE_DB_PATH`), não mais `db/journal.sqlite`
-- (`core.config.DB_PATH`). Nenhuma mudança de DDL veio com essa separação;
-- só o arquivo físico onde `journal.live_store.ensure_tables` as cria mudou.
--
-- `live_intents` e `live_orders` são tabelas SEPARADAS de propósito.
-- Intent é o registro do CÉREBRO ("o robô decidiu X, para valer no pregão Y");
-- Order é o registro do BRAÇO ("mandei isso para a corretora, e ela respondeu
-- assim"). Uma Intent pode gerar zero, uma ou várias Orders (retry, rejeição,
-- fatiamento). Se as duas fossem uma tabela só, a pergunta que mais importa
-- quando um trade dá errado — "o robô decidiu errado ou a execução falhou?" —
-- não teria como ser respondida sem reconstruir o histórico na mão. Separadas,
-- é uma junção. Ver docstring de `core/live_models.py` para o raciocínio
-- completo (é o mesmo raciocínio, aqui virando DDL).
--
-- `live_equity` guarda `patrimonio` (carteira + caixa externo) além de
-- `equity` (só carteira) porque, quando existe política de saque, a carteira
-- cai no dia do saque sem ninguém ter perdido nada — o dinheiro só mudou de
-- lugar (foi para fora do risco). Medir drawdown pela carteira sozinha
-- confundiria "saque programado" com "perda real". `patrimonio` é a medida
-- honesta de risco; `equity` fica guardada também porque é o que o robô de
-- investimento realmente enxerga (ver `AccountState.equity` vs
-- `AccountState.patrimonio` em `core/live_models.py`).

CREATE TABLE IF NOT EXISTS live_accounts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT    NOT NULL UNIQUE,
    -- Vocabulário canônico: ver `core.live_models.BrokerMode` (FEAT-001).
    mode               TEXT    NOT NULL CHECK (mode IN ('mt5')),
    initial_capital    REAL    NOT NULL,
    cash               REAL    NOT NULL,
    -- Saldo paralelo, só atualizado em execution_mode="shadow" -- nunca
    -- confundido com `cash` (dinheiro real). Ver `AccountState.cash_sombra`.
    cash_sombra        REAL    NOT NULL DEFAULT 0,
    investment_robot   TEXT    NOT NULL DEFAULT '',
    withdrawal_robot   TEXT    NOT NULL DEFAULT '',
    -- Ativo que ESTA conta negocia. Vazio no swing (o robô diário escolhe
    -- dentro do universo dele); obrigatório no day trade, onde a conta É o par
    -- robô+ativo — desde 2026-08-22 o painel abre quantas contas de day trade
    -- o dono quiser, uma por ativo. Ver `AccountState.symbol`.
    symbol             TEXT    NOT NULL DEFAULT '',
    withdrawn_total    REAL    NOT NULL DEFAULT 0,
    external_cash      REAL    NOT NULL DEFAULT 0,
    -- Estado com memória da política de saque (fila do mínimo, mês já pago,
    -- topo histórico) — precisa sobreviver a um restart do processo. Ver
    -- docstring de `AccountState.policy_state` em `core/live_models.py`.
    policy_state       TEXT    NOT NULL DEFAULT '{}',
    -- Posição manual no painel, entre as contas de day trade (menor = mais
    -- acima). Default 0 para todas: com todas empatadas, o desempate por
    -- `id` reproduz a ordem de criação de sempre — só passa a valer depois
    -- que o dono arrasta um cartão, o que reescreve esta coluna para
    -- TODAS as contas de day trade de uma vez (ver
    -- `live_store.set_daytrade_account_order`).
    sort_order         INTEGER NOT NULL DEFAULT 0,
    -- Quando o dono removeu o robô GUARDANDO o histórico (2026-08-26). A
    -- conta continua inteira -- diário, ordens, trades, caixa -- e só some do
    -- painel: `accounts_with_symbol` filtra por `archived_at IS NULL`. Criar
    -- de novo o mesmo trio (robô, ativo, modo) oferece restaurar isto; criar
    -- "do zero" apaga. NULL = conta viva, e é o estado de toda conta que
    -- existia antes desta coluna.
    archived_at        TEXT,
    created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Posição REAL: existe porque a corretora confirmou um fill, não porque o
-- robô quis (ver docstring de `LivePosition`). UNIQUE(account_id, ticker,
-- kind) porque um ticker pode ter, ao mesmo tempo, uma posição 'main' e uma
-- 'satellite' — são posições com origem e regra de saída diferentes.
CREATE TABLE IF NOT EXISTS live_positions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id         INTEGER NOT NULL REFERENCES live_accounts(id) ON DELETE CASCADE,
    ticker             TEXT    NOT NULL,
    quantity           INTEGER NOT NULL,
    entry_date         TEXT    NOT NULL,
    entry_price        REAL    NOT NULL,
    capital_allocated  REAL    NOT NULL,
    current_stop       REAL,
    fees_paid          REAL    NOT NULL DEFAULT 0,
    slippage_paid      REAL    NOT NULL DEFAULT 0,
    max_price_seen     REAL    NOT NULL DEFAULT 0,
    min_price_seen     REAL    NOT NULL DEFAULT 0,
    bars_held          INTEGER NOT NULL DEFAULT 0,
    kind               TEXT    NOT NULL DEFAULT 'main' CHECK (kind IN ('main','satellite')),
    metadata           TEXT    NOT NULL DEFAULT '{}',
    UNIQUE (account_id, ticker, kind)
);

CREATE INDEX IF NOT EXISTS idx_live_positions_account ON live_positions(account_id);

-- Intent = decisão do robô no fecho de D, para executar em D+1 (regra 4 do
-- AGENTS.md). Imutável depois de gravada — o que muda é só `status`.
CREATE TABLE IF NOT EXISTS live_intents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   INTEGER NOT NULL REFERENCES live_accounts(id) ON DELETE CASCADE,
    robot        TEXT    NOT NULL,
    role         TEXT    NOT NULL CHECK (role IN ('investment','withdrawal')),
    kind         TEXT    NOT NULL CHECK (kind IN ('enter','exit','adjust_stop','withdraw')),
    decided_on   TEXT    NOT NULL,
    execute_on   TEXT    NOT NULL,
    ticker       TEXT,
    reason       TEXT    NOT NULL DEFAULT '',
    size_hint    REAL,
    stop_price   REAL,
    amount       REAL,
    status       TEXT    NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','executing','done','expired','cancelled','rejected')),
    payload      TEXT    NOT NULL DEFAULT '{}',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Índice pensado para a pergunta que o runtime faz todo dia: "quais intents
-- pendentes valem para a sessão de hoje desta conta?".
CREATE INDEX IF NOT EXISTS idx_live_intents_exec ON live_intents(account_id, execute_on, status);

-- Order = execução na corretora que tenta cumprir uma Intent. `intent_id`
-- pode ser NULL (ordem manual, fora do ciclo de decisão do robô) e usa
-- ON DELETE SET NULL para nunca apagar o histórico de execução junto com a
-- intenção que a gerou.
CREATE TABLE IF NOT EXISTS live_orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL REFERENCES live_accounts(id) ON DELETE CASCADE,
    intent_id     INTEGER REFERENCES live_intents(id) ON DELETE SET NULL,
    ticker        TEXT    NOT NULL,
    side          TEXT    NOT NULL CHECK (side IN ('buy','sell')),
    quantity      INTEGER NOT NULL,
    order_type    TEXT    NOT NULL DEFAULT 'market' CHECK (order_type IN ('market','limit','on_open')),
    limit_price   REAL,
    status        TEXT    NOT NULL DEFAULT 'new'
                  CHECK (status IN ('new','sent','partial','filled','cancelled','rejected')),
    filled_qty    INTEGER NOT NULL DEFAULT 0,
    avg_price     REAL,
    fees          REAL    NOT NULL DEFAULT 0,
    slippage      REAL    NOT NULL DEFAULT 0,
    broker_ref    TEXT,
    sent_at       TEXT,
    note          TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_live_orders_status  ON live_orders(status);
CREATE INDEX IF NOT EXISTS idx_live_orders_account ON live_orders(account_id);

-- Fill = execução (parcial ou total) reportada pela corretora para uma Order.
-- Uma Order pode ter N Fills (execução fatiada pelo book).
CREATE TABLE IF NOT EXISTS live_fills (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL REFERENCES live_orders(id) ON DELETE CASCADE,
    quantity   INTEGER NOT NULL,
    price      REAL    NOT NULL,
    fees       REAL    NOT NULL DEFAULT 0,
    ts         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_live_fills_order ON live_fills(order_id);

-- Marcação diária da conta. Ver comentário no topo desta seção sobre por que
-- `patrimonio` (equity + external_cash) existe ao lado de `equity`.
CREATE TABLE IF NOT EXISTS live_equity (
    account_id     INTEGER NOT NULL REFERENCES live_accounts(id) ON DELETE CASCADE,
    date           TEXT    NOT NULL,
    cash           REAL    NOT NULL,
    invested       REAL    NOT NULL,
    equity         REAL    NOT NULL,
    external_cash  REAL    NOT NULL DEFAULT 0,
    patrimonio     REAL    NOT NULL,
    PRIMARY KEY (account_id, date)
);

-- Saque executado (ou tentado) pela política de retirada. `liquidated`
-- guarda, em JSON, o que precisou ser vendido para gerar o caixa do saque
-- (ticker -> quantidade), quando o caixa em conta não bastava.
CREATE TABLE IF NOT EXISTS live_withdrawals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id     INTEGER NOT NULL REFERENCES live_accounts(id) ON DELETE CASCADE,
    date           TEXT    NOT NULL,
    requested      REAL    NOT NULL,
    executed       REAL    NOT NULL,
    equity_before  REAL    NOT NULL,
    fees_paid      REAL    NOT NULL DEFAULT 0,
    liquidated     TEXT    NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_live_withdrawals_account ON live_withdrawals(account_id);

-- Depósito detectado (ou registrado à mão): dinheiro que entrou na conta
-- vindo de FORA do sistema — o dono colocou dinheiro na corretora. `origin`
-- distingue as duas origens legítimas: `'mt5_reconciliation'` (checagem
-- automática do saldo real do terminal antes do pregão abrir, ver
-- `live.runtime.reconcile_broker_cash`) e `'manual'` (botão "Registrar
-- aporte" do dashboard — força o crédito sem esperar a próxima checagem
-- automática). `note` guarda o saldo real vs. caixa esperado no caso
-- automático, para o crédito ser auditável depois.
CREATE TABLE IF NOT EXISTS live_deposits (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id     INTEGER NOT NULL REFERENCES live_accounts(id) ON DELETE CASCADE,
    date           TEXT    NOT NULL,
    amount         REAL    NOT NULL,
    origin         TEXT    NOT NULL,
    note           TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_live_deposits_account ON live_deposits(account_id);

-- Log operacional (não é métrica, é auditoria em texto): avisos do runtime,
-- dado atrasado recusado, ordem rejeitada, etc. `account_id` pode ser NULL
-- para eventos que não pertencem a nenhuma conta (ex.: falha ao abrir o feed).
-- Contexto de mercado no momento em que o robô DECIDIU, ao vivo. Espelha
-- coluna por coluna a `signal_snapshots` do backtest, de propósito: a
-- pergunta que justifica a tabela é "o que o robô viu no dia da compra real,
-- e como isso se compara com o que ele via nas compras simuladas?". Mesmas
-- colunas, mesmas unidades, mesmo código de cálculo (`core/market_features.py`)
-- => a comparação é um único SQL depois de um ATTACH dos dois arquivos.
--
-- Por que uma tabela NOVA em vez de reusar `signal_snapshots`: os dois bancos
-- são arquivos SQLite separados (`DB_PATH` × `LIVE_DB_PATH`) e foram separados
-- justamente para que backtest e operação real não disputassem lock do mesmo
-- arquivo. Gravar o snapshot ao vivo dentro do banco de backtest reintroduziria
-- essa disputa — o loop ao vivo passaria a escrever no arquivo que um sweep de
-- 100 robôs pode estar segurando. Tabela espelhada no banco da operação
-- preserva a comparabilidade sem reabrir o problema.
--
-- Ancorada em `live_intents` (a DECISÃO), não na ordem: o snapshot descreve o
-- que o robô viu ao decidir, e essa leitura existe mesmo que a ordem seja
-- rejeitada pela corretora depois. Ancorar na ordem perderia exatamente os
-- casos mais informativos — as decisões que não viraram trade.
CREATE TABLE IF NOT EXISTS live_signal_snapshots (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    intent_id                   INTEGER NOT NULL REFERENCES live_intents(id) ON DELETE CASCADE,
    moment                      TEXT    NOT NULL CHECK (moment IN ('entry','exit')),
    ticker                      TEXT    NOT NULL,
    close                       REAL,
    volume                      REAL,
    volume_vs_avg20             REAL,
    mm20                        REAL,
    mm50                        REAL,
    mm200                       REAL,
    mm50_over_mm200_pct         REAL,
    days_since_cross            INTEGER,
    ifr14                       REAL,
    atr14                       REAL,
    historical_vol_30d          REAL,
    distance_from_52w_high_pct  REAL,
    distance_from_52w_low_pct   REAL,
    ibov_close                  REAL,
    ibov_mm200                  REAL,
    ibov_above_mm200            INTEGER,
    ibov_trend_strength         REAL,
    correlation_with_ibov_60d   REAL,
    UNIQUE (intent_id, moment)
);

CREATE INDEX IF NOT EXISTS idx_live_snapshots_intent ON live_signal_snapshots(intent_id);

CREATE TABLE IF NOT EXISTS live_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   INTEGER REFERENCES live_accounts(id) ON DELETE CASCADE,
    ts           TEXT    NOT NULL DEFAULT (datetime('now')),
    level        TEXT    NOT NULL CHECK (level IN ('info','warn','error')),
    source       TEXT    NOT NULL,
    message      TEXT    NOT NULL,
    payload      TEXT    NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_live_events_ts ON live_events(ts);
-- Cobre exatamente `WHERE account_id = ? [AND date(ts) = ?] ORDER BY ts DESC,
-- id DESC` (ver `live_store.recent_events`): sem isto, o filtro por conta
-- caía num scan da tabela inteira ordenado por `idx_live_events_ts` (todas as
-- contas juntas) -- ficava mais lento a cada evento novo de QUALQUER conta,
-- não só desta. Com o histórico completo ("Diário Completo" do painel,
-- 2026-08-25) fazendo scroll infinito por `id` (cursor de página), este
-- índice já entrega as linhas na ordem certa sem sort extra.
CREATE INDEX IF NOT EXISTS idx_live_events_account_ts ON live_events(account_id, ts DESC, id DESC);

-- Aviso de CAPITAL DISPONÍVEL: um robô de day trade em operação diz que já
-- juntou caixa suficiente para o dono abrir um robô novo num ativo que ainda
-- não roda. É um AVISO, nunca uma ação — quem abre o robô é o dono, no painel.
--
-- Tabela separada de `live_events` por duas coisas que evento de log não tem:
--
--   1. DEDUPLICAÇÃO. `UNIQUE(account_id, suggested_symbol)` é o que faz o robô
--      avisar UMA vez por ativo, e não a cada barra/pregão em que a condição
--      continua verdadeira (seriam centenas de mensagens iguais por dia). O
--      robô grava com `INSERT ... ON CONFLICT DO NOTHING` e não precisa saber
--      se já avisou — o banco decide.
--   2. ESTADO DE LEITURA. `acknowledged_at` é o "marcar como feito" do painel.
--      Um evento de log é imutável por natureza; este aviso tem ciclo de vida.
--
-- `suggested_symbol` NÃO tem FK para conta nenhuma de propósito: o ativo
-- sugerido é, por definição, um que ainda não tem conta.
CREATE TABLE IF NOT EXISTS live_capital_signals (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id         INTEGER NOT NULL REFERENCES live_accounts(id) ON DELETE CASCADE,
    ts                 TEXT    NOT NULL DEFAULT (datetime('now')),
    robot              TEXT    NOT NULL,
    suggested_symbol   TEXT    NOT NULL,
    -- Quanto a conta que avisou tinha em caixa, e quanto o ativo sugerido
    -- exige, NO MOMENTO do aviso. Guardados porque o preço muda todo dia: sem
    -- eles, um aviso de duas semanas atrás não teria como ser conferido.
    cash_brl           REAL    NOT NULL,
    required_brl       REAL    NOT NULL,
    acknowledged_at    TEXT,
    UNIQUE (account_id, suggested_symbol)
);

CREATE INDEX IF NOT EXISTS idx_live_capital_signals_ack
    ON live_capital_signals(acknowledged_at);
