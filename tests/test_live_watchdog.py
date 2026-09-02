"""Watchdog de travamento — `dashboard/live_control.py`, seção "watchdog de
travamento (heartbeat)".

Achado ao vivo em 02/09/2026: os 7 supervisores de day trade travaram (PID
vivo, CPU acumulada parada, `tasklist` os via "rodando") por 21h+, sem nenhum
sinal no sistema além do PID continuar de pé. Estes testes protegem a
INTERPRETAÇÃO do heartbeat (idade velha + PID vivo = travado; PID morto =
parado de propósito, nunca travado; heartbeat ausente = processo recém-subido,
nunca travado) e o ciclo detectar -> logar -> notificar -> reiniciar ->
cooldown, sem nunca chamar o SO ou a corretora de verdade.

Isolamento: mesmo fixture `isolated` de `test_live_control.py` (repetido aqui,
não importado, para este arquivo não depender da ordem/presença do outro sob
`--dist load`) — `_STATE_PATH`/`_LOG_DIR` em `tmp_path`, banco de diário em
`tmp_path`, `_processos_do_sistema` neutralizado. Adiciona `_restart_attempts`
zerado a cada teste: é um dict em memória, no MÓDULO — sem resetar, dois
testes que tocam o mesmo slot_id no mesmo worker do pytest-xdist vazariam
cooldown de um para o outro.
"""
from __future__ import annotations

import os
import time

import pytest

from dashboard import live_control
from journal import live_store
from live import runtime as live_runtime

DAYTRADE = "dt-gremah-pmam3-shadow"
SWING = "swing"


