"""Diário da OPERAÇÃO REAL — leitura e escrita das tabelas `live_*`.

Por que este módulo é um único arquivo (e não `live_reader.py` + `live_writer.py`
como o par `reader.py`/`writer.py` do backtest)
-----------------------------------------------------------------------------
O diário de backtest é, na prática, append-only: uma run é criada, trades e
equity são inseridos, a run é fechada. Ler e escrever são operações
independentes que quase nunca disputam a mesma linha, então separar em dois
arquivos custa pouco.

O diário AO VIVO é o oposto: é uma MÁQUINA DE ESTADO. Quase toda operação
aqui é ler uma linha, decidir algo em cima do valor lido, e escrever de
volta — `save_account` depende de `load_account`, `upsert_position` faz
INSERT-ou-UPDATE na mesma UNIQUE, `set_intent_status` só faz sentido depois
de `pending_intents`/`stale_intents` terem decidido o que mudar. Se leitura e
escrita morassem em arquivos diferentes, a fronteira da transação (o que
precisa acontecer atomicamente dentro de um único `with live_journal(...)`)
ficaria espalhada por dois módulos, e quem chama teria de coordenar isso na
mão. Manter os dois juntos aqui é o que permite que cada função pública seja,
sozinha, uma transação completa e coerente.

Fronteira de import (regra 1 do AGENTS.md): este módulo importa só de
`core/` (os contratos em `core.live_models`). Não importa `live/`,
`backtest/`, `strategy/` nem `market_data/` — journal é feature, e feature só
enxerga `core/`.

Por que este módulo NÃO reusa `journal.writer._connect`/`journal`
-----------------------------------------------------------------------------
`writer._connect` roda `_migrate`, que só sabe sobre as colunas de `runs`
(schema de backtest). Reusá-lo criaria acoplamento entre o schema de
backtest e o de operação ao vivo por nenhum motivo — são dois domínios que,
desde a separação física do banco (FEAT-000), nem sequer compartilham o
mesmo arquivo `.sqlite` (backtest fica em `core.config.DB_PATH`, operação
real em `core.config.LIVE_DB_PATH`). Este módulo define seu próprio
`_connect`/`live_journal` no mesmo estilo (mesmo contextmanager, mesmo
commit/rollback), mas chamando `ensure_tables(conn)` em vez de `_migrate`.

Por que `ensure_tables(conn)` roda a cada conexão
-----------------------------------------------------------------------------
`journal.writer.init_db()` só é chamado uma vez, no setup do projeto — e o
schema dele hoje não inclui as tabelas `live_*` (foram adicionadas depois).
Um banco `db/journal.sqlite` já existente, criado antes desta feature, não
tem `live_accounts`/`live_positions`/etc. Se este store dependesse de alguém
rodar `init_db()` de novo, o primeiro uso em produção quebraria com "no such
table". Por isso `_connect` chama `ensure_tables(conn)` sempre: os `CREATE
TABLE IF NOT EXISTS` são baratos e idempotentes, e o store fica
AUTO-SUFICIENTE — funciona em banco novo ou em banco antigo, sem passo manual.

Para não duplicar DDL (schema.sql já tem as definições das tabelas `live_*`,
apendadas por esta mesma feature), `ensure_tables` LÊ `schema.sql` e executa
só os statements que mencionam `live_` — uma única fonte de verdade para o
formato das tabelas.
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from core.b3_session import SAO_PAULO
from core.config import LIVE_DB_PATH, SCHEMA_PATH
from core.live_models import (
    AccountState,
    Fill,
    Intent,
    IntentKind,
    IntentStatus,
    LivePosition,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    RobotRole,
)
from core.models import MarketSnapshot

# Status de Order que não vão mudar mais — não fazem sentido em "open_orders".
_TERMINAL_ORDER_STATUSES = (
    OrderStatus.FILLED.value,
    OrderStatus.CANCELLED.value,
    OrderStatus.REJECTED.value,
)


# ---------------------------------------------------------------------------
# conexão e schema
# ---------------------------------------------------------------------------

def _live_ddl(schema_path: Path) -> str:
    """Extrai de `schema.sql` só os statements DDL das tabelas `live_*`.

    `schema.sql` não tem strings com ';' dentro (é DDL puro, sem dados), então
    dividir por ';' é seguro. Filtramos por "CREATE ... LIVE_" no texto em
    maiúsculas para pegar tanto `CREATE TABLE live_x` quanto
    `CREATE INDEX idx_live_x ON live_x(...)`, sem tocar nas tabelas de
    backtest (`runs`, `trades`, etc.) que moram no mesmo arquivo.
    """
    text = schema_path.read_text(encoding="utf-8")
    # Remove as linhas de comentário ("-- ...") ANTES de dividir por ';'.
    # Motivo: os comentários explicativos em português às vezes têm ';' na
    # prosa (ex.: "risco; `equity` fica guardada..."). Se dividíssemos o
    # texto bruto por ';' primeiro, esse ';' de prosa cortaria o comentário
    # ao meio e a metade final ficaria numa linha sem o prefixo "--" —
    # parecendo início de statement e escapando do filtro de CREATE TABLE.
    # Removendo comentário inteiro por linha primeiro, nenhum ';' de prosa
    # sobra para confundir o split.
    code_only = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
    statements: list[str] = []
    for raw in code_only.split(";"):
        stmt = raw.strip()
        if not stmt:
            continue
        upper = stmt.upper()
        if upper.startswith("CREATE") and "LIVE_" in upper:
            statements.append(stmt)
    if not statements:
        return ""
    return ";\n".join(statements) + ";"


class LegacyPaperAccountError(RuntimeError):
    """`live_accounts` ainda usa um CHECK antigo (vocabulário `paper`/`manual`/
    `broker`, ou o canônico intermediário `manual`/`mt5`) e contém ao menos
    uma conta de SIMULAÇÃO (`mode='paper'`).

    Não é seguro converter isso em silêncio para o vocabulário canônico
    (`mt5`, ver `core.live_models.BrokerMode`) — uma conta de simulação virar
    conta real por engano é o tipo de bug que só aparece quando já é tarde.
    Renomear a conta NÃO desbloqueia nada (o CHECK novo rejeita pelo VALOR da
    coluna `mode`, não pelo nome) — a única saída real é apagar a(s)
    linha(s), ou um `UPDATE` manual de `mode` feito com decisão humana
    consciente. Ver a mensagem da exceção para o texto completo.
    """


class LegacyManualAccountError(RuntimeError):
    """`live_accounts` contém ao menos uma conta em `mode='manual'` — modo
    descontinuado: o usuário decidiu que o robô sempre decide E executa
    sozinho, sem confirmação humana em nenhum momento, então só resta `mt5`.

    Não é seguro converter isso em silêncio para `'mt5'`: uma conta manual
    nunca teve `mt5_shares_per_lot`/credenciais MT5 configuradas, então virar
    `'mt5'` de graça seria inventar configuração que não existe. A única
    saída real é decisão humana consciente: recriar a conta em modo mt5 (com
    os parâmetros mt5 corretos), ou apagar a linha. Ver a mensagem da
    exceção para o texto completo.
    """


def _legacy_check_present(conn: sqlite3.Connection) -> bool:
    """`True` se `live_accounts` já existe no banco E seu DDL (lido de
    `sqlite_master`, posicionalmente — sem depender de `row_factory`) ainda
    permite um `mode` diferente de `'mt5'` sozinho. Dois marcadores cobrem as
    duas fraturas de vocabulário que já existiram: `'broker'` (vocabulário
    pré-FEAT-001: `paper`/`manual`/`broker`) e `'manual'` (vocabulário
    canônico de FEAT-001, antes do modo manual ser descontinuado). O
    vocabulário canônico atual (`mt5` sozinho) não contém nenhum dos dois.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'live_accounts'"
    ).fetchone()
    if row is None:
        return False
    ddl = row[0] or ""
    return "'broker'" in ddl or "'manual'" in ddl


def _live_accounts_rebuild_ddl(schema_path: Path) -> str:
    """DDL de `CREATE TABLE live_accounts_new (...)`, extraído de
    `schema.sql` (fonte única de verdade do formato final da tabela) e
    renomeado — nunca duplicado à mão aqui, senão o rebuild divergiria do
    schema no primeiro `ALTER TABLE` que alguém fizer em `schema.sql`."""
    text = schema_path.read_text(encoding="utf-8")
    code_only = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
    for raw in code_only.split(";"):
        stmt = raw.strip()
        if not stmt:
            continue
        head = stmt.upper().split("(", 1)[0].rstrip()
        if head.startswith("CREATE TABLE") and head.endswith("LIVE_ACCOUNTS"):
            return re.sub(
                r"(?i)(CREATE TABLE(?:\s+IF NOT EXISTS)?\s+)live_accounts\b",
                r"\1live_accounts_new", stmt, count=1,
            ) + ";"
    raise RuntimeError("definição de live_accounts não encontrada em schema.sql")


