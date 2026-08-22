"""Teste leve do dashboard FastAPI (`dashboard/app.py`) — cobre as rotas de
`/operacao` (criar/parar conta, credenciais, fragmento HTMX). Este arquivo
estabelece o padrao minimo: `TestClient` SEM usar `with` — entrar no `with`
dispara a
`lifespan` do app (3 loops de fundo que baixam dado de mercado/macro e
rerrodam o ranking automatico), o que faria o teste depender de rede e ser
lento/instavel por nada que a rota testada precise.

Isolamento do diario ao vivo
----------------------------
`journal.live_store.live_journal` e um `@contextlib.contextmanager`: o
parametro `db_path` tem seu default resolvido em tempo de DEFINICAO da
funcao geradora original, nao em tempo de chamada, e o wrapper que o
decorator devolve so repassa `*args/**kwds` — nao carrega o default ele
mesmo. Por isso `monkeypatch.setattr(..., "DB_PATH", tmp)` no MODULO nao
teria efeito nenhum sobre uma chamada `live_journal()` sem argumento; o
jeito de fato mudar o default e sobrescrever `__defaults__` da funcao
geradora original, acessivel via `live_journal.__wrapped__` (que
`functools.wraps`, usado por `contextmanager`, sempre preserva). Sem isso o
teste tocaria `db/journal.sqlite` de verdade.

`live.runtime.DB_PATH` e diferente: `LiveRuntime.__init__` le esse nome do
MODULO dinamicamente a cada instancia nova (`self.db_path = db_path if
db_path is not None else DB_PATH`, uma linha de codigo executada em toda
chamada, nao um default de parametro fixado na definicao) — ai sim
`monkeypatch.setattr(live_runtime, "DB_PATH", tmp)` funciona direto.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backtest.withdrawal import OFFICIAL_FLOOR_MULTIPLE
from dashboard import app as dashboard_app
from dashboard import live_control, live_service
from journal import live_store
from live import runtime as live_runtime


@pytest.fixture
def isolated_journal(tmp_path, monkeypatch):
    """Redireciona TODO acesso a `journal.live_store.live_journal()` (sem
    argumento) e a construcao de `LiveRuntime` (via `live_service`) para um
    banco isolado em `tmp_path` — nunca o `db/journal.sqlite` real."""
    db_path = tmp_path / "live_journal.sqlite"
    monkeypatch.setattr(live_store.live_journal.__wrapped__, "__defaults__", (db_path,))
    monkeypatch.setattr(live_runtime, "DB_PATH", db_path)
    return db_path


@pytest.fixture
def client():
    # SEM `with TestClient(...) as client:` de proposito — ver docstring do
    # modulo: entrar no context manager dispara a lifespan real do app.
    return TestClient(dashboard_app.app)


# Slot de SWING -- e' onde vivem as regras de robo/ranking/disjuntor que este
# arquivo cobre. O slot de day trade (`daytrade`) escolhe robo pelo catalogo
# PROPRIO de day trade (`strategy.daytrade.registry`, sempre disponivel, sem
# ranking recalculado por hora) -- ver `tests/test_dashboard_daytrade_robot.py`.
SWING = "swing"


def _create_mt5_account(
    db_path, capital: float = 50_000.0, slot: str = SWING, investment_robot: str | None = None,
) -> int:
    # Default por slot: "portfolio_dip2_hw40" (swing) nao existe no registry
    # de day trade -- uma conta do slot "daytrade" com esse robo levantaria
    # `KeyError` ao montar o painel (ver `strategy.daytrade.registry`).
    robo = investment_robot or ("gremah" if slot == "daytrade" else "portfolio_dip2_hw40")
    with live_store.live_journal(db_path) as conn:
        acc = live_store.ensure_account(
            conn, name=slot, mode="mt5",
            initial_capital=capital, investment_robot=robo,
            withdrawal_robot="official_policy",
        )
        return acc.id


def _state_v2(tmp_path, monkeypatch, slot: str, config: dict):
    """Escreve o arquivo de estado de processo no formato v2 (um bloco por
    slot, ver `dashboard/live_control`) e aponta o modulo para ele."""
    state_path = tmp_path / "live_process.json"
    state_path.write_text(json.dumps({
        "version": 2,
        "slots": {slot: {"pid": None, "started_at": None, "config": config}},
    }), encoding="utf-8")
    monkeypatch.setattr(live_control, "_STATE_PATH", state_path)
    return state_path


# Schema MINIMO no vocabulario ANTIGO (so o suficiente para
# `_legacy_check_present` detectar via a substring `'broker'` no DDL) --
# usado so para simular uma conta legada `mode='paper'` bloqueando o rebuild.
_LEGACY_DDL_MIN = """
CREATE TABLE live_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL CHECK (mode IN ('paper','manual','broker')),
    initial_capital REAL NOT NULL,
    cash REAL NOT NULL,
    investment_robot TEXT NOT NULL DEFAULT '',
    withdrawal_robot TEXT NOT NULL DEFAULT '',
    withdrawn_total REAL NOT NULL DEFAULT 0,
    external_cash REAL NOT NULL DEFAULT 0,
    policy_state TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


