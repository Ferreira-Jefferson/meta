from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.models import ExitReason, MarketSnapshot, Trade
from journal import reader
from journal.writer import (
    append_equity,
    create_run,
    finalize_run,
    init_db,
    insert_trade,
    journal,
)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "journal.sqlite"
    schema_path = Path(__file__).resolve().parents[1] / "src" / "journal" / "schema.sql"
    # monkey-patch config paths so writer/reader hit the temp db.
    from core import config as core_config
    monkeypatch.setattr(core_config, "DB_PATH", db_path)
    monkeypatch.setattr(core_config, "SCHEMA_PATH", schema_path)
    from journal import writer as _w, reader as _r
    monkeypatch.setattr(_w, "DB_PATH", db_path)
    monkeypatch.setattr(_w, "SCHEMA_PATH", schema_path)
    monkeypatch.setattr(_r, "DB_PATH", db_path)
    init_db(db_path=db_path, schema_path=schema_path)
    return db_path


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        close=100.0, volume=1_000_000, volume_vs_avg20=1.2,
        mm20=99, mm50=95, mm200=90, mm50_over_mm200_pct=0.055,
        days_since_cross=3, ifr14=55.0, atr14=1.5, historical_vol_30d=0.25,
        distance_from_52w_high_pct=-0.05, distance_from_52w_low_pct=0.30,
        ibov_close=120_000, ibov_mm200=110_000, ibov_above_mm200=True,
        ibov_trend_strength=0.09, correlation_with_ibov_60d=0.62,
    )


def _sample_trade() -> Trade:
    return Trade(
        ticker="PETR4.SA",
        strategy_name="baseline_ma_cross",
        strategy_version="1.0",
        entry_date=date(2024, 1, 3),
        entry_price=30.0,
        quantity=100,
        capital_allocated=3_000.0,
        exit_date=date(2024, 3, 15),
        exit_price=33.0,
        exit_reason=ExitReason.CROSS_DOWN,
        fees_total=1.80,
        slippage_total=4.50,
        max_favorable_excursion=0.12,
        max_adverse_excursion=-0.03,
        entry_snapshot=_snapshot(),
        exit_snapshot=_snapshot(),
        tags={"signal_quality": "textbook", "outcome": "winner"},
    )


def test_full_write_read_cycle(tmp_db):
    with journal(db_path=tmp_db) as conn:
        run_id = create_run(conn, "baseline_ma_cross", "1.0", "2024-01-01", "2024-06-30", 100_000.0)
        trade_id = insert_trade(conn, run_id, _sample_trade())
        append_equity(conn, run_id, [("2024-01-03", 100_000.0, 100_000.0),
                                     ("2024-03-15", 105_000.0, 102_000.0)])
        finalize_run(conn, run_id, {
            "final_capital": 105_000.0, "cagr": 0.10, "sharpe": 1.2, "sortino": 1.4,
            "max_drawdown": -0.05, "calmar": 2.0, "win_rate": 1.0, "profit_factor": 5.0,
            "trades_count": 1, "benchmark_cagr": 0.04,
        })

    runs = reader.list_runs(db_path=tmp_db)
    assert len(runs) == 1
    assert runs[0]["trades_count"] == 1

    trades = reader.list_trades(runs[0]["id"], db_path=tmp_db)
    assert len(trades) == 1
    assert trades[0]["ticker"] == "PETR4.SA"
    assert trades[0]["exit_reason"] == "cross_down"

    snaps = reader.trade_snapshots(trade_id, db_path=tmp_db)
    assert "entry" in snaps and "exit" in snaps
    assert snaps["entry"]["ibov_above_mm200"] == 1

    tags = reader.trade_tags(trade_id, db_path=tmp_db)
    assert {t["tag_type"] for t in tags} == {"signal_quality", "outcome"}

    curve = reader.equity_curve(runs[0]["id"], db_path=tmp_db)
    assert len(curve) == 2
