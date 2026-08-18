from __future__ import annotations

from datetime import date, datetime

import pytest

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
from journal.live_store import (
    delete_position,
    ensure_account,
    ensure_tables,
    equity_series,
    load_account,
    load_positions,
    log_event,
    live_journal,
    open_orders,
    pending_intents,
    record_equity,
    record_fill,
    record_deposit,
    record_intent,
    record_order,
    record_withdrawal,
    recent_events,
    save_account,
    set_intent_status,
    stale_intents,
    update_order,
    upsert_position,
    withdrawals,
)


@pytest.fixture
def db_path(tmp_path):
    # Banco totalmente isolado — nunca toca em db/journal.sqlite.
    return tmp_path / "live_journal.sqlite"


def _account(conn) -> AccountState:
    return ensure_account(
        conn,
        name="conta_teste",
        mode="paper",
        initial_capital=10_000.0,
        investment_robot="dip2_hw40",
        withdrawal_robot="official_policy",
    )


# ---------------------------------------------------------------------------
# conta
# ---------------------------------------------------------------------------

def test_ensure_account_idempotente(db_path):
    with live_journal(db_path) as conn:
        a1 = _account(conn)
        a2 = _account(conn)
        assert a1.id == a2.id
        count = conn.execute("SELECT COUNT(*) AS c FROM live_accounts").fetchone()["c"]
        assert count == 1


def test_save_account_persiste_cash_e_policy_state(db_path):
    with live_journal(db_path) as conn:
        account = _account(conn)
        account.cash = 8_500.0
        account.withdrawn_total = 500.0
        account.external_cash = 500.0
        account.policy_state = {"month_paid": "2026-08", "floor": 55_000.0}
        save_account(conn, account)

    with live_journal(db_path) as conn:
        reloaded = load_account(conn, "conta_teste")
        assert reloaded is not None
        assert reloaded.cash == 8_500.0
        assert reloaded.withdrawn_total == 500.0
        assert reloaded.external_cash == 500.0
        assert reloaded.policy_state == {"month_paid": "2026-08", "floor": 55_000.0}


# ---------------------------------------------------------------------------
# posições
# ---------------------------------------------------------------------------

def _position(ticker="WEGE3.SA", kind="main") -> LivePosition:
    return LivePosition(
        ticker=ticker,
        quantity=100,
        entry_date=date(2026, 8, 10),
        entry_price=40.0,
        capital_allocated=4_000.0,
        current_stop=36.0,
        fees_paid=1.2,
        slippage_paid=0.5,
        max_price_seen=41.0,
        min_price_seen=39.5,
        bars_held=3,
        kind=kind,
        metadata={"entry_reason": "dip_confirmed", "atr14": 1.8},
    )


def test_upsert_load_update_delete_position(db_path):
    with live_journal(db_path) as conn:
        account = _account(conn)
        pos = _position()
        pos_id = upsert_position(conn, account.id, pos)
        assert pos_id == pos.id

        loaded = load_positions(conn, account.id)
        assert set(loaded.keys()) == {"WEGE3.SA"}
        stored = loaded["WEGE3.SA"]
        assert stored.quantity == 100
        assert stored.current_stop == 36.0
        assert stored.metadata == {"entry_reason": "dip_confirmed", "atr14": 1.8}
        assert stored.kind == "main"

        # update: mesma chave (account_id, ticker, kind) -> UPSERT, não duplica.
        pos.quantity = 150
        pos.current_stop = 37.5
        upsert_position(conn, account.id, pos)
        loaded2 = load_positions(conn, account.id)
        assert len(loaded2) == 1
        assert loaded2["WEGE3.SA"].quantity == 150
        assert loaded2["WEGE3.SA"].current_stop == 37.5

        delete_position(conn, account.id, "WEGE3.SA", kind="main")
        assert load_positions(conn, account.id) == {}