# ---------- get_status() carrega capital/disjuntor REAIS da conta (1.7) -----

def test_get_status_usa_capital_real_da_conta_atraves_de_build_runtime(isolated_journal, monkeypatch):
    """Correcao do plan-reviewer (secao 4): a prova atravessa `get_status()`
    de ponta a ponta (nao chama `_build_daily_runtime` a mao com o capital
    certo), senao um `get_status()` que continuasse mandando `DEFAULT_CAPITAL`
    passaria despercebido."""
    db_path = isolated_journal
    _create_mt5_account(db_path, capital=50_000.0)

    captured: dict = {}
    original = live_service._build_daily_runtime

    def _spy(slot, mode, capital, robot):
        rt = original(slot, mode, capital, robot)
        captured["rt"] = rt
        return rt

    monkeypatch.setattr(live_service, "_build_daily_runtime", _spy)

    live_service.get_status(SWING)

    rt = captured["rt"]
    assert rt.config.initial_capital == pytest.approx(50_000.0)
    assert rt.withdrawal.policy.floor == pytest.approx(50_000.0 * OFFICIAL_FLOOR_MULTIPLE)
    # A conta do slot E o slot -- nao existe mais conta "principal".
    assert rt.account_name == SWING


def test_get_status_disjuntor_nao_nulo_quando_ha_config_salva(isolated_journal, tmp_path, monkeypatch):
    db_path = isolated_journal
    _create_mt5_account(db_path, capital=1_000.0)
    _state_v2(tmp_path, monkeypatch, SWING, {
        "mode": "mt5", "capital": 1_000.0, "slot": SWING,
        "daily_loss_limit": 0.05, "monthly_loss_limit": None,
        "notify_min_level": "warn", "mt5_shares_per_lot": None,
    })

    status = live_service.get_status(SWING)
    assert status["disjuntor"] is not None


def test_get_status_de_um_slot_nao_ve_a_conta_do_outro(isolated_journal):
    """Cada slot e' uma conta, e a conta e' o caixa: o painel de um robo nunca
    pode mostrar o caixa do outro. Com a conta de swing criada e a de day
    trade ainda nao, o day trade tem de reportar `existe: False`."""
    _create_mt5_account(isolated_journal, capital=1_000.0, slot=SWING)

    assert live_service.get_status(SWING)["existe"] is True
    assert live_service.get_status("daytrade")["existe"] is False


# ---------- iniciar: acoes por lote detectada, robo do ranking (swing) ------

def test_operacao_iniciar_sem_shares_per_lot_detectavel_pede_campo_sem_iniciar(
    isolated_journal, client, monkeypatch,
):
    """Regra do dono (2026-08-20): 'acoes por lote' nao e campo digitado em
    lugar nenhum -- vem de `live_control.detect_shares_per_lot(slot)`
    (consulta o symbol_info do terminal MT5 conectado). Deteccao retornando
    `None` (terminal fechado/deslogado): tem de bloquear com erro claro em
    vez de subir o processo sem valor."""
    called: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: called.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: None)

    resp = client.post(f"/operacao/{SWING}/iniciar", data={})

    assert resp.status_code == 200
    assert "lote" in resp.text.lower()
    assert called == []


