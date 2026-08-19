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
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, Optional

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
    """`live_accounts` ainda usa o CHECK antigo (vocabulário `paper`/`manual`/
    `broker`) e contém ao menos uma conta de SIMULAÇÃO (`mode='paper'`).

    Não é seguro converter isso em silêncio para o vocabulário canônico
    (`manual`/`mt5`, ver `core.live_models.BrokerMode`) — uma conta de
    simulação virar conta real por engano é o tipo de bug que só aparece
    quando já é tarde. Renomear a conta NÃO desbloqueia nada (o CHECK novo
    rejeita pelo VALOR da coluna `mode`, não pelo nome) — a única saída real
    é apagar a(s) linha(s), ou um `UPDATE` manual de `mode` feito com decisão
    humana consciente. Ver a mensagem da exceção para o texto completo.
    """


def _legacy_check_present(conn: sqlite3.Connection) -> bool:
    """`True` se `live_accounts` já existe no banco E seu DDL (lido de
    `sqlite_master`, posicionalmente — sem depender de `row_factory`) ainda
    tem o CHECK antigo. O marcador usado é `'broker'`: só existe no
    vocabulário antigo, o vocabulário canônico (`manual`/`mt5`) nunca o tem.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'live_accounts'"
    ).fetchone()
    if row is None:
        return False
    ddl = row[0] or ""
    return "'broker'" in ddl


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
    """Rebuild de `live_accounts` do vocabulário antigo (`paper`/`manual`/
    `broker`) para o canônico (`manual`/`mt5`) — chamado no início de
    `ensure_tables`, antes de qualquer outra tabela ser tocada.

    Recusa (levanta `LegacyPaperAccountError`, não mexe em nada) se houver
    alguma conta `mode='paper'` — nunca converte simulação em conta real em
    silêncio. Caso contrário, reconstrói a tabela na ordem OBRIGATÓRIA
    criar-nova -> copiar -> dropar-antiga -> renomear (nunca o inverso: a
    partir do SQLite 3.25 `ALTER TABLE ... RENAME` reescreve as cláusulas
    `REFERENCES` das tabelas FILHAS — renomear `live_accounts` para
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
            f"vocabulário canônico (manual/mt5) não cobre: {nomes}. Renomear "
            "a conta NÃO resolve — o CHECK novo rejeita pelo VALOR da coluna "
            "mode, não pelo nome da conta. As únicas saídas reais são: "
            "apagar a(s) linha(s) (perde o histórico dela), ou, com decisão "
            "humana consciente de que é seguro tratar essa conta como real, "
            "um UPDATE manual de mode para 'manual' ou 'mt5' depois de "
            "confirmar isso. Se esta conexão é para o banco de SIMULAÇÃO "
            "(db/live_sim.sqlite), a saída mais simples é apagar esse "
            "arquivo inteiro — não mexa na conta real por engano."
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
    """Contextmanager de transação, no mesmo estilo de `journal.writer.journal`."""
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
            (name, mode, initial_capital, cash, investment_robot, withdrawal_robot)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(name) DO NOTHING""",
        (name, mode, initial_capital, initial_capital, investment_robot, withdrawal_robot),
    )
    account = load_account(conn, name)
    assert account is not None, "insert com ON CONFLICT DO NOTHING não pode deixar a conta ausente"
    if account.mode != mode:
        raise ValueError(
            f"conta '{name}' já existe com mode={account.mode!r}, mas foi "
            f"pedida com mode={mode!r} — divergência entre a conta gravada "
            "e o broker/CLI que está chamando agora."
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
        investment_robot=row["investment_robot"] or "",
        withdrawal_robot=row["withdrawal_robot"] or "",
        withdrawn_total=row["withdrawn_total"],
        external_cash=row["external_cash"],
        policy_state=_loads(row["policy_state"]),
    )
    account.positions = load_positions(conn, account.id)
    return account


def save_account(conn: sqlite3.Connection, account: AccountState) -> None:
    """Persiste cash/withdrawn_total/external_cash/policy_state.

    Não mexe em posições — elas têm suas próprias funções (`upsert_position`/
    `delete_position`), porque uma conta pode ter N posições e não faz sentido
    reescrever a lista inteira a cada save da conta.
    """
    conn.execute(
        """UPDATE live_accounts
           SET cash = ?, withdrawn_total = ?, external_cash = ?, policy_state = ?,
               updated_at = datetime('now')
           WHERE id = ?""",
        (
            account.cash,
            account.withdrawn_total,
            account.external_cash,
            _dumps(account.policy_state),
            account.id,
        ),
    )


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


def recent_events(conn: sqlite3.Connection, account_id: Optional[int] = None, limit: int = 100) -> list[dict]:
    if account_id is None:
        rows = conn.execute(
            "SELECT * FROM live_events ORDER BY ts DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM live_events WHERE account_id = ? ORDER BY ts DESC, id DESC LIMIT ?",
            (account_id, limit),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["payload"] = _loads(item["payload"])
        result.append(item)
    return result
