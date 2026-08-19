"""Testes da linha de comando (`scripts/run_live.py`) — dispatch de `build()`
(1.2).

Isolamento obrigatorio do banco (FEAT-001, ACTION-PLAN secao 2): `build()`
monta `LiveRuntime` com `db_path=None` (cai no default de modulo) — sem
isolar, este arquivo escreveria no `db/live.sqlite` REAL. Usa as duas mesmas
tecnicas de `tests/test_dashboard_app.py` (docstring do modulo, linhas 9-26):
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
from live import clock
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
        feed="yfinance", mode="mt5", capital=1_000.0, floor=None,
        notify_min_level="warn", daily_loss_limit=None, monthly_loss_limit=None,
        mt5_magic=20260817, mt5_shares_per_lot=None, mt5_symbol_map=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _sacar_args(valor, intent_id=None, data=None, **overrides) -> argparse.Namespace:
    args = _args(**overrides)
    args.valor = valor
    args.intent_id = intent_id
    args.data = data
    return args


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


def test_build_mt5_com_shares_per_lot_zero_ou_negativo_levanta_valueerror(cli, isolated_db):
    """Item 2 da correção pós-code-review (hipótese-agente): as 3 validações
    de `mt5_shares_per_lot` (aqui, em `dashboard.live_control.start` e em
    `dashboard.app.operacao_iniciar`) checavam só `is None` -- um valor `0`
    ou negativo passava direto e causaria `ZeroDivisionError` em
    `MT5Broker._to_volume` na hora de mandar ordem real (`volume = quantity /
    shares_per_lot`)."""
    with pytest.raises(ValueError):
        cli.build(_args(mode="mt5", mt5_shares_per_lot=0))
    with pytest.raises(ValueError):
        cli.build(_args(mode="mt5", mt5_shares_per_lot=-1.0))


def test_build_mt5_com_shares_per_lot_monta_mt5_broker(cli, isolated_db):
    rt = cli.build(_args(mode="mt5", mt5_shares_per_lot=1.0))
    assert rt.broker.mode == "mt5"


# ---------- feed obrigatorio em operacao real (FEAT-004, item 4.1) ---------

def test_build_recusa_feed_parquet_em_operacao_real(cli, isolated_db):
    """`--feed parquet` (dado de D-1, ou mais velho) nunca pode operar
    dinheiro real -- `build()` recusa no unico modo real que existe (mt5)."""
    with pytest.raises(ValueError):
        cli.build(_args(mode="mt5", feed="parquet", mt5_shares_per_lot=1.0))


def test_build_monta_mt5feed_quando_pedido(cli, isolated_db):
    from live.feed import MT5Feed

    rt = cli.build(_args(mode="mt5", feed="mt5", mt5_shares_per_lot=1.0))
    assert isinstance(rt.feed, MT5Feed)


# ---------- cmd_execute recusa fora da fase OPEN (FEAT-004, item 4.4c) -----

class _FakeRuntimeExecute:
    """Minimo o suficiente para exercitar so o dispatch de `cmd_execute` --
    nao monta universo/dado real (`execute_session` de verdade exigiria
    parquet em disco para o WATCHLIST inteiro, irrelevante para o que este
    teste prova: a guarda de fase roda ANTES de chamar `execute_session`)."""

    def __init__(self):
        self.executed = False

    def execute_session(self, session):
        self.executed = True
        return f"execute_session chamado para {session}"


def test_cmd_execute_recusa_fora_da_fase_open(cli, isolated_db, monkeypatch):
    """Rodar `execute` fora da fase OPEN executaria as intencoes de D+1
    contra as cotacoes de D (a sessao errada) -- `cmd_execute` recusa antes
    de chamar `execute_session`."""
    from core.live_models import SessionPhase
    from live import clock as live_clock

    fake_rt = _FakeRuntimeExecute()
    monkeypatch.setattr(cli, "build", lambda args: fake_rt)
    monkeypatch.setattr(live_clock, "phase", lambda *a, **k: SessionPhase.POST_CLOSE)

    with pytest.raises(SystemExit):
        cli.cmd_execute(_args())
    assert fake_rt.executed is False


def test_cmd_execute_no_fase_open_nao_recusa(cli, isolated_db, monkeypatch):
    from core.live_models import SessionPhase
    from live import clock as live_clock

    fake_rt = _FakeRuntimeExecute()
    monkeypatch.setattr(cli, "build", lambda args: fake_rt)
    monkeypatch.setattr(live_clock, "phase", lambda *a, **k: SessionPhase.OPEN)

    cli.cmd_execute(_args())  # nao levanta SystemExit
    assert fake_rt.executed is True


# ---------- cmd_loop: ValueError de conta/broker divergente e FATAL (item 6) --

class _FakeNotifier:
    def __init__(self):
        self.calls: list = []

    def notify(self, level, source, message):
        self.calls.append((level, source, message))


class _FakeRuntimeValueError:
    """Simula um `LiveRuntime` cujo `run_once()` levanta o `ValueError` da
    guarda de conta/broker divergente (`LiveRuntime._load_account`) -- sem
    montar um runtime de verdade, so o suficiente para exercitar o dispatch
    de excecao do `cmd_loop`."""

    def __init__(self):
        self.notifier = _FakeNotifier()

    def run_once(self):
        raise ValueError("conta 'principal' esta em modo 'mt5', broker instanciado e 'mt5-mas-errado'")


def test_cmd_loop_valueerror_de_conta_broker_divergente_e_fatal(cli, isolated_db, monkeypatch):
    """Correcao pos-code-review (item 6, hipotese-agente): antes desta
    correcao, um `ValueError` de conta/broker divergente caia no `except
    Exception` generico do loop, que loga, notifica, dorme 60s e tenta de
    novo -- para sempre, com o processo vivo e o painel mostrando "ativo"
    enquanto nada e decidido. Agora o loop distingue esse erro como FATAL:
    notifica em nivel error e ENCERRA o processo (exit != 0) em vez de
    continuar tentando."""
    fake_rt = _FakeRuntimeValueError()
    monkeypatch.setattr(cli, "build", lambda args: fake_rt)

    from live import clock as live_clock
    monkeypatch.setattr(live_clock, "seconds_until_active_window", lambda: 0)

    args = _args(seconds=60)
    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_loop(args)
    assert exc_info.value.code != 0

    # notificou (nivel error) antes de encerrar -- nao e um erro silencioso.
    assert fake_rt.notifier.calls
    level, source, message = fake_rt.notifier.calls[0]
    assert level == "error"
    assert "FATAL" in message


# ---------- cmd_sacar: confirma recomendacao de saque pendente (passo 13) --

def _create_account_com_recomendacao(cli, isolated_db, amount=500.0):
    """Cria a conta via CLI e grava uma recomendacao de saque PENDING direto
    no diario -- mais simples que rodar `close_and_decide` real para exercitar
    so o dispatch do `cmd_sacar`, sem depender de dado de mercado/politica.

    `decided_on` e derivado do mes CIVIL da sessao corrente (`clock.
    session_date()`, o mesmo relogio que `cmd_sacar` usa quando `--data` nao
    e passado) -- nunca um mes fixo hardcodado a mao: uma `decided_on` de mes
    civil distante e fixo viraria recomendacao ja EXPIRADA assim que o mes
    civil real virasse, quebrando o teste sem nenhuma mudanca de codigo."""
    from core.live_models import Intent, IntentKind, RobotRole

    rt = cli.build(_args(capital=1_000.0, mt5_shares_per_lot=1.0))
    rt.ensure_account()
    mes_corrente = clock.session_date().replace(day=1)
    with live_store.live_journal(isolated_db) as conn:
        acc = live_store.load_account(conn, cli.ACCOUNT)
        intent = Intent(
            robot="withdrawal:teste", role=RobotRole.WITHDRAWAL, kind=IntentKind.WITHDRAW,
            decided_on=mes_corrente, execute_on=clock.next_session(mes_corrente), amount=amount,
            reason="teste",
        )
        live_store.record_intent(conn, acc.id, intent)
    return intent


def test_cmd_sacar_confirma_recomendacao_pendente_debita_caixa(cli, isolated_db, capsys):
    _create_account_com_recomendacao(cli, isolated_db, amount=500.0)
    args = _sacar_args(500.0, capital=1_000.0, mt5_shares_per_lot=1.0)

    cli.cmd_sacar(args)

    with live_store.live_journal(isolated_db) as conn:
        acc = live_store.load_account(conn, cli.ACCOUNT)
    assert acc.cash == pytest.approx(500.0)
    assert acc.external_cash == pytest.approx(500.0)
    captured = capsys.readouterr()
    assert "withdraw_confirm" in captured.out


def test_cmd_sacar_sem_recomendacao_pendente_sai_com_erro(cli, isolated_db):
    rt = cli.build(_args(capital=1_000.0, mt5_shares_per_lot=1.0))
    rt.ensure_account()
    args = _sacar_args(500.0, capital=1_000.0, mt5_shares_per_lot=1.0)

    with pytest.raises(SystemExit):
        cli.cmd_sacar(args)

    with live_store.live_journal(isolated_db) as conn:
        acc = live_store.load_account(conn, cli.ACCOUNT)
    assert acc.cash == pytest.approx(1_000.0)


def test_cmd_sacar_com_intent_id_errado_sai_com_erro_sem_mexer_no_caixa(cli, isolated_db):
    _create_account_com_recomendacao(cli, isolated_db, amount=500.0)
    args = _sacar_args(500.0, intent_id=999_999, capital=1_000.0, mt5_shares_per_lot=1.0)

    with pytest.raises(SystemExit):
        cli.cmd_sacar(args)

    with live_store.live_journal(isolated_db) as conn:
        acc = live_store.load_account(conn, cli.ACCOUNT)
    assert acc.cash == pytest.approx(1_000.0)


def test_cmd_loop_outros_erros_continuam_com_retry(cli, isolated_db, monkeypatch):
    """Contraste com o teste acima: outras excecoes (rede, dado, etc.) NAO
    podem virar fatais por causa desta correcao -- continuam no `except
    Exception` generico, que loga/notifica e deixa o loop tentar de novo.
    Aqui a 2a chamada de `run_once()` levanta `KeyboardInterrupt` (em vez de
    monkeypatchar `time.sleep`, que roda FORA do bloco try/except e nao seria
    capturado do jeito certo) so para o loop parar e o teste nao rodar para
    sempre."""

    class _FakeRuntimeGenericError:
        def __init__(self):
            self.notifier = _FakeNotifier()
            self.calls = 0

        def run_once(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("erro transitorio de rede")
            raise KeyboardInterrupt

    fake_rt = _FakeRuntimeGenericError()
    monkeypatch.setattr(cli, "build", lambda args: fake_rt)

    from live import clock as live_clock
    monkeypatch.setattr(live_clock, "seconds_until_active_window", lambda: 0)
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)  # nao dorme de verdade

    args = _args(seconds=60)
    cli.cmd_loop(args)  # KeyboardInterrupt tratado dentro do loop, retorna normal

    assert fake_rt.calls == 2  # continuou tentando apos o 1o erro generico
    assert fake_rt.notifier.calls  # notificou o erro generico, mas nao fatal
    level, _source, message = fake_rt.notifier.calls[0]
    assert "RuntimeError" in message
