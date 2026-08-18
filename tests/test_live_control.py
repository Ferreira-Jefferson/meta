"""Testes de `dashboard/live_control.py` — prova de vida do processo (1.6) e
o parametro novo `mt5_shares_per_lot` (1.7, fim do `1.0` hardcoded).

Isolamento: `_STATE_PATH`/`_LOG_PATH` monkeypatchados para `tmp_path` (nunca
`db/live_process.json`/`db/live_process.log` reais); `_STARTUP_GRACE_SECONDS`
monkeypatchado para 0 (o teste nao pode esperar de verdade); `live.runtime.
DB_PATH` monkeypatchado para o diario de `create_account()` nunca tocar
`db/live.sqlite` real.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dashboard import live_control
from live import runtime as live_runtime


class _FakeProc:
    def __init__(self, pid: int, poll_value):
        self.pid = pid
        self._poll_value = poll_value

    def poll(self):
        return self._poll_value


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    state_path = tmp_path / "live_process.json"
    log_path = tmp_path / "live_process.log"
    db_path = tmp_path / "live_control_test.sqlite"
    monkeypatch.setattr(live_control, "_STATE_PATH", state_path)
    monkeypatch.setattr(live_control, "_LOG_PATH", log_path)
    monkeypatch.setattr(live_control, "_STARTUP_GRACE_SECONDS", 0)
    monkeypatch.setattr(live_runtime, "DB_PATH", db_path)
    return {"state": state_path, "log": log_path, "db": db_path}


def _fake_popen(poll_value, captured_argv, log_message: str = ""):
    def _popen(argv, **kwargs):
        captured_argv.append(argv)
        stdout = kwargs.get("stdout")
        if log_message and stdout is not None:
            stdout.write(log_message)
            stdout.flush()
        return _FakeProc(pid=99999, poll_value=poll_value)
    return _popen


def test_start_processo_morre_na_hora_levanta_runtimeerror_sem_gravar_estado(isolated, monkeypatch):
    captured: list = []
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        _fake_popen(poll_value=1, captured_argv=captured,
                   log_message="[erro fake] terminal MT5 nao encontrado"),
    )

    cfg = live_control.ProcessConfig(mode="manual", capital=1_000.0)
    with pytest.raises(RuntimeError) as exc_info:
        live_control.start(cfg)

    assert "terminal MT5 nao encontrado" in str(exc_info.value)
    assert live_control._read_state() is None


def test_start_processo_sobrevive_grava_pid(isolated, monkeypatch):
    captured: list = []
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        _fake_popen(poll_value=None, captured_argv=captured),
    )

    cfg = live_control.ProcessConfig(mode="manual", capital=1_000.0)
    state = live_control.start(cfg)

    assert state["pid"] == 99999
    saved = live_control._read_state()
    assert saved is not None
    assert saved["pid"] == 99999


def test_start_mt5_sem_shares_per_lot_recusa_antes_do_popen(isolated, monkeypatch):
    called = []
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        lambda *a, **k: called.append((a, k)) or _FakeProc(pid=1, poll_value=None),
    )

    cfg = live_control.ProcessConfig(mode="mt5", capital=1_000.0, mt5_shares_per_lot=None)
    with pytest.raises(RuntimeError):
        live_control.start(cfg)

    assert called == []  # Popen nunca chamado


def test_start_mt5_inclui_shares_per_lot_no_argv(isolated, monkeypatch):
    captured: list = []
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        _fake_popen(poll_value=None, captured_argv=captured),
    )

    cfg = live_control.ProcessConfig(mode="mt5", capital=1_000.0, mt5_shares_per_lot=2.0)
    live_control.start(cfg)

    assert len(captured) == 1
    argv = captured[0]
    assert "--mt5-shares-per-lot" in argv
    idx = argv.index("--mt5-shares-per-lot")
    assert argv[idx + 1] == "2.0"
