from __future__ import annotations

from datetime import date

from core.live_models import Intent, IntentKind, IntentStatus, RobotRole
from journal.live_store import (
    all_intents,
    ensure_account,
    live_journal,
    record_intent,
    set_intent_status,
)


def _account(conn):
    return ensure_account(
        conn,
        name="conta_teste",
        mode="manual",
        initial_capital=10_000.0,
        investment_robot="dip2_hw40",
        withdrawal_robot="official_policy",
    )


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
        amount=None,
        payload={"signal_strength": 0.7},
    )


def test_all_intents_mais_recente_primeiro(tmp_path):
    db_path = tmp_path / "live_journal.sqlite"
    with live_journal(db_path) as conn:
        account = _account(conn)
        d1 = date(2026, 8, 10)
        d2 = date(2026, 8, 11)
        d3 = date(2026, 8, 12)

        i1 = _intent(decided_on=d1, execute_on=d2, ticker="WEGE3.SA")
        record_intent(conn, account.id, i1)

        i2 = _intent(decided_on=d2, execute_on=d3, kind=IntentKind.EXIT, reason="ma_cross", ticker="RADL3.SA")
        record_intent(conn, account.id, i2)

        i3 = _intent(decided_on=d3, execute_on=d3, kind=IntentKind.ADJUST_STOP, reason="trailing", ticker="VALE3.SA")
        record_intent(conn, account.id, i3)

        set_intent_status(conn, i2.id, IntentStatus.DONE)

        result = all_intents(conn, account.id)

        # mais recente primeiro (id DESC): i3, i2, i1.
        assert [i.ticker for i in result] == ["VALE3.SA", "RADL3.SA", "WEGE3.SA"]

        # campos voltam como os tipos Python certos (enum, não string crua).
        first = result[0]
        assert first.kind is IntentKind.ADJUST_STOP
        assert isinstance(first.kind, IntentKind)
        assert first.role is RobotRole.INVESTMENT
        assert isinstance(first.status, IntentStatus)
        assert first.status is IntentStatus.PENDING
        assert first.decided_on == d3
        assert first.execute_on == d3
        assert first.reason == "trailing"

        # status atualizado é refletido na leitura.
        second = result[1]
        assert second.ticker == "RADL3.SA"
        assert second.status is IntentStatus.DONE


def test_all_intents_respeita_limit(tmp_path):
    db_path = tmp_path / "live_journal.sqlite"
    with live_journal(db_path) as conn:
        account = _account(conn)
        base = date(2026, 8, 1)
        for offset in range(5):
            decided = date(2026, 8, 1 + offset)
            execute = date(2026, 8, 2 + offset)
            record_intent(conn, account.id, _intent(decided_on=decided, execute_on=execute, ticker="WEGE3.SA"))

        result = all_intents(conn, account.id, limit=2)
        assert len(result) == 2
        # os dois mais recentes: decided_on 08-05 e 08-04.
        assert result[0].decided_on == date(2026, 8, 5)
        assert result[1].decided_on == date(2026, 8, 4)


def test_all_intents_vazio_sem_registro(tmp_path):
    db_path = tmp_path / "live_journal.sqlite"
    with live_journal(db_path) as conn:
        account = _account(conn)
        assert all_intents(conn, account.id) == []