def test_operacao_iniciar_swing_ignora_execution_mode_do_form_sempre_live(
    isolated_journal, client, monkeypatch,
):
    """O toggle sombra/real (2026-08-22) é só do slot intradiário -- swing
    nunca teve modo sombra, então mesmo que um form adulterado mande
    `execution_mode=shadow`, a conta continua indo pra "live"."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(dashboard_app.reader, "top_strategies_by_final_capital",
                        lambda **kw: [{"strategy_name": "portfolio_dip2_hw40", "final_capital": 5_000.0}])

    client.post(f"/operacao/{SWING}/caixa", data={"caixa": "100.00"})
    resp = client.post(f"/operacao/{SWING}/iniciar",
                       data={"robo": "portfolio_dip2_hw40", "execution_mode": "shadow"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].execution_mode == "live"


def test_operacao_iniciar_primeira_vez_usa_caixa_do_ledger_como_capital(
    isolated_journal, client, monkeypatch,
):
    """O capital de uma conta NOVA e o caixa que o dono destinou a ESTE robo
    no ledger manual -- nunca lido da corretora.

    `detect_broker_capital()` foi removida em 2026-08-21: achado ao vivo de
    que o saldo do terminal MT5 nao acompanha o da Rico, e com dois robos
    disputando a mesma conta um numero atrasado viraria dois livros-caixa
    errados."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(dashboard_app.reader, "top_strategies_by_final_capital",
                        lambda **kw: [{"strategy_name": "portfolio_dip2_hw40", "final_capital": 5_000.0}])

    # ledger manual primeiro: sem isso, o piso de R$50 bloqueia (testado abaixo)
    client.post(f"/operacao/{SWING}/caixa", data={"caixa": "7530.00"})
    resp = client.post(f"/operacao/{SWING}/iniciar", data={"robo": "portfolio_dip2_hw40"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].capital == pytest.approx(7_530.0)
    assert captured[0].strategy == "portfolio_dip2_hw40"
    assert captured[0].slot == SWING


def test_operacao_iniciar_sem_caixa_no_ledger_bloqueia_com_piso_claro(
    isolated_journal, client, monkeypatch,
):
    """Piso de operacao (decisao do dono, 2026-08-21): abaixo de R$50 no
    ledger daquele robo, ele nao inicia -- e a mensagem diz o numero, em vez
    de so desabilitar o botao."""
    called: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: called.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(dashboard_app.reader, "top_strategies_by_final_capital",
                        lambda **kw: [{"strategy_name": "portfolio_dip2_hw40", "final_capital": 5_000.0}])

    client.post(f"/operacao/{SWING}/caixa", data={"caixa": "40.00"})
    resp = client.post(f"/operacao/{SWING}/iniciar", data={"robo": "portfolio_dip2_hw40"})

    assert resp.status_code == 200
    assert "50" in resp.text
    assert called == []


def test_operacao_iniciar_usa_mapa_fracionario_detectado_no_config(
    isolated_journal, client, monkeypatch,
):
    """Mercado fracionario (sufixo `*F`, ex. Rico): o mapa detectado via
    `live_control.detect_fractional_symbol_map()` chega ate `ProcessConfig`
    -- sem isso, ordens abaixo do lote padrao (tipicamente 100 acoes) seriam
    sempre rejeitadas pelo MT5, inviabilizando operar com capital pequeno."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map",
                        lambda slot, robot_key=None: {"WEGE3.SA": "WEGE3F"})
    monkeypatch.setattr(dashboard_app.reader, "top_strategies_by_final_capital",
                        lambda **kw: [{"strategy_name": "portfolio_dip2_hw40", "final_capital": 5_000.0}])

    client.post(f"/operacao/{SWING}/caixa", data={"caixa": "100.00"})
    resp = client.post(f"/operacao/{SWING}/iniciar", data={"robo": "portfolio_dip2_hw40"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].mt5_fractional_map == {"WEGE3.SA": "WEGE3F"}


def test_operacao_iniciar_ignora_piso_e_disjuntor_arbitrarios_do_form(
    isolated_journal, client, monkeypatch,
):
    """Regra do dono (2026-08-19): piso de saque e disjuntor de risco nao sao
    parametro que quem opera deva digitar -- o robo ja sabe o valor certo
    (testado em backtest). `ProcessConfig` nao tem esses campos, entao mesmo
    um form malicioso/desatualizado enviando `floor`/`daily_loss_limit`/
    `monthly_loss_limit` nao pode influenciar o robo."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(dashboard_app.reader, "top_strategies_by_final_capital",
                        lambda **kw: [{"strategy_name": "portfolio_dip2_hw40", "final_capital": 5_000.0}])

    client.post(f"/operacao/{SWING}/caixa", data={"caixa": "7530.00"})
    resp = client.post(f"/operacao/{SWING}/iniciar", data={
        "robo": "portfolio_dip2_hw40",
        "floor": "1", "daily_loss_limit": "99", "monthly_loss_limit": "99",
    })

    assert resp.status_code == 200
    assert len(captured) == 1
    assert not hasattr(captured[0], "floor")
    assert not hasattr(captured[0], "daily_loss_limit")
    assert not hasattr(captured[0], "monthly_loss_limit")


