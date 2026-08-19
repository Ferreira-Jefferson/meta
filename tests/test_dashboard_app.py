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


def _create_account(db_path) -> int:
    with live_store.live_journal(db_path) as conn:
        acc = live_store.ensure_account(
            conn, name=live_service.ACCOUNT_NAME, mode="mt5",
            initial_capital=1_000.0, investment_robot="dip2_hw40",
            withdrawal_robot="official_policy",
        )
        return acc.id


def _create_mt5_account(db_path, capital: float = 50_000.0) -> int:
    with live_store.live_journal(db_path) as conn:
        acc = live_store.ensure_account(
            conn, name=live_service.ACCOUNT_NAME, mode="mt5",
            initial_capital=capital, investment_robot="dip2_hw40",
            withdrawal_robot="official_policy",
        )
        return acc.id


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
    de ponta a ponta (nao chama `_build_runtime` a mao com o capital certo),
    senao um `get_status()` que continuasse mandando `DEFAULT_CAPITAL`
    passaria despercebido."""
    db_path = isolated_journal
    with live_store.live_journal(db_path) as conn:
        live_store.ensure_account(
            conn, name=live_service.ACCOUNT_NAME, mode="mt5",
            initial_capital=50_000.0, investment_robot="dip2_hw40",
            withdrawal_robot="official_policy",
        )

    captured: dict = {}
    original = live_service._build_runtime

    def _spy(mode, capital):
        rt = original(mode, capital)
        captured["rt"] = rt
        return rt

    monkeypatch.setattr(live_service, "_build_runtime", _spy)

    live_service.get_status()

    rt = captured["rt"]
    assert rt.config.initial_capital == pytest.approx(50_000.0)
    assert rt.withdrawal.policy.floor == pytest.approx(50_000.0 * OFFICIAL_FLOOR_MULTIPLE)


def test_get_status_disjuntor_nao_nulo_quando_ha_config_salva(isolated_journal, tmp_path, monkeypatch):
    db_path = isolated_journal
    with live_store.live_journal(db_path) as conn:
        live_store.ensure_account(
            conn, name=live_service.ACCOUNT_NAME, mode="mt5",
            initial_capital=1_000.0, investment_robot="dip2_hw40",
            withdrawal_robot="official_policy",
        )

    state_path = tmp_path / "live_process.json"
    state_path.write_text(json.dumps({
        "pid": None, "started_at": None,
        "config": {
            "mode": "mt5", "capital": 1_000.0, "floor": None,
            "daily_loss_limit": 0.05, "monthly_loss_limit": None,
            "notify_min_level": "warn", "mt5_shares_per_lot": None,
        },
    }), encoding="utf-8")
    monkeypatch.setattr(live_control, "_STATE_PATH", state_path)

    status = live_service.get_status()
    assert status["disjuntor"] is not None


def test_operacao_iniciar_sem_shares_per_lot_nas_credenciais_pede_campo_sem_iniciar(
    isolated_journal, client, monkeypatch,
):
    """Regra do dono (2026-08-19): 'ações por lote' não é mais campo do form
    de iniciar/retomar -- vem de `live_control.load_credentials()` (salvo em
    Acesso e credenciais → MetaTrader 5). Banco isolado VAZIO (a rota só lê
    o form quando não há conta ainda) e credenciais sem o campo: tem de
    pedir a configuração em vez de subir o processo sem valor."""
    called: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: called.append(cfg))
    monkeypatch.setattr(live_control, "load_credentials", lambda: {})

    resp = client.post("/operacao/iniciar", data={})

    assert resp.status_code == 200
    assert "lote" in resp.text.lower()
    assert called == []


def test_operacao_iniciar_primeira_vez_usa_saldo_da_corretora_como_capital(
    isolated_journal, client, monkeypatch,
):
    """Regra do dono (2026-08-19): capital nunca e digitado -- na primeira
    criacao de conta, `operacao_iniciar` consulta
    `live_control.detect_broker_capital()` (saldo real da corretora) e usa
    isso como capital, mesmo sem nenhum campo `capital` no form."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_broker_capital", lambda: 7_530.0)
    monkeypatch.setattr(live_control, "load_credentials", lambda: {"mt5_shares_per_lot": "1.0"})
    monkeypatch.setattr(dashboard_app.reader, "top_strategies_by_final_capital",
                         lambda **kw: [{"strategy_name": "portfolio_dip2_hw40", "final_capital": 5_000.0}])

    resp = client.post("/operacao/iniciar", data={"robo": "portfolio_dip2_hw40"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].capital == pytest.approx(7_530.0)
    assert captured[0].strategy == "portfolio_dip2_hw40"


def test_operacao_iniciar_ignora_piso_e_disjuntor_arbitrarios_do_form(
    isolated_journal, client, monkeypatch,
):
    """Regra do dono (2026-08-19): piso de saque e disjuntor de risco não são
    parâmetro que quem opera deva digitar -- o robô já sabe o valor certo
    (testado em backtest). `ProcessConfig` não tem mais esses campos, então
    mesmo um form malicioso/desatualizado enviando `floor`/`daily_loss_limit`/
    `monthly_loss_limit` não pode influenciar o robô."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_broker_capital", lambda: 7_530.0)
    monkeypatch.setattr(live_control, "load_credentials", lambda: {"mt5_shares_per_lot": "1.0"})
    monkeypatch.setattr(dashboard_app.reader, "top_strategies_by_final_capital",
                         lambda **kw: [{"strategy_name": "portfolio_dip2_hw40", "final_capital": 5_000.0}])

    resp = client.post("/operacao/iniciar", data={
        "robo": "portfolio_dip2_hw40",
        "floor": "1", "daily_loss_limit": "99", "monthly_loss_limit": "99",
    })

    assert resp.status_code == 200
    assert len(captured) == 1
    assert not hasattr(captured[0], "floor")
    assert not hasattr(captured[0], "daily_loss_limit")
    assert not hasattr(captured[0], "monthly_loss_limit")


def test_operacao_iniciar_primeira_vez_sem_saldo_da_corretora_bloqueia_com_erro_claro(
    isolated_journal, client, monkeypatch,
):
    """Se a corretora nao responder (terminal fechado/deslogado, credenciais
    ausentes), a criacao da conta e bloqueada com uma mensagem clara --
    nunca cai num capital default inventado."""
    called: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: called.append(cfg))
    monkeypatch.setattr(live_control, "detect_broker_capital", lambda: None)
    monkeypatch.setattr(live_control, "load_credentials", lambda: {"mt5_shares_per_lot": "1.0"})
    monkeypatch.setattr(dashboard_app.reader, "top_strategies_by_final_capital",
                         lambda **kw: [{"strategy_name": "portfolio_dip2_hw40", "final_capital": 5_000.0}])

    resp = client.post("/operacao/iniciar", data={"robo": "portfolio_dip2_hw40"})

    assert resp.status_code == 200
    assert "MetaTrader 5" in resp.text
    assert called == []


# ---------- ações por lote vem das credenciais, não do form (2026-08-19) ----

def test_operacao_iniciar_retoma_conta_mt5_existente_usa_shares_per_lot_das_credenciais(
    isolated_journal, client, monkeypatch,
):
    """'Ações por lote' é parâmetro do terminal MT5 do usuário, salvo junto
    das credenciais (Acesso e credenciais → MetaTrader 5) -- POST
    /operacao/iniciar sobre uma conta mt5 JÁ EXISTENTE (robô parado) chega
    em `live_control.start` com o valor lido de lá, sem nenhum campo no
    form de retomada (extingue o workaround antigo, ver
    operacao_live_panel.html)."""
    db_path = isolated_journal
    _create_mt5_account(db_path)
    monkeypatch.setattr(live_control, "load_credentials", lambda: {"mt5_shares_per_lot": "3.5"})

    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))

    resp = client.post("/operacao/iniciar", data={})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].mode == "mt5"
    assert captured[0].mt5_shares_per_lot == pytest.approx(3.5)
    assert captured[0].strategy == "dip2_hw40"  # investment_robot da conta ja existente


def test_operacao_iniciar_mt5_shares_per_lot_zero_nas_credenciais_pede_campo_sem_iniciar(
    isolated_journal, client, monkeypatch,
):
    """Item 2 da correção pós-code-review (hipótese-agente): `0`/negativo tem
    de ser recusado igual a ausente -- um valor assim causaria
    `ZeroDivisionError` em `MT5Broker._to_volume` na hora de mandar ordem
    real (`volume = quantity / shares_per_lot`). Continua valendo agora que
    o valor vem das credenciais, não do form."""
    called: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: called.append(cfg))
    monkeypatch.setattr(live_control, "load_credentials", lambda: {"mt5_shares_per_lot": "0"})

    resp = client.post("/operacao/iniciar", data={})

    assert resp.status_code == 200
    assert "lote" in resp.text.lower()
    assert called == []


# ---------- robô vem do top-3 do ranking, não é campo livre (2026-08-19) ----

def test_operacao_iniciar_robo_fora_do_top3_bloqueia_sem_iniciar(
    isolated_journal, client, monkeypatch,
):
    """O robô de uma conta NOVA só pode ser um dos top-3 do ranking automático
    (janela FULL) -- um form adulterado/desatualizado mandando uma chave que
    não está mais no ranking não pode colar (mesmo espírito de floor/
    disjuntor: quem opera não escolhe um valor arbitrário fora do que foi
    validado)."""
    called: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: called.append(cfg))
    monkeypatch.setattr(live_control, "load_credentials", lambda: {"mt5_shares_per_lot": "1.0"})
    monkeypatch.setattr(dashboard_app.reader, "top_strategies_by_final_capital",
                         lambda **kw: [{"strategy_name": "portfolio_dip2_hw40", "final_capital": 5_000.0}])

    resp = client.post("/operacao/iniciar", data={"robo": "robo-fora-do-ranking"})

    assert resp.status_code == 200
    assert "robô" in resp.text.lower() or "lista" in resp.text.lower()
    assert called == []


def test_operacao_iniciar_sem_ranking_ainda_bloqueia_com_erro_claro(
    isolated_journal, client, monkeypatch,
):
    """Ranking automático ainda não rodou (top-3 vazio) -- bloqueia com
    mensagem clara em vez de deixar escolher qualquer coisa ou estourar."""
    called: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: called.append(cfg))
    monkeypatch.setattr(live_control, "load_credentials", lambda: {"mt5_shares_per_lot": "1.0"})
    monkeypatch.setattr(dashboard_app.reader, "top_strategies_by_final_capital", lambda **kw: [])

    resp = client.post("/operacao/iniciar", data={"robo": "portfolio_dip2_hw40"})

    assert resp.status_code == 200
    assert "ranking" in resp.text.lower()
    assert called == []


def test_operacao_iniciar_conta_existente_ignora_robo_do_form_usa_investment_robot(
    isolated_journal, client, monkeypatch,
):
    """Achado de segurança: uma conta JÁ EXISTENTE nunca pode trocar de robô
    através do form de retomada, mesmo que o ranking tenha mudado desde a
    criação -- `LiveRuntime._restore_robot_state` descarta silenciosamente o
    estado acumulado (`bars_held`, pyramids etc.) quando o robô muda, e um
    robô diferente rodando sobre dinheiro real sem ninguém decidir isso
    explicitamente seria um incidente. `operacao_iniciar` tem de usar sempre
    `conta.investment_robot`, nunca o `robo` que porventura vier no form."""
    db_path = isolated_journal
    _create_mt5_account(db_path)  # investment_robot="dip2_hw40" (ver _create_mt5_account)
    monkeypatch.setattr(live_control, "load_credentials", lambda: {"mt5_shares_per_lot": "1.0"})
    # Ranking mudou depois da criação -- top-3 atual nem contém o robô da conta.
    monkeypatch.setattr(dashboard_app.reader, "top_strategies_by_final_capital",
                         lambda **kw: [{"strategy_name": "um-robo-novo-que-nao-e-o-da-conta", "final_capital": 9_000.0}])

    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))

    resp = client.post("/operacao/iniciar", data={"robo": "um-robo-novo-que-nao-e-o-da-conta"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].strategy == "dip2_hw40"


# ---------- LegacyPaperAccountError não pode virar 500 cru (item 5) ---------

def test_operacao_com_conta_legada_paper_devolve_pagina_com_mensagem_sem_500(
    isolated_journal, client,
):
    """Item 5 da correção pós-code-review (hipótese-agente):
    `LegacyPaperAccountError` é um `RuntimeError` levantado dentro de
    `_connect`/`live_journal`, chamado ANTES de qualquer try/except nos
    handlers de `/operacao` -- sem tratamento específico, uma conta legada
    `mode='paper'` no banco fazia GET /operacao estourar 500 cru. Agora
    devolve a página normal (200) com a mensagem clara no banner de erro."""
    import sqlite3

    conn = sqlite3.connect(isolated_journal)
    try:
        conn.executescript(_LEGACY_DDL_MIN)
        conn.execute(
            "INSERT INTO live_accounts (name, mode, initial_capital, cash) "
            "VALUES ('principal', 'paper', 1000.0, 1000.0)"
        )
        conn.commit()
    finally:
        conn.close()

    resp = client.get("/operacao")

    assert resp.status_code == 200
    assert "principal" in resp.text
    assert "simula" in resp.text.lower() or "paper" in resp.text.lower()
