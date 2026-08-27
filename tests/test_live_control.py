"""Testes de `dashboard/live_control.py` — prova de vida do processo (1.6), o
parametro `mt5_shares_per_lot` (1.7, fim do `1.0` hardcoded) e, desde
2026-08-21, o estado de processo POR SLOT (dois robos ao vivo, cada um com o
seu caixa — ver `core.config.SLOTS`).

Isolamento: `_STATE_PATH`/`_LOG_DIR` monkeypatchados para `tmp_path` (nunca
`db/live_process.json`/`db/live_process*.log` reais); `_STARTUP_GRACE_SECONDS`
monkeypatchado para 0 (o teste nao pode esperar de verdade); `live.runtime.
DB_PATH` E o default de `journal.live_store.live_journal` monkeypatchados para
`tmp_path`, porque `start()` passou a LER o caixa do slot no diario ao vivo
(piso de operacao) alem de criar a conta.

Sobre o default de `live_journal`: e um `@contextlib.contextmanager`, cujo
default de `db_path` e resolvido em tempo de DEFINICAO da funcao geradora —
`monkeypatch.setattr(modulo, "LIVE_DB_PATH", tmp)` nao teria efeito nenhum.
O jeito de fato mudar e sobrescrever `__defaults__` da geradora original,
acessivel via `live_journal.__wrapped__` (preservado por `functools.wraps`).
Mesmo padrao de `tests/test_dashboard_app.py`.
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from dashboard import live_control
from journal import live_store
from live import runtime as live_runtime

# Slot de day trade DINAMICO (`dt-<robo>-<ativo>-<modo>`, modo fixo no id
# desde 2026-08-24): nao existe mais um slot fixo chamado "daytrade" em
# `core.config.SLOTS` -- o painel abre quantos o dono quiser, um por ativo
# (e ate dois por ativo, sombra e real, cada um com seu processo/conta).
DAYTRADE = "dt-gremah-pmam3-shadow"


class _FakeProc:
    def __init__(self, pid: int, poll_value):
        self.pid = pid
        self._poll_value = poll_value

    def poll(self):
        return self._poll_value


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    state_path = tmp_path / "live_process.json"
    db_path = tmp_path / "live_control_test.sqlite"
    monkeypatch.setattr(live_control, "_STATE_PATH", state_path)
    monkeypatch.setattr(live_control, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(live_control, "_STARTUP_GRACE_SECONDS", 0)
    monkeypatch.setattr(live_runtime, "DB_PATH", db_path)
    monkeypatch.setattr(live_store.live_journal.__wrapped__, "__defaults__", (db_path,))
    # `IntradayLiveRuntime` NAO passa pelo default de `live_journal()`: ele
    # guarda `LIVE_DB_PATH` no `__init__` e o passa EXPLICITAMENTE em toda
    # chamada. Sem este patch, `create_account`/`start` de um slot de day trade
    # criavam conta no `db/live.sqlite` REAL durante a suite -- descoberto em
    # 2026-08-22, quando o id do slot deixou de ser "daytrade" (que ja existia
    # no banco real e absorvia a escrita em silencio via ON CONFLICT) e passou
    # a ser `dt-gremah-pmam3`, que aparecia como conta nova de R$1.000.
    from live import intraday_runtime

    monkeypatch.setattr(intraday_runtime, "LIVE_DB_PATH", db_path)
    # `start()` varre processos orfaos do slot antes de subir (2026-08-27,
    # ver docstring dele) via `_processos_do_sistema()`, que dispara um
    # `subprocess.run` de verdade (PowerShell/`ps`) -- sem este default a
    # zero, cada teste da suite ficaria: (a) lento de verdade shellando pro
    # SO, e (b) sujeito a colidir com o `subprocess.Popen` fake que os testes
    # de `start()` instalam pra CAPTURAR o argv do robo, que nao suporta o
    # protocolo de context manager que `subprocess.run` exige. Testes que
    # querem simular um orfao de verdade sobrescrevem isto de novo.
    monkeypatch.setattr(live_control, "_processos_do_sistema", lambda: [])
    return {"state": state_path, "dir": tmp_path, "db": db_path}


def _seed_cash(db_path, slot: str, cash: float) -> None:
    """Ledger manual do slot — `start()` recusa abaixo de `Slot.min_cash_brl`."""
    with live_store.live_journal(db_path) as conn:
        acc = live_store.ensure_account(
            conn, name=slot, mode="mt5", initial_capital=cash,
            investment_robot="portfolio_dip2_hw40", withdrawal_robot="official_policy",
        )
        acc.cash = cash
        live_store.save_account(conn, acc)


def _cfg(**over):
    base = dict(mode="mt5", capital=1_000.0, strategy="portfolio_dip2_hw40",
                slot="swing", mt5_shares_per_lot=1.0)
    base.update(over)
    return live_control.ProcessConfig(**base)


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
    _seed_cash(isolated["db"], "swing", 1_000.0)
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        _fake_popen(poll_value=1, captured_argv=[],
                    log_message="[erro fake] terminal MT5 nao encontrado"),
    )

    with pytest.raises(RuntimeError) as exc_info:
        live_control.start(_cfg())

    assert "terminal MT5 nao encontrado" in str(exc_info.value)
    assert live_control._read_state("swing") is None


def test_start_processo_sobrevive_grava_pid(isolated, monkeypatch):
    _seed_cash(isolated["db"], "swing", 1_000.0)
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        _fake_popen(poll_value=None, captured_argv=[]))

    state = live_control.start(_cfg())

    assert state["pid"] == 99999
    saved = live_control._read_state("swing")
    assert saved is not None
    assert saved["pid"] == 99999
    # Formato v2: um bloco por slot, nao mais chaves no topo do arquivo.
    bruto = json.loads(isolated["state"].read_text(encoding="utf-8"))
    assert bruto["version"] == 2
    assert set(bruto["slots"]) == {"swing"}


def test_start_mt5_sem_shares_per_lot_recusa_antes_do_popen(isolated, monkeypatch):
    called = []
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        lambda *a, **k: called.append((a, k)) or _FakeProc(pid=1, poll_value=None),
    )

    with pytest.raises(RuntimeError):
        live_control.start(_cfg(mt5_shares_per_lot=None))

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
        with pytest.raises(RuntimeError):
            live_control.start(_cfg(mt5_shares_per_lot=valor))

    assert called == []


def test_start_mt5_inclui_shares_per_lot_no_argv(isolated, monkeypatch):
    _seed_cash(isolated["db"], "swing", 1_000.0)
    captured: list = []
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        _fake_popen(poll_value=None, captured_argv=captured))

    live_control.start(_cfg(mt5_shares_per_lot=2.0))

    assert len(captured) == 1
    argv = captured[0]
    assert argv[argv.index("--mt5-shares-per-lot") + 1] == "2.0"


def test_start_mt5_sem_fractional_map_nao_inclui_flag_no_argv(isolated, monkeypatch):
    """Sem mapa fracionário detectado (`mt5_fractional_map=None`), o argv não
    ganha `--mt5-fractional-map` -- `run_live.py::build()` cai no
    comportamento de sempre (só lote padrão)."""
    _seed_cash(isolated["db"], "swing", 1_000.0)
    captured: list = []
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        _fake_popen(poll_value=None, captured_argv=captured))

    live_control.start(_cfg(mt5_fractional_map=None))

    assert len(captured) == 1
    assert "--mt5-fractional-map" not in captured[0]


def test_start_mt5_com_fractional_map_inclui_json_no_argv(isolated, monkeypatch):
    """Mapa fracionário detectado vira JSON em `--mt5-fractional-map` -- o
    MESMO formato que `run_live.py::build()` já sabe ler (`json.loads`)."""
    _seed_cash(isolated["db"], "swing", 1_000.0)
    captured: list = []
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        _fake_popen(poll_value=None, captured_argv=captured))

    live_control.start(_cfg(mt5_fractional_map={"WEGE3.SA": "WEGE3F"}))

    argv = captured[0]
    assert json.loads(argv[argv.index("--mt5-fractional-map") + 1]) == {"WEGE3.SA": "WEGE3F"}


def test_create_account_serializa_fractional_map_em_json_para_build(monkeypatch):
    """`create_account()` chama `cli.build(args)` (o MESMO `run_live.py`) --
    `args.mt5_fractional_map` precisa chegar como STRING json (ou `None`),
    nunca como dict cru, porque `build()` faz
    `json.loads(args.mt5_fractional_map)`."""
    captured_args: list = []

    class _FakeRuntime:
        def ensure_account(self):
            return "conta-fake"

    class _FakeCli:
        @staticmethod
        def build(args):
            captured_args.append(args)
            return _FakeRuntime()

    monkeypatch.setattr(live_control, "_load_cli", lambda: _FakeCli)

    resultado = live_control.create_account(_cfg(mt5_fractional_map={"WEGE3.SA": "WEGE3F"}))

    assert resultado == "conta-fake"
    assert json.loads(captured_args[0].mt5_fractional_map) == {"WEGE3.SA": "WEGE3F"}
    # O slot chega no `build` -- sem isso o CLI recusaria (`--slot` sem default).
    assert captured_args[0].slot == "swing"


def test_create_account_sem_fractional_map_passa_none_para_build(monkeypatch):
    captured_args: list = []

    class _FakeRuntime:
        def ensure_account(self):
            return "conta-fake"

    class _FakeCli:
        @staticmethod
        def build(args):
            captured_args.append(args)
            return _FakeRuntime()

    monkeypatch.setattr(live_control, "_load_cli", lambda: _FakeCli)
    live_control.create_account(_cfg(mt5_fractional_map=None))

    assert captured_args[0].mt5_fractional_map is None


def test_create_account_usa_o_magic_do_slot_nunca_um_fixo(monkeypatch):
    """Conta NETTING (verificado no terminal real, 2026-08-21): as ordens dos
    dois robôs só são distinguíveis pelo `magic`. Um valor fixo aqui faria os
    dois slots gravarem o mesmo carimbo."""
    from core.config import slot_by_id

    captured_args: list = []

    class _FakeRuntime:
        def ensure_account(self):
            return "conta-fake"

    class _FakeCli:
        @staticmethod
        def build(args):
            captured_args.append(args)
            return _FakeRuntime()

    monkeypatch.setattr(live_control, "_load_cli", lambda: _FakeCli)
    live_control.create_account(_cfg(slot=DAYTRADE, strategy="gremah"))

    assert captured_args[0].mt5_magic == slot_by_id(DAYTRADE).magic


# ---------- --strategy/--slot sempre no argv, sem robo padrao --------------

def test_start_inclui_strategy_e_slot_no_argv(isolated, monkeypatch):
    _seed_cash(isolated["db"], "swing", 1_000.0)
    captured: list = []
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        _fake_popen(poll_value=None, captured_argv=captured))

    live_control.start(_cfg())

    argv = captured[0]
    assert argv[argv.index("--strategy") + 1] == "portfolio_dip2_hw40"
    assert argv[argv.index("--slot") + 1] == "swing"
    assert argv[argv.index("--execution-mode") + 1] == "shadow"


def test_start_sem_strategy_recusa_antes_do_popen(isolated, monkeypatch):
    """Sem robo default (regra do dono, 2026-08-19): `strategy` vazio/None tem
    que recusar igual a `mt5_shares_per_lot` ausente -- nunca sobe o processo
    sem saber que robo rodar."""
    called = []
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        lambda *a, **k: called.append((a, k)) or _FakeProc(pid=1, poll_value=None),
    )

    with pytest.raises(RuntimeError):
        live_control.start(_cfg(strategy=""))

    assert called == []


def test_start_execution_mode_invalido_recusa_antes_do_popen(isolated, monkeypatch):
    called = []
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        lambda *a, **k: called.append((a, k)) or _FakeProc(pid=1, poll_value=None),
    )

    with pytest.raises(RuntimeError, match="execution_mode"):
        live_control.start(_cfg(execution_mode="pra-valer"))

    assert called == []


def test_start_mata_orfao_do_slot_antes_de_subir_novo_processo(isolated, monkeypatch):
    """2026-08-27, achado numa conferencia manual do dono: `stop()` pode zerar
    `pid`/`started_at` no arquivo sem o `_matar_arvore` ter pego o processo de
    verdade (reparentado, `taskkill` engasgado) -- o arquivo dizia "parado"
    com um `run_live.py` de verdade ainda vivo por tras. `start()` via so' o
    arquivo e subia um SEGUNDO processo pro MESMO slot por cima do orfao (foi
    exatamente o que aconteceu com `dt-gremah-pmam3-shadow`: dois processos
    escrevendo na mesma conta ao mesmo tempo). Este teste prova que `start()`
    agora varre e mata qualquer orfao do slot ANTES do `Popen` novo."""
    _seed_cash(isolated["db"], DAYTRADE, 100.0)
    linha_orfa = (
        r'"C:\...\python.exe" "C:\...\run_live.py" --mode mt5 --capital 40.86 '
        f'--strategy gremah --slot {DAYTRADE} --execution-mode shadow loop --seconds 5'
    )
    monkeypatch.setattr(live_control, "_processos_do_sistema",
                        lambda: [(11111, 22222, linha_orfa)])
    mortos = []
    monkeypatch.setattr(live_control, "_matar_arvore", lambda pid: mortos.append(pid))
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        _fake_popen(poll_value=None, captured_argv=[]))

    state = live_control.start(_cfg(slot=DAYTRADE, strategy="gremah"))

    assert mortos == [11111]
    assert state["pid"] == 99999


def test_start_sem_orfao_nao_mata_nada(isolated, monkeypatch):
    """Caso comum (nenhum orfao no sistema): a varredura nao pode matar nada
    nem impedir a subida normal."""
    _seed_cash(isolated["db"], DAYTRADE, 100.0)
    mortos = []
    monkeypatch.setattr(live_control, "_matar_arvore", lambda pid: mortos.append(pid))
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        _fake_popen(poll_value=None, captured_argv=[]))

    state = live_control.start(_cfg(slot=DAYTRADE, strategy="gremah"))

    assert mortos == []
    assert state["pid"] == 99999


def test_start_day_trade_usa_passo_de_5s_swing_60s(isolated, monkeypatch):
    """Day trade decide barra a barra e o stop dele resolve em barra M1
    fechada: um passo de 60s perderia a barra inteira. Swing decide 1x por
    pregão e mantém 60s."""
    _seed_cash(isolated["db"], "swing", 1_000.0)
    _seed_cash(isolated["db"], DAYTRADE, 100.0)
    captured: list = []
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        _fake_popen(poll_value=None, captured_argv=captured))
    monkeypatch.setattr(live_control, "_pid_alive", lambda pid: True)

    live_control.start(_cfg(slot=DAYTRADE, strategy="gremah"))
    live_control.start(_cfg(slot="swing"))

    assert captured[0][captured[0].index("--seconds") + 1] == "5"
    assert captured[1][captured[1].index("--seconds") + 1] == "60"


# ---------- piso de caixa por slot (decisao do dono, 2026-08-21) -----------

def test_start_recusa_caixa_abaixo_do_piso_do_slot(isolated, monkeypatch):
    """R$50 é checado NO SERVIDOR, não só no template: um botão desabilitado
    não cobre POST repetido, fragmento HTMX velho nem a linha de comando."""
    _seed_cash(isolated["db"], "swing", 40.0)
    called = []
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        lambda *a, **k: called.append((a, k)) or _FakeProc(pid=1, poll_value=None),
    )

    with pytest.raises(RuntimeError, match="abaixo do mínimo"):
        live_control.start(_cfg())

    assert called == []


def test_start_aceita_caixa_exatamente_no_piso(isolated, monkeypatch):
    """O piso é "mínimo para operar", não "acima de" — R$50 exatos passam."""
    _seed_cash(isolated["db"], "swing", 50.0)
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        _fake_popen(poll_value=None, captured_argv=[]))

    assert live_control.start(_cfg())["pid"] == 99999


# ---------- piso de caixa POR ROBÔ no day trade (decisão do dono, 2026-08-22) -

def test_min_cash_for_swing_usa_o_piso_generico_do_slot():
    """Swing não tem conceito de "lote" — o piso é sempre `Slot.min_cash_brl`,
    não importa o robô."""
    from core.config import slot_by_id

    slot = slot_by_id("swing")
    assert live_control.min_cash_for(slot) == pytest.approx(slot.min_cash_brl)
    assert live_control.min_cash_for(slot, "portfolio_dip2_hw40") == pytest.approx(slot.min_cash_brl)


def test_min_cash_for_daytrade_usa_capital_minimo_do_robo(monkeypatch):
    """O ponto central da mudança: o piso do day trade vem do PREÇO do
    símbolo do robô, não de um número cego (`Slot.min_cash_brl`)."""
    from core.config import slot_by_id

    monkeypatch.setattr(live_control, "_intraday_capital_minimo", lambda robot_key, symbol=None: 123.45)
    slot = slot_by_id(DAYTRADE)

    assert live_control.min_cash_for(slot, "gremah") == pytest.approx(123.45)


def test_min_cash_for_daytrade_sem_robot_key_usa_o_default_do_slot(monkeypatch):
    """Conta NOVA, ainda sem robô escolhido: usa `slot.robot_key` (o mesmo
    pré-selecionado no `<select>` do template) para achar o piso."""
    from core.config import slot_by_id

    capturado = []
    monkeypatch.setattr(live_control, "_intraday_capital_minimo",
                        lambda robot_key, symbol=None: capturado.append(robot_key) or 50.0)
    slot = slot_by_id(DAYTRADE)

    live_control.min_cash_for(slot)

    assert capturado == [slot.robot_key]


def test_min_cash_for_daytrade_sem_preco_local_cai_no_piso_generico(monkeypatch):
    """Parquet ausente/robô fora do catálogo: `_intraday_capital_minimo`
    devolve `None`, e isso NUNCA pode travar o "Iniciar" por falta de dado
    que não é culpa do dono — degrada para `Slot.min_cash_brl`."""
    from core.config import slot_by_id

    monkeypatch.setattr(live_control, "_intraday_capital_minimo", lambda robot_key, symbol=None: None)
    slot = slot_by_id(DAYTRADE)

    assert live_control.min_cash_for(slot, "gremah") == pytest.approx(slot.min_cash_brl)


def test_start_daytrade_recusa_caixa_abaixo_do_piso_do_robo(isolated, monkeypatch):
    """O ponto central do pedido, de ponta a ponta pelo `start()`: caixa que
    cobriria o piso genérico de R$50 mas não cobre o piso REAL do robô
    escolhido tem de ser recusado."""
    _seed_cash(isolated["db"], DAYTRADE, 100.0)
    monkeypatch.setattr(live_control, "min_cash_for", lambda slot, robot_key=None: 200.0)
    called = []
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        lambda *a, **k: called.append((a, k)) or _FakeProc(pid=1, poll_value=None),
    )

    with pytest.raises(RuntimeError, match="abaixo do mínimo de R\\$ 200"):
        live_control.start(_cfg(slot=DAYTRADE, strategy="gremah"))

    assert called == []


def test_available_cash_sem_conta_devolve_none(isolated):
    assert live_control.available_cash("swing") is None


def test_available_cash_le_o_ledger_do_slot_pedido(isolated):
    _seed_cash(isolated["db"], "swing", 123.45)
    _seed_cash(isolated["db"], DAYTRADE, 67.89)

    assert live_control.available_cash("swing") == pytest.approx(123.45)
    assert live_control.available_cash(DAYTRADE) == pytest.approx(67.89)


# ---------- dois slots, dois processos independentes ------------------------

def test_start_de_dois_slots_convivem_e_stop_derruba_so_um(isolated, monkeypatch):
    """O pedido inteiro: os dois robôs operando ao mesmo tempo, cada um com o
    seu processo. Parar um não pode parar o outro."""
    _seed_cash(isolated["db"], "swing", 1_000.0)
    _seed_cash(isolated["db"], DAYTRADE, 100.0)
    pids = iter([111, 222])

    monkeypatch.setattr(live_control.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc(pid=next(pids), poll_value=None))
    monkeypatch.setattr(live_control, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(live_control, "_pids_alive", lambda pids: set(pids))
    monkeypatch.setattr(live_control.subprocess, "run", lambda *a, **k: None)

    live_control.start(_cfg(slot="swing"))
    live_control.start(_cfg(slot=DAYTRADE, strategy="gremah"))

    assert live_control.status("swing")["pid"] == 111
    assert live_control.status(DAYTRADE)["pid"] == 222
    assert set(live_control.status_all(["swing", DAYTRADE])) == {"swing", DAYTRADE}

    assert live_control.stop(DAYTRADE) is True

    assert live_control.status("swing")["pid"] == 111       # intacto
    assert live_control.status(DAYTRADE) is None
    # `stop` preserva a config para o form de retomada continuar preenchido.
    assert live_control.last_config(DAYTRADE)["strategy"] == "gremah"


def test_start_no_mesmo_slot_duas_vezes_recusa_a_segunda(isolated, monkeypatch):
    _seed_cash(isolated["db"], "swing", 1_000.0)
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        _fake_popen(poll_value=None, captured_argv=[]))
    monkeypatch.setattr(live_control, "_pid_alive", lambda pid: True)

    live_control.start(_cfg())
    with pytest.raises(RuntimeError, match="já está rodando"):
        live_control.start(_cfg())


def test_start_log_e_por_slot(isolated, monkeypatch):
    """Dois processos no MESMO arquivo de log entrelaçariam linhas, e
    `_tail_log()` explicaria a morte de um robô com o log do outro."""
    _seed_cash(isolated["db"], DAYTRADE, 100.0)
    monkeypatch.setattr(
        live_control.subprocess, "Popen",
        _fake_popen(poll_value=1, captured_argv=[], log_message="[erro fake] boom daytrade"),
    )

    with pytest.raises(RuntimeError, match="boom daytrade"):
        live_control.start(_cfg(slot=DAYTRADE, strategy="gremah"))

    assert (isolated["dir"] / f"live_process.{DAYTRADE}.log").exists()
    assert not (isolated["dir"] / "live_process.log").exists()


def test_estado_legado_v1_e_adotado_como_slot_de_swing(isolated):
    """Um arquivo de estado do formato antigo (chaves no topo, um robô só)
    tem de continuar sendo LIDO -- senão um PID órfão de antes da migração
    ficaria vivo e sem botão "Parar" que o alcance."""
    isolated["state"].write_text(json.dumps({
        "pid": 4242, "started_at": "2026-08-20T13:00:00+00:00",
        "config": {"mode": "mt5", "capital": 1_000.0, "strategy": "portfolio_dip2_hw40"},
    }), encoding="utf-8")

    assert live_control._read_state("swing")["pid"] == 4242
    assert live_control._read_state(DAYTRADE) is None
    assert live_control.last_config("swing")["strategy"] == "portfolio_dip2_hw40"


def test_write_state_de_um_slot_preserva_o_outro(isolated):
    """Read-modify-write do MESMO arquivo: gravar o estado de um slot nunca
    pode apagar o do outro (é por isso que `_start_lock` continua único, e
    não um lock por slot)."""
    live_control._write_state("swing", {"pid": 1, "started_at": None, "config": {}})
    live_control._write_state(DAYTRADE, {"pid": 2, "started_at": None, "config": {}})

    assert live_control._read_state("swing")["pid"] == 1
    assert live_control._read_state(DAYTRADE)["pid"] == 2

    live_control._write_state(DAYTRADE, None)

    assert live_control._read_state("swing")["pid"] == 1
    assert live_control._read_state(DAYTRADE) is None


def test_write_state_escreve_via_arquivo_temporario_atomico(isolated):
    """`_write_state` nunca deve deixar o arquivo final pela metade — troca
    via `Path.replace` a partir de um `.tmp` (achado 2026-08-24: um leitor
    concorrente pegando o arquivo torto via `write_text` direto via
    `_read_all` como vazio, e uma escrita seguinte baseada nisso apagava
    TODOS os outros slots sem que ninguém tivesse chamado
    `_write_state(slot, None)` para eles)."""
    live_control._write_state("swing", {"pid": 1, "started_at": None, "config": {}})

    tmp_path = live_control._STATE_PATH.with_suffix(
        f"{live_control._STATE_PATH.suffix}.tmp"
    )
    assert not tmp_path.exists()  # o temporário nunca sobra depois da troca
    assert live_control._read_state("swing")["pid"] == 1


def _falha_tasklist(*a, **k):
    raise TimeoutError("tasklist não respondeu (simulado)")


def test_tasklist_indisponivel_nao_derruba_status_de_ninguem(isolated, monkeypatch):
    """Achado ao vivo 2026-08-24: um `tasklist` que falha por engasgo
    passageiro do Windows NÃO prova que os processos morreram, mas
    `status_all()` tratava a falha como "conjunto vazio" == "todo mundo
    morreu ao mesmo tempo", e reescrevia `db/live_process.json` zerando
    `pid`/`started_at` de TODOS os slots numa penada só (PMAM3 e PMAM3-tick
    caíram juntos no painel no mesmo poll, com os processos reais
    continuando vivos por fora). `status()`/`status_all()` têm de devolver o
    estado GRAVADO sem autocorrigir quando a vivacidade é indeterminada."""
    live_control._write_state("swing", {"pid": 111, "started_at": "t0", "config": {}})
    live_control._write_state(DAYTRADE, {"pid": 222, "started_at": "t0", "config": {}})
    monkeypatch.setattr(live_control.subprocess, "run", _falha_tasklist)

    assert live_control.status("swing")["pid"] == 111
    assert live_control.status(DAYTRADE)["pid"] == 222

    todos = live_control.status_all(["swing", DAYTRADE])
    assert todos["swing"]["pid"] == 111
    assert todos[DAYTRADE]["pid"] == 222

    # nada foi reescrito no arquivo por causa da falha indeterminada
    assert live_control._read_state("swing")["pid"] == 111
    assert live_control._read_state(DAYTRADE)["pid"] == 222


def test_stop_com_tasklist_indisponivel_ainda_tenta_matar(isolated, monkeypatch):
    """"Parar" é um pedido de MATAR, não "matar só se eu confirmar que está
    vivo" -- se a vivacidade é indeterminada, `stop()` tem de tentar o
    `taskkill` mesmo assim (inofensivo contra um PID já morto) em vez de
    arriscar marcar "parado" no arquivo um processo que continua vivo."""
    live_control._write_state("swing", {"pid": 333, "started_at": "t0", "config": {}})
    chamadas: list = []

    def _run(argv, **kwargs):
        chamadas.append(argv)
        if argv[0] == "tasklist":
            raise TimeoutError("tasklist não respondeu (simulado)")
        return None

    monkeypatch.setattr(live_control.subprocess, "run", _run)

    assert live_control.stop("swing") is True
    assert any(argv[0] == "taskkill" for argv in chamadas)
    assert live_control._read_state("swing")["pid"] is None


def test_start_concorrente_no_mesmo_slot_apenas_um_vence(isolated, monkeypatch):
    """Correção pós-code-review (crítico nº2): duas chamadas a `start()`
    quase simultâneas (dois cliques em "Iniciar" processados em threads
    diferentes do `asyncio.to_thread`, já que `run_dashboard.py` é
    single-process) não podem as duas passarem pelo guard `status(slot) is
    not None` antes de qualquer uma gravar estado -- isso subia dois
    processos `run_live.py loop` órfãos com só o segundo PID rastreável.

    Um `Barrier` de 2 partes força as duas threads a chamarem `start()`
    praticamente no mesmo instante -- é a race de verdade (não sequencial).
    O fake `Popen` ainda dorme um pouco antes de retornar, alargando a janela
    em que o processo "sobe" -- se o lock não cobrisse do guard até
    `_write_state`, a segunda thread teria uma chance real de ler
    `status() is None` enquanto a primeira ainda está dentro do `Popen`."""
    _seed_cash(isolated["db"], "swing", 1_000.0)
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

    results: list = []
    errors: list = []

    def _run():
        start_barrier.wait(timeout=5)  # as duas threads entram em start() juntas
        try:
            results.append(live_control.start(_cfg()))
        except RuntimeError as e:
            errors.append(e)

    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in [pool.submit(_run) for _ in range(2)]:
            f.result(timeout=10)

    assert len(results) == 1
    assert len(errors) == 1
    assert "já está rodando" in str(errors[0])
    assert len(captured) == 1  # só um processo foi de fato criado

    saved = live_control._read_state("swing")
    assert saved is not None
    assert saved["pid"] == results[0]["pid"]


# ---------- catalogo de slots: magic/simbolo disjuntos ---------------------

def _slot(**over):
    from core.config import Slot

    base = dict(id="a", kind="daily", robot_key="x", label="A", dek="",
                order=0, magic=1)
    base.update(over)
    return Slot(**base)


def test_assert_slots_disjuntos_recusa_magic_repetido(isolated, monkeypatch):
    """`SLOTS` é editável — e o custo de dois slots com o mesmo `magic` é
    dinheiro real (ordens indistinguíveis na corretora). A checagem existe
    no código, não só na revisão do catálogo.

    `robot_key="x"` não existe em registry nenhum, mas isso não importa
    aqui: o `magic` repetido é recusado ANTES de qualquer resolução de
    robô/símbolo (ver ordem das checagens em `_assert_slots_disjuntos`)."""
    from core import config as core_config

    gemeos = (_slot(id="a", magic=777), _slot(id="b", magic=777, order=1))
    monkeypatch.setattr(core_config, "SLOTS", gemeos)

    with pytest.raises(RuntimeError, match="mesmo `magic`"):
        live_control._assert_slots_disjuntos(gemeos[0], "x")


def test_assert_slots_disjuntos_recusa_simbolo_repetido_quando_outro_esta_live(
    isolated, monkeypatch,
):
    """Conta NETTING: duas posições no mesmo símbolo se FUNDEM numa só,
    independente de `magic` — e os dois livros-caixa passam a mentir.

    Símbolo não é mais campo do slot (removido 2026-08-21) — vem do robô
    ESCOLHIDO. Dois slots intraday resolvendo o MESMO robô (`gremah`, sem
    conta ainda em nenhum dos dois — cai no default do catálogo) colidem no
    símbolo dele (PMAM3), que é o cenário que este teste cobre.

    Mode-aware (2026-08-24): o risco só existe com ORDEM REAL concorrente —
    aqui o "outro" slot ('b') está com um processo de pé em `execution_mode
    ="live"`, então subir 'a' também em live tem de ser recusado."""
    from core import config as core_config

    gemeos = (_slot(id="a", kind="intraday", robot_key="gremah", magic=1),
              _slot(id="b", kind="intraday", robot_key="gremah", magic=2, order=1))
    monkeypatch.setattr(core_config, "SLOTS", gemeos)
    monkeypatch.setattr(live_control, "_pid_alive", lambda pid: True)
    live_control._write_state(
        "b", {"pid": 1, "started_at": "2026-08-24T00:00:00+00:00",
              "config": {"execution_mode": "live"}},
    )

    with pytest.raises(RuntimeError, match="mesmo\\(s\\) símbolo"):
        live_control._assert_slots_disjuntos(gemeos[0], "gremah", "live")


def test_assert_slots_disjuntos_permite_simbolo_repetido_se_outro_e_sombra(
    isolated, monkeypatch,
):
    """Mode-aware (2026-08-24, pedido do dono): sombra nunca manda ordem pra
    corretora, então dois robôs no mesmo símbolo só colidem de verdade quando
    os DOIS estão em modo live ao mesmo tempo. Aqui 'b' está rodando, mas em
    sombra -- subir 'a' em live não pode ser bloqueado."""
    from core import config as core_config

    gemeos = (_slot(id="a", kind="intraday", robot_key="gremah", magic=1),
              _slot(id="b", kind="intraday", robot_key="gremah", magic=2, order=1))
    monkeypatch.setattr(core_config, "SLOTS", gemeos)
    monkeypatch.setattr(live_control, "_pid_alive", lambda pid: True)
    live_control._write_state(
        "b", {"pid": 1, "started_at": "2026-08-24T00:00:00+00:00",
              "config": {"execution_mode": "shadow"}},
    )

    live_control._assert_slots_disjuntos(gemeos[0], "gremah", "live")  # não levanta


def test_assert_slots_disjuntos_permite_simbolo_repetido_se_outro_nao_roda(
    isolated, monkeypatch,
):
    """Idem, mas com 'b' sem processo nenhum de pé: só ter o CARTÃO criado no
    mesmo ativo (nunca clicou Iniciar) não é risco nenhum -- nenhuma ordem
    sai enquanto não houver processo vivo do outro lado."""
    from core import config as core_config

    gemeos = (_slot(id="a", kind="intraday", robot_key="gremah", magic=1),
              _slot(id="b", kind="intraday", robot_key="gremah", magic=2, order=1))
    monkeypatch.setattr(core_config, "SLOTS", gemeos)

    live_control._assert_slots_disjuntos(gemeos[0], "gremah", "live")  # não levanta


def test_assert_slots_disjuntos_colisao_traz_slot_pra_parar(isolated, monkeypatch):
    """`SlotSymbolCollisionError` (2026-08-25) carrega o suficiente pro
    painel oferecer "parar o outro robô" direto no card de erro em vez de só
    uma mensagem — ver `dashboard/app.py::operacao_iniciar` e
    `partials/operacao_colisao.html`. Sem posição nem ordem pendente no outro
    lado, `pode_parar` é True."""
    from core import config as core_config

    gemeos = (_slot(id="a", kind="intraday", robot_key="gremah", magic=1, label="A"),
              _slot(id="b", kind="intraday", robot_key="gremah", magic=2, order=1, label="B"))
    monkeypatch.setattr(core_config, "SLOTS", gemeos)
    monkeypatch.setattr(live_control, "_pid_alive", lambda pid: True)
    live_control._write_state(
        "b", {"pid": 1, "started_at": "2026-08-24T00:00:00+00:00",
              "config": {"execution_mode": "live"}},
    )

    with pytest.raises(live_control.SlotSymbolCollisionError) as exc_info:
        live_control._assert_slots_disjuntos(gemeos[0], "gremah", "live")

    err = exc_info.value
    assert err.slot_id == "b"
    assert err.slot_label == "B"
    assert err.symbols == ["PMAM3"]
    assert err.pode_parar is True
    assert err.motivo_bloqueio is None


def test_assert_slots_disjuntos_colisao_bloqueia_parar_com_ordem_pendente(isolated, monkeypatch):
    """Com o outro lado tendo mandado ordem de entrada ainda não resolvida
    (`pending_entry_refs`), `pode_parar` vira False — parar o processo agora
    deixaria essa ordem sem ninguém vigiando até o próximo `Iniciar`."""
    from core import config as core_config

    gemeos = (_slot(id="a", kind="intraday", robot_key="gremah", magic=1, label="A"),
              _slot(id="b", kind="intraday", robot_key="gremah", magic=2, order=1, label="B"))
    monkeypatch.setattr(core_config, "SLOTS", gemeos)
    monkeypatch.setattr(live_control, "_pid_alive", lambda pid: True)
    live_control._write_state(
        "b", {"pid": 1, "started_at": "2026-08-24T00:00:00+00:00",
              "config": {"execution_mode": "live"}},
    )
    with live_store.live_journal() as conn:
        conta = live_store.ensure_account(
            conn, name="b", mode="mt5", initial_capital=100.0,
            investment_robot="gremah", withdrawal_robot="", symbol="PMAM3",
        )
        conta.policy_state = {"intraday": {"pending_entry_refs": ["abc123"]}}
        live_store.save_account(conn, conta)

    with pytest.raises(live_control.SlotSymbolCollisionError) as exc_info:
        live_control._assert_slots_disjuntos(gemeos[0], "gremah", "live")

    err = exc_info.value
    assert err.pode_parar is False
    assert "aguarde" in err.motivo_bloqueio


def test_catalogo_oficial_de_slots_e_disjunto(isolated):
    """O catálogo REAL do projeto tem de passar na própria checagem, com o
    robô DEFAULT de cada slot (nenhuma conta ainda existe no banco isolado
    deste teste)."""
    from core.config import SLOTS

    for slot in SLOTS:
        live_control._assert_slots_disjuntos(slot, slot.robot_key)


# ---------- universo por slot ---------------------------------------------

def test_universe_for_slot_intraday_e_o_simbolo_declarado(isolated):
    """O slot de day trade NÃO passa pelo registry de swing:
    `get_strategy("gremah")` levantaria `KeyError` (o scan de
    `strategy.discovery` exige `issubclass(obj, Strategy)` e nem varre o
    pacote `daytrade`) e isso viraria um 500 em `/operacao`."""
    assert live_control.universe_for_slot(DAYTRADE) == ("PMAM3",)


def test_universe_for_slot_swing_vem_do_robo(isolated):
    """Slot diário usa o universo do PRÓPRIO robô (`Strategy.
    universe_tickers`), não uma `WATCHLIST` fixa — robôs que escolhem por
    liquidez têm dezenas de papéis, e alimentar só sete rodaria uma
    estratégia que nunca foi testada, em silêncio."""
    universo = live_control.universe_for_slot("swing")
    assert len(universo) > 0
    assert all(isinstance(t, str) for t in universo)


# ---------- detecção no terminal MT5 (por slot) ---------------------------

class _FakeLotBroker:
    def __init__(self, value, captured, **kwargs):
        captured.append(kwargs)
        self._value = value

    def detect_shares_per_lot(self, tickers):
        self.tickers = list(tickers)
        return self._value


def test_detect_shares_per_lot_usa_credenciais_salvas_e_universo_do_slot(monkeypatch):
    """Credenciais salvas vão pro construtor do broker, NUNCA via
    `os.environ` (o processo do dashboard não recebe essas variáveis); os
    tickers consultados são os do universo DAQUELE slot."""
    monkeypatch.setattr(live_control, "load_credentials", lambda: {
        "mt5_login": "12345", "mt5_password": "segredo",
        "mt5_server": "Corretora-Live", "mt5_terminal_path": r"C:\mt5\terminal64.exe",
    })
    captured: list = []
    fakes: list = []
    import live.broker_mt5 as broker_mt5

    def _factory(**kwargs):
        fake = _FakeLotBroker(1.0, captured, **kwargs)
        fakes.append(fake)
        return fake

    monkeypatch.setattr(broker_mt5, "MT5Broker", _factory)

    assert live_control.detect_shares_per_lot(DAYTRADE) == pytest.approx(1.0)
    assert captured[0]["login"] == 12345
    assert captured[0]["server"] == "Corretora-Live"
    assert fakes[0].tickers == ["PMAM3"]


def test_detect_shares_per_lot_sem_valor_unico_devolve_none(monkeypatch):
    """Terminal fechado/deslogado, ou papéis com contract_size diferente entre
    si: repassa `None` -- nunca inventa um valor default."""
    monkeypatch.setattr(live_control, "load_credentials", lambda: {})
    import live.broker_mt5 as broker_mt5
    monkeypatch.setattr(broker_mt5, "MT5Broker",
                        lambda **kwargs: _FakeLotBroker(None, [], **kwargs))

    assert live_control.detect_shares_per_lot(DAYTRADE) is None


class _FakeFractionalBroker:
    def __init__(self, value, captured, **kwargs):
        captured.append(kwargs)
        self._value = value

    def detect_fractional_symbol_map(self, tickers):
        self.tickers = list(tickers)
        return self._value

    def symbol_for(self, ticker):
        # Mesmo default de `MT5Broker.symbol_for` (sem override) -- usado por
        # `live_control.detect_fractional_symbol_map()` pra filtrar do mapa
        # os tickers onde o "fracionário" devolvido é só o símbolo base.
        return ticker[: -len(".SA")] if ticker.endswith(".SA") else ticker


def test_detect_fractional_symbol_map_do_slot_de_day_trade(monkeypatch):
    """PMAM3 -> PMAM3F é o que torna uma ordem de R$14 executável (ver
    `mt5_fractional_execution_2026_08_21` na memória do projeto)."""
    monkeypatch.setattr(live_control, "load_credentials", lambda: {"mt5_login": "12345"})
    captured: list = []
    fakes: list = []
    import live.broker_mt5 as broker_mt5

    def _factory(**kwargs):
        fake = _FakeFractionalBroker({"PMAM3": "PMAM3F"}, captured, **kwargs)
        fakes.append(fake)
        return fake

    monkeypatch.setattr(broker_mt5, "MT5Broker", _factory)

    assert live_control.detect_fractional_symbol_map(DAYTRADE) == {"PMAM3": "PMAM3F"}
    assert captured[0]["login"] == 12345
    assert fakes[0].tickers == ["PMAM3"]


def test_detect_fractional_symbol_map_filtra_quem_nao_tem_fracionario(monkeypatch):
    """`MT5Broker.detect_fractional_symbol_map` devolve mapa COMPLETO (com
    fallback pro símbolo base); esta função filtra só quem TEM fracionário de
    fato -- um ticker ausente aqui significa "sem fracionário", não "usa o
    símbolo base"."""
    monkeypatch.setattr(live_control, "load_credentials", lambda: {})
    import live.broker_mt5 as broker_mt5
    monkeypatch.setattr(
        broker_mt5, "MT5Broker",
        lambda **kwargs: _FakeFractionalBroker({"PMAM3": "PMAM3"}, [], **kwargs),
    )

    assert live_control.detect_fractional_symbol_map(DAYTRADE) == {}


def test_detect_fractional_symbol_map_falha_de_conexao_devolve_none(monkeypatch):
    """Terminal fechado/deslogado: repassa `None` -- o chamador
    (`app.py::operacao_iniciar`) trata como "sem fracionário" (lote padrão),
    nunca como erro fatal."""
    monkeypatch.setattr(live_control, "load_credentials", lambda: {})
    import live.broker_mt5 as broker_mt5
    monkeypatch.setattr(broker_mt5, "MT5Broker",
                        lambda **kwargs: _FakeFractionalBroker(None, [], **kwargs))

    assert live_control.detect_fractional_symbol_map(DAYTRADE) is None