def test_operacao_iniciar_retoma_conta_mt5_existente_usa_shares_per_lot_detectado(
    isolated_journal, client, monkeypatch,
):
    """'Acoes por lote' e parametro do terminal MT5 do usuario, detectado
    sozinho via `live_control.detect_shares_per_lot()` -- POST iniciar sobre
    uma conta mt5 JA EXISTENTE (robo parado) chega em `live_control.start`
    com o valor detectado, sem nenhum campo digitado em lugar nenhum."""
    db_path = isolated_journal
    _create_mt5_account(db_path)
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 3.5)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)

    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))

    resp = client.post(f"/operacao/{SWING}/iniciar", data={})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].mode == "mt5"
    assert captured[0].mt5_shares_per_lot == pytest.approx(3.5)
    assert captured[0].strategy == "portfolio_dip2_hw40"  # investment_robot da conta ja existente


def test_operacao_iniciar_mt5_shares_per_lot_zero_detectado_pede_campo_sem_iniciar(
    isolated_journal, client, monkeypatch,
):
    """Item 2 da correcao pos-code-review (hipotese-agente): `0`/negativo tem
    de ser recusado igual a `None` -- um valor assim causaria
    `ZeroDivisionError` em `MT5Broker._to_volume` na hora de mandar ordem
    real (`volume = quantity / shares_per_lot`)."""
    called: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: called.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 0.0)

    resp = client.post(f"/operacao/{SWING}/iniciar", data={})

    assert resp.status_code == 200
    assert "lote" in resp.text.lower()
    assert called == []


# ---------- robo vem do top-3 do ranking, nao e campo livre (2026-08-19) ----

def test_operacao_iniciar_robo_fora_do_top3_bloqueia_sem_iniciar(
    isolated_journal, client, monkeypatch,
):
    """O robo de uma conta NOVA de swing so pode ser um dos top-3 do ranking
    automatico (janela FULL) -- um form adulterado/desatualizado mandando uma
    chave que nao esta mais no ranking nao pode colar."""
    called: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: called.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(dashboard_app.reader, "top_strategies_by_final_capital",
                        lambda **kw: [{"strategy_name": "portfolio_dip2_hw40", "final_capital": 5_000.0}])

    resp = client.post(f"/operacao/{SWING}/iniciar", data={"robo": "robo-fora-do-ranking"})

    assert resp.status_code == 200
    assert "lista" in resp.text.lower()
    assert called == []


def test_operacao_iniciar_sem_ranking_ainda_bloqueia_com_erro_claro(
    isolated_journal, client, monkeypatch,
):
    """Ranking automatico ainda nao rodou (top-3 vazio) -- bloqueia com
    mensagem clara em vez de deixar escolher qualquer coisa ou estourar."""
    called: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: called.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(dashboard_app.reader, "top_strategies_by_final_capital", lambda **kw: [])

    resp = client.post(f"/operacao/{SWING}/iniciar", data={"robo": "portfolio_dip2_hw40"})

    assert resp.status_code == 200
    assert "ranking" in resp.text.lower()
    assert called == []