def test_position_main_e_satellite_coexistem_na_tabela(db_path):
    with live_journal(db_path) as conn:
        account = _account(conn)
        upsert_position(conn, account.id, _position(ticker="RADL3.SA", kind="main"))
        upsert_position(conn, account.id, _position(ticker="RADL3.SA", kind="satellite"))
        rows = conn.execute(
            "SELECT kind FROM live_positions WHERE account_id = ? AND ticker = ? ORDER BY kind",
            (account.id, "RADL3.SA"),
        ).fetchall()
        assert [r["kind"] for r in rows] == ["main", "satellite"]


# ---------------------------------------------------------------------------
# intents
# ---------------------------------------------------------------------------

def _intent(decided_on, execute_on, kind=IntentKind.ENTER, reason="dip_confirmed", ticker="WEGE3.SA") -> Intent:
    return Intent(
        robot="dip2_hw40",
        role=RobotRole.INVESTMENT,
        kind=kind,
        decided_on=decided_on,
        execute_on=execute_on,
        ticker=ticker,
        reason=reason,
        size_hint=0.2,
        payload={"signal_strength": 0.7},
    )


def test_record_intent_rejeita_look_ahead(db_path):
    with live_journal(db_path) as conn:
        account = _account(conn)
        d = date(2026, 8, 14)
        bad = _intent(decided_on=d, execute_on=d)  # execute_on == decided_on -> proibido
        with pytest.raises(ValueError):
            record_intent(conn, account.id, bad)

        bad2 = _intent(decided_on=d, execute_on=date(2026, 8, 13))  # execute_on < decided_on
        with pytest.raises(ValueError):
            record_intent(conn, account.id, bad2)


def test_record_intent_aceita_excecoes_de_is_immediate(db_path):
    with live_journal(db_path) as conn:
        account = _account(conn)
        d = date(2026, 8, 14)

        adjust = _intent(decided_on=d, execute_on=d, kind=IntentKind.ADJUST_STOP, reason="trailing")
        adjust_id = record_intent(conn, account.id, adjust)
        assert adjust_id == adjust.id

        stop_exit = _intent(decided_on=d, execute_on=d, kind=IntentKind.EXIT, reason="stop")
        stop_id = record_intent(conn, account.id, stop_exit)
        assert stop_id == stop_exit.id


def test_pending_and_stale_intents_e_transicao_status(db_path):
    with live_journal(db_path) as conn:
        account = _account(conn)
        decided = date(2026, 8, 13)
        today = date(2026, 8, 14)
        tomorrow = date(2026, 8, 15)

        i_today = _intent(decided_on=decided, execute_on=today, ticker="WEGE3.SA")
        record_intent(conn, account.id, i_today)

        i_future = _intent(decided_on=today, execute_on=tomorrow, ticker="RADL3.SA")
        record_intent(conn, account.id, i_future)

        due = pending_intents(conn, account.id, today)
        assert [i.ticker for i in due] == ["WEGE3.SA"]

        set_intent_status(conn, i_today.id, IntentStatus.DONE)
        assert pending_intents(conn, account.id, today) == []

        stale = stale_intents(conn, account.id, before=tomorrow)
        # i_future ainda está pendente com execute_on == tomorrow, não é < tomorrow.
        assert stale == []

        stale2 = stale_intents(conn, account.id, before=date(2026, 8, 16))
        assert [i.ticker for i in stale2] == ["RADL3.SA"]


# ---------------------------------------------------------------------------
# ordens e fills
# ---------------------------------------------------------------------------

def test_order_and_fills_and_open_orders(db_path):
    with live_journal(db_path) as conn:
        account = _account(conn)
        order = Order(
            ticker="WEGE3.SA",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.ON_OPEN,
            status=OrderStatus.SENT,
            sent_at=datetime(2026, 8, 14, 10, 5),
        )
        order_id = record_order(conn, account.id, order)
        assert order_id == order.id

        assert [o.ticker for o in open_orders(conn, account.id)] == ["WEGE3.SA"]

        fill = Fill(order_id=order_id, quantity=100, price=40.10, fees=1.2, ts=datetime(2026, 8, 14, 10, 6))
        fill_id = record_fill(conn, fill)
        assert fill_id > 0

        order.status = OrderStatus.FILLED
        order.filled_qty = 100
        order.avg_price = 40.10
        update_order(conn, order)

        assert open_orders(conn, account.id) == []

        row = conn.execute("SELECT * FROM live_orders WHERE id = ?", (order_id,)).fetchone()
        assert row["status"] == "filled"
        assert row["filled_qty"] == 100