def _migrate_account_mode_vocabulary(conn: sqlite3.Connection, schema_path: Path = SCHEMA_PATH) -> None:
    """Rebuild de `live_accounts` de um vocabulário antigo (`paper`/`manual`/
    `broker`, ou o canônico intermediário `manual`/`mt5`) para o canônico
    atual (`mt5` sozinho) — chamado no início de `ensure_tables`, antes de
    qualquer outra tabela ser tocada.

    Recusa (levanta `LegacyPaperAccountError`, não mexe em nada) se houver
    alguma conta `mode='paper'` — nunca converte simulação em conta real em
    silêncio. Pelo mesmo motivo, recusa (`LegacyManualAccountError`) se
    houver alguma conta `mode='manual'` — modo descontinuado, e uma conta
    manual nunca teve `mt5_shares_per_lot`/credenciais mt5 configuradas para
    virar mt5 de graça. Caso contrário, reconstrói a tabela na ordem
    OBRIGATÓRIA criar-nova -> copiar -> dropar-antiga -> renomear (nunca o
    inverso: a partir do SQLite 3.25 `ALTER TABLE ... RENAME` reescreve as
    cláusulas `REFERENCES` das tabelas FILHAS — renomear `live_accounts` para
    `live_accounts_old` primeiro deixaria `live_positions`/`live_orders`/
    `live_intents` apontando para o nome velho, corrompendo o banco em
    silêncio). `PRAGMA foreign_keys` é desligado/religado aqui (fora de
    qualquer transação — o pragma é um no-op dentro de uma), porque
    `_connect` já o liga ANTES de chamar `ensure_tables`.
    """
    if not _legacy_check_present(conn):
        return

    legacy_paper = conn.execute(
        "SELECT name FROM live_accounts WHERE mode = 'paper'"
    ).fetchall()
    if legacy_paper:
        nomes = ", ".join(str(row[0]) for row in legacy_paper)
        raise LegacyPaperAccountError(
            "live_accounts tem conta(s) de SIMULAÇÃO (mode='paper') que o "
            f"vocabulário canônico (mt5) não cobre: {nomes}. Renomear "
            "a conta NÃO resolve — o CHECK novo rejeita pelo VALOR da coluna "
            "mode, não pelo nome da conta. As únicas saídas reais são: "
            "apagar a(s) linha(s) (perde o histórico dela), ou, com decisão "
            "humana consciente de que é seguro tratar essa conta como real, "
            "um UPDATE manual de mode para 'mt5' depois de confirmar isso. "
            "Se esta conexão é para o banco de SIMULAÇÃO (db/live_sim.sqlite), "
            "a saída mais simples é apagar esse arquivo inteiro — não mexa "
            "na conta real por engano."
        )

    legacy_manual = conn.execute(
        "SELECT name FROM live_accounts WHERE mode = 'manual'"
    ).fetchall()
    if legacy_manual:
        nomes = ", ".join(str(row[0]) for row in legacy_manual)
        raise LegacyManualAccountError(
            f"live_accounts tem conta(s) em modo 'manual', que foi "
            f"descontinuado: {nomes}. Modo manual não existe mais neste "
            "sistema — o robô sempre decide E executa sozinho via MT5, sem "
            "confirmação humana em nenhum momento. Não dá para converter "
            "essa conta para 'mt5' automaticamente (ela nunca teve "
            "mt5_shares_per_lot/credenciais mt5 configuradas) — é preciso "
            "decidir manualmente: recriar a conta em modo mt5 com os "
            "parâmetros corretos, ou apagar a linha."
        )

    conn.execute("PRAGMA foreign_keys = OFF")
    # Uma execução anterior interrompida no meio do rebuild pode ter deixado
    # `live_accounts_new` para trás (criada, mas nunca dropada/renomeada) —
    # sem este DROP, a tentativa seguinte quebraria com "table already
    # exists" em vez de recomeçar do zero.
    conn.execute("DROP TABLE IF EXISTS live_accounts_new")
    conn.executescript(_live_accounts_rebuild_ddl(schema_path))
    conn.execute(
        """INSERT INTO live_accounts_new
            (id, name, mode, initial_capital, cash, investment_robot, withdrawal_robot,
             withdrawn_total, external_cash, policy_state, created_at, updated_at)
           SELECT id, name, CASE WHEN mode = 'broker' THEN 'mt5' ELSE mode END,
                  initial_capital, cash, investment_robot, withdrawal_robot,
                  withdrawn_total, external_cash, policy_state, created_at, updated_at
           FROM live_accounts"""
    )
    conn.execute("DROP TABLE live_accounts")
    conn.execute("ALTER TABLE live_accounts_new RENAME TO live_accounts")

    # `PRAGMA foreign_key_check` ANTES do commit, ainda dentro da mesma
    # transação aberta pelo INSERT acima: uma violação tem de ABORTAR o
    # rebuild (rollback) em vez de só ser reportada depois de o schema novo
    # já estar gravado — checar depois do commit não desfaz nada, só avisa
    # tarde demais.
    fk_problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk_problems:
        conn.rollback()
        raise RuntimeError(
            f"rebuild de live_accounts deixou referência(s) inválida(s): {fk_problems}"
        )

    # Commit ANTES de religar o pragma: `PRAGMA foreign_keys` é um no-op
    # dentro de uma transação aberta (a que o INSERT acima começou) — sem
    # commitar primeiro, `foreign_keys=ON` abaixo não teria efeito nenhum
    # pelo resto da vida desta conexão.
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")


def ensure_tables(conn: sqlite3.Connection, schema_path: Path = SCHEMA_PATH) -> None:
    """Cria as tabelas `live_*` se ainda não existirem. Idempotente e barato.

    Chamado a cada `_connect` — ver docstring do módulo para o porquê.
    Primeiro passo: migrar o vocabulário de modo se `live_accounts` ainda
    estiver no formato antigo (ver `_migrate_account_mode_vocabulary`).
    """
    _migrate_account_mode_vocabulary(conn, schema_path)
    ddl = _live_ddl(schema_path)
    if ddl:
        conn.executescript(ddl)
        conn.commit()
    _add_missing_account_columns(conn)


#: Colunas adicionadas a `live_accounts` DEPOIS de o banco existir em produção.
#: `CREATE TABLE IF NOT EXISTS` (o caminho normal de `ensure_tables`) não toca
#: numa tabela que já existe, então uma coluna nova precisa de `ALTER TABLE`
#: explícito — e um rebuild completo (o caminho de
#: `_migrate_account_mode_vocabulary`) seria desproporcional para acrescentar
#: coluna com default.
_ACCOUNT_COLUMNS_ADICIONADAS = (
    ("symbol", "TEXT NOT NULL DEFAULT ''"),
    ("cash_sombra", "REAL NOT NULL DEFAULT 0"),
    ("sort_order", "INTEGER NOT NULL DEFAULT 0"),
    ("archived_at", "TEXT"),
)


def _add_missing_account_columns(conn: sqlite3.Connection) -> None:
    """Acrescenta a `live_accounts` as colunas de `_ACCOUNT_COLUMNS_ADICIONADAS`
    que ainda não existirem. Idempotente e barato (uma leitura de
    `PRAGMA table_info` por conexão), no mesmo espírito de `ensure_tables`:
    o store funciona em banco novo ou antigo, sem passo manual."""
    # Índice posicional (coluna 1 = `name`), e não `row["name"]`: esta função
    # roda dentro de `ensure_tables`, que também é chamada por
    # `scripts/migrate_live_db.py` com uma conexão CRUA — sem
    # `row_factory = sqlite3.Row`, e ali um acesso por chave seria `TypeError`.
    existentes = {row[1] for row in conn.execute("PRAGMA table_info(live_accounts)")}
    novas = [(nome, ddl) for nome, ddl in _ACCOUNT_COLUMNS_ADICIONADAS if nome not in existentes]
    if not novas:
        return
    for nome, ddl in novas:
        conn.execute(f"ALTER TABLE live_accounts ADD COLUMN {nome} {ddl}")
    if any(nome == "cash_sombra" for nome, _ in novas):
        # Semeia com `cash` (o saldo REAL de agora), não `initial_capital` --
        # para uma conta que já rodou e teve `cash` ajustado por depósito/
        # trade real, `initial_capital` pode estar bem defasado (visto na
        # prática: conta com cash=30 e initial_capital=0). Sem isto, toda
        # conta que já existia antes desta coluna nascer mostraria "saldo
        # sombra R$0" mesmo sem nunca ter rodado sombra, o que parece bug em
        # vez de "ainda não simulou nada". Seguro rodar incondicional: este
        # ramo só executa UMA vez, no instante em que a coluna acaba de ser
        # criada (`novas` só contém "cash_sombra" nessa mesma passada).
        conn.execute("UPDATE live_accounts SET cash_sombra = cash")
    conn.commit()


