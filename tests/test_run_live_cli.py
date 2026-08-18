"""Testes da linha de comando (`scripts/run_live.py`) — dispatch de `build()`
(1.2) e recusa de `tickets`/`confirm` sobre conta cujo modo real nao e
`manual` (1.5).

Isolamento obrigatorio do banco (FEAT-001, ACTION-PLAN secao 2): `build()`
monta `LiveRuntime` com `db_path=None` (cai no default de modulo) e
`_require_manual_account()`/`cmd_tickets`/`cmd_confirm` abrem
`store.live_journal()` SEM argumento — sem isolar, este arquivo escreveria no
`db/live.sqlite` REAL. Usa as duas mesmas tecnicas de
`tests/test_dashboard_app.py` (docstring do modulo, linhas 9-26):
`monkeypatch.setattr(live_store.live_journal.__wrapped__, "__defaults__", (tmp_db,))`
e `monkeypatch.setattr(live_runtime, "DB_PATH", tmp_db)`.

Carrega `scripts/run_live.py` pelo MESMO truque de `importlib` que
`dashboard.live_control._load_cli()` ja usa (`scripts/` nao e pacote e nao
esta no pythonpath do projeto).
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest

from journal import live_store
from live import runtime as live_runtime

_RUN_LIVE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_live.py"


def _load_run_live_cli():
    spec = importlib.util.spec_from_file_location("run_live_cli_test", _RUN_LIVE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli():
    return _load_run_live_cli()


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Redireciona `store.live_journal()` (sem argumento) e o default de
    `LiveRuntime.db_path` para um banco isolado em `tmp_path`."""
    db_path = tmp_path / "live_cli_test.sqlite"
    monkeypatch.setattr(live_store.live_journal.__wrapped__, "__defaults__", (db_path,))
    monkeypatch.setattr(live_runtime, "DB_PATH", db_path)
    return db_path


def _args(**overrides) -> argparse.Namespace:
    base = dict(
        feed="parquet", mode="manual", capital=1_000.0, floor=None,
        notify_min_level="warn", daily_loss_limit=None, monthly_loss_limit=None,
        mt5_magic=20260817, mt5_shares_per_lot=None, mt5_symbol_map=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


# ---------- dispatch de build() (1.2) ---------------------------------------

def test_build_modo_desconhecido_levanta_valueerror(cli, isolated_db):
    with pytest.raises(ValueError):
        cli.build(_args(mode="broker"))


def test_build_modo_ausente_levanta_valueerror(cli, isolated_db):
    with pytest.raises(ValueError):
        cli.build(_args(mode=None))


def test_build_mt5_sem_shares_per_lot_levanta_valueerror(cli, isolated_db):
    with pytest.raises(ValueError):
        cli.build(_args(mode="mt5", mt5_shares_per_lot=None))


def test_build_manual_monta_manual_broker(cli, isolated_db):
    rt = cli.build(_args(mode="manual"))
    assert rt.broker.mode == "manual"


def test_build_mt5_com_shares_per_lot_monta_mt5_broker(cli, isolated_db):
    rt = cli.build(_args(mode="mt5", mt5_shares_per_lot=1.0))
    assert rt.broker.mode == "mt5"


# ---------- recusa de tickets/confirm sobre conta nao-manual (1.5) ----------

def _create_account(cli, isolated_db, mode: str) -> None:
    rt = cli.build(_args(mode=mode, mt5_shares_per_lot=1.0 if mode == "mt5" else None,
                         capital=1_000.0))
    rt.ensure_account()


def test_cmd_tickets_recusa_conta_nao_manual(cli, isolated_db, capsys):
    _create_account(cli, isolated_db, mode="mt5")
    args = _args(mode="mt5")

    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_tickets(args)
    assert "mt5" in str(exc_info.value)

    with live_store.live_journal(isolated_db) as conn:
        acc = live_store.load_account(conn, cli.ACCOUNT)
        abertas = live_store.open_orders(conn, acc.id)
    assert abertas == []


def test_cmd_confirm_recusa_conta_nao_manual(cli, isolated_db):
    _create_account(cli, isolated_db, mode="mt5")
    args = _args(mode="mt5", order_id=1, quantity=100, price=40.0, fees=0.0)

    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_confirm(args)
    assert "mt5" in str(exc_info.value)

    with live_store.live_journal(isolated_db) as conn:
        acc = live_store.load_account(conn, cli.ACCOUNT)
        abertas = live_store.open_orders(conn, acc.id)
    assert abertas == []
