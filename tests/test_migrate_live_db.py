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

from migrate_live_db import migrate  # type: ignore[import-not-found]
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


def test_migrate_origem_inexistente_devolve_vazio(tmp_path):
    source = tmp_path / "nao_existe.sqlite"
    dest = tmp_path / "dest.sqlite"
    assert migrate(source=source, dest=dest) == {}


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