# ---------------------------------------------------------------------------
# equity e saques
# ---------------------------------------------------------------------------

def test_record_equity_upsert_e_patrimonio(db_path):
    with live_journal(db_path) as conn:
        account = _account(conn)
        day = date(2026, 8, 14)
        record_equity(conn, account.id, day, cash=1_000.0, invested=9_000.0, equity=10_000.0, external_cash=500.0)
        # segunda chamada na mesma data -> upsert, não duplica linha.
        record_equity(conn, account.id, day, cash=800.0, invested=9_200.0, equity=10_000.0, external_cash=500.0)

        series = equity_series(conn, account.id)
        assert len(series) == 1
        d, equity, patrimonio = series[0]
        assert d == day.isoformat()
        assert equity == 10_000.0
        assert patrimonio == equity + 500.0


def test_record_withdrawal_and_events(db_path):
    with live_journal(db_path) as conn:
        account = _account(conn)
        w_id = record_withdrawal(
            conn,
            account.id,
            day=date(2026, 8, 14),
            requested=1_000.0,
            executed=1_000.0,
            equity_before=100_000.0,
            fees_paid=3.5,
            liquidated={"WEGE3.SA": 10},
        )
        assert w_id > 0

        rows = withdrawals(conn, account.id)
        assert len(rows) == 1
        assert rows[0]["liquidated"] == {"WEGE3.SA": 10}
        assert rows[0]["requested"] == 1_000.0

        log_event(conn, account.id, "info", "withdrawal_robot", "saque executado", {"amount": 1_000.0})
        log_event(conn, account.id, "warn", "feed", "dado atrasado", None)

        events = recent_events(conn, account.id)
        assert len(events) == 2
        assert events[0]["level"] in {"info", "warn"}
        sources = {e["source"] for e in events}
        assert sources == {"withdrawal_robot", "feed"}


def test_record_deposit(db_path):
    with live_journal(db_path) as conn:
        account = _account(conn)
        d_id = record_deposit(
            conn, account.id, day=date(2026, 8, 18), amount=500.0,
            origin="mt5_reconciliation", note="saldo real 10500.00 vs caixa esperado 10000.00",
        )
        assert d_id > 0

        rows = conn.execute(
            "SELECT * FROM live_deposits WHERE account_id = ?", (account.id,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["amount"] == 500.0
        assert rows[0]["origin"] == "mt5_reconciliation"
        assert rows[0]["date"] == "2026-08-18"

        # `note` default vazio quando nao informado (botao manual nao precisa dele).
        record_deposit(conn, account.id, day=date(2026, 8, 19), amount=100.0, origin="manual")
        rows2 = conn.execute(
            "SELECT * FROM live_deposits WHERE account_id = ? ORDER BY id", (account.id,)
        ).fetchall()
        assert rows2[1]["note"] == ""


# ---------------------------------------------------------------------------
# auto-suficiência do store
# ---------------------------------------------------------------------------

def test_ensure_tables_em_banco_vazio(tmp_path):
    """Um banco criado do zero (sem passar por init_db) tem de ganhar as
    tabelas live_* só por conectar — é a garantia de auto-suficiência do
    store, já que db/journal.sqlite pode já existir sem essas tabelas."""
    import sqlite3

    raw_db = tmp_path / "raw.sqlite"
    conn = sqlite3.connect(raw_db)
    conn.row_factory = sqlite3.Row
    try:
        tables_before = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "live_accounts" not in tables_before

        ensure_tables(conn)

        tables_after = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        expected = {
            "live_accounts", "live_positions", "live_intents", "live_orders",
            "live_fills", "live_equity", "live_withdrawals", "live_events",
        }
        assert expected.issubset(tables_after)

        # tabelas de backtest não foram criadas por engano — ensure_tables é
        # filtrado para as tabelas live_* apenas.
        assert "runs" not in tables_after
        assert "trades" not in tables_after
    finally:
        conn.close()
