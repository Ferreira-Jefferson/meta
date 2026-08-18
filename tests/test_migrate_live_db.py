"""Testes de FEAT-000: migração `journal.sqlite` -> `live.sqlite` (P4) e a
guarda do simulador acelerado contra apagar um banco não-descartável (P5).

As duas salvaguardas de `scripts/` desta feature moram no mesmo arquivo de
teste (ver plano de ação, seção 2) para não criar um 4º arquivo novo.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

# `scripts/` não é um pacote (sem __init__.py) e não está no pythonpath do
# projeto (só `src/` está, via pyproject.toml). Mesma técnica que os próprios
# scripts usam para achar `src/`.
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.config import DB_PATH, LIVE_DB_PATH
from core.live_models import (
    Fill,
    Intent,
    IntentKind,
    LivePosition,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    RobotRole,
)
from journal import live_store as store

from migrate_live_db import (  # type: ignore[import-not-found]
    MigrationIncomplete,
    MigrationRefused,
    migrate,
)
from run_live_sim import SIM_DB, _ensure_disposable_sim_db  # type: ignore[import-not-found]


def _seed(source: Path) -> None:
    with store.live_journal(source) as conn:
        account = store.ensure_account(
            conn,
            name="principal",
            mode="paper",
            initial_capital=10_000.0,
            investment_robot="dip2_hw40",
            withdrawal_robot="official_policy",
        )
        store.upsert_position(
            conn,
            account.id,
            LivePosition(
                ticker="WEGE3.SA",
                quantity=100,
                entry_date=date(2026, 8, 10),
                entry_price=40.0,
                capital_allocated=4_000.0,
                current_stop=36.0,
            ),
        )
        intent = Intent(
            robot="dip2_hw40",
            role=RobotRole.INVESTMENT,
            kind=IntentKind.ENTER,
            decided_on=date(2026, 8, 10),
            execute_on=date(2026, 8, 11),
            ticker="WEGE3.SA",
            reason="dip_confirmed",
            size_hint=0.2,
        )
        store.record_intent(conn, account.id, intent)

        order = Order(
            ticker="WEGE3.SA",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.ON_OPEN,
            status=OrderStatus.FILLED,
            filled_qty=100,
            avg_price=40.0,
        )
        store.record_order(conn, account.id, order)
        store.record_fill(conn, Fill(order_id=order.id, quantity=100, price=40.0, fees=1.2))

        store.record_equity(
            conn, account.id, date(2026, 8, 10),
            cash=6_000.0, invested=4_000.0, equity=10_000.0, external_cash=0.0,
        )
        store.record_withdrawal(
            conn, account.id, date(2026, 8, 11),
            requested=100.0, executed=100.0, equity_before=10_000.0,
            fees_paid=0.5, liquidated={},
        )
        store.record_deposit(conn, account.id, date(2026, 8, 9), amount=10_000.0, origin="manual")
        store.log_event(conn, account.id, "info", "test", "seed")


# ---------------------------------------------------------------------------
# migração (P4)
# ---------------------------------------------------------------------------

def test_migrate_copia_e_e_idempotente_e_preserva_origem(tmp_path):
    source = tmp_path / "journal.sqlite"
    dest = tmp_path / "live.sqlite"
    _seed(source)
    before = source.read_bytes()

    result = migrate(source=source, dest=dest)
    assert result == {
        "live_accounts": 1,
        "live_positions": 1,
        "live_intents": 1,
        "live_orders": 1,
        "live_fills": 1,
        "live_equity": 1,
        "live_withdrawals": 1,
        "live_deposits": 1,
        "live_events": 1,
    }

    # a falsificação que esta prova pega: origem alterada byte a byte.
    assert source.read_bytes() == before

    # 2a rodada: idempotente, 0 linhas novas em qualquer tabela.
    result2 = migrate(source=source, dest=dest)
    assert all(v == 0 for v in result2.values())

    conn = sqlite3.connect(dest)
    try:
        fk_problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert fk_problems == []
        count = conn.execute("SELECT COUNT(*) FROM live_accounts").fetchone()[0]
        assert count == 1  # 2a rodada não duplicou a conta
    finally:
        conn.close()


def test_migrate_origem_sem_tabelas_live_devolve_vazio(tmp_path):
    source = tmp_path / "sem_live.sqlite"
    dest = tmp_path / "dest.sqlite"
    conn = sqlite3.connect(source)
    conn.execute("CREATE TABLE dummy (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    assert migrate(source=source, dest=dest) == {}


def test_migrate_origem_inexistente_levanta_filenotfound(tmp_path):
    """Correção pós-code-review (A7): origem ausente é provavelmente um typo
    em `--source`, não uma "migração completa" — antes devolvia `{}`/exit 0,
    hoje levanta `FileNotFoundError` com o caminho na mensagem, e o CLI sai
    != 0. Sem isso, o operador conclui "migração ok" quando na verdade nada
    rodou."""
    source = tmp_path / "nao_existe.sqlite"
    dest = tmp_path / "dest.sqlite"
    with pytest.raises(FileNotFoundError, match=r"nao_existe\.sqlite"):
        migrate(source=source, dest=dest)
    # nada foi criado no destino: a checagem acontece antes de qualquer
    # escrita.
    assert not dest.exists()


# ---------------------------------------------------------------------------
# marcador de conclusão de migração (correção pós-code-review, A1/A2/A4/B2)
# ---------------------------------------------------------------------------

def test_migrate_recusa_destino_ja_povoado_sem_marcador(tmp_path):
    """Destino com `user_version == 0` mas já tem uma conta em live_accounts
    (escrita real por fora desta migração, ex.: o robô já rodou contra este
    banco) -> recusa, sem copiar nada, sem --force."""
    source = tmp_path / "journal.sqlite"
    dest = tmp_path / "live.sqlite"
    _seed(source)

    dest_conn = sqlite3.connect(dest)
    try:
        dest_conn.executescript(
            "CREATE TABLE live_accounts (id INTEGER PRIMARY KEY, name TEXT UNIQUE, "
            "mode TEXT, initial_capital REAL, cash REAL, investment_robot TEXT, "
            "withdrawal_robot TEXT, withdrawn_total REAL DEFAULT 0, "
            "external_cash REAL DEFAULT 0, policy_state TEXT DEFAULT '{}', "
            "created_at TEXT, updated_at TEXT);"
        )
        dest_conn.execute(
            "INSERT INTO live_accounts (id, name, mode, initial_capital, cash) "
            "VALUES (1, 'ja_existe', 'paper', 1000.0, 1000.0)"
        )
        dest_conn.commit()
        # user_version fica no default 0 -- nunca foi migrado por este script.
        assert dest_conn.execute("PRAGMA user_version").fetchone()[0] == 0
    finally:
        dest_conn.close()

    with pytest.raises(MigrationRefused, match="live_accounts"):
        migrate(source=source, dest=dest)

    # recusa é total: a conta pré-existente continua sozinha, nada da origem
    # foi copiado por cima dela.
    conn = sqlite3.connect(dest)
    try:
        count = conn.execute("SELECT COUNT(*) FROM live_accounts").fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_migrate_force_ignora_recusa_e_copia(tmp_path):
    """`--force` (force=True) ignora só a checagem de "destino povoado sem
    marcador" -- a cópia acontece normalmente."""
    source = tmp_path / "journal.sqlite"
    dest = tmp_path / "live.sqlite"
    _seed(source)

    dest_conn = sqlite3.connect(dest)
    try:
        dest_conn.executescript(
            "CREATE TABLE live_accounts (id INTEGER PRIMARY KEY, name TEXT UNIQUE, "
            "mode TEXT, initial_capital REAL, cash REAL, investment_robot TEXT, "
            "withdrawal_robot TEXT, withdrawn_total REAL DEFAULT 0, "
            "external_cash REAL DEFAULT 0, policy_state TEXT DEFAULT '{}', "
            "created_at TEXT, updated_at TEXT);"
        )
        dest_conn.execute(
            "INSERT INTO live_accounts (id, name, mode, initial_capital, cash) "
            "VALUES (99, 'ja_existe', 'paper', 1000.0, 1000.0)"
        )
        dest_conn.commit()
    finally:
        dest_conn.close()

    result = migrate(source=source, dest=dest, force=True)
    assert result["live_accounts"] == 1  # a conta "principal" da origem entrou

    conn = sqlite3.connect(dest)
    try:
        count = conn.execute("SELECT COUNT(*) FROM live_accounts").fetchone()[0]
        assert count == 2  # a pré-existente + a migrada, nenhuma sobrescrita
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert user_version == 1
    finally:
        conn.close()


