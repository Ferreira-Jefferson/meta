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
    # passo de 5s * margem 6 = 30s, bem abaixo do piso de 900s -- o piso vence.
    assert live_control._hang_threshold_seconds(slot) == 900.0


def test_limiar_swing_tambem_usa_o_piso(isolated):
    from core.config import slot_by_id

    slot = slot_by_id(SWING)
    # passo de 60s * margem 6 = 360s, ainda abaixo do piso de 900s.
    assert live_control._hang_threshold_seconds(slot) == 900.0


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


# ---------- espiral de reinício (achado 04/09/2026) --------------------------
#
# `db/live.sqlite`, `live_events` `source='watchdog'`, slot
# `dt-wdo_grid_reload_maker-wdo@-shadow`: reinícios automáticos às 13:28:53,
# 13:45:04 e 14:01:00 de 04/09/2026 -- gaps de 971s e 956s. Cada um desses
# gaps já é MAIOR que a janela de cooldown antiga (`_COOLDOWN_WINDOW_SECONDS
# == _HEARTBEAT_FLOOR_SECONDS`, 900s): o ciclo completo "trava -> detecta
# (piso 900s) -> mata -> sobe" nunca cabe dentro de uma janela do MESMO
# tamanho do próprio piso. Os dois testes abaixo replicam esse gap real
# (`_GAP_REAL_SEGUNDOS`) com um relógio FAKE (nunca `time.sleep`, nunca
# depende do relógio de parede) para provar a espiral com a janela antiga e
# provar que ela para de existir com a janela atual (derivada de
# `_RESTART_CYCLE_SECONDS`, ver comentário da constante em `live_control.py`).

_GAP_REAL_SEGUNDOS = 971.0  # pior gap medido ao vivo entre dois restarts do watchdog


class _RelogioFake:
    """Substitui o módulo `time` inteiro dentro de `live_control` por algo
    com só `.time()` -- `_registrar_tentativa` não chama `time.sleep`, então
    não precisa de mais nada, e isto evita monkeypatchar `time.time` GLOBAL
    (que afetaria qualquer outro código do processo durante o teste)."""

    def __init__(self, inicio: float):
        self.agora = inicio

    def time(self) -> float:
        return self.agora


def test_espiral_com_janela_antiga_igual_ao_piso_nunca_desiste(isolated, monkeypatch):
    """ANTES do fix: com a janela do MESMO tamanho do piso (o valor antigo,
    `_COOLDOWN_WINDOW_SECONDS = _HEARTBEAT_FLOOR_SECONDS`), reinícios
    espaçados pelo gap real (971s) nunca acumulam -- a tentativa mais antiga
    sempre cai da lista antes da próxima ser registrada, o contador nunca
    passa de 1, e o watchdog reiniciaria o MESMO slot para sempre."""
    monkeypatch.setattr(live_control, "_COOLDOWN_WINDOW_SECONDS",
                        live_control._HEARTBEAT_FLOOR_SECONDS)
    relogio = _RelogioFake(1_757_000_000.0)
    monkeypatch.setattr(live_control, "time", relogio)

    resultados = []
    for _ in range(6):
        resultados.append(live_control._registrar_tentativa(DAYTRADE))
        relogio.agora += _GAP_REAL_SEGUNDOS

    assert resultados == [True] * 6  # NUNCA desiste -- é a espiral do bug de desenho


