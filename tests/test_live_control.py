"""Testes de `dashboard/live_control.py` — prova de vida do processo (1.6) e
o parametro novo `mt5_shares_per_lot` (1.7, fim do `1.0` hardcoded).

Isolamento: `_STATE_PATH`/`_LOG_PATH` monkeypatchados para `tmp_path` (nunca
`db/live_process.json`/`db/live_process.log` reais); `_STARTUP_GRACE_SECONDS`
monkeypatchado para 0 (o teste nao pode esperar de verdade); `live.runtime.
DB_PATH` monkeypatchado para o diario de `create_account()` nunca tocar
`db/live.sqlite` real.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
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

    cfg = live_control.ProcessConfig(mode="mt5", capital=1_000.0, strategy="portfolio_dip2_hw40", mt5_shares_per_lot=1.0)
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

    cfg = live_control.ProcessConfig(mode="mt5", capital=1_000.0, strategy="portfolio_dip2_hw40", mt5_shares_per_lot=1.0)
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

    cfg = live_control.ProcessConfig(mode="mt5", capital=1_000.0, strategy="portfolio_dip2_hw40", mt5_shares_per_lot=None)
    with pytest.raises(RuntimeError):
        live_control.start(cfg)

    assert called == []  # Popen nunca chamado


def test_start_mt5_com_shares_per_lot_zero_ou_negativo_recusa_antes_do_popen(isolated, monkeypatch):
    """Item 2 da correção pós-code-review (hipótese-agente): a checagem
    antiga só olhava `is None` -- um valor `0` ou negativo passava direto e
    causaria `ZeroDivisionError` em `MT5Broker._to_volume` na hora de mandar
    ordem real (`volume = quantity / shares_per_lot`)."""
    called = []
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        lambda *a, **k: called.append((a, k)) or _FakeProc(pid=1, poll_value=None),
    )

    for valor in (0, -1.0):
        cfg = live_control.ProcessConfig(mode="mt5", capital=1_000.0, strategy="portfolio_dip2_hw40", mt5_shares_per_lot=valor)
        with pytest.raises(RuntimeError):
            live_control.start(cfg)

    assert called == []  # Popen nunca chamado


def test_start_mt5_inclui_shares_per_lot_no_argv(isolated, monkeypatch):
    captured: list = []
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        _fake_popen(poll_value=None, captured_argv=captured),
    )

    cfg = live_control.ProcessConfig(mode="mt5", capital=1_000.0, strategy="portfolio_dip2_hw40", mt5_shares_per_lot=2.0)
    live_control.start(cfg)

    assert len(captured) == 1
    argv = captured[0]
    assert "--mt5-shares-per-lot" in argv
    idx = argv.index("--mt5-shares-per-lot")
    assert argv[idx + 1] == "2.0"


# ---------- --strategy sempre no argv, sem robo padrao (2026-08-19) --------

def test_start_inclui_strategy_no_argv(isolated, monkeypatch):
    captured: list = []
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        _fake_popen(poll_value=None, captured_argv=captured),
    )

    cfg = live_control.ProcessConfig(mode="mt5", capital=1_000.0,
                                      strategy="portfolio_dip2_hw40", mt5_shares_per_lot=1.0)
    live_control.start(cfg)

    assert len(captured) == 1
    argv = captured[0]
    assert "--strategy" in argv
    idx = argv.index("--strategy")
    assert argv[idx + 1] == "portfolio_dip2_hw40"


def test_start_sem_strategy_recusa_antes_do_popen(isolated, monkeypatch):
    """Sem robo padrao (regra do dono, 2026-08-19): `strategy` vazio/None tem
    que recusar igual a `mt5_shares_per_lot` ausente -- nunca sobe o processo
    sem saber que robo rodar."""
    called = []
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        lambda *a, **k: called.append((a, k)) or _FakeProc(pid=1, poll_value=None),
    )

    cfg = live_control.ProcessConfig(mode="mt5", capital=1_000.0, strategy="", mt5_shares_per_lot=1.0)
    with pytest.raises(RuntimeError):
        live_control.start(cfg)

    assert called == []  # Popen nunca chamado


def test_start_concorrente_apenas_um_vence_o_outro_ve_ja_rodando(isolated, monkeypatch):
    """Correção pós-code-review (crítico nº2): duas chamadas a `start()`
    quase simultâneas (dois cliques em "Iniciar" processados em threads
    diferentes do `asyncio.to_thread`, já que `run_dashboard.py` é
    single-process) não podem as duas passarem pelo guard `status() is not
    None` antes de qualquer uma gravar estado -- isso subia dois processos
    `run_live.py loop` órfãos com só o segundo PID rastreável.

    Um `Barrier` de 2 partes força as duas threads a chamarem `start()`
    praticamente no mesmo instante -- é a race de verdade (não sequencial).
    O fake `Popen` ainda dorme um pouco antes de retornar, alargando a janela
    em que o processo "sobe" -- se o lock não cobrisse do guard até
    `_write_state`, a segunda thread teria uma chance real de ler
    `status() is None` enquanto a primeira ainda está dentro do `Popen`."""
    captured: list = []
    pid_counter = iter([11111, 22222])
    start_barrier = threading.Barrier(2)

    def _slow_popen(argv, **kwargs):
        time.sleep(0.05)
        captured.append(argv)
        return _FakeProc(pid=next(pid_counter), poll_value=None)

    monkeypatch.setattr(live_control.subprocess, "Popen", _slow_popen)
    # `status()` do vencedor chama `_pid_alive` (que usa `subprocess.run` ->
    # `tasklist`) para a thread perdedora ver "já rodando" -- como o
    # `Popen` acima foi trocado pelo fake (sem suporte a context manager),
    # o `tasklist` real quebraria; simula "processo vivo" direto.
    monkeypatch.setattr(live_control, "_pid_alive", lambda pid: True)

    cfg = live_control.ProcessConfig(mode="mt5", capital=1_000.0, strategy="portfolio_dip2_hw40", mt5_shares_per_lot=1.0)
    results: list = []
    errors: list = []

    def _run():
        start_barrier.wait(timeout=5)  # as duas threads entram em start() juntas
        try:
            results.append(live_control.start(cfg))
        except RuntimeError as e:
            errors.append(e)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_run) for _ in range(2)]
        for f in futures:
            f.result(timeout=10)

    # O lock serializa a seção crítica inteira -- a segunda thread só entra
    # no `Popen` depois que a primeira já escreveu estado, então o barrier
    # de 2 partes nunca deveria ser atingido pelas duas ao mesmo tempo DENTRO
    # da seção crítica. Se o lock não existisse (ou não cobrisse do guard até
    # `_write_state`), as duas passariam pelo guard e ambas chegariam ao
    # barrier -- exatamente o bug original.
    assert len(results) == 1
    assert len(errors) == 1
    assert "já existe um robô rodando" in str(errors[0])

    # Só um processo foi de fato criado.
    assert len(captured) == 1

    saved = live_control._read_state()
    assert saved is not None
    assert saved["pid"] == results[0]["pid"]


# ---------- detect_broker_capital() -- capital nunca digitado (regra do dono, 2026-08-19) --

class _FakeCashBroker:
    """Substitui `live.broker_mt5.MT5Broker` para os testes de
    `detect_broker_capital()` -- captura os kwargs de construção (pra provar
    que vêm das credenciais salvas, não de `os.environ`) e devolve um saldo
    fixo (ou `None`, simulando corretora inacessível)."""

    def __init__(self, cash, captured, **kwargs):
        captured.append(kwargs)
        self._cash = cash

    def cash_balance(self):
        return self._cash


def test_detect_broker_capital_usa_credenciais_salvas_nunca_os_environ(monkeypatch):
    """As credenciais MT5 salvas em db/live_secrets.json (`load_credentials`)
    têm de ir direto pro construtor do broker -- NUNCA via `os.environ` do
    processo do dashboard, que não recebe essas variáveis (só o processo
    FILHO recebe, via `_credentials_env()` dentro de `start()`)."""
    monkeypatch.setattr(live_control, "load_credentials", lambda: {
        "mt5_login": "12345", "mt5_password": "segredo",
        "mt5_server": "Corretora-Live", "mt5_terminal_path": r"C:\mt5\terminal64.exe",
    })
    captured: list = []
    import live.broker_mt5 as broker_mt5
    monkeypatch.setattr(
        broker_mt5, "MT5Broker",
        lambda **kwargs: _FakeCashBroker(7_530.42, captured, **kwargs),
    )

    assert live_control.detect_broker_capital() == pytest.approx(7_530.42)
    assert captured[0]["login"] == 12345
    assert captured[0]["password"] == "segredo"
    assert captured[0]["server"] == "Corretora-Live"


def test_detect_broker_capital_sem_saldo_devolve_none(monkeypatch):
    """Terminal fechado/deslogado, credenciais ausentes, ou qualquer falha:
    `cash_balance()` devolve `None` e `detect_broker_capital()` repassa isso
    -- nunca inventa um valor default."""
    monkeypatch.setattr(live_control, "load_credentials", lambda: {})
    captured: list = []
    import live.broker_mt5 as broker_mt5
    monkeypatch.setattr(
        broker_mt5, "MT5Broker",
        lambda **kwargs: _FakeCashBroker(None, captured, **kwargs),
    )

    assert live_control.detect_broker_capital() is None
    assert captured[0]["login"] is None


# ---------- detect_shares_per_lot() -- não digitado, detectado (regra do dono, 2026-08-20) --

class _FakeLotBroker:
    """Substitui `live.broker_mt5.MT5Broker` para os testes de
    `detect_shares_per_lot()` -- captura os kwargs de construção e os
    tickers pedidos, e devolve um `shares_per_lot` fixo (ou `None`,
    simulando corretora inacessível ou watchlist com contract_size misto)."""

    def __init__(self, value, captured, **kwargs):
        captured.append(kwargs)
        self._value = value

    def detect_shares_per_lot(self, tickers):
        self.tickers = list(tickers)
        return self._value


def test_detect_shares_per_lot_usa_credenciais_salvas_e_watchlist(monkeypatch):
    """Mesma regra de `detect_broker_capital()`: credenciais salvas vão pro
    construtor do broker, nunca via `os.environ`; os tickers consultados são
    os da watchlist oficial (`core.config.WATCHLIST`), não uma lista
    arbitrária."""
    monkeypatch.setattr(live_control, "load_credentials", lambda: {
        "mt5_login": "12345", "mt5_password": "segredo",
        "mt5_server": "Corretora-Live", "mt5_terminal_path": r"C:\mt5\terminal64.exe",
    })
    captured: list = []
    import live.broker_mt5 as broker_mt5
    from core.config import WATCHLIST
    fakes: list = []

    def _factory(**kwargs):
        fake = _FakeLotBroker(1.0, captured, **kwargs)
        fakes.append(fake)
        return fake

    monkeypatch.setattr(broker_mt5, "MT5Broker", _factory)

    assert live_control.detect_shares_per_lot() == pytest.approx(1.0)
    assert captured[0]["login"] == 12345
    assert captured[0]["server"] == "Corretora-Live"
    assert fakes[0].tickers == list(WATCHLIST)


def test_detect_shares_per_lot_sem_valor_unico_devolve_none(monkeypatch):
    """Terminal fechado/deslogado, ou papéis da watchlist com contract_size
    diferente entre si: `MT5Broker.detect_shares_per_lot` devolve `None` e
    `live_control.detect_shares_per_lot()` repassa isso -- nunca inventa um
    valor default."""
    monkeypatch.setattr(live_control, "load_credentials", lambda: {})
    captured: list = []
    import live.broker_mt5 as broker_mt5
    monkeypatch.setattr(
        broker_mt5, "MT5Broker",
        lambda **kwargs: _FakeLotBroker(None, captured, **kwargs),
    )

    assert live_control.detect_shares_per_lot() is None
    assert captured[0]["login"] is None