def test_migrate_destino_ja_migrado_nao_exige_force(tmp_path):
    """`user_version >= 1` (já migrado antes) segue copiando normalmente,
    mesmo com `live_accounts` não vazia -- sem precisar de --force."""
    source = tmp_path / "journal.sqlite"
    dest = tmp_path / "live.sqlite"
    _seed(source)

    # 1a migração de verdade: marca user_version = 1.
    migrate(source=source, dest=dest)

    # 2a chamada, sem --force: já está migrado (user_version == 1), então a
    # checagem de "povoado sem marcador" nem se aplica.
    result = migrate(source=source, dest=dest)
    assert all(v == 0 for v in result.values())  # idempotente, nada novo


# ---------------------------------------------------------------------------
# relatório de divergência de contagem (correção pós-code-review, F1/A5/A6)
# ---------------------------------------------------------------------------

def test_migrate_reporta_divergencia_e_levanta_incompleto(tmp_path, capsys):
    """Origem simula um schema mais antigo (sem o CHECK de `mode` que a
    tabela `live_accounts` de verdade aplica -- ver schema.sql) contendo uma
    linha com `mode` inválido. `INSERT OR IGNORE` descarta essa linha em
    silêncio contra o destino (schema atual, mais estrito) -- em vez de
    silêncio, o script tem que AVISAR por tabela e sinalizar (via exceção,
    depois de já ter commitado o resto) que a migração ficou incompleta."""
    source = tmp_path / "journal.sqlite"
    dest = tmp_path / "live.sqlite"

    source_conn = sqlite3.connect(source)
    try:
        source_conn.executescript(
            "CREATE TABLE live_accounts (id INTEGER PRIMARY KEY, name TEXT UNIQUE, "
            "mode TEXT, initial_capital REAL, cash REAL, "
            "investment_robot TEXT DEFAULT '', withdrawal_robot TEXT DEFAULT '', "
            "withdrawn_total REAL DEFAULT 0, external_cash REAL DEFAULT 0, "
            "policy_state TEXT DEFAULT '{}', "
            "created_at TEXT DEFAULT (datetime('now')), "
            "updated_at TEXT DEFAULT (datetime('now')));"
        )
        source_conn.execute(
            "INSERT INTO live_accounts (id, name, mode, initial_capital, cash) "
            "VALUES (1, 'principal', 'paper', 1000.0, 1000.0)"
        )
        # dest exige mode IN ('paper','manual','broker') -- este valor só
        # existia porque a origem é de ANTES do CHECK ter sido acrescentado.
        source_conn.execute(
            "INSERT INTO live_accounts (id, name, mode, initial_capital, cash) "
            "VALUES (2, 'legado', 'modo_invalido_pre_check', 500.0, 500.0)"
        )
        source_conn.commit()
    finally:
        source_conn.close()

    with pytest.raises(MigrationIncomplete) as exc_info:
        migrate(source=source, dest=dest)

    assert exc_info.value.result["live_accounts"] == 1  # só a linha válida entrou
    assert exc_info.value.mismatches == [("live_accounts", 2, 1)]

    captured = capsys.readouterr()
    assert "AVISO" in captured.out
    assert "live_accounts" in captured.out

    # o que já estava certo continua commitado -- não é rollback.
    conn = sqlite3.connect(dest)
    try:
        rows = conn.execute("SELECT name FROM live_accounts").fetchall()
        assert [r[0] for r in rows] == ["principal"]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# guarda do simulador acelerado (P5)
# ---------------------------------------------------------------------------

def test_run_live_sim_recusa_apagar_banco_real():
    with pytest.raises(SystemExit):
        _ensure_disposable_sim_db(LIVE_DB_PATH)
    with pytest.raises(SystemExit):
        _ensure_disposable_sim_db(DB_PATH)
    # o próprio banco de simulação não é recusado.
    _ensure_disposable_sim_db(SIM_DB)