class _FakeProc:
    def __init__(self, pid: int, poll_value=None):
        self.pid = pid
        self._poll_value = poll_value

    def poll(self):
        return self._poll_value


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    state_path = tmp_path / "live_process.json"
    db_path = tmp_path / "live_watchdog_test.sqlite"
    monkeypatch.setattr(live_control, "_STATE_PATH", state_path)
    monkeypatch.setattr(live_control, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(live_control, "_STARTUP_GRACE_SECONDS", 0)
    monkeypatch.setattr(live_control, "_restart_attempts", {})
    monkeypatch.setattr(live_runtime, "DB_PATH", db_path)
    monkeypatch.setattr(live_store.live_journal.__wrapped__, "__defaults__", (db_path,))
    from live import intraday_runtime

    monkeypatch.setattr(intraday_runtime, "LIVE_DB_PATH", db_path)
    monkeypatch.setattr(live_control, "_processos_do_sistema", lambda: [])
    return {"state": state_path, "dir": tmp_path, "db": db_path}


def _seed_account(db_path, slot: str, *, robot: str, cash: float, shadow: bool) -> None:
    from core.config import slot_by_id

    # `symbol` precisa vir preenchido para um slot de day trade aparecer em
    # `dashboard.slots.daytrade_slots` (lido de `live_store.accounts_with_
    # symbol`) -- sem isto `status_all()`/`slots_travados()` nunca enxergam o
    # slot, mesmo com o arquivo de estado (`live_process.json`) apontando um
    # PID de verdade para ele.
    slot_obj = slot_by_id(slot)
    symbol = slot_obj.symbol if slot_obj.is_intraday else ""
    with live_store.live_journal(db_path) as conn:
        acc = live_store.ensure_account(
            conn, name=slot, mode="mt5", initial_capital=cash,
            investment_robot=robot, withdrawal_robot="", symbol=symbol,
        )
        if shadow:
            acc.cash_sombra = cash
        else:
            acc.cash = cash
        live_store.save_account(conn, acc)


def _grava_estado(state_path, slot_id: str, pid, config: dict) -> None:
    import json

    todos = {"version": 2, "slots": {slot_id: {
        "pid": pid, "started_at": "2026-09-01T12:00:00+00:00", "config": config,
    }}}
    state_path.write_text(json.dumps(todos), encoding="utf-8")


def _toca_heartbeat(dir_, slot_id: str, idade_segundos: float) -> None:
    """Cria/atualiza o heartbeat do slot com mtime `idade_segundos` no
    passado -- simula um processo que tocou o heartbeat há X segundos."""
    path = dir_ / f"live_process.{slot_id}.heartbeat"
    path.touch()
    quando = time.time() - idade_segundos
    os.utime(path, (quando, quando))


# ---------- idade do heartbeat / limiar -------------------------------------

def test_heartbeat_ausente_devolve_none(isolated):
    assert live_control._heartbeat_age_seconds(DAYTRADE) is None


def test_heartbeat_idade_bate_com_o_mtime(isolated):
    _toca_heartbeat(isolated["dir"], DAYTRADE, 42.0)
    idade = live_control._heartbeat_age_seconds(DAYTRADE)
    assert idade == pytest.approx(42.0, abs=2.0)


def test_limiar_day_trade_e_o_piso_nao_o_multiplo(isolated):
    from core.config import slot_by_id

    slot = slot_by_id(DAYTRADE)
    # passo de 5s * margem 6 = 30s, abaixo do piso de 180s -- o piso vence.
    assert live_control._hang_threshold_seconds(slot) == 180.0


def test_limiar_swing_usa_o_multiplo_do_passo_de_60s(isolated):
    from core.config import slot_by_id

    slot = slot_by_id(SWING)
    assert live_control._hang_threshold_seconds(slot) == 360.0


# ---------- slots_travados ---------------------------------------------------

def test_pid_morto_nunca_e_travamento_mesmo_com_heartbeat_velho(isolated, monkeypatch):
    _seed_account(isolated["db"], DAYTRADE, robot="gremah", cash=1_000.0, shadow=True)
    _grava_estado(isolated["state"], DAYTRADE, pid=None, config={"slot": DAYTRADE})
    _toca_heartbeat(isolated["dir"], DAYTRADE, 10_000.0)

    assert live_control.slots_travados() == []


def test_pid_vivo_heartbeat_fresco_nao_e_travamento(isolated, monkeypatch):
    _seed_account(isolated["db"], DAYTRADE, robot="gremah", cash=1_000.0, shadow=True)
    _grava_estado(isolated["state"], DAYTRADE, pid=4242, config={"slot": DAYTRADE})
    _toca_heartbeat(isolated["dir"], DAYTRADE, 5.0)
    monkeypatch.setattr(live_control, "_pids_alive", lambda pids: set(pids))

    assert live_control.slots_travados() == []


def test_pid_vivo_heartbeat_velho_e_travamento(isolated, monkeypatch):
    _seed_account(isolated["db"], DAYTRADE, robot="gremah", cash=1_000.0, shadow=True)
    _grava_estado(isolated["state"], DAYTRADE, pid=4242, config={"slot": DAYTRADE})
    _toca_heartbeat(isolated["dir"], DAYTRADE, 999.0)  # > limiar de 180s
    monkeypatch.setattr(live_control, "_pids_alive", lambda pids: set(pids))

    assert live_control.slots_travados() == [DAYTRADE]


def test_heartbeat_nunca_tocado_nao_e_travamento(isolated, monkeypatch):
    """Processo recém-subido (`start()` ainda não teve tempo de dar a
    primeira volta do laço) -- arquivo de heartbeat nem existe ainda."""
    _seed_account(isolated["db"], DAYTRADE, robot="gremah", cash=1_000.0, shadow=True)
    _grava_estado(isolated["state"], DAYTRADE, pid=4242, config={"slot": DAYTRADE})
    monkeypatch.setattr(live_control, "_pids_alive", lambda pids: set(pids))

    assert live_control.slots_travados() == []


# ---------- cooldown ----------------------------------------------------------

def test_cooldown_libera_ate_o_limite_e_depois_desiste(isolated):
    for _ in range(live_control._MAX_AUTO_RESTARTS):
        assert live_control._registrar_tentativa(DAYTRADE) is True
    assert live_control._registrar_tentativa(DAYTRADE) is False


def test_cooldown_e_por_slot(isolated):
    for _ in range(live_control._MAX_AUTO_RESTARTS):
        live_control._registrar_tentativa(DAYTRADE)
    assert live_control._registrar_tentativa(DAYTRADE) is False
    assert live_control._registrar_tentativa(SWING) is True


def test_cooldown_expira_fora_da_janela(isolated, monkeypatch):
    agora = time.time()
    velhas = [agora - live_control._COOLDOWN_WINDOW_SECONDS - 1] * live_control._MAX_AUTO_RESTARTS
    monkeypatch.setattr(live_control, "_restart_attempts", {DAYTRADE: velhas})

    assert live_control._registrar_tentativa(DAYTRADE) is True


# ---------- reiniciar_travado ------------------------------------------------

def test_reiniciar_travado_sem_pid_recusa(isolated):
    with pytest.raises(RuntimeError, match="não está rodando"):
        live_control.reiniciar_travado(DAYTRADE)


def test_reiniciar_travado_sem_robo_gravado_recusa(isolated):
    _grava_estado(isolated["state"], DAYTRADE, pid=4242, config={"slot": DAYTRADE})
    _seed_account(isolated["db"], DAYTRADE, robot="", cash=1_000.0, shadow=True)

    with pytest.raises(RuntimeError, match="sem conta/robô gravado"):
        live_control.reiniciar_travado(DAYTRADE)


def test_reiniciar_travado_mata_o_velho_redeteta_e_sobe_de_novo(isolated, monkeypatch):
    _grava_estado(isolated["state"], DAYTRADE, pid=4242,
                  config={"slot": DAYTRADE, "notify_min_level": "warn",
                          "mt5_symbol_map": {"velho": "contrato-vencido"}})
    _seed_account(isolated["db"], DAYTRADE, robot="gremah", cash=1_000.0, shadow=True)

    mortos = []
    monkeypatch.setattr(live_control, "_matar_arvore", mortos.append)
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda *a, **k: 1.0)
    # `mt5_symbol_map` REDETECTADO -- não é o `{"velho": ...}` salvo no
    # estado antigo, é isto que prova que o restart não confia em cache
    # velho (contrato de futuro pode ter rolado durante a janela travada).
    monkeypatch.setattr(live_control, "detect_futures_symbol_map",
                        lambda *a, **k: {"novo": "contrato-fresco"})
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc(pid=9999))
    monkeypatch.setattr(live_control, "_pids_alive", lambda pids: set(pids))

    novo_estado = live_control.reiniciar_travado(DAYTRADE)

    assert mortos == [4242]
    assert novo_estado["pid"] == 9999
    assert novo_estado["config"]["mt5_symbol_map"] == {"novo": "contrato-fresco"}
    assert live_control._read_state(DAYTRADE)["pid"] == 9999