def _connect(db_path: Path = LIVE_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    # WAL + busy_timeout: o motivo desta feature. Sem os dois, um backtest
    # longo em `threading.Thread` e a gravação de uma ordem real disputam
    # lock do arquivo (WAL permite leitor+escritor concorrentes). O
    # `sqlite3.connect` do Python já usa `timeout=5.0` (5s) por padrão — a
    # linha abaixo NÃO é a origem da proteção atual contra "database is
    # locked"; ela é uma defesa EXPLÍCITA para o dia em que alguém, no
    # futuro, passar `timeout=0` (ou outro valor baixo) ao conectar sem notar
    # que isso reduz o busy_timeout do driver junto — fixar o PRAGMA aqui
    # garante os 5s independente do que `connect()` receber. `journal_mode=
    # WAL` devolve uma linha com o modo resultante — precisa ser lida, senão
    # o cursor fica pendente.
    conn.execute("PRAGMA journal_mode=WAL").fetchone()
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    ensure_tables(conn)
    return conn


@contextmanager
def live_journal(db_path: Path = LIVE_DB_PATH) -> Iterator[sqlite3.Connection]:
    """Contextmanager de transação, no mesmo estilo de `journal.writer.journal`.

    `conn.commit()`/`conn.rollback()` aqui cobrem o que sobrar ATÉ O FIM do
    `with` — mas nada impede quem chama de commitar ANTES, no meio do
    bloco, por conta própria. O SQLite aceita commit no meio de uma conexão
    e reabre uma transação nova implícita para o que vier depois; quem faz
    isso vira dono de uma fração do trabalho, e uma exceção depois desse
    ponto só desfaz o que veio depois dele.

    `IntradayLiveRuntime._checkpoint` (`live/intraday_runtime.py`) faz
    exatamente isso — comita a MESMA conexão logo depois de um efeito
    colateral externo confirmado (ticket recebido na corretora, fill,
    proteção SL/TP registrada), para uma exceção mais adiante no mesmo
    `run_once` (ex.: `BrokerExecutionError` de `kind=FALHA_ALTO`, deixada
    para propagar de propósito — ver a docstring dela) não apagar, via
    `rollback()`, o registro de algo que já aconteceu de verdade com
    dinheiro real (MÉDIO 7, auditoria adversarial 2026-08-28: antes desse
    checkpoint, qualquer exceção tardia em `run_once` desfazia TUDO desde o
    início do passo, inclusive uma ordem/fechamento já confirmado pela
    corretora segundos antes, na mesma chamada). Este contextmanager não
    precisa saber disso — só precisa não presumir que "uma transação só"
    é garantia estrutural, porque não é: é o comportamento quando ninguém
    commita cedo."""
    conn = _connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# serialização de campos JSON (metadata/payload/policy_state/liquidated)
# ---------------------------------------------------------------------------

def _dumps(value: Optional[dict]) -> str:
    return json.dumps(value or {})


def _loads(value: Optional[str]) -> dict:
    if not value:
        return {}
    return json.loads(value)


# ---------------------------------------------------------------------------
# conta
# ---------------------------------------------------------------------------

def ensure_account(
    conn: sqlite3.Connection,
    name: str,
    mode: str,
    initial_capital: float,
    investment_robot: str,
    withdrawal_robot: str,
    symbol: str = "",
) -> AccountState:
    """Cria a conta se não existir; se já existir, não mexe nela.

    Idempotente por causa de `ON CONFLICT(name) DO NOTHING`: chamar duas vezes
    com os MESMOS dados não duplica linha nem sobrescreve o estado atual —
    quem quer mudar cash/robôs usa `save_account`. Chamar com um `mode`
    DIFERENTE do já gravado levanta `ValueError`: o modo de uma conta nunca
    muda por baixo do broker que a criou (antes disso era ignorado em
    silêncio pelo `ON CONFLICT DO NOTHING`).
    """
    conn.execute(
        """INSERT INTO live_accounts
            (name, mode, initial_capital, cash, cash_sombra, investment_robot, withdrawal_robot, symbol)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(name) DO NOTHING""",
        (name, mode, initial_capital, initial_capital, initial_capital, investment_robot,
         withdrawal_robot, symbol),
    )
    account = load_account(conn, name)
    assert account is not None, "insert com ON CONFLICT DO NOTHING não pode deixar a conta ausente"
    if account.mode != mode:
        raise ValueError(
            f"conta '{name}' já existe com mode={account.mode!r}, mas foi "
            f"pedida com mode={mode!r} — divergência entre a conta gravada "
            "e o broker/CLI que está chamando agora."
        )
    # Mesmo rigor de `mode`, e pelo mesmo motivo — mas mais grave: o ativo é o
    # que a conta NEGOCIA. Uma conta criada para PMAM3 sendo aberta para KLBN4
    # herdaria posições, caixa e histórico do papel errado. Só bloqueia quando
    # os dois lados declaram algo: uma conta antiga (`symbol=''`, criada antes
    # da coluna existir) aceita ganhar o símbolo em `save_account`.
    if symbol and account.symbol and account.symbol != symbol:
        raise ValueError(
            f"conta '{name}' já existe negociando {account.symbol!r}, mas foi "
            f"pedida para {symbol!r} — uma conta de day trade é o par "
            "robô+ativo e nunca troca de papel; crie outra conta."
        )
    return account


def load_account(conn: sqlite3.Connection, name: str) -> Optional[AccountState]:
    """Carrega a conta pelo nome, já com as posições preenchidas."""
    row = conn.execute("SELECT * FROM live_accounts WHERE name = ?", (name,)).fetchone()
    if row is None:
        return None
    account = AccountState(
        id=row["id"],
        name=row["name"],
        mode=row["mode"],
        initial_capital=row["initial_capital"],
        cash=row["cash"],
        cash_sombra=(row["cash_sombra"] if "cash_sombra" in row.keys() else 0.0),
        investment_robot=row["investment_robot"] or "",
        withdrawal_robot=row["withdrawal_robot"] or "",
        symbol=(row["symbol"] or "") if "symbol" in row.keys() else "",
        archived_at=(row["archived_at"] if "archived_at" in row.keys() else None),
        withdrawn_total=row["withdrawn_total"],
        external_cash=row["external_cash"],
        policy_state=_loads(row["policy_state"]),
    )
    account.positions = load_positions(conn, account.id)
    return account


def save_account(conn: sqlite3.Connection, account: AccountState) -> None:
    """Persiste o estado mutável da conta: caixa, contadores de saque,
    `policy_state`, e a IDENTIDADE OPERACIONAL (robô, capital inicial, ativo).

    Não mexe em posições — elas têm suas próprias funções (`upsert_position`/
    `delete_position`), porque uma conta pode ter N posições e não faz sentido
    reescrever a lista inteira a cada save da conta.

    `investment_robot`/`initial_capital`/`symbol` entraram aqui em 2026-08-22,
    corrigindo um bug silencioso: eles só eram gravados no INSERT de
    `ensure_account`, que é `ON CONFLICT(name) DO NOTHING`. Como o painel cria
    a conta primeiro como linha só contábil (`POST /operacao/.../caixa`, com
    `investment_robot=''`, para o caixa digitado sobreviver ao F5) e só depois
    escolhe o robô, o `ensure_account` seguinte não atualizava nada e o
    `save_account` também não — o robô ficava gravado só em memória e a conta
    permanecia para sempre sem `investment_robot`. Efeito visível:
    `live_service.get_status()` devolvia `existe: False` para uma conta que
    estava operando de verdade.

    Não é escrita perigosa: todo chamador em produção carrega a conta com
    `load_account` e devolve a MESMA instância, então os três campos fazem
    round-trip idênticos a menos que alguém os mude de propósito.
    `mode` continua de fora — esse é imutável por decisão (ver `ensure_account`).
    """
    conn.execute(
        """UPDATE live_accounts
           SET cash = ?, cash_sombra = ?, withdrawn_total = ?, external_cash = ?, policy_state = ?,
               investment_robot = ?, initial_capital = ?, symbol = ?,
               updated_at = datetime('now')
           WHERE id = ?""",
        (
            account.cash,
            account.cash_sombra,
            account.withdrawn_total,
            account.external_cash,
            _dumps(account.policy_state),
            account.investment_robot or "",
            account.initial_capital,
            account.symbol or "",
            account.id,
        ),
    )


def accounts_with_symbol(conn: sqlite3.Connection) -> list[AccountState]:
    """Todas as contas que declaram um ativo (`symbol != ''`) — ou seja, as
    contas de DAY TRADE — na ordem em que aparecem no painel.

    A ordem é `sort_order` (posição escolhida pelo dono ao arrastar um cartão,
    ver `set_daytrade_account_order`), com empate em `id` (ordem de criação):
    toda conta nasce com `sort_order=0`, então até o dono mexer pela primeira
    vez a lista continua saindo em ordem de criação, como sempre foi.

    É a fonte de verdade de "quais ativos já estão alocados", e existe para
    ser lida por DOIS lados independentes: o painel (para desenhar a bolinha
    verde e ordenar o select) e o PROCESSO de cada robô (para saber o que já
    roda antes de sugerir um ativo novo). Vem do BANCO, e não do arquivo de
    estado dos processos (`db/live_process.json`), de propósito: aquele
    arquivo é do dashboard, e um robô parado continua sendo dono do ativo
    dele — o caixa está lá.

    `archived_at IS NULL` porque conta ARQUIVADA não é vaga ocupada: o dono
    removeu aquele robô do painel (guardando o histórico, ver
    `archive_account`) e o ativo tem de voltar a ficar livre na mesma hora.
    Fosse contada aqui, o cartão sumiria da tela mas o ativo continuaria
    bloqueado — o pior dos dois mundos, e sem lugar nenhum para o dono
    entender o motivo.
    """
    rows = conn.execute(
        "SELECT name FROM live_accounts WHERE symbol IS NOT NULL AND symbol != '' "
        "AND archived_at IS NULL ORDER BY sort_order, id"
    ).fetchall()
    contas = [load_account(conn, row["name"]) for row in rows]
    return [c for c in contas if c is not None]


def set_daytrade_account_order(conn: sqlite3.Connection, ordem: list[str]) -> None:
    """Grava a ordem MANUAL completa das contas de day trade, na sequência
    de `ordem` (lista de `slot.id` == `live_accounts.name`, de cima pra
    baixo) — pedido do dono (2026-08-24): arrastar o cartão FECHADO para
    qualquer posição, e ela sobreviver a F5 e a reiniciar o `dev.bat`.

    Quem monta `ordem` é o JS do painel, lendo o DOM depois do drop (ver
    `static/js/operacao.js`) — já é a ordem final desejada, então aqui só
    resta ESCREVER: `sort_order = posição` para cada nome, 0..N-1. Um nome em
    `ordem` que não estiver mais entre as contas de day trade (aba dupla, F5
    concorrente que apagou o robô no meio do arrasto) é ignorado em
    silêncio — não há erro possível que valha a pena mostrar por causa de uma
    corrida de tela, e as contas que sobrarem de fora de `ordem` só mantêm o
    `sort_order` antigo delas, sem quebrar a lista.
    """
    existentes = {
        row["name"] for row in conn.execute(
            "SELECT name FROM live_accounts WHERE symbol IS NOT NULL AND symbol != ''"
        )
    }
    for posicao, nome in enumerate(ordem):
        if nome in existentes:
            conn.execute("UPDATE live_accounts SET sort_order = ? WHERE name = ?", (posicao, nome))


def delete_account(conn: sqlite3.Connection, name: str) -> bool:
    """Apaga a conta e TUDO que pende dela (posições, ordens, fills, avisos —
    `ON DELETE CASCADE`). `False` se não existia.

    Existe para o painel poder remover um robô de day trade que o dono criou
    por engano ou não quer mais. RECUSA (`ValueError`) se a conta ainda tiver
    posição aberta ou caixa: apagar a linha não fecha posição na corretora nem
    devolve dinheiro — deixaria uma posição órfã, viva no MT5 e invisível no
    painel. Zerar o caixa e fechar posição é decisão do dono, feita antes.
    """
    account = load_account(conn, name)
    if account is None:
        return False
    if account.positions:
        raise ValueError(
            f"conta '{name}' tem {len(account.positions)} posição(ões) aberta(s) — "
            "feche na corretora antes de remover o robô, senão a posição fica "
            "viva no MT5 e invisível aqui."
        )
    if abs(account.cash) >= 0.005:
        raise ValueError(
            f"conta '{name}' ainda tem R$ {account.cash:.2f} em caixa — "
            "zere o caixa dela no painel antes de remover o robô."
        )
    conn.execute("DELETE FROM live_accounts WHERE id = ?", (account.id,))
    return True


# ---------------------------------------------------------------------------
# arquivo: remover o robô do painel SEM perder o que ele viveu
# ---------------------------------------------------------------------------
#
# Pedido do dono em 26/08/2026, olhando o Resumo Financeiro de um robô cujo
# processo já tinha morrido: "eu sei que tem um processo morto, mas eu não
# quero perder as informações do que estou rodando". Até aqui, remover era
# sempre `delete_account` — e o `ON DELETE CASCADE` levava junto diário,
# ordens, fills e avisos. Não havia meio-termo entre "o cartão fica na tela
# para sempre" e "some tudo".
#
# O meio-termo é este: a conta continua INTEIRA no banco, só marcada com
# `archived_at`. Some do painel (`accounts_with_symbol`), o ativo volta a
# ficar livre na hora, e o histórico espera. Quem decide o destino final é o
# próprio dono, depois, no formulário de robô novo: recriar o MESMO trio
# (robô, ativo, modo) oferece restaurar; criar "do zero" descarta.
#
# `load_account` de propósito NÃO filtra por `archived_at` — restaurar e
# descartar precisam achar a conta pelo nome, e o nome é o id do slot.


def archive_account(conn: sqlite3.Connection, name: str) -> bool:
    """Marca a conta como arquivada, sem apagar nada. `False` se não existia.

    RECUSA (`ValueError`) com posição aberta, pelo mesmo motivo de
    `delete_account`: arquivar tira o cartão da tela, e uma posição viva no
    MT5 sem cartão que a mostre é órfã invisível — o desfecho que
    `dashboard.live_teardown` existe para impedir.

    Ao contrário de `delete_account`, NÃO exige caixa zerado: o caixa é parte
    do que o dono pediu para guardar. Ele fica reservado a este robô até o
    arquivo ser restaurado ou descartado, exatamente como ficava enquanto o
    robô estava parado.

    Arquivar uma conta já arquivada é no-op (`True`), sem mexer na data
    original — a primeira remoção é a que conta.
    """
    account = load_account(conn, name)
    if account is None:
        return False
    if account.positions:
        raise ValueError(
            f"conta '{name}' tem {len(account.positions)} posição(ões) aberta(s) — "
            "feche na corretora antes de arquivar o robô, senão a posição fica "
            "viva no MT5 e invisível aqui."
        )
    if account.archived_at:
        return True
    conn.execute(
        "UPDATE live_accounts SET archived_at = datetime('now'), "
        "updated_at = datetime('now') WHERE id = ?",
        (account.id,),
    )
    return True


def restore_account(conn: sqlite3.Connection, name: str) -> Optional[AccountState]:
    """Traz a conta arquivada de volta ao painel, com tudo que ela guardava.
    Devolve a conta restaurada, ou `None` se não havia nada arquivado com
    esse nome (conta viva não é "restaurada" — não foi a lugar nenhum).
    """
    account = load_account(conn, name)
    if account is None or not account.archived_at:
        return None
    conn.execute(
        "UPDATE live_accounts SET archived_at = NULL, updated_at = datetime('now') "
        "WHERE id = ?",
        (account.id,),
    )
    account.archived_at = None
    return account


def purge_account(conn: sqlite3.Connection, name: str) -> bool:
    """Descarta de vez uma conta ARQUIVADA — ela e tudo que pende dela.
    `False` se não existia.

    Só aceita conta arquivada (`ValueError` caso contrário): é o caminho do
    "criar do zero", onde o dono desmarcou "restaurar" e disse, por omissão,
    que aquele histórico não interessa mais. Uma conta VIVA nunca some por
    este caminho — para essa existe `delete_account`, com os guardas de
    posição e caixa.

    E aqui o caixa NÃO é guarda: a conta já saiu do painel quando foi
    arquivada, e o guarda de `delete_account` existe para o dono não apagar
    sem querer um robô que ainda tem dinheiro alocado na tela. Aqui a decisão
    já foi tomada duas vezes (remover guardando, depois recriar do zero), e
    exigir "zere o caixa antes" só travaria o formulário com uma mensagem
    sobre uma conta que ele nem mostra mais.
    """
    account = load_account(conn, name)
    if account is None:
        return False
    if not account.archived_at:
        raise ValueError(
            f"conta '{name}' não está arquivada — `purge_account` é só para o "
            "arquivo. Use `delete_account`, que confere posição e caixa."
        )
    conn.execute("DELETE FROM live_accounts WHERE id = ?", (account.id,))
    return True


def archived_accounts(conn: sqlite3.Connection) -> list[AccountState]:
    """Contas de day trade arquivadas, mais recentes primeiro.

    É o que o formulário de robô novo lê para saber em quais trios (robô,
    ativo, modo) o toggle "restaurar" tem o que restaurar — mostrar a opção
    onde não há arquivo nenhum seria oferecer um botão que não faz nada.
    """
    rows = conn.execute(
        "SELECT name FROM live_accounts WHERE symbol IS NOT NULL AND symbol != '' "
        "AND archived_at IS NOT NULL ORDER BY archived_at DESC, id DESC"
    ).fetchall()
    contas = [load_account(conn, row["name"]) for row in rows]
    return [c for c in contas if c is not None]


# ---------------------------------------------------------------------------
# avisos de capital disponível (enxame de day trade)
# ---------------------------------------------------------------------------

def record_capital_signal(
    conn: sqlite3.Connection,
    account_id: int,
    robot: str,
    suggested_symbol: str,
    cash_brl: float,
    required_brl: float,
) -> bool:
    """Grava o aviso "esta conta já tem caixa para o dono abrir `robot` em
    `suggested_symbol`". `True` se foi gravado agora, `False` se já existia.

    A deduplicação é do BANCO (`UNIQUE(account_id, suggested_symbol)` +
    `ON CONFLICT DO NOTHING`), não de quem chama: a condição que dispara o
    aviso continua verdadeira em toda barra seguinte, e um robô de day trade vê
    centenas de barras por dia. Sem isso, a caixa de mensagens viraria um log
    de spam e o "marcar como feito" não significaria nada.

    Um aviso já marcado como feito NÃO volta: a linha continua lá (com
    `acknowledged_at` preenchido) e o `ON CONFLICT` a preserva. É o
    comportamento desejado — "já cuidei disso" vale para sempre naquele ativo,
    e se o dono quiser ser avisado de novo ele remove o aviso.
    """
    cur = conn.execute(
        """INSERT INTO live_capital_signals
            (account_id, robot, suggested_symbol, cash_brl, required_brl)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(account_id, suggested_symbol) DO NOTHING""",
        (account_id, robot, suggested_symbol, float(cash_brl), float(required_brl)),
    )
    return cur.rowcount > 0


def capital_signals(conn: sqlite3.Connection, pending_only: bool = False) -> list[dict]:
    """Avisos de capital, do mais novo para o mais velho, já com o nome da
    conta que avisou. `pending_only=True` devolve só os que ainda não foram
    marcados como feitos."""
    sql = """SELECT s.id, s.ts, s.robot, s.suggested_symbol, s.cash_brl,
                    s.required_brl, s.acknowledged_at, a.name AS account_name
             FROM live_capital_signals s
             JOIN live_accounts a ON a.id = s.account_id"""
    if pending_only:
        sql += " WHERE s.acknowledged_at IS NULL"
    sql += " ORDER BY s.ts DESC, s.id DESC"
    return [dict(row) for row in conn.execute(sql)]


def acknowledge_capital_signal(conn: sqlite3.Connection, signal_id: int) -> bool:
    """Marca o aviso como feito. `False` se o id não existe ou já estava
    marcado — idempotente contra F5/POST repetido."""
    cur = conn.execute(
        "UPDATE live_capital_signals SET acknowledged_at = datetime('now') "
        "WHERE id = ? AND acknowledged_at IS NULL",
        (signal_id,),
    )
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# posições
# ---------------------------------------------------------------------------

def upsert_position(conn: sqlite3.Connection, account_id: int, position: LivePosition) -> int:
    """Insere ou atualiza a posição (chave: account_id + ticker + kind).

    Preenche `position.id` como conveniência para quem chamou, mas o valor de
    retorno é a fonte de verdade.
    """
    conn.execute(
        """INSERT INTO live_positions
            (account_id, ticker, quantity, entry_date, entry_price, capital_allocated,
             current_stop, fees_paid, slippage_paid, max_price_seen, min_price_seen,
             bars_held, kind, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(account_id, ticker, kind) DO UPDATE SET
               quantity = excluded.quantity,
               entry_date = excluded.entry_date,
               entry_price = excluded.entry_price,
               capital_allocated = excluded.capital_allocated,
               current_stop = excluded.current_stop,
               fees_paid = excluded.fees_paid,
               slippage_paid = excluded.slippage_paid,
               max_price_seen = excluded.max_price_seen,
               min_price_seen = excluded.min_price_seen,
               bars_held = excluded.bars_held,
               metadata = excluded.metadata""",
        (
            account_id,
            position.ticker,
            position.quantity,
            position.entry_date.isoformat(),
            position.entry_price,
            position.capital_allocated,
            position.current_stop,
            position.fees_paid,
            position.slippage_paid,
            position.max_price_seen,
            position.min_price_seen,
            position.bars_held,
            position.kind,
            _dumps(position.metadata),
        ),
    )
    row = conn.execute(
        "SELECT id FROM live_positions WHERE account_id = ? AND ticker = ? AND kind = ?",
        (account_id, position.ticker, position.kind),
    ).fetchone()
    position.id = int(row["id"])
    return position.id


def delete_position(conn: sqlite3.Connection, account_id: int, ticker: str, kind: str = "main") -> None:
    conn.execute(
        "DELETE FROM live_positions WHERE account_id = ? AND ticker = ? AND kind = ?",
        (account_id, ticker, kind),
    )


def _row_to_position(row: sqlite3.Row) -> LivePosition:
    return LivePosition(
        id=row["id"],
        ticker=row["ticker"],
        quantity=row["quantity"],
        entry_date=date.fromisoformat(row["entry_date"]),
        entry_price=row["entry_price"],
        capital_allocated=row["capital_allocated"],
        current_stop=row["current_stop"],
        fees_paid=row["fees_paid"],
        slippage_paid=row["slippage_paid"],
        max_price_seen=row["max_price_seen"],
        min_price_seen=row["min_price_seen"],
        bars_held=row["bars_held"],
        kind=row["kind"],
        metadata=_loads(row["metadata"]),
    )


def load_positions(conn: sqlite3.Connection, account_id: int) -> dict[str, LivePosition]:
    """Todas as posições da conta, chaveadas por ticker (espelha `AccountState.positions`).

    Nota: o schema permite um ticker ter posição 'main' E 'satellite' ao
    mesmo tempo (UNIQUE inclui `kind`), mas `AccountState.positions` — assim
    como as duas structures separadas em `backtest.engine_satellite` — só tem
    um slot por ticker neste dicionário. Na prática as duas camadas de
    posição do robô (principal e satélite) não coexistem para o mesmo
    ticker; se algum dia coexistirem, quem precisar das duas deve consultar
    `live_positions` diretamente por `kind`.
    """
    rows = conn.execute(
        "SELECT * FROM live_positions WHERE account_id = ? ORDER BY id",
        (account_id,),
    ).fetchall()
    return {row["ticker"]: _row_to_position(row) for row in rows}


# ---------------------------------------------------------------------------
# intenções
# ---------------------------------------------------------------------------

def _row_to_intent(row: sqlite3.Row) -> Intent:
    return Intent(
        id=row["id"],
        robot=row["robot"],
        role=RobotRole(row["role"]),
        kind=IntentKind(row["kind"]),
        decided_on=date.fromisoformat(row["decided_on"]),
        execute_on=date.fromisoformat(row["execute_on"]),
        ticker=row["ticker"],
        reason=row["reason"] or "",
        size_hint=row["size_hint"],
        stop_price=row["stop_price"],
        amount=row["amount"],
        status=IntentStatus(row["status"]),
        payload=_loads(row["payload"]),
    )


def record_intent(conn: sqlite3.Connection, account_id: int, intent: Intent) -> int:
    """Grava a intenção. Preenche `intent.id`.

    Invariante de banco para a regra 4 do AGENTS.md ("sem look-ahead"): ao
    vivo essa regra vira uma disciplina de relógio (ver docstring de
    `core.live_models`), e o ponto mais barato para impedi-la de vazar é aqui,
    na gravação — se `execute_on <= decided_on` para uma intent que NÃO é
    imediata (`Intent.is_immediate` cobre as três exceções legítimas,
    ADJUST_STOP, reason == 'stop' e WITHDRAW same-day por evento de
    liquidez), é bug de look-ahead e a gravação é rejeitada antes de virar
    linha no diário.
    """
    if not intent.is_immediate and intent.execute_on <= intent.decided_on:
        raise ValueError(
            f"look-ahead: execute_on ({intent.execute_on.isoformat()}) <= "
            f"decided_on ({intent.decided_on.isoformat()}) para intent "
            f"kind={intent.kind.value!r} reason={intent.reason!r}. Regra 4 do "
            "AGENTS.md: decisão no fecho de D só executa em D+1 (exceções: "
            "ADJUST_STOP, reason='stop' e WITHDRAW same-day por liquidez, "
            "ver Intent.is_immediate)."
        )
    cur = conn.execute(
        """INSERT INTO live_intents
            (account_id, robot, role, kind, decided_on, execute_on, ticker, reason,
             size_hint, stop_price, amount, status, payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            account_id,
            intent.robot,
            intent.role.value,
            intent.kind.value,
            intent.decided_on.isoformat(),
            intent.execute_on.isoformat(),
            intent.ticker,
            intent.reason,
            intent.size_hint,
            intent.stop_price,
            intent.amount,
            intent.status.value,
            _dumps(intent.payload),
        ),
    )
    intent.id = int(cur.lastrowid)
    return intent.id


def pending_intents(conn: sqlite3.Connection, account_id: int, execute_on: date) -> list[Intent]:
    """Intents PENDING cuja `execute_on` é exatamente a data dada.

    É a pergunta que o runtime faz no pregão de hoje: "o que devo tentar
    executar agora?".
    """
    rows = conn.execute(
        """SELECT * FROM live_intents
           WHERE account_id = ? AND status = ? AND execute_on = ?
           ORDER BY id""",
        (account_id, IntentStatus.PENDING.value, execute_on.isoformat()),
    ).fetchall()
    return [_row_to_intent(row) for row in rows]


def stale_intents(conn: sqlite3.Connection, account_id: int, before: date) -> list[Intent]:
    """Intents PENDING cuja `execute_on` já passou (< `before`) — candidatas a EXPIRED.

    Existe porque decisão atrasada não executa (regra 7 do AGENTS.md): o
    runtime usa isto para achar intents que ficaram para trás (máquina fora do
    ar) e marcá-las como `EXPIRED` em vez de executá-las tarde.

    `kind != 'withdraw'` exclui recomendações de saque de propósito: elas não
    expiram por dia (uma recomendação decidida ontem continua válida hoje,
    amanhã, até o fim do mês) — quem expira recomendação de saque é
    `LiveRuntime._expire_withdraw_advice`, na virada do mês civil, não este
    filtro por data de execução.
    """
    rows = conn.execute(
        """SELECT * FROM live_intents
           WHERE account_id = ? AND status = ? AND execute_on < ? AND kind != ?
           ORDER BY id""",
        (account_id, IntentStatus.PENDING.value, before.isoformat(), IntentKind.WITHDRAW.value),
    ).fetchall()
    return [_row_to_intent(row) for row in rows]


def pending_withdraw_intents(conn: sqlite3.Connection, account_id: int) -> list[Intent]:
    """Todas as recomendações de saque (`kind='withdraw'`) ainda PENDING, de
    qualquer dia — ao contrário de `pending_intents`, que filtra por uma
    `execute_on` exata. Uma recomendação de saque fica visível/confirmável
    o mês inteiro (ver `stale_intents` acima e `LiveRuntime.
    _expire_withdraw_advice`), então quem precisa saber "o que está esperando
    confirmação humana agora" pergunta aqui, não a `pending_intents`.
    Ordenada por `id` (mais antiga primeiro).
    """
    rows = conn.execute(
        """SELECT * FROM live_intents
           WHERE account_id = ? AND status = ? AND kind = ?
           ORDER BY id""",
        (account_id, IntentStatus.PENDING.value, IntentKind.WITHDRAW.value),
    ).fetchall()
    return [_row_to_intent(row) for row in rows]


def set_intent_status(conn: sqlite3.Connection, intent_id: int, status: IntentStatus) -> None:
    conn.execute("UPDATE live_intents SET status = ? WHERE id = ?", (status.value, intent_id))


def claim_intent(
    conn: sqlite3.Connection, intent_id: int, from_status: IntentStatus, to_status: IntentStatus
) -> bool:
    """Transição de status ATÔMICA — `UPDATE ... WHERE id=? AND status=?`,
    devolve `cur.rowcount == 1`.

    Esta é a TRAVA contra duplo-clique/confirmação concorrente: duas chamadas
    disputando a mesma intent (um humano clicando duas vezes, um `sacar` de
    CLI repetido, dois processos) só deixam UMA vencer — quem recebe `False`
    perdeu a corrida e NÃO pode mover dinheiro (`set_intent_status` continua
    existindo para as transições onde não há corrida, como marcar EXECUTING/
    DONE/EXPIRED em fluxos que já são de dono único).
    """
    cur = conn.execute(
        "UPDATE live_intents SET status = ? WHERE id = ? AND status = ?",
        (to_status.value, intent_id, from_status.value),
    )
    return cur.rowcount == 1


def intents_by_status(conn: sqlite3.Connection, account_id: int, status: IntentStatus) -> list[Intent]:
    """Intents da conta num status qualquer — usada por `live.runtime.reconcile_pending_fills`
    para achar as `EXECUTING` (ordem no ar, aguardando confirmacao que chegou depois
    do ciclo original de execucao)."""
    rows = conn.execute(
        "SELECT * FROM live_intents WHERE account_id = ? AND status = ? ORDER BY id",
        (account_id, status.value),
    ).fetchall()
    return [_row_to_intent(row) for row in rows]


def all_intents(conn: sqlite3.Connection, account_id: int, limit: int = 500) -> list[Intent]:
    """Todas as intencoes da conta, mais recentes primeiro — para a pagina de
    historico (ao contrario de `pending_intents`/`stale_intents`, que filtram
    por status e servem ao runtime, esta e so leitura para auditoria)."""
    rows = conn.execute(
        "SELECT * FROM live_intents WHERE account_id = ? ORDER BY id DESC LIMIT ?",
        (account_id, limit),
    ).fetchall()
    return [_row_to_intent(row) for row in rows]


# ---------------------------------------------------------------------------
# snapshot de contexto de sinal (o "por que" de cada decisao)
# ---------------------------------------------------------------------------

# Ordem das colunas de `live_signal_snapshots` que vem do `MarketSnapshot`.
# Uma tupla so, usada tanto no INSERT quanto na leitura, para que acrescentar
# uma feature nova (regra 3 do AGENTS.md: "sempre que uma nova feature
# aparecer no snapshot, adicione coluna") seja UMA edicao aqui + UMA no
# schema, sem risco de desalinhar valor com coluna.
_SNAPSHOT_COLUMNS: tuple[str, ...] = (
    "close", "volume", "volume_vs_avg20", "mm20", "mm50", "mm200",
    "mm50_over_mm200_pct", "days_since_cross", "ifr14", "atr14",
    "historical_vol_30d", "distance_from_52w_high_pct",
    "distance_from_52w_low_pct", "ibov_close", "ibov_mm200",
    "ibov_above_mm200", "ibov_trend_strength", "correlation_with_ibov_60d",
)


def record_intent_snapshot(
    conn: sqlite3.Connection,
    intent_id: int,
    moment: str,
    ticker: str,
    snapshot: MarketSnapshot,
) -> int:
    """Grava o contexto de mercado que o robo viu ao decidir.

    `INSERT OR REPLACE` sobre o UNIQUE `(intent_id, moment)`: gravar duas
    vezes o snapshot da MESMA intencao no mesmo momento nao e conflito de
    dado, e reentrancia do runtime (um retry de sessao interrompida). A
    segunda gravacao descreve o mesmo pregao com o mesmo painel, entao
    sobrescrever e correto e nao duplica linha no diario.
    """
    if moment not in ("entry", "exit"):
        raise ValueError(f"moment invalido: {moment!r} (esperado 'entry' ou 'exit')")
    valores = [getattr(snapshot, c) for c in _SNAPSHOT_COLUMNS]
    cols = ", ".join(_SNAPSHOT_COLUMNS)
    marks = ", ".join("?" for _ in _SNAPSHOT_COLUMNS)
    cur = conn.execute(
        f"""INSERT OR REPLACE INTO live_signal_snapshots
                (intent_id, moment, ticker, {cols})
            VALUES (?, ?, ?, {marks})""",
        (intent_id, moment, ticker, *valores),
    )
    return int(cur.lastrowid)


def intent_snapshot(
    conn: sqlite3.Connection, intent_id: int, moment: Optional[str] = None
) -> Optional[dict]:
    """Snapshot gravado de uma intencao, como dict coluna->valor.

    Devolve dict (e nao `MarketSnapshot`) porque quem le isto e auditoria:
    dashboard e query exploratoria querem os nomes das colunas do jeito que
    estao no banco, iguais aos do backtest, para comparar lado a lado.
    """
    sql = "SELECT * FROM live_signal_snapshots WHERE intent_id = ?"
    params: list = [intent_id]
    if moment is not None:
        sql += " AND moment = ?"
        params.append(moment)
    row = conn.execute(sql + " ORDER BY id DESC LIMIT 1", params).fetchone()
    return dict(row) if row is not None else None


def intent_snapshots(conn: sqlite3.Connection, account_id: int,
                     limit: int = 500) -> dict[int, dict]:
    """`intent_id` -> snapshot, para as intencoes mais recentes da conta.

    Uma query so em vez de N: a pagina de historico lista centenas de
    intencoes e precisa do contexto de cada uma.
    """
    rows = conn.execute(
        """SELECT s.* FROM live_signal_snapshots s
             JOIN live_intents i ON i.id = s.intent_id
            WHERE i.account_id = ?
            ORDER BY s.id DESC LIMIT ?""",
        (account_id, limit),
    ).fetchall()
    return {int(r["intent_id"]): dict(r) for r in rows}


# ---------------------------------------------------------------------------
# ordens e fills
# ---------------------------------------------------------------------------

def _row_to_order(row: sqlite3.Row) -> Order:
    return Order(
        id=row["id"],
        intent_id=row["intent_id"],
        ticker=row["ticker"],
        side=OrderSide(row["side"]),
        quantity=row["quantity"],
        order_type=OrderType(row["order_type"]),
        limit_price=row["limit_price"],
        status=OrderStatus(row["status"]),
        filled_qty=row["filled_qty"],
        avg_price=row["avg_price"],
        fees=row["fees"],
        slippage=row["slippage"],
        broker_ref=row["broker_ref"],
        sent_at=datetime.fromisoformat(row["sent_at"]) if row["sent_at"] else None,
        note=row["note"] or "",
    )


def record_order(conn: sqlite3.Connection, account_id: int, order: Order) -> int:
    """Grava a ordem enviada (ou a enviar). Preenche `order.id`."""
    cur = conn.execute(
        """INSERT INTO live_orders
            (account_id, intent_id, ticker, side, quantity, order_type, limit_price,
             status, filled_qty, avg_price, fees, slippage, broker_ref, sent_at, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            account_id,
            order.intent_id,
            order.ticker,
            order.side.value,
            order.quantity,
            order.order_type.value,
            order.limit_price,
            order.status.value,
            order.filled_qty,
            order.avg_price,
            order.fees,
            order.slippage,
            order.broker_ref,
            order.sent_at.isoformat() if order.sent_at else None,
            order.note,
        ),
    )
    order.id = int(cur.lastrowid)
    return order.id


def update_order(conn: sqlite3.Connection, order: Order) -> None:
    """Atualiza o estado de uma ordem já gravada (status, fill acumulado, etc.)."""
    conn.execute(
        """UPDATE live_orders
           SET status = ?, filled_qty = ?, avg_price = ?, fees = ?, slippage = ?,
               broker_ref = ?, sent_at = ?, note = ?
           WHERE id = ?""",
        (
            order.status.value,
            order.filled_qty,
            order.avg_price,
            order.fees,
            order.slippage,
            order.broker_ref,
            order.sent_at.isoformat() if order.sent_at else None,
            order.note,
            order.id,
        ),
    )


def record_fill(conn: sqlite3.Connection, fill: Fill) -> int:
    """Grava uma execução (parcial ou total) reportada pela corretora."""
    ts = fill.ts.isoformat() if fill.ts else datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO live_fills (order_id, quantity, price, fees, ts) VALUES (?, ?, ?, ?, ?)",
        (fill.order_id, fill.quantity, fill.price, fill.fees, ts),
    )
    return int(cur.lastrowid)