def test_espiral_com_janela_atual_acumula_e_desiste_no_limite(isolated, monkeypatch):
    """DEPOIS do fix: `_COOLDOWN_WINDOW_SECONDS` (produção, sem monkeypatch)
    deriva de `_RESTART_CYCLE_SECONDS` com folga sobre o mínimo estrito. O
    MESMO gap real (971s) agora ACUMULA: as `_MAX_AUTO_RESTARTS` primeiras
    tentativas ainda passam, e a que reproduziria a espiral (a
    `_MAX_AUTO_RESTARTS + 1`-ésima) o watchdog desiste."""
    relogio = _RelogioFake(1_757_000_000.0)
    monkeypatch.setattr(live_control, "time", relogio)

    resultados = []
    for _ in range(live_control._MAX_AUTO_RESTARTS + 1):
        resultados.append(live_control._registrar_tentativa(DAYTRADE))
        relogio.agora += _GAP_REAL_SEGUNDOS

    esperado = [True] * live_control._MAX_AUTO_RESTARTS + [False]
    assert resultados == esperado


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
    # Sem posição na corretora -- caminho normal de restart (caso (b) do
    # risco fechado em 04/09/2026: watchdog/reiniciar_travado SEM posição
    # continuam reiniciando como antes). Nunca chama a corretora de verdade.
    monkeypatch.setattr(live_control, "_posicao_aberta_na_corretora",
                        lambda slot, robot_key: (False, ""))
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
    """Caso (b) do risco fechado em 04/09/2026: SEM posição aberta na
    corretora, o watchdog continua reiniciando como antes."""
    _sem_alerta_externo(monkeypatch)
    _grava_estado(isolated["state"], DAYTRADE, pid=4242,
                  config={"slot": DAYTRADE, "notify_min_level": "warn"})
    _seed_account(isolated["db"], DAYTRADE, robot="gremah", cash=1_000.0, shadow=True)
    _toca_heartbeat(isolated["dir"], DAYTRADE, 999.0)

    monkeypatch.setattr(live_control, "_pids_alive", lambda pids: set(pids))
    monkeypatch.setattr(live_control, "_matar_arvore", lambda pid: None)
    monkeypatch.setattr(live_control, "_posicao_aberta_na_corretora",
                        lambda slot, robot_key: (False, ""))
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
    monkeypatch.setattr(live_control, "_posicao_aberta_na_corretora",
                        lambda slot, robot_key: (False, ""))

    chamou_popen = []
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        lambda argv, **kw: chamou_popen.append(argv) or _FakeProc(pid=9999))
    for _ in range(live_control._MAX_AUTO_RESTARTS):
        live_control._registrar_tentativa(DAYTRADE)

    relatorio = live_control.verificar_e_recuperar_travamentos()

    assert relatorio[0]["acao"] == "cooldown"
    assert chamou_popen == []                       # nunca tentou subir de novo
    assert live_control._read_state(DAYTRADE)["pid"] == 4242  # continua "travado"


def test_verificar_desiste_grava_evento_e_notifica(isolated, monkeypatch):
    """Caminho de "desistir e alertar" (~1712-1724 de `live_control.py`):
    quando o cooldown já está no limite, `verificar_e_recuperar_travamentos`
    tem de GRAVAR o evento de desistência em `live_events` E notificar pelo
    canal externo -- sem os dois, o slot fica travado em silêncio esperando
    alguém notar por conta própria, o oposto do que o watchdog existe para
    fazer."""
    _grava_estado(isolated["state"], DAYTRADE, pid=4242, config={"slot": DAYTRADE})
    _seed_account(isolated["db"], DAYTRADE, robot="gremah", cash=1_000.0, shadow=True)
    _toca_heartbeat(isolated["dir"], DAYTRADE, 999.0)
    monkeypatch.setattr(live_control, "_pids_alive", lambda pids: set(pids))
    monkeypatch.setattr(live_control, "_posicao_aberta_na_corretora",
                        lambda slot, robot_key: (False, ""))

    notificacoes = []

    class _NotifierEspiao:
        def notify(self, level, source, message, payload=None):
            notificacoes.append((level, source, message))

    class _CliFake:
        def _build_notifier(self, notify_min_level):
            return _NotifierEspiao()

    monkeypatch.setattr(live_control, "_load_cli", lambda: _CliFake())

    chamou_popen = []
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        lambda argv, **kw: chamou_popen.append(argv) or _FakeProc(pid=9999))
    for _ in range(live_control._MAX_AUTO_RESTARTS):
        live_control._registrar_tentativa(DAYTRADE)

    relatorio = live_control.verificar_e_recuperar_travamentos()

    assert relatorio[0]["acao"] == "cooldown"
    assert chamou_popen == []

    eventos = _eventos(isolated["db"], DAYTRADE)
    niveis = [linha[0] for linha in eventos]
    mensagens = [linha[2] for linha in eventos]
    assert niveis == ["error", "error"]  # achado (travamento) + desistência
    assert "desistiu de reiniciar sozinho" in mensagens[-1]

    # notificou as DUAS vezes -- achado do travamento e desistência do watchdog
    assert len(notificacoes) == 2
    assert notificacoes[-1][2] == mensagens[-1]