def test_operacao_iniciar_conta_existente_ignora_robo_do_form_usa_investment_robot(
    isolated_journal, client, monkeypatch,
):
    """Achado de seguranca: uma conta JA EXISTENTE nunca pode trocar de robo
    atraves do form de retomada, mesmo que o ranking tenha mudado desde a
    criacao -- `LiveRuntime._restore_robot_state` descarta silenciosamente o
    estado acumulado (`bars_held`, pyramids etc.) quando o robo muda, e um
    robo diferente rodando sobre dinheiro real sem ninguem decidir isso
    explicitamente seria um incidente."""
    db_path = isolated_journal
    _create_mt5_account(db_path)  # investment_robot="portfolio_dip2_hw40"
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    # Ranking mudou depois da criacao -- top-3 atual nem contem o robo da conta.
    monkeypatch.setattr(dashboard_app.reader, "top_strategies_by_final_capital",
                        lambda **kw: [{"strategy_name": "um-robo-novo", "final_capital": 9_000.0}])

    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))

    resp = client.post(f"/operacao/{SWING}/iniciar", data={"robo": "um-robo-novo"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].strategy == "portfolio_dip2_hw40"


def test_operacao_slot_desconhecido_devolve_404(isolated_journal, client):
    """Um slot que nao esta no catalogo nunca pode ser operado por chute --
    `core.config.slot_by_id` nao tem default silencioso, e a rota traduz isso
    em 404 em vez de 500."""
    assert client.post("/operacao/nao-existe/iniciar", data={}).status_code == 404
    assert client.post("/operacao/nao-existe/caixa", data={"caixa": "10"}).status_code == 404
    assert client.get("/operacao/nao-existe/fragment").status_code == 404


# ---------- LegacyPaperAccountError nao pode virar 500 cru (item 5) ---------

def test_operacao_com_conta_legada_paper_devolve_pagina_com_mensagem_sem_500(
    isolated_journal, client,
):
    """Item 5 da correcao pos-code-review (hipotese-agente):
    `LegacyPaperAccountError` e um `RuntimeError` levantado dentro de
    `_connect`/`live_journal`, chamado ANTES de qualquer try/except nos
    handlers de `/operacao` -- sem tratamento especifico, uma conta legada
    `mode='paper'` no banco fazia GET /operacao estourar 500 cru. Agora
    devolve a pagina normal (200) com a mensagem clara no banner de erro."""
    import sqlite3

    conn = sqlite3.connect(isolated_journal)
    try:
        conn.executescript(_LEGACY_DDL_MIN)
        conn.execute(
            "INSERT INTO live_accounts (name, mode, initial_capital, cash) "
            "VALUES ('swing', 'paper', 1000.0, 1000.0)"
        )
        conn.commit()
    finally:
        conn.close()

    resp = client.get("/operacao")

    assert resp.status_code == 200
    assert "simula" in resp.text.lower() or "paper" in resp.text.lower()


# ---------- ledger manual de caixa, por robo (2026-08-21) ------------------

def test_operacao_caixa_sem_conta_cria_a_linha_contabil_com_o_valor(isolated_journal, client):
    """Sem conta ainda, informar o caixa CRIA a linha contabil daquele slot com
    o valor -- nao bloqueia. Sem isso o piso de R$50 seria inalcancavel: o
    numero digitado tinha de sobreviver ao F5 para o botao "Iniciar" poder
    habilitar."""
    resp = client.post(f"/operacao/{SWING}/caixa", data={"caixa": "500"})

    assert resp.status_code == 200
    with live_store.live_journal(isolated_journal) as conn:
        conta = live_store.load_account(conn, SWING)
    assert conta is not None
    assert conta.cash == pytest.approx(500.0)


def test_operacao_caixa_aplica_diferenca_e_audita(isolated_journal, client):
    """O caixa informado vira o novo `account.cash` DAQUELE slot, com uma
    linha de auditoria em `live_deposits` (`origin="manual_ledger"`)."""
    db_path = isolated_journal
    _create_mt5_account(db_path, capital=1_000.0)  # cash inicial = 1_000.0

    resp = client.post(f"/operacao/{SWING}/caixa", data={"caixa": "1500.00"})

    assert resp.status_code == 200
    assert "atualizado" in resp.text.lower()

    with live_store.live_journal(db_path) as conn:
        conta = live_store.load_account(conn, SWING)
        rows = conn.execute(
            "SELECT * FROM live_deposits WHERE account_id = ?", (conta.id,)
        ).fetchall()
    assert conta.cash == pytest.approx(1_500.0)
    assert len(rows) == 1
    assert rows[0]["origin"] == "manual_ledger"
    assert rows[0]["amount"] == pytest.approx(500.0)


def test_operacao_caixa_reenviar_o_mesmo_valor_nao_grava_nada(isolated_journal, client):
    """Reenviar um valor ja convergido (double-click/F5) nao pode gerar
    deposito duplicado -- a idempotencia vem de mandar um valor ABSOLUTO, nao
    de uma guarda de dedup em memoria."""
    db_path = isolated_journal
    _create_mt5_account(db_path, capital=1_000.0)

    resp = client.post(f"/operacao/{SWING}/caixa", data={"caixa": "1000.00"})

    assert resp.status_code == 200
    with live_store.live_journal(db_path) as conn:
        conta = live_store.load_account(conn, SWING)
        rows = conn.execute(
            "SELECT * FROM live_deposits WHERE account_id = ?", (conta.id,)
        ).fetchall()
    assert conta.cash == pytest.approx(1_000.0)
    assert rows == []


def test_operacao_caixa_tolerancia_fina_nao_engole_meio_real(isolated_journal, client):
    """`reconcile_cash` tem `tolerance=1.0` por default -- num caixa de R$50
    (o piso deste painel) isso engoliria uma correcao de R$0,50 em silencio,
    1% do capital do robo. A rota passa `tolerance=0.005`."""
    db_path = isolated_journal
    _create_mt5_account(db_path, capital=50.0)

    resp = client.post(f"/operacao/{SWING}/caixa", data={"caixa": "50.50"})

    assert resp.status_code == 200
    with live_store.live_journal(db_path) as conn:
        conta = live_store.load_account(conn, SWING)
    assert conta.cash == pytest.approx(50.50)


def test_operacao_caixa_de_um_slot_nao_mexe_no_outro(isolated_journal, client):
    """O pedido inteiro: cada robo so manipula o SEU caixa. Definir o caixa do
    day trade nao pode tocar o do swing."""
    _create_mt5_account(isolated_journal, capital=1_000.0, slot=SWING)

    client.post("/operacao/daytrade/caixa", data={"caixa": "80"})

    with live_store.live_journal(isolated_journal) as conn:
        assert live_store.load_account(conn, SWING).cash == pytest.approx(1_000.0)
        assert live_store.load_account(conn, "daytrade").cash == pytest.approx(80.0)


def test_operacao_caixa_valor_negativo_bloqueia(isolated_journal, client):
    db_path = isolated_journal
    _create_mt5_account(db_path, capital=1_000.0)

    resp = client.post(f"/operacao/{SWING}/caixa", data={"caixa": "-5"})

    assert resp.status_code == 200
    assert "caixa" in resp.text.lower()

    with live_store.live_journal(db_path) as conn:
        conta = live_store.load_account(conn, SWING)
    assert conta.cash == pytest.approx(1_000.0)  # nao mexeu

# ---------- ordem e independencia dos cartoes (pedido do dono, 2026-08-21) --

def test_operacao_mostra_os_dois_cartoes_com_day_trade_em_cima(isolated_journal, client):
    """Pedido explicito do dono: as duas estrategias como opcoes de topo, day
    trade EM CIMA -- "nao por ser melhor, mas por ser a primeira opcao, ainda
    nao temos capital para operar com a liqflop"."""
    html = client.get("/operacao").text

    i_day = html.index("Day trade")
    i_swing = html.index("Swing")
    assert i_day < i_swing
    # cada cartao tem o SEU form de caixa e o SEU botao de iniciar
    for slot in ("daytrade", "swing"):
        assert f"/operacao/{slot}/caixa" in html
        assert f"/operacao/{slot}/iniciar" in html
        assert f"/operacao/{slot}/fragment" in html


def test_home_lista_os_dois_tipos_de_robo_no_MESMO_catalogo(client):
    """A home tem UM catalogo, com etiqueta de tipo por robo -- nao uma grade
    de swing e uma segunda secao de day trade emendada embaixo.

    O discovery de swing nunca varre `strategy/daytrade/` (motor/metricas
    incomparaveis ao ranking FULL/5Y/1Y), entao os dois catalogos sao
    diferentes na origem; o que NAO precisava ser diferente era a tela. Ver
    `dashboard/robot_view.py`."""
    html = client.get("/").text

    assert "liqflop" in html
    assert "gremah" in html
    # Uma grade so: a segunda secao "Robôs de day trade" deixou de existir.
    assert html.count('class="robots-grid') == 1
    assert "Robôs de day trade" not in html
    # A etiqueta de tipo vive DENTRO do cartao.
    assert "robot-kind-swing" in html
    assert "robot-kind-daytrade" in html


def test_home_manda_os_dois_robos_para_a_ficha_e_nao_um_para_operacao(client):
    """Pedido do dono (2026-08-21): clicar no `gremah` tem de abrir
    `/strategies/gremah`, como acontece com o `liqflop` -- antes o cartao de
    day trade apontava para `/operacao` (a rota de ficha nao resolvia robo de
    day trade e dava 404), e dois cartoes da mesma grade levavam a dois
    lugares diferentes."""
    html = client.get("/").text

    assert 'href="/strategies/liqflop"' in html
    assert 'href="/strategies/gremah"' in html


def test_ficha_do_robo_de_day_trade_existe_e_explica_o_robo(client):
    """`/strategies/gremah` era 404 -- a rota so consultava o registry de
    swing. Agora resolve os dois catalogos (`robot_view.detail`) e a ficha tem
    de trazer a EXPLICACAO, nao so' a tabela de parametros: era exatamente
    isso que faltava na tela antiga, que renderizava "Entrada/Saida/Sizing"
    como tres caixas vazias porque ninguem nunca preenchia esses campos."""
    resp = client.get("/strategies/gremah")

    assert resp.status_code == 200
    html = resp.text
    assert "O que ele olha" in html
    assert "Quando compra" in html
    assert "Quando vende" in html
    # Motor incomparavel: a ficha dele NAO oferece o formulario de simulacao
    # de carteira, manda para o painel de operacao.
    assert 'action="/strategies/gremah/run"' not in html
    assert 'href="/operacao"' in html


def test_ficha_nunca_renderiza_bloco_de_regra_vazio(client):
    """A tela antiga mostrava sempre os tres titulos (Entrada, Saida, Sizing &
    custos) com `<ol>` vazio embaixo, porque `StrategyInfo` criava as listas
    vazias e nada as populava. Bloco sem item nao pode existir: ou tem
    conteudo, ou nao e' renderizado."""
    import re

    html = client.get("/strategies/liqflop").text

    blocos = re.findall(r'<article class="doc-block">.*?</article>', html, re.S)
    assert blocos, "a ficha do robo do podio tem de ter blocos de regra"
    for bloco in blocos:
        assert "<li>" in bloco, f"bloco de regra sem nenhum item: {bloco[:120]}"


def test_ficha_nao_mostra_docstring_de_desenvolvedor_ao_usuario(client):
    """A ficha e' a tela do DONO DO CAPITAL. A primeira versao dela
    reaproveitava o docstring da classe, que e escrito para outra audiencia:
    hipotese a priori, refutacao, nome de parametro, data de promocao. O texto
    da tela vem de `plain_summary`/`plain_example` (ver `strategy/base.py`), e
    o docstring nao pode vazar para la."""
    html = client.get("/strategies/liqflop").text

    # frases que so existem no docstring/comentario tecnico do robo
    for vazamento in ("Hipotese a priori", "hipótese a priori", "kwargs.setdefault",
                      "PROMOVIDO ao ranking", "docstring"):
        assert vazamento not in html, f"texto de desenvolvedor na tela: {vazamento!r}"
    # e o texto humano ESTA la
    assert "Ele carrega uma ação por vez" in html
    assert "Passo a passo" in html


def test_ficha_esconde_o_encanamento_da_tabela_de_parametros(client):
    """Caminho de arquivo e chave de modo interno nao sao decisao de
    investimento -- `selic_path` e `redist_mode` saem da ficha via
    `Strategy.param_hidden`. Continuam existindo e configuraveis; so nao sao
    oferecidos ao dono como se fossem um botao dele."""
    html = client.get("/strategies/liqflop").text

    assert "selic_path" not in html
    assert "redist_mode" not in html
    assert "dip_pct" in html  # este SIM e uma decisao, e continua na tabela


def test_ficha_mostra_o_valor_EFETIVO_do_parametro_nao_o_default_da_base(client):
    """`liqflop` opera `dip_pct=0.02`/`high_window=40` (postos por
    `DipTop1Portfolio` via `kwargs.setdefault`), nao o 0.03/20 da assinatura de
    `BuyTheDip`. A ficha le do OBJETO -- um numero errado na tela e' pior que
    numero nenhum, porque parece conferido."""
    from dashboard import robot_view

    params = dict((n, v) for n, v, _ in robot_view.detail("liqflop").params)

    # 2% e 40 pregoes sao os EFETIVOS; 3% e 20 sao os defaults de `BuyTheDip`
    assert params["dip_pct"] == "2%"
    assert params["high_window"] == "40"
    # e a fracao chega na tela como percentual, nao como "0.02" cru
    assert "2%" in client.get("/strategies/liqflop").text


def test_menu_nao_marca_a_home_como_pagina_atual_na_ficha_do_robo(client):
    """Reclamacao do dono: estando em `/strategies/<robo>`, o item "Robôs" do
    menu (que aponta para `/`) acendia como `aria-current="page"` -- o menu
    afirmava que a pagina atual era a home. Filha de secao usa
    `data-section`, um estado visual mais fraco."""
    # so' o <header> do topo (o menu) -- o resto da pagina tem outros headers
    menu_home = client.get("/").text.split("</header>")[0]
    menu_ficha = client.get("/strategies/liqflop").text.split("</header>")[0]

    assert 'aria-current="page"' in menu_home       # na home, "Robôs" É a pagina
    assert 'aria-current="page"' not in menu_ficha  # na ficha, nao
    assert 'data-section="true"' in menu_ficha      # so' a secao acesa


def test_operacao_nunca_resolve_o_robo_de_day_trade_pelo_registry_de_swing(
    isolated_journal, client, monkeypatch,
):
    """Armadilha real: `IntradayStrategy` NAO herda de `Strategy` (de
    proposito -- um robo intradiario de um papel nao compete no mesmo podio
    que um robo diario de carteira). `get_strategy("gremah")` levantaria
    `KeyError` e viraria um 500 em `/operacao` so por existir um cartao de day
    trade na tela. O despacho tem de ser por `slot.kind` ANTES de tocar no
    registry."""
    from strategy import registry

    chamado: list = []
    original = registry.get_strategy

    def _spy(chave):
        chamado.append(chave)
        return original(chave)

    monkeypatch.setattr(dashboard_app.live_service, "get_strategy", _spy)
    _create_mt5_account(isolated_journal, capital=1_000.0, slot="daytrade")

    resp = client.get("/operacao")

    assert resp.status_code == 200
    assert "gremah" not in chamado


def test_operacao_poe_os_robos_antes_das_credenciais(isolated_journal, client):
    """Hierarquia da tela (2026-08-21): o painel e' para ver os ROBOS. O bloco
    "Acesso e credenciais" -- um form de senha que se preenche uma vez na vida
    -- abria a pagina, entao quem chegava para olhar a operacao encontrava
    configuracao primeiro. Configuracao vem DEPOIS do que ela configura."""
    html = client.get("/operacao").text

    assert html.index("Day trade") < html.index("Acesso e credenciais")
    assert html.index("Swing") < html.index("Acesso e credenciais")


def test_painel_ao_vivo_linka_a_ficha_do_robo_da_conta(isolated_journal, client):
    """Ciclo de navegacao fechado: a ficha de um robo de day trade manda para
    `/operacao`, e daqui se chega as REGRAS que o robo esta executando com
    dinheiro real. O link usa o robo GRAVADO na conta, nunca o default do
    slot -- apontar para o default seria oferecer a ficha de um robo que
    talvez nao seja o que esta rodando."""
    _create_mt5_account(isolated_journal, capital=1_000.0, slot=SWING,
                        investment_robot="liqflop")

    html = client.get(f"/operacao/{SWING}/fragment").text

    assert 'href="/strategies/liqflop"' in html


def test_fragmento_de_um_slot_nao_renderiza_o_outro(isolated_journal, client):
    """Um poll por slot: o refresh de fundo de um robo nao pode recriar o DOM
    do outro (nem reabrir/fechar nada do outro cartao)."""
    html = client.get("/operacao/daytrade/fragment").text

    assert 'id="ops-slot-live-daytrade"' in html
    assert "ops-slot-live-swing" not in html
    # credencial e caixa ficam FORA do no com polling
    assert "Acesso e credenciais" not in html
    assert "/operacao/daytrade/caixa" not in html


def test_botao_iniciar_desabilitado_sem_caixa_no_ledger(isolated_journal, client, monkeypatch):
    """O piso de R$50 tambem aparece na tela: botao desabilitado + a dica que
    diz o numero. (O servidor recusa de qualquer forma -- ver
    `tests/test_live_control.py`.)"""
    monkeypatch.setattr(live_control, "credential_status",
                        lambda: {"telegram": False, "smtp": False, "mt5": True})

    html = client.get("/operacao/daytrade/fragment").text

    assert "disabled" in html
    assert "50" in html
