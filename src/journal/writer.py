"""Escritor do diário. Único caminho para persistir trades/snapshots."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Iterator

from core.config import DB_PATH, SCHEMA_PATH
from core.models import MarketSnapshot, Trade


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    _migrate(conn)
    return conn


# Colunas adicionadas depois da criação inicial do schema. Migração idempotente:
# roda a cada conexão, mas só executa ALTER TABLE se a coluna ainda não existe —
# preserva as runs já gravadas (AGENTS.md: "não descarte dado").
_RUNS_MIGRATIONS: list[tuple[str, str]] = [
    ("neg_years", "ALTER TABLE runs ADD COLUMN neg_years INTEGER"),
    ("run_kind", "ALTER TABLE runs ADD COLUMN run_kind TEXT NOT NULL DEFAULT 'ad_hoc'"),
    ("data_fingerprint", "ALTER TABLE runs ADD COLUMN data_fingerprint TEXT"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    has_runs = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='runs'"
    ).fetchone()
    if not has_runs:
        return  # tabela ainda não existe — init_db() vai criá-la já com as colunas atuais
    existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    for col, ddl in _RUNS_MIGRATIONS:
        if col not in existing:
            conn.execute(ddl)
    conn.commit()


def init_db(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> None:
    with _connect(db_path) as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.commit()


@contextmanager
def journal(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = _connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_run(
    conn: sqlite3.Connection,
    strategy_name: str,
    strategy_version: str,
    period_start: str,
    period_end: str,
    initial_capital: float,
    run_kind: str = "ad_hoc",
    data_fingerprint: str | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO runs (strategy_name, strategy_version, period_start, period_end,
                             initial_capital, run_kind, data_fingerprint)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (strategy_name, strategy_version, period_start, period_end, initial_capital,
         run_kind, data_fingerprint),
    )
    return int(cur.lastrowid)


def finalize_run(
    conn: sqlite3.Connection,
    run_id: int,
    metrics: dict,
) -> None:
    cols = [
        "final_capital",
        "cagr",
        "sharpe",
        "sortino",
        "max_drawdown",
        "calmar",
        "win_rate",
        "profit_factor",
        "trades_count",
        "benchmark_cagr",
        "neg_years",
    ]
    updates = ", ".join(f"{c} = ?" for c in cols)
    values = [metrics.get(c) for c in cols] + [run_id]
    conn.execute(f"UPDATE runs SET {updates} WHERE id = ?", values)


def _insert_snapshot(
    conn: sqlite3.Connection,
    trade_id: int,
    moment: str,
    snapshot: MarketSnapshot,
) -> None:
    data = asdict(snapshot)
    data["ibov_above_mm200"] = 1 if data["ibov_above_mm200"] else 0
    cols = ["trade_id", "moment"] + list(data.keys())
    placeholders = ",".join("?" for _ in cols)
    conn.execute(
        f"INSERT INTO signal_snapshots ({','.join(cols)}) VALUES ({placeholders})",
        [trade_id, moment] + list(data.values()),
    )


def insert_trade(conn: sqlite3.Connection, run_id: int, trade: Trade) -> int:
    cur = conn.execute(
        """INSERT INTO trades
            (run_id, ticker, strategy_name, strategy_version,
             entry_date, entry_price, quantity, capital_allocated,
             exit_date, exit_price, exit_reason, holding_days,
             fees_total, slippage_total, pnl_brl, pnl_pct, r_multiple,
             max_favorable_excursion, max_adverse_excursion, status)
           VALUES (?, ?, ?, ?,  ?, ?, ?, ?,  ?, ?, ?, ?,  ?, ?, ?, ?, ?,  ?, ?, ?)""",
        (
            run_id,
            trade.ticker,
            trade.strategy_name,
            trade.strategy_version,
            trade.entry_date.isoformat(),
            trade.entry_price,
            trade.quantity,
            trade.capital_allocated,
            trade.exit_date.isoformat() if trade.exit_date else None,
            trade.exit_price,
            trade.exit_reason.value,
            trade.holding_days if not trade.is_open else None,
            trade.fees_total,
            trade.slippage_total,
            trade.pnl_brl if not trade.is_open else None,
            trade.pnl_pct if not trade.is_open else None,
            trade.r_multiple if not trade.is_open else None,
            trade.max_favorable_excursion,
            trade.max_adverse_excursion,
            "closed" if not trade.is_open else "open",
        ),
    )
    trade_id = int(cur.lastrowid)

    if trade.entry_snapshot is not None:
        _insert_snapshot(conn, trade_id, "entry", trade.entry_snapshot)
    if trade.exit_snapshot is not None:
        _insert_snapshot(conn, trade_id, "exit", trade.exit_snapshot)

    for tag_type, tag_value in trade.tags.items():
        conn.execute(
            "INSERT INTO notes (trade_id, tag_type, tag_value) VALUES (?, ?, ?)",
            (trade_id, tag_type, tag_value),
        )
    return trade_id


def append_equity(conn: sqlite3.Connection, run_id: int, points: list[tuple[str, float, float | None]]) -> None:
    conn.executemany(
        "INSERT INTO equity_curve (run_id, date, equity, benchmark) VALUES (?, ?, ?, ?)",
        [(run_id, d, e, b) for (d, e, b) in points],
    )