def test_verificar_registra_falha_sem_derrubar_o_laco(isolated, monkeypatch):
    _sem_alerta_externo(monkeypatch)
    _grava_estado(isolated["state"], DAYTRADE, pid=4242, config={"slot": DAYTRADE})
    _seed_account(isolated["db"], DAYTRADE, robot="gremah", cash=1_000.0, shadow=True)
    _toca_heartbeat(isolated["dir"], DAYTRADE, 999.0)
    monkeypatch.setattr(live_control, "_pids_alive", lambda pids: set(pids))
    monkeypatch.setattr(live_control, "_posicao_aberta_na_corretora",
                        lambda slot, robot_key: (False, ""))

    def _falha(slot_id):
        raise RuntimeError("terminal MT5 fechado (simulado)")

    monkeypatch.setattr(live_control, "reiniciar_travado", _falha)

    relatorio = live_control.verificar_e_recuperar_travamentos()

    assert relatorio[0]["acao"] == "falhou"
    assert "terminal MT5 fechado" in relatorio[0]["detalhe"]


# ---------- posição aberta bloqueia restart automático (achado 04/09/2026) --
#
# Risco fechado nesta data: o watchdog reiniciava um slot travado sem
# perguntar à corretora se havia posição aberta -- e um restart automático
# dispara o protocolo de buraco do runtime (`IntradayLiveRuntime.
# _start_session`/`force_flatten`), que pode ACHATAR a posição A MERCADO por
# decisão da infraestrutura, não do mercado. Os quatro testes abaixo cobrem
# os casos pedidos: (a) posição aberta -> não reinicia, grava evento, notifica;
# (b) sem posição -> reinicia como sempre (já coberto acima, nos testes que
# passaram a mockar `_posicao_aberta_na_corretora` retornando `(False, "")`);
# (c) consulta falhando -> NÃO reinicia (tri-estado, item 1.6 de
# LICOES_DE_PRODUCAO.md: "não sei" nunca autoriza ação); (d) caminho MANUAL
# com `permitir_com_posicao_aberta=True` reinicia mesmo com posição.


def test_watchdog_nao_reinicia_com_posicao_aberta_grava_evento_e_notifica(isolated, monkeypatch):
    """Caso (a): posição CONFIRMADA aberta na corretora -- o watchdog grava o
    achado, notifica e desiste desta rodada sem NUNCA tentar subir o
    processo de novo (nem contar como tentativa de restart)."""
    _grava_estado(isolated["state"], DAYTRADE, pid=4242, config={"slot": DAYTRADE})
    _seed_account(isolated["db"], DAYTRADE, robot="gremah", cash=1_000.0, shadow=True)
    _toca_heartbeat(isolated["dir"], DAYTRADE, 999.0)
    monkeypatch.setattr(live_control, "_pids_alive", lambda pids: set(pids))
    monkeypatch.setattr(
        live_control, "_posicao_aberta_na_corretora",
        lambda slot, robot_key: (True, "posição aberta em 'PMAM3' na corretora (long, qty=100)"),
    )

    notificacoes = []

    class _NotifierEspiao:
        def notify(self, level, source, message, payload=None):
            notificacoes.append((level, source, message))

    class _CliFake:
        def _build_notifier(self, notify_min_level):
            return _NotifierEspiao()

    monkeypatch.setattr(live_control, "_load_cli", lambda: _CliFake())

    chamou_popen = []
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        lambda argv, **kw: chamou_popen.append(argv) or _FakeProc(pid=9999))

    relatorio = live_control.verificar_e_recuperar_travamentos()

    assert relatorio == [{"slot": DAYTRADE, "idade_heartbeat_s": pytest.approx(999.0, abs=2.0),
                          "acao": "posicao_aberta", "detalhe": relatorio[0]["detalhe"]}]
    assert chamou_popen == []                                  # NUNCA sobe o processo com posição aberta
    assert live_control._read_state(DAYTRADE)["pid"] == 4242   # continua travado -- ninguém tocou
    assert live_control._restart_attempts.get(DAYTRADE, []) == []  # não consumiu tentativa do cooldown

    eventos = _eventos(isolated["db"], DAYTRADE)
    niveis = [linha[0] for linha in eventos]
    mensagens = [linha[2] for linha in eventos]
    assert niveis == ["error", "error"]  # achado do travamento + bloqueio por posição
    assert "posição aberta" in mensagens[-1]

    assert len(notificacoes) == 2
    assert notificacoes[-1][0] == "error"
    assert "posição aberta" in notificacoes[-1][2]