def orders_for_intent(conn: sqlite3.Connection, intent_id: int) -> list[Order]:
    """Todas as ordens geradas por uma intencao, em ordem de criacao.

    Uma Intent pode gerar N Orders (retry, fatiamento, rejeicao) — ver o
    docstring de `core.live_models` sobre a separacao Intent/Order. Usada pela
    reconciliacao para achar a ultima ordem emitida para uma intencao ainda
    `EXECUTING`.
    """
    rows = conn.execute(
        "SELECT * FROM live_orders WHERE intent_id = ? ORDER BY id",
        (intent_id,),
    ).fetchall()
    return [_row_to_order(row) for row in rows]


def open_orders(conn: sqlite3.Connection, account_id: int) -> list[Order]:
    """Ordens que ainda podem mudar de estado (não terminais)."""
    placeholders = ",".join("?" for _ in _TERMINAL_ORDER_STATUSES)
    rows = conn.execute(
        f"""SELECT * FROM live_orders
            WHERE account_id = ? AND status NOT IN ({placeholders})
            ORDER BY id""",
        (account_id, *_TERMINAL_ORDER_STATUSES),
    ).fetchall()
    return [_row_to_order(row) for row in rows]


# ---------------------------------------------------------------------------
# marcação e saques
# ---------------------------------------------------------------------------

