"""Teste leve do dashboard FastAPI (`dashboard/app.py`) — cobre so a rota
nova desta feature, `/operacao/aportar` (registrar aporte manual). Nenhum
teste de dashboard existia antes desta feature; este arquivo estabelece o
padrao minimo: `TestClient` SEM usar `with` — entrar no `with` dispara a
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
            conn, name=live_service.ACCOUNT_NAME, mode="manual",
            initial_capital=1_000.0, investment_robot="dip2_hw40",
            withdrawal_robot="official_policy",
        )
        return acc.id


def test_operacao_aportar_credita_caixa_e_grava_deposito(isolated_journal, client):
    db_path = isolated_journal
    account_id = _create_account(db_path)

    resp = client.post("/operacao/aportar", data={"amount": "500.00"})
    assert resp.status_code == 200

    with live_store.live_journal(db_path) as conn:
        acc = live_store.load_account(conn, live_service.ACCOUNT_NAME)
        rows = conn.execute(
            "SELECT * FROM live_deposits WHERE account_id = ?", (account_id,)
        ).fetchall()
    assert acc.cash == pytest.approx(1_500.0)
    assert len(rows) == 1
    assert rows[0]["origin"] == "manual"
    assert rows[0]["amount"] == pytest.approx(500.0)


def test_operacao_aportar_valor_invalido_nao_mexe_no_caixa(isolated_journal, client):
    db_path = isolated_journal
    _create_account(db_path)

    resp = client.post("/operacao/aportar", data={"amount": "-10"})
    assert resp.status_code == 200
    assert "Informe um valor de aporte" in resp.text

    with live_store.live_journal(db_path) as conn:
        acc = live_store.load_account(conn, live_service.ACCOUNT_NAME)
        rows = conn.execute("SELECT * FROM live_deposits").fetchall()
    assert acc.cash == pytest.approx(1_000.0)
    assert rows == []


# ---------- get_status() carrega capital/disjuntor REAIS da conta (1.7) -----

def test_get_status_usa_capital_real_da_conta_atraves_de_build_runtime(isolated_journal, monkeypatch):
    """Correcao do plan-reviewer (secao 4): a prova atravessa `get_status()`
    de ponta a ponta (nao chama `_build_runtime` a mao com o capital certo),
    senao um `get_status()` que continuasse mandando `DEFAULT_CAPITAL`
    passaria despercebido."""
    db_path = isolated_journal
    with live_store.live_journal(db_path) as conn:
        live_store.ensure_account(
            conn, name=live_service.ACCOUNT_NAME, mode="manual",
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
            conn, name=live_service.ACCOUNT_NAME, mode="manual",
            initial_capital=1_000.0, investment_robot="dip2_hw40",
            withdrawal_robot="official_policy",
        )

    state_path = tmp_path / "live_process.json"
    state_path.write_text(json.dumps({
        "pid": None, "started_at": None,
        "config": {
            "mode": "manual", "capital": 1_000.0, "floor": None,
            "daily_loss_limit": 0.05, "monthly_loss_limit": None,
            "notify_min_level": "warn", "mt5_shares_per_lot": None,
        },
    }), encoding="utf-8")
    monkeypatch.setattr(live_control, "_STATE_PATH", state_path)

    status = live_service.get_status()
    assert status["disjuntor"] is not None


def test_operacao_iniciar_mt5_sem_shares_per_lot_pede_campo_sem_iniciar(isolated_journal, client, monkeypatch):
    """Banco isolado VAZIO (a rota so le o form quando nao ha conta ainda):
    mode=mt5 + confirmar_real sem mt5_shares_per_lot tem de pedir o campo em
    vez de subir o processo com o default `1.0` sem valor universal."""
    called: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: called.append(cfg))

    resp = client.post("/operacao/iniciar", data={
        "mode": "mt5", "capital": "1000", "confirmar_real": "1",
    })

    assert resp.status_code == 200
    assert "lote" in resp.text.lower()
    assert called == []


def test_operacao_aportar_sem_conta_devolve_erro_sem_criar_deposito(isolated_journal, client):
    """Nenhuma conta criada ainda: a rota nao pode inventar uma so para
    aceitar o aporte — devolve erro e nao grava nada."""
    resp = client.post("/operacao/aportar", data={"amount": "100"})
    assert resp.status_code == 200
    assert "Nenhuma conta de operação" in resp.text

    with live_store.live_journal(isolated_journal) as conn:
        rows = conn.execute("SELECT * FROM live_deposits").fetchall()
    assert rows == []
