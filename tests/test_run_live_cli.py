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
        feed="yfinance", mode="mt5", capital=1_000.0, strategy="portfolio_dip2_hw40",
        floor=None, notify_min_level="warn", daily_loss_limit=None, monthly_loss_limit=None,
        mt5_shares_per_lot=None, mt5_symbol_map=None,
        mt5_fractional_map=None,
        # `--slot` nao tem default (ver docstring de `run_live.py`): estes
        # testes cobrem o slot DIARIO, o unico que `build()` monta sem
        # precisar de terminal MT5 aberto.
        slot="swing", execution_mode="shadow",
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


def test_build_mt5_repassa_fractional_map_para_o_broker(cli, isolated_db):
    """`--mt5-fractional-map` (JSON) precisa chegar ao `MT5Broker` -- e o
    mapa que ele usa pra decidir, a cada ordem, entre lote padrao (gratis na
    Rico) e fracionario (paga por ordem), ver docstring de
    `live/broker_mt5.py`."""
    import json as json_mod

    mapa = {"WEGE3.SA": "WEGE3F"}
    rt = cli.build(_args(mode="mt5", mt5_shares_per_lot=1.0,
                          mt5_fractional_map=json_mod.dumps(mapa)))
    assert rt.broker._fractional_map == mapa


# ---------- disjuntor SEMPRE ativo, nao e escolha de quem opera (2026-08-19) -

def test_build_sem_limites_no_form_ainda_ativa_disjuntor_com_default_da_classe(cli, isolated_db):
    """Piso de saque e disjuntor nao sao parametro de estrategia que o
    usuario deva digitar -- o robo ja sabe o valor certo. Sem
    `--daily-loss-limit`/`--monthly-loss-limit` (caminho do dashboard, que
    nunca envia essas flags), `build()` tem de montar o `CircuitBreaker`
    mesmo assim, com os defaults da propria classe (5%/15%), nunca `None`."""
    rt = cli.build(_args(mode="mt5", mt5_shares_per_lot=1.0,
                          daily_loss_limit=None, monthly_loss_limit=None))
    assert rt.risk_guard is not None
    assert rt.risk_guard.daily_loss_pct == pytest.approx(0.05)
    assert rt.risk_guard.monthly_loss_pct == pytest.approx(0.15)


# ---------- --strategy sem default, resolvido via registry (2026-08-19) ----

def test_build_sem_strategy_levanta_valueerror(cli, isolated_db):
    """Regra do dono: nao ha robo padrao escolhido sozinho -- quem cria a
    conta tem que escolher a chave explicitamente."""
    with pytest.raises(ValueError, match="strategy"):
        cli.build(_args(mode="mt5", mt5_shares_per_lot=1.0, strategy=None))


def test_build_strategy_desconhecida_levanta_valueerror(cli, isolated_db):
    with pytest.raises(ValueError):
        cli.build(_args(mode="mt5", mt5_shares_per_lot=1.0, strategy="robo-que-nao-existe"))


def test_build_resolve_strategy_do_registry(cli, isolated_db):
    """`--strategy` vira a MESMA instancia que `strategy.registry.get_strategy`
    devolveria -- `build()` nao pode ter nenhum robo hardcoded por fora do
    registry (extingue o `DipTop1Portfolio` fixo de antes)."""
    rt = cli.build(_args(mode="mt5", mt5_shares_per_lot=1.0, strategy="portfolio_dip2_hw40"))
    assert rt.investment.key == "portfolio_dip2_hw40"


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
        raise ValueError("conta 'swing' esta em modo 'mt5', broker instanciado e 'mt5-mas-errado'")


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

# ---------- slots: despacho por cadencia (2026-08-21) ---------------------

def test_build_sem_slot_levanta_valueerror(cli, isolated_db):
    """`--slot` nao tem default de proposito, mesmo precedente de
    `--strategy`: um fallback silencioso aqui operaria dinheiro real na vaga
    errada."""
    with pytest.raises(ValueError, match="slot"):
        cli.build(_args(slot=None, mt5_shares_per_lot=1.0))


def test_build_slot_desconhecido_levanta_valueerror(cli, isolated_db):
    with pytest.raises(ValueError, match="slot"):
        cli.build(_args(slot="vaga-que-nao-existe", mt5_shares_per_lot=1.0))


def test_build_slot_diario_usa_o_slot_como_nome_da_conta(cli, isolated_db):
    """A conta "principal" deixou de existir: o nome da conta E o id do slot,
    porque e isso que da a cada robo um caixa proprio."""
    rt = cli.build(_args(mt5_shares_per_lot=1.0))
    assert rt.account_name == "swing"


def test_build_slot_diario_usa_o_magic_do_slot(cli, isolated_db):
    """Conta NETTING: `magic` distinto por slot e o unico jeito de distinguir
    as ordens de um robo das do outro. Deixou de ser flag digitavel."""
    from core.config import slot_by_id

    rt = cli.build(_args(mt5_shares_per_lot=1.0))
    assert rt.broker._magic == slot_by_id("swing").magic


def test_daytrade_strategy_resolve_gremah_fora_do_registry_de_swing(cli):
    """`IntradayStrategy` NAO herda de `Strategy` (de proposito), entao
    `strategy.registry.get_strategy("gremah")` levantaria `KeyError`. O CLI
    tem um resolvedor proprio para a familia intradiaria."""
    from strategy.registry import get_strategy

    with pytest.raises(KeyError):
        get_strategy("gremah")

    robo = cli._daytrade_strategy("gremah")
    assert robo.name == "gremah"


def test_daytrade_strategy_desconhecida_levanta_valueerror(cli):
    with pytest.raises(ValueError, match="day trade"):
        cli._daytrade_strategy("robo-intradiario-que-nao-existe")


def test_cmd_decide_recusa_slot_intradiario(cli, isolated_db, monkeypatch):
    """Nao ha "fecho do pregao" a forcar num robo que decide barra a barra.
    Recusar explicitamente e melhor que um `AttributeError` cru vindo de um
    runtime que nao tem o metodo."""
    chamado: list = []
    monkeypatch.setattr(cli, "build", lambda args: chamado.append(args))

    with pytest.raises(SystemExit):
        cli.cmd_decide(_args(slot="daytrade", strategy="gremah"))

    assert chamado == []  # nem tentou montar o runtime


def test_cmd_execute_e_unfreeze_tambem_recusam_slot_intradiario(cli, isolated_db, monkeypatch):
    chamado: list = []
    monkeypatch.setattr(cli, "build", lambda args: chamado.append(args))

    for fn in (cli.cmd_execute, cli.cmd_unfreeze, cli.cmd_reconcile):
        with pytest.raises(SystemExit):
            fn(_args(slot="daytrade", strategy="gremah"))

    assert chamado == []