def record_equity(
    conn: sqlite3.Connection,
    account_id: int,
    day: date,
    cash: float,
    invested: float,
    equity: float,
    external_cash: float,
) -> None:
    """Upsert do ponto de marcação do dia. `patrimonio` é derivado aqui (equity + external_cash)
    para nunca divergir do que foi de fato gravado — ver comentário em `schema.sql`
    sobre por que essa é a medida honesta de risco quando há saque.
    """
    patrimonio = float(equity) + float(external_cash)
    conn.execute(
        """INSERT INTO live_equity (account_id, date, cash, invested, equity, external_cash, patrimonio)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(account_id, date) DO UPDATE SET
               cash = excluded.cash,
               invested = excluded.invested,
               equity = excluded.equity,
               external_cash = excluded.external_cash,
               patrimonio = excluded.patrimonio""",
        (account_id, day.isoformat(), cash, invested, equity, external_cash, patrimonio),
    )


def claim_session(
    conn: sqlite3.Connection,
    account_id: int,
    day: date,
    cash: float,
    invested: float,
    equity: float,
    external_cash: float,
) -> bool:
    """Reivindica ATOMICAMENTE o direito de decidir por `day`. `True` = venceu.

    Mesma trava de `claim_intent`, aplicada à decisão do fecho em vez de à
    intenção: `INSERT ... ON CONFLICT DO NOTHING` sobre a chave primária
    `(account_id, date)` de `live_equity`, e `rowcount == 1` responde "fui eu
    que marquei este pregão". Só o vencedor consulta a estratégia.

    Por que não basta o `SELECT` de "já decidido" que `close_and_decide` faz
    no início: entre ler e gravar existe uma janela, e nela cabe um segundo
    supervisor. Não há guarda de instância única no projeto — nenhum pidfile,
    nenhum lock de arquivo — e é plausível ter dois processos no mesmo banco
    (o painel e `scripts/run_live.py`, ou um restart que não matou o anterior).
    Duas decisões para o mesmo pregão significariam a MESMA rotação enviada
    duas vezes à corretora, com dinheiro de verdade. O `SELECT` continua
    existindo porque evita trabalho inútil no caso comum (`run_once` a cada
    minuto); esta função é o que torna o erro impossível, não só improvável.

    `record_equity` continua sendo upsert e continua existindo: ele é o
    caminho de CORREÇÃO/montagem de estado (testes, `scripts/migrate_live_db`),
    onde sobrescrever é o comportamento desejado. Quem decide usa este.
    """
    patrimonio = float(equity) + float(external_cash)
    cur = conn.execute(
        """INSERT INTO live_equity (account_id, date, cash, invested, equity, external_cash, patrimonio)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(account_id, date) DO NOTHING""",
        (account_id, day.isoformat(), float(cash), float(invested), float(equity),
         float(external_cash), patrimonio),
    )
    return cur.rowcount == 1