def test_watchdog_nao_reinicia_quando_consulta_de_posicao_falha(isolated, monkeypatch):
    """Caso (c): a consulta à corretora FALHA (terminal fora do ar, por
    exemplo) -- item 1.6 de LICOES_DE_PRODUCAO.md: "não sei" nunca vira "não
    tem", então o watchdog trata como se HOUVESSE posição e não reinicia."""
    _sem_alerta_externo(monkeypatch)
    _grava_estado(isolated["state"], DAYTRADE, pid=4242, config={"slot": DAYTRADE})
    _seed_account(isolated["db"], DAYTRADE, robot="gremah", cash=1_000.0, shadow=True)
    _toca_heartbeat(isolated["dir"], DAYTRADE, 999.0)
    monkeypatch.setattr(live_control, "_pids_alive", lambda pids: set(pids))
    monkeypatch.setattr(
        live_control, "_posicao_aberta_na_corretora",
        lambda slot, robot_key: (None, "sem conexao com o terminal MT5 (simulado)"),
    )

    chamou_popen = []
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        lambda argv, **kw: chamou_popen.append(argv) or _FakeProc(pid=9999))

    relatorio = live_control.verificar_e_recuperar_travamentos()

    assert relatorio[0]["acao"] == "posicao_aberta"
    assert chamou_popen == []
    assert live_control._read_state(DAYTRADE)["pid"] == 4242


def test_reiniciar_travado_recusa_com_posicao_e_permite_com_flag_explicita(isolated, monkeypatch):
    """Caso (d): o caminho MANUAL (`reiniciar_travado` chamado direto, como o
    painel/CLI fariam) também recusa por padrão com posição aberta -- e só
    reinicia se o chamador pedir `permitir_com_posicao_aberta=True`
    explicitamente. Prova as duas metades: sem o parâmetro recusa (mesmo
    risco do caminho automático), com o parâmetro segue em frente."""
    _grava_estado(isolated["state"], DAYTRADE, pid=4242,
                  config={"slot": DAYTRADE, "notify_min_level": "warn"})
    _seed_account(isolated["db"], DAYTRADE, robot="gremah", cash=1_000.0, shadow=True)

    mortos = []
    monkeypatch.setattr(live_control, "_matar_arvore", mortos.append)
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda *a, **k: 1.0)
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda *a, **k: None)
    monkeypatch.setattr(live_control.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc(pid=9999))
    monkeypatch.setattr(live_control, "_pids_alive", lambda pids: set(pids))
    monkeypatch.setattr(
        live_control, "_posicao_aberta_na_corretora",
        lambda slot, robot_key: (True, "posição aberta (simulada)"),
    )

    # SEM o parâmetro -- recusa, e NÃO mata o processo (checagem roda antes).
    with pytest.raises(live_control.PosicaoAbertaError, match="posição aberta"):
        live_control.reiniciar_travado(DAYTRADE)
    assert mortos == []
    assert live_control._read_state(DAYTRADE)["pid"] == 4242

    # COM o parâmetro explícito -- reinicia mesmo com posição confirmada.
    novo_estado = live_control.reiniciar_travado(DAYTRADE, permitir_com_posicao_aberta=True)
    assert mortos == [4242]
    assert novo_estado["pid"] == 9999