# ---------- verificar_e_recuperar_travamentos --------------------------------

def _sem_alerta_externo(monkeypatch):
    """`_load_cli()._build_notifier` lê variável de ambiente de verdade --
    garante `NullNotifier` (sem tentar rede) mesmo que a máquina de quem
    rodar o teste tenha TELEGRAM_BOT_TOKEN etc. configurado no shell."""
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_HOST",
               "SMTP_USER", "SMTP_PASSWORD", "SMTP_TO"):
        monkeypatch.delenv(var, raising=False)


def _eventos(db_path, slot_id: str) -> list[tuple]:
    with live_store.live_journal(db_path) as conn:
        conta = live_store.load_account(conn, slot_id)
        cur = conn.execute(
            "SELECT level, source, message FROM live_events WHERE account_id = ? ORDER BY id",
            (conta.id,),
        )
        return cur.fetchall()


def test_verificar_recupera_reinicia_slot_travado(isolated, monkeypatch):
    _sem_alerta_externo(monkeypatch)
    _grava_estado(isolated["state"], DAYTRADE, pid=4242,
                  config={"slot": DAYTRADE, "notify_min_level": "warn"})
    _seed_account(isolated["db"], DAYTRADE, robot="gremah", cash=1_000.0, shadow=True)
    _toca_heartbeat(isolated["dir"], DAYTRADE, 999.0)

    monkeypatch.setattr(live_control, "_pids_alive", lambda pids: set(pids))
    monkeypatch.setattr(live_control, "_matar_arvore", lambda pid: None)
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda *a, **k: 1.0)
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda *a, **k: None)
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc(pid=9999))

    relatorio = live_control.verificar_e_recuperar_travamentos()

    assert relatorio == [{"slot": DAYTRADE, "idade_heartbeat_s": pytest.approx(999.0, abs=2.0),
                          "acao": "reiniciado",
                          "detalhe": relatorio[0]["detalhe"]}]
    assert live_control._read_state(DAYTRADE)["pid"] == 9999
    niveis = [linha[0] for linha in _eventos(isolated["db"], DAYTRADE)]
    assert niveis == ["error", "warn"]  # achado (error) + reiniciado (warn)


def test_verificar_respeita_cooldown_e_nao_reinicia(isolated, monkeypatch):
    _sem_alerta_externo(monkeypatch)
    _grava_estado(isolated["state"], DAYTRADE, pid=4242, config={"slot": DAYTRADE})
    _seed_account(isolated["db"], DAYTRADE, robot="gremah", cash=1_000.0, shadow=True)
    _toca_heartbeat(isolated["dir"], DAYTRADE, 999.0)
    monkeypatch.setattr(live_control, "_pids_alive", lambda pids: set(pids))

    chamou_popen = []
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        lambda argv, **kw: chamou_popen.append(argv) or _FakeProc(pid=9999))
    for _ in range(live_control._MAX_AUTO_RESTARTS):
        live_control._registrar_tentativa(DAYTRADE)

    relatorio = live_control.verificar_e_recuperar_travamentos()

    assert relatorio[0]["acao"] == "cooldown"
    assert chamou_popen == []                       # nunca tentou subir de novo
    assert live_control._read_state(DAYTRADE)["pid"] == 4242  # continua "travado"


def test_verificar_registra_falha_sem_derrubar_o_laco(isolated, monkeypatch):
    _sem_alerta_externo(monkeypatch)
    _grava_estado(isolated["state"], DAYTRADE, pid=4242, config={"slot": DAYTRADE})
    _seed_account(isolated["db"], DAYTRADE, robot="gremah", cash=1_000.0, shadow=True)
    _toca_heartbeat(isolated["dir"], DAYTRADE, 999.0)
    monkeypatch.setattr(live_control, "_pids_alive", lambda pids: set(pids))

    def _falha(slot_id):
        raise RuntimeError("terminal MT5 fechado (simulado)")

    monkeypatch.setattr(live_control, "reiniciar_travado", _falha)

    relatorio = live_control.verificar_e_recuperar_travamentos()

    assert relatorio[0]["acao"] == "falhou"
    assert "terminal MT5 fechado" in relatorio[0]["detalhe"]