def equity_series(conn: sqlite3.Connection, account_id: int) -> list[tuple[str, float, float]]:
    """Série (date, equity, patrimonio) em ordem cronológica."""
    rows = conn.execute(
        "SELECT date, equity, patrimonio FROM live_equity WHERE account_id = ? ORDER BY date",
        (account_id,),
    ).fetchall()
    return [(row["date"], row["equity"], row["patrimonio"]) for row in rows]


def last_equity(
    conn: sqlite3.Connection, account_id: int, on_or_before: str
) -> tuple[str, float, float] | None:
    """Última linha de `live_equity` com `date <= on_or_before` (date, equity, patrimonio).

    Existe porque o disjuntor intra-dia (FEAT-003) consulta a base do fecho
    anterior em CADA `intraday_tick` — `run_once` roda a cada minuto, e
    `equity_series` varre a tabela inteira (custo O(n) por chamada,
    ~480x/pregão). `ORDER BY date DESC LIMIT 1` resolve em O(log n) com o
    índice existente. Um único helper serve os três consumidores desta
    feature: base do fecho anterior (`_previous_close_patrimonio`),
    checagem de "já decidido" e a lista de pregões sem decisão em `status()`.
    Devolve `None` quando não há nenhuma linha `<= on_or_before`.
    """
    row = conn.execute(
        """SELECT date, equity, patrimonio FROM live_equity
           WHERE account_id = ? AND date <= ? ORDER BY date DESC LIMIT 1""",
        (account_id, on_or_before),
    ).fetchone()
    if row is None:
        return None
    return (row["date"], row["equity"], row["patrimonio"])


def record_withdrawal(
    conn: sqlite3.Connection,
    account_id: int,
    day: date,
    requested: float,
    executed: float,
    equity_before: float,
    fees_paid: float,
    liquidated: dict,
) -> int:
    cur = conn.execute(
        """INSERT INTO live_withdrawals
            (account_id, date, requested, executed, equity_before, fees_paid, liquidated)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (account_id, day.isoformat(), requested, executed, equity_before, fees_paid, _dumps(liquidated)),
    )
    return int(cur.lastrowid)


def record_deposit(
    conn: sqlite3.Connection,
    account_id: int,
    day: date,
    amount: float,
    origin: str,
    note: str = "",
) -> int:
    cur = conn.execute(
        """INSERT INTO live_deposits (account_id, date, amount, origin, note)
           VALUES (?, ?, ?, ?, ?)""",
        (account_id, day.isoformat(), amount, origin, note),
    )
    return int(cur.lastrowid)


def reconcile_cash(
    conn: sqlite3.Connection,
    account: AccountState,
    target_balance: float,
    day: date,
    origin: str,
    note: str = "",
    tolerance: float = 1.0,
) -> tuple[float, bool]:
    """Ajusta `account.cash` para `target_balance` (mutação in-place +
    `save_account`) e audita em `live_deposits`, SE a diferença passar de
    `tolerance` -- caso contrário não toca em nada. Devolve `(diferenca,
    aplicado)`; `diferenca` vem sempre arredondada a 2 casas, mesmo quando
    `aplicado` é `False`, porque quem chama (ver `dashboard/app.py::
    operacao_caixa`) quer reportar "já convergiu, diferença de R$0,00" em vez
    de esconder o número.

    Único chamador desde 2026-08-21: o LEDGER MANUAL de caixa por robô
    (`origin="manual_ledger"`). Antes havia dois — o sync automático com o
    saldo do MT5 (`origin="mt5_auto_sync"`, `LiveRuntime.
    reconcile_broker_cash`) e o override manual (`origin="manual_override"`)
    — e o primeiro foi removido porque o terminal atrasa em relação ao saldo
    real da corretora. `origin` continua parâmetro (e não constante) porque é
    o que distingue as linhas HISTÓRICAS de `live_deposits` na auditoria.

    `tolerance` importa: o default de R$1,00 foi calibrado para contas de
    milhares de reais e engoliria uma correção de R$0,50 num caixa de R$50 —
    quem opera com pouco capital passa um valor menor (ver
    `dashboard/app.py::operacao_caixa`, que usa `0.005`)."""
    diff = round(target_balance - account.cash, 2)
    if abs(diff) <= tolerance:
        return diff, False
    anterior = account.cash
    account.cash = target_balance
    save_account(conn, account)
    record_deposit(conn, account.id, day, diff, origin=origin,
                    note=note or f"caixa anterior {anterior:.2f} -> {target_balance:.2f}")
    return diff, True


def reconcile_cash_sombra(
    conn: sqlite3.Connection,
    account: AccountState,
    target_balance: float,
    tolerance: float = 1.0,
) -> tuple[float, bool]:
    """Irmã de `reconcile_cash`, mas para `account.cash_sombra` -- pedido do
    dono (2026-08-23): poder digitar/resetar o saldo de um teste em sombra
    sem tocar `cash`, o mesmo jeito que já podia com o caixa real.

    NÃO grava em `live_deposits`: aquela tabela é a auditoria de depósito de
    dinheiro DE VERDADE (lida por `available_cash`/relatórios de aporte, ver
    `live.intraday_runtime._avaliar_sugestao_de_capital`), e uma linha ali
    para um número simulado corromperia essa leitura. Um `log_event`
    informativo já basta para o histórico do slot."""
    diff = round(target_balance - account.cash_sombra, 2)
    if abs(diff) <= tolerance:
        return diff, False
    account.cash_sombra = target_balance
    save_account(conn, account)
    return diff, True


def withdrawals(conn: sqlite3.Connection, account_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM live_withdrawals WHERE account_id = ? ORDER BY date, id",
        (account_id,),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["liquidated"] = _loads(item["liquidated"])
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# log operacional
# ---------------------------------------------------------------------------

def log_event(
    conn: sqlite3.Connection,
    account_id: Optional[int],
    level: str,
    source: str,
    message: str,
    payload: Optional[dict] = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO live_events (account_id, level, source, message, payload)
           VALUES (?, ?, ?, ?, ?)""",
        (account_id, level, source, message, _dumps(payload)),
    )
    return int(cur.lastrowid)


def _dia_brt_em_utc(day: str) -> tuple[str, str]:
    """Bordas UTC (`[inicio, fim)`) do dia CIVIL de Brasília `day`.

    `ts` é gravado em UTC (`datetime('now')`), então `date(ts) = day` filtrava
    pelo dia UTC — que vira no dia seguinte às 21:00 de Brasília. Qualquer
    evento entre 21:00 e a meia-noite (supervisor de pé, robô iniciado à
    noite) caía no dia UTC seguinte e sumia do "diário do dia" mesmo tendo
    acontecido hoje no relógio do dono. Com o console mostrando hora de
    Brasília (`app.py::hora_br`), o corte tem de ser do mesmo relógio.

    Pelo FUSO, nunca por "-3h" fixo, e em Python (não em SQL): o SQLite não
    tem base de fusos, e `date(ts, '-3 hours')` seria justamente o escalar que
    volta a errar se o horário de verão brasileiro voltar. Devolve texto no
    mesmo formato do `ts` gravado (`YYYY-MM-DD HH:MM:SS`), então a comparação
    lexicográfica do `>=`/`<` é a comparação cronológica — e ainda usa o
    índice `idx_live_events_account_ts`, que `date(ts)` não usava.
    """
    d = date.fromisoformat(day)
    inicio = datetime.combine(d, time(0, 0), tzinfo=SAO_PAULO)
    fim = datetime.combine(d + timedelta(days=1), time(0, 0), tzinfo=SAO_PAULO)
    fmt = "%Y-%m-%d %H:%M:%S"
    return (inicio.astimezone(timezone.utc).strftime(fmt),
            fim.astimezone(timezone.utc).strftime(fmt))


def recent_events(conn: sqlite3.Connection, account_id: Optional[int] = None, limit: int = 100,
                   day: Optional[str] = None, before_id: Optional[int] = None) -> list[dict]:
    """`day` (`YYYY-MM-DD`) restringe ao pregão daquele dia, contado no
    relógio de BRASÍLIA (`_dia_brt_em_utc`) e não no dia UTC em que o `ts` foi
    gravado — é o mesmo relógio que o console do painel mostra (`app.py::
    hora_br`). Painel de `/operacao` usa isso para o console de eventos nunca
    acumular dias antigos (ver `IntradayLiveRuntime.status`/
    `LiveRuntime.status`).

    `before_id` é o cursor do scroll infinito do botão "Diário Completo"
    (ver `app.py::operacao_eventos_mais_antigos`): pega só eventos com `id`
    menor que o último já carregado. `id` (autoincrement) é seguro como
    cursor de "mais antigo que" porque cresce com a ordem de inserção, a
    mesma ordem de `ts` que o `ORDER BY` já usa como desempate."""
    clauses = []
    params: list = []
    if account_id is not None:
        clauses.append("account_id = ?")
        params.append(account_id)
    if day is not None:
        inicio, fim = _dia_brt_em_utc(day)
        clauses.append("ts >= ? AND ts < ?")
        params.extend([inicio, fim])
    if before_id is not None:
        clauses.append("id < ?")
        params.append(before_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM live_events {where} ORDER BY ts DESC, id DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["payload"] = _loads(item["payload"])
        result.append(item)
    return result


def daytrade_exit_events(conn: sqlite3.Connection, account_id: int) -> list[dict]:
    """Uma linha por SAÍDA (cheia ou fatia) do day trade desta conta, do
    início da conta pra cá -- fonte de ganhos/perdas e CAGR/DD do painel de
    `/operacao` (dia e acumulado, ver `IntradayLiveRuntime.status`). Uma
    saída dividida em fatias grava mais de uma linha com o MESMO par
    `(date, round)`; quem precisa do resultado da RODADA inteira soma as
    linhas com esse par. `_on_closed`/`_on_closed_partial` gravam
    `numero_ordem`/`side`/`pnl_brl`/`sessao` no payload exatamente para isto
    -- filtrar por `pnl_brl` presente (só) distingue essas linhas das
    demais (posicionada/cancelada/entrada não têm `pnl_brl`). `date`
    prefere o `sessao` GRAVADO no payload (não o `ts` de inserção: o
    pregão simulado/declarado pode não bater com o relógio da máquina,
    mesma cautela de `core.b3_session`) mas cai para `ts[:10]` quando
    `sessao` não existe -- todo evento gravado ANTES deste campo existir
    (2026-08-24) não tem `sessao` nenhum, e sem o fallback ele
    desapareceria de "hoje" mesmo tendo acontecido hoje.

    REGRESSÃO CORRIGIDA no mesmo dia: a versão anterior também exigia
    `numero_ordem` presente para aceitar a linha -- isso é mais NOVO que
    `pnl_brl` (a numeração de rodada só passou a existir no meio do dia do
    deploy), então todo trade fechado ANTES da numeração existir tinha
    `pnl_brl` mas não `numero_ordem`, e desaparecia de "Ganhos do dia"
    inteiro (não só de "hoje" -- sumia do acumulado também). Achado ao
    vivo: `policy_state["intraday"]["shadow_pnl_brl"]` (a soma DE VERDADE,
    incrementada direto por `_on_closed`/`_on_closed_partial`, nunca lida
    do log) mostrava R$5,92 no dia; este painel mostrava R$1,97 -- só os 2
    trades fechados DEPOIS da numeração existir. `round` agora cai para o
    `id` da própria linha quando falta `numero_ordem`: cada linha assim
    vira uma rodada PRÓPRIA (nunca correlacionada com outra) -- sem o
    número real não dá pra saber se duas linhas são fatias da MESMA
    rodada, e assumir que são o mesmo trade juntaria coisas que talvez não
    tenham nada a ver."""
    rows = conn.execute(
        """SELECT id, ts, payload FROM live_events
           WHERE account_id = ? AND source = 'daytrade'
           ORDER BY ts, id""",
        (account_id,),
    ).fetchall()
    out = []
    for row in rows:
        payload = _loads(row["payload"])
        if payload.get("pnl_brl") is None:
            continue
        out.append({
            "date": payload.get("sessao") or row["ts"][:10],
            "round": payload.get("numero_ordem", f"legado-{row['id']}"),
            "side": payload.get("side"),
            "pnl_brl": float(payload["pnl_brl"]),
        })
    return out


def daytrade_order_events_on(conn: sqlite3.Connection, account_id: int, day: str) -> list[dict]:
    """Uma linha por ordem armada/preenchida/cancelada do day trade desta
    conta no PREGÃO `day` (`YYYY-MM-DD`) -- fonte do card "Ordens
    posicionadas" do painel de `/operacao`. `_on_limit_placed`/`_on_opened`/
    `_on_opened_top_up`/`_on_limit_cancelled` gravam `side` ("long"/"short",
    vocabulário interno do day trade) e `tipo` ("armada"/"preenchida"/
    "cancelada") no payload -- o tipo saiu do texto da mensagem e virou campo
    próprio em 2026-08-25, ver o comentário no laço abaixo.

    `day` casa com `sessao` (payload) quando existe, ou com `ts[:10]` (hora
    de inserção) em evento gravado ANTES desse campo existir -- mesmo
    fallback e mesmo motivo de `daytrade_exit_events`. `"armada"` no texto
    da mensagem é o nome ANTIGO do que virou "posicionada" no mesmo deploy
    que acrescentou `sessao` -- um evento sem `sessao` nunca vem com
    "posicionada", então aceitar os dois nomes é o que mantém o histórico
    de antes do deploy contável."""
    rows = conn.execute(
        """SELECT ts, message, payload FROM live_events
           WHERE account_id = ? AND source = 'daytrade'
           ORDER BY ts, id""",
        (account_id,),
    ).fetchall()
    out = []
    for row in rows:
        payload = _loads(row["payload"])
        if (payload.get("sessao") or row["ts"][:10]) != day:
            continue
        side = payload.get("side")
        if side is None:
            continue
        # `tipo` no payload é a fonte; o texto é só o fallback do histórico.
        # Nasceu porque o formato das linhas foi reescrito (2026-08-25, pedido
        # do dono: ação primeiro, sem "SOMBRA", em lotes) e classificar evento
        # lendo a frase que a tela mostra amarra o CARD ao texto -- toda
        # reescrita futura quebraria este filtro em silêncio, sem teste
        # vermelho, com o card só ficando vazio. Evento gravado antes de
        # 2026-08-25 não tem `tipo`, então o casamento por texto continua
        # aqui: "armada" é o nome mais antigo ainda, de antes de virar
        # "posicionada"; "entrada"/"TOP-UP" eram o preenchimento.
        kind = payload.get("tipo")
        if kind is None:
            msg = row["message"]
            if "posicionada" in msg or "armada" in msg:
                kind = "armada"
            elif "cancelada" in msg:
                kind = "cancelada"
            elif "entrada" in msg or "TOP-UP" in msg:
                kind = "preenchida"
        if kind not in ("armada", "cancelada", "preenchida"):
            continue
        # `quantity`/`price` (o preco vem como `limit_price` na armada e
        # `price` na entrada -- nomes diferentes no payload de cada evento,
        # ver `_on_limit_placed`/`_on_opened`) alimentam o VALOR em R$ do
        # card "Ordens" do painel (pedido do dono, 2026-08-24: "deve
        # aparecer os valores, e as quantidades abaixo") -- `None` quando o
        # evento nao carrega os dois (ex.: cancelamento antigo sem
        # `quantity`), e quem soma trata isso como "sem contribuicao".
        out.append({
            "side": side, "kind": kind,
            "quantity": payload.get("quantity"),
            "price": payload.get("limit_price", payload.get("price")),
            # Reancoragem da MESMA rodada carrega o mesmo `numero_ordem` --
            # e' o que deixa `_ordens_por_lado` (intraday_runtime.py) nao
            # contar um "(substitui)" como ordem nova. `None` num evento sem
            # o campo (payload antigo) faz cada linha contar sozinha, igual
            # sempre contou.
            "numero_ordem": payload.get("numero_ordem"),
        })
    return out


def daytrade_position_history(conn: sqlite3.Connection, account_id: int,
                              limit: int = 200) -> list[dict]:
    """Uma linha por POSIÇÃO (rodada) do day trade desta conta, da mais
    recente pra trás -- fonte do cartão "Posições" do painel de `/operacao`.

    Existe porque o cartão mostrava só `account.positions`, que é o que está
    aberto AGORA: fechou, sumiu da tela (queixa do dono, 2026-09-09). O
    histórico de rodadas já estava no diário desde 2026-08-24 (`numero_ordem`
    marca a rodada: posicionada -> [top-up(s)] -> saída), só nunca tinha sido
    lido como tabela -- reconstruir aqui é o que evita criar uma tabela nova
    e um segundo lugar pra verdade sair de sincronia.

    A CHAVE da rodada é `(sessão, numero_ordem)`, o mesmo par de
    `daytrade_exit_events`/`_resultado_dia_e_acumulado`: `trade_seq` só
    avança dentro do pregão, então o número sozinho não identifica nada.
    Evento sem `numero_ordem` (payload anterior à numeração) vira uma rodada
    PRÓPRIA por linha, pelo mesmo motivo documentado lá -- sem o número não
    há como afirmar que duas linhas são a mesma tentativa, e juntá-las
    inventaria um trade que talvez não tenha existido.

    FECHADA x ABERTA não se decide comparando quantidades: `_on_closed_partial`
    grava `quantidade_restante` e `_on_closed` não, e essa ausência é o
    único sinal que vale também para os eventos legados (que não gravavam
    `quantity` na saída). Uma rodada só é dada por fechada quando aparece uma
    saída SEM `quantidade_restante`.

    Os preços saem do payload, nunca do texto da mensagem (mesma cautela de
    `daytrade_order_events_on`): `entrada` prefere o `entry_price` da saída
    (preço médio que a máquina calculou pra posição inteira) e cai pra média
    ponderada dos fills quando a rodada ainda está aberta; `stop`/`alvo`
    preferem o valor do FECHO (o stop reancora no fill real, então o da
    entrada pode estar velho) e caem pro declarado na entrada."""
    rows = conn.execute(
        """SELECT id, ts, payload FROM live_events
           WHERE account_id = ? AND source = 'daytrade'
           ORDER BY ts, id""",
        (account_id,),
    ).fetchall()
    rodadas: dict[tuple, dict] = {}
    ordem: list[tuple] = []
    for row in rows:
        payload = _loads(row["payload"])
        saida = payload.get("pnl_brl") is not None
        entrada = payload.get("tipo") == "preenchida"
        if not (saida or entrada):
            continue
        sessao = payload.get("sessao") or row["ts"][:10]
        numero = payload.get("numero_ordem")
        chave = (sessao, numero if numero is not None else f"legado-{row['id']}")
        r = rodadas.get(chave)
        if r is None:
            r = {"sessao": sessao, "numero": numero, "lado": payload.get("side"),
                 "qtd": 0, "entrada": None, "alvo": None, "stop": None,
                 "saida": None, "motivo": None, "pnl_brl": None,
                 "duracao_s": None, "fatias": 0, "aberta": True,
                 # Capital comprometido AGORA -- preenchido so' pra rodada
                 # aberta, por `IntradayLiveRuntime.status`, que e' quem tem a
                 # posicao viva em maos. Fechada, o capital ja' voltou pro
                 # caixa e o numero honesto e' `None`.
                 "valor": None,
                 "hora_entrada": None, "hora_saida": None,
                 "_soma_entrada": 0.0, "_soma_saida": 0.0, "_peso_saida": 0.0}
            rodadas[chave] = r
            ordem.append(chave)
        if r["lado"] is None:
            r["lado"] = payload.get("side")
        if entrada:
            # Top-up entra aqui de novo com a fatia DELE: somar preço×quantidade
            # é o que faz a média ponderada bater com o preço médio da máquina
            # enquanto a rodada ainda não fechou (fechada, o `entry_price` da
            # saída manda -- ver a docstring).
            qtd = int(payload.get("quantity") or 0)
            preco = payload.get("price")
            if qtd and preco is not None:
                r["qtd"] += qtd
                r["_soma_entrada"] += float(preco) * qtd
            if payload.get("stop") is not None:
                r["stop"] = float(payload["stop"])
            if payload.get("target") is not None:
                r["alvo"] = float(payload["target"])
            if r["hora_entrada"] is None:
                r["hora_entrada"] = row["ts"]
        if saida:
            r["fatias"] += 1
            r["pnl_brl"] = (r["pnl_brl"] or 0.0) + float(payload["pnl_brl"])
            r["motivo"] = payload.get("exit_reason") or r["motivo"]
            r["hora_saida"] = row["ts"]
            if payload.get("duracao_s") is not None:
                r["duracao_s"] = float(payload["duracao_s"])
            if payload.get("entry_price") is not None:
                r["entrada"] = float(payload["entry_price"])
            # Peso 1 quando a saída não diz a quantidade (payload anterior a
            # 2026-09-09): sem isso a fatia legada não entraria na média e o
            # preço de saída da rodada apareceria vazio mesmo existindo.
            preco_saida = payload.get("exit_price")
            if preco_saida is not None:
                peso = float(payload.get("quantity") or 1)
                r["_soma_saida"] += float(preco_saida) * peso
                r["_peso_saida"] += peso
            if payload.get("stop") is not None:
                r["stop"] = float(payload["stop"])
            if payload.get("alvo_declarado") is not None:
                r["alvo"] = float(payload["alvo_declarado"])
            if "quantidade_restante" not in payload:
                r["aberta"] = False
    out = []
    for chave in reversed(ordem):
        r = rodadas[chave]
        if r["entrada"] is None and r["qtd"]:
            r["entrada"] = round(r["_soma_entrada"] / r["qtd"], 4)
        if r["_peso_saida"]:
            r["saida"] = round(r["_soma_saida"] / r["_peso_saida"], 4)
        if r["pnl_brl"] is not None:
            r["pnl_brl"] = round(r["pnl_brl"], 2)
        for descartavel in ("_soma_entrada", "_soma_saida", "_peso_saida"):
            r.pop(descartavel)
        out.append(r)
        if len(out) >= limit:
            break
    return out
