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
    banco isolado em `tmp_path` — nunca o `db/journal.sqlite` real.

    `live.intraday_runtime.LIVE_DB_PATH` precisa de patch PROPRIO: e' um
    `from core.config import LIVE_DB_PATH` (bind estatico no modulo) que o
    `IntradayLiveRuntime` ainda guarda no `__init__` e passa explicito, entao
    nem o default de `live_journal()` nem `live_runtime.DB_PATH` o alcancam.
    Sem isto, qualquer rota que monte o painel de um slot de day trade
    (`/operacao`, `/operacao/dt-.../fragment`) grava uma conta fantasma no
    `db/live.sqlite` REAL -- ja aconteceu. O `conftest.py` tem uma trava
    autouse que falha o teste que sujar, caso este patch se perca de novo.

    `dashboard.live_control._STATE_PATH` entra pelo MESMO motivo (achado em
    auditoria, 2026-08-28): `GET /operacao` chama `live_control.status_all()`,
    que le -- e pode REESCREVER, no ramo de autocorrecao de PID morto --
    `db/live_process.json` de verdade quando este patch falta. Sem isolar,
    dois testes (`test_operacao_mostra_os_cartoes_na_ordem_pedida` e o
    equivalente em `test_dashboard_daytrade_robot.py`) piscavam conforme
    robos reais do dono estivessem rodando ou nao na maquina -- flakiness
    dependente de ambiente, a pior especie (ver `AGENTS.md` /
    `LICOES_DE_PRODUCAO.md`). Isolado aqui, na fixture usada por
    praticamente todo teste deste arquivo que chama `client`, em vez de em
    cada teste (o padrao ja usado em `test_dashboard_processos.py`,
    `test_live_arquivo_robo.py`, `test_dashboard_remocao_robo.py` e
    `test_live_teardown.py`)."""
    from live import intraday_runtime

    db_path = tmp_path / "live_journal.sqlite"
    monkeypatch.setattr(live_store.live_journal.__wrapped__, "__defaults__", (db_path,))
    monkeypatch.setattr(live_runtime, "DB_PATH", db_path)
    monkeypatch.setattr(intraday_runtime, "LIVE_DB_PATH", db_path)
    monkeypatch.setattr(live_control, "_STATE_PATH", tmp_path / "live_process.json")
    # `credential_status()`/`load_credentials()` leem `db/live_secrets.json`
    # em CADA render de `/operacao` (secao "Acesso e credenciais") -- sem
    # isolar, os testes que nao mockam `credential_status` diretamente leriam
    # as credenciais REAIS salvas na maquina (nenhuma asserção depende do
    # valor hoje, mas ficaria dependente de ambiente por acidente).
    monkeypatch.setattr(live_control, "_SECRETS_PATH", tmp_path / "live_secrets.json")
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
# Slot de day trade DINAMICO (`dt-<robo>-<ativo>-<modo>`, modo fixo no id
# desde 2026-08-24) -- desde 2026-08-22 nao ha mais um slot fixo "daytrade":
# o dono abre quantos quiser, um por ativo (e por modo).
DAYTRADE = "dt-gremah-pmam3-shadow"
DAYTRADE_SYMBOL = "PMAM3"
# Mesmo robo+ativo de `DAYTRADE`, em modo REAL -- desde 2026-08-24 os dois
# coexistem como slots/contas independentes.
DAYTRADE_LIVE = "dt-gremah-pmam3-live"


def _create_mt5_account(
    db_path, capital: float = 50_000.0, slot: str = SWING, investment_robot: str | None = None,
) -> int:
    # Default por slot: "portfolio_dip2_hw40" (swing) nao existe no registry
    # de day trade -- uma conta de day trade com esse robo levantaria
    # `KeyError` ao montar o painel (ver `strategy.daytrade.registry`).
    eh_daytrade = slot.startswith("dt-")
    robo = investment_robot or ("gremah" if eh_daytrade else "portfolio_dip2_hw40")
    with live_store.live_journal(db_path) as conn:
        acc = live_store.ensure_account(
            conn, name=slot, mode="mt5",
            initial_capital=capital, investment_robot=robo,
            withdrawal_robot="official_policy",
            # O ativo E' parte da identidade da conta de day trade: sem ele a
            # conta nao vira slot e o cartao nao aparece no painel. Sai do
            # PROPRIO id (`dt-<robo>-<ativo>-<modo>`) e nao de uma constante,
            # senao dois slots diferentes nasceriam com o mesmo papel --
            # exatamente o que o painel proibe (conta NETTING). O ativo e' o
            # penultimo segmento (o ultimo e' o modo, fixo no id desde
            # 2026-08-24).
            symbol=slot.rsplit("-", 2)[-2].upper() if eh_daytrade else "",
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
    assert live_service.get_status(DAYTRADE)["existe"] is False


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
    em 404 em vez de 500.

    Vale para tudo que AGE (iniciar, parar, caixa, remover). O fragmento e' a
    excecao deliberada e fica no teste ao lado: ele nao age, so' desenha, e o
    unico cliente dele e' o polling do HTMX -- para o qual um slot inexistente
    significa "esta aba esta velha", nao "voce digitou errado". O servidor nao
    tem como distinguir um id chutado de um id que existia ate ontem."""
    assert client.post("/operacao/nao-existe/iniciar", data={}).status_code == 404
    assert client.post("/operacao/nao-existe/caixa", data={"caixa": "10"}).status_code == 404
    assert client.post("/operacao/nao-existe/remover", data={}).status_code == 404


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

    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "80"})

    with live_store.live_journal(isolated_journal) as conn:
        assert live_store.load_account(conn, SWING).cash == pytest.approx(1_000.0)
        assert live_store.load_account(conn, DAYTRADE).cash == pytest.approx(80.0)


def test_operacao_caixa_valor_negativo_bloqueia(isolated_journal, client):
    db_path = isolated_journal
    _create_mt5_account(db_path, capital=1_000.0)

    resp = client.post(f"/operacao/{SWING}/caixa", data={"caixa": "-5"})

    assert resp.status_code == 200
    assert "caixa" in resp.text.lower()

    with live_store.live_journal(db_path) as conn:
        conta = live_store.load_account(conn, SWING)
    assert conta.cash == pytest.approx(1_000.0)  # nao mexeu


def test_operacao_caixa_ignora_execution_mode_forjado_no_form(isolated_journal, client):
    """O modo é fixo no slot desde 2026-08-24 (não há mais `<select
    execution_mode>` nem eco de escolha-ainda-não-salva pra sobreviver a este
    POST): um `execution_mode` forjado no form (form adulterado, ou o antigo
    comportamento tentando voltar) é ignorado -- `DAYTRADE` termina em
    '-shadow', então o caixa digitado vai sempre para `cash_sombra`, mesmo
    pedindo "live" no form."""
    _create_mt5_account(isolated_journal, capital=10.0, slot=DAYTRADE)  # cash=cash_sombra=10

    resp = client.post(f"/operacao/{DAYTRADE}/caixa",
                        data={"caixa": "80", "execution_mode": "live"})

    assert resp.status_code == 200
    with live_store.live_journal(isolated_journal) as conn:
        conta = live_store.load_account(conn, DAYTRADE)
    assert conta.cash_sombra == pytest.approx(80.0)
    assert conta.cash == pytest.approx(10.0)  # real intacto


def test_operacao_caixa_com_execution_mode_shadow_mexe_so_no_cash_sombra(
    isolated_journal, client,
):
    """O pedido do dono (2026-08-23): "separação dos campos de saldo, pra o
    sombra ter seu saldo e o real o seu". `DAYTRADE` é '-shadow': o valor
    digitado tem de ir para `cash_sombra` -- `cash` (o dinheiro real) fica
    intocado."""
    _create_mt5_account(isolated_journal, capital=10.0, slot=DAYTRADE)  # cash=cash_sombra=10

    resp = client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "500"})

    assert resp.status_code == 200
    with live_store.live_journal(isolated_journal) as conn:
        conta = live_store.load_account(conn, DAYTRADE)
    assert conta.cash_sombra == pytest.approx(500.0)
    assert conta.cash == pytest.approx(10.0)  # real intacto


def test_operacao_caixa_no_slot_live_mexe_so_no_cash_real(
    isolated_journal, client,
):
    """Contraprova: no slot `-live` (mesmo robô+ativo de `DAYTRADE`, mas outra
    conta), o caixa digitado vai sempre para `cash`, `cash_sombra` fica
    intocado -- os dois slots nunca se cruzam."""
    _create_mt5_account(isolated_journal, capital=10.0, slot=DAYTRADE_LIVE)  # cash=cash_sombra=10

    resp = client.post(f"/operacao/{DAYTRADE_LIVE}/caixa", data={"caixa": "500"})

    assert resp.status_code == 200
    with live_store.live_journal(isolated_journal) as conn:
        conta = live_store.load_account(conn, DAYTRADE_LIVE)
    assert conta.cash == pytest.approx(500.0)
    assert conta.cash_sombra == pytest.approx(10.0)  # sombra intacto


# ---------- ordem e independencia dos cartoes (pedido do dono, 2026-08-21) --

def test_operacao_mostra_os_cartoes_na_ordem_pedida(isolated_journal, client):
    """Ordem da tela, definida pelo dono em 2026-08-22: 01 acesso e
    credenciais, 02 swing, 03 day trade -- e TUDO que e' de day trade (os
    robos, os avisos deles, o form de robo novo) mora dentro da secao 03.

    Substituiu a ordem de 2026-08-21 ("day trade em cima, credenciais por
    ultimo"): com N robos de day trade a secao virou a maior da pagina, e o
    dono preferiu ve-la por ultimo, ja recolhida por secao."""
    _create_mt5_account(isolated_journal, capital=100.0, slot=DAYTRADE)

    html = client.get("/operacao").text

    # Compara as CHAVES das secoes, nao as palavras soltas: "Swing" tambem
    # aparece no menu de navegacao, muito antes de qualquer cartao.
    ordem = [html.index(f'data-ops-key="{k}"')
             for k in ("cred", f"slot:{SWING}", "daytrade")]
    assert ordem == sorted(ordem)
    # o cartao do robo fica DENTRO da secao de day trade
    assert html.index('data-ops-key="daytrade"') < html.index(f'data-ops-key="slot:{DAYTRADE}"')
    # cada cartao tem o SEU form de caixa e o SEU botao de iniciar
    for slot in (DAYTRADE, SWING):
        assert f"/operacao/{slot}/caixa" in html
        assert f"/operacao/{slot}/iniciar" in html
        assert f"/operacao/{slot}/fragment" in html


@pytest.mark.parametrize("digitado, esperado", [
    ("1.234,56", 1234.56),   # o que a mascara de moeda produz
    ("0,07", 0.07),
    ("1234,56", 1234.56),    # sem separador de milhar
    ("1.234", 1234.0),       # pontos em grupos de 3 = milhar, nao decimal
    ("1234.56", 1234.56),    # formato canonico (sem JS, ou POST programatico)
    ("1234", 1234.0),
    ("R$ 1.234,56", 1234.56),
    ("-5", -5.0),            # ver o assert abaixo: o sinal TEM de sobreviver
    ("", None),
    ("abc", None),
])
def test_valor_brl_le_o_formato_da_mascara_de_moeda(digitado, esperado):
    """O campo de caixa virou `type="text"` com mascara (o `type="number"`
    deixava digitar `0,0444410` para so entao acusar), entao o servidor passou
    a receber "1.234,56". O `float(x.replace(",", "."))` de antes quebrava
    exatamente nesse formato -- virava "1.234.56".

    O caso "-5" e' o que quase passou: a primeira versao limpava tudo que nao
    fosse digito/virgula/ponto e comia o sinal, entao "-5" voltava `5.0`,
    escapava da guarda `valor < 0` do handler e GRAVAVA cinco reais no caixa
    em vez de recusar."""
    assert dashboard_app._valor_brl(digitado) == esperado


def test_robos_ficam_abaixo_do_form_e_em_ordem_de_criacao(isolated_journal, client):
    """Pedido do dono (2026-08-22): o formulario e' ponto fixo no topo da secao
    e os robos crescem ABAIXO dele, do mais antigo para o mais recente.

    REGRESSAO: `all_slots` desempatava por `s.id`, e como TODO slot de day
    trade tem `order == 0` o desempate valia sempre -- a lista saia em ordem
    alfabetica do id. Criar KLBN4 depois de PMAM3 punha o novo ACIMA do antigo.
    Este teste so distingue as duas ordens porque cria na ordem CONTRARIA a
    alfabetica."""
    _create_mt5_account(isolated_journal, capital=10.0, slot="dt-gremah-pmam3-shadow")
    _create_mt5_account(isolated_journal, capital=10.0, slot="dt-gremah-klbn4-shadow")

    html = client.get("/operacao").text

    i_form = html.index('class="ops-new-robot-form"')
    i_pmam = html.index('data-ops-key="slot:dt-gremah-pmam3-shadow"')
    i_klbn = html.index('data-ops-key="slot:dt-gremah-klbn4-shadow"')
    assert i_form < i_pmam, "o form tem de ficar ACIMA dos cartoes"
    assert i_pmam < i_klbn, "ordem de criacao, mais recente por ultimo"


def test_cartao_de_day_trade_nao_repete_a_descricao_do_robo(isolated_journal, client):
    """O cartao ficou com texto demais (dono, 2026-08-22): o cabecalho ja diz
    ATIVO + robo, e as regras completas ficam a um clique na ficha. O swing
    MANTEM o dek -- o rotulo da secao dele e' so "Swing", sem esse par."""
    _create_mt5_account(isolated_journal, capital=10.0, slot=DAYTRADE)

    html = client.get("/operacao").text

    assert "sem posição overnight" not in html          # dek do day trade
    assert "rotação mensal por liquidez" in html        # dek do swing, fica


def test_etiqueta_de_modo_diz_o_execution_mode_do_slot(isolated_journal, client):
    """A faixa "Modo sombra" saiu, mas o FATO nao podia sair junto: sem ele um
    robo mandando ordem de verdade fica indistinguivel de um que nao manda
    nada.

    REGRESSAO que a faixa carregava: ela era condicionada a `slot.is_intraday`
    e escrevia "nenhuma ordem e' enviada a corretora" mesmo com o robo
    iniciado em Real. A garantia morou um tempo numa etiqueta a parte dentro
    do fragmento de polling (lendo `s.daytrade.execution_mode`, o processo);
    saiu de la' (dono, 2026-08-24: duplicava o pill abaixo) e passou a viver
    so' no `.ops-slot-mode` do cabecalho do cartao (`operacao_body.html`),
    que le `slot.execution_mode` -- o mesmo valor com que o processo e'
    sempre iniciado (`live_control.py::start`, `--execution-mode`), entao os
    dois nunca divergem."""
    _create_mt5_account(isolated_journal, capital=10.0, slot=DAYTRADE)

    html = client.get("/operacao").text
    assert "Nenhuma ordem é enviada à corretora" not in html   # a prosa saiu
    assert "ops-slot-mode" in html and "simulação" in html
    assert "is-live" not in html            # simulação: sem vermelho

    _create_mt5_account(isolated_journal, capital=10.0, slot="dt-gremah-klbn4-live")
    html = client.get("/operacao").text
    assert "real" in html
    assert "ops-slot-mode is-live" in html  # vermelho: dinheiro de verdade


def test_caixa_e_controle_na_mesma_linha_fora_do_polling(isolated_journal, client):
    """Pedido do dono (2026-08-22): caixa, mínimo e iniciar numa linha só, e o
    "Salvar" permanente trocado por ✓/✕ que aparecem ao focar o campo.

    Os dois `<form>` ficam FORA do nó com polling. Para o caixa isso já valia
    (um `<input>` em digitação seria apagado); para o controle passou a valer
    agora, e por um motivo mais grave — ver o teste seguinte."""
    _create_mt5_account(isolated_journal, capital=100.0, slot=DAYTRADE)

    html = client.get("/operacao").text
    i_bar = html.index('class="ops-bar"')
    i_no_polled = html.index(f'id="ops-slot-live-{DAYTRADE}"')

    assert i_bar < i_no_polled, "a barra tem de ficar fora (antes) do nó com polling"
    assert 'class="ops-cash-actions"' in html
    assert 'type="reset"' in html          # cancelar funciona sem JS
    assert ">Salvar<" not in html          # o botão permanente saiu
    # e o nó com polling não traz mais uma segunda cópia do controle
    assert html.count(f'id="ops-ctl-{DAYTRADE}"') == 1


def test_controle_so_e_reemitido_quando_o_processo_muda_de_estado(
    isolated_journal, client, monkeypatch,
):
    """A barra de controle tem o `<select name="execution_mode">` dentro.

    Reemiti-la a cada poll (como o resumo do cabeçalho) resetaria a escolha do
    dono no meio dela, e nas DUAS direções isso é perigoso: escolher "Real" e
    o refresh voltar para "Sombra" (o clique inicia em sombra achando que é
    real), ou o inverso — que manda ordem de verdade à corretora.

    Então o fragmento só reemite quando o estado do processo diverge do que o
    navegador tem na tela, informado pelo `?rodando=` que o próprio nó põe na
    URL do poll."""
    _create_mt5_account(isolated_journal, capital=100.0, slot=DAYTRADE)
    monkeypatch.setattr(live_control, "status", lambda sid: None)     # parado

    # estado bate (parado, e a tela também acha que está parado): não mexe
    html = client.get(f"/operacao/{DAYTRADE}/fragment?rodando=0").text
    assert 'id="ops-ctl-' not in html
    assert "execution_mode" not in html

    # o robô subiu por fora (CLI, ou o processo caiu e voltou): corrige
    monkeypatch.setattr(live_control, "status",
                        lambda sid: {"pid": 1, "started_at": "2026-08-22T10:00:00"})
    html = client.get(f"/operacao/{DAYTRADE}/fragment?rodando=0").text
    assert f'id="ops-ctl-{DAYTRADE}"' in html
    assert 'hx-swap-oob="true"' in html
    assert "Parar operação" in html
    # e o nó novo passa a declarar o estado certo na URL do próprio poll
    assert "rodando=1" in html


def test_cabecalho_recolhido_diz_caixa_e_estado_e_o_polling_atualiza(
    isolated_journal, client,
):
    """Um cartao fechado nao pode mentir sobre dinheiro.

    O `<summary>` carrega caixa e "operando/parado", e fica FORA do no com
    `hx-trigger` (que e' o corpo do cartao) -- entao o refresh de fundo jamais
    o alcancaria. O fragmento resolve mandando o resumo como swap
    fora-de-banda; sem isso um cartao recolhido seguiria escrito "operando"
    depois de o robo parar."""
    _create_mt5_account(isolated_journal, capital=250.0, slot=DAYTRADE)

    html = client.get("/operacao").text
    assert f'id="ops-sum-{DAYTRADE}"' in html
    assert "250,00" in html

    frag = client.get(f"/operacao/{DAYTRADE}/fragment").text
    assert f'id="ops-sum-{DAYTRADE}"' in frag
    assert 'hx-swap-oob="true"' in frag
    # O htmx so extrai o fora-de-banda da RAIZ da resposta: se ele vier
    # aninhado dentro do no principal, o swap silenciosamente nao acontece.
    assert frag.index("hx-swap-oob") < frag.index('id="ops-slot-live-')


def test_operacao_sem_nenhum_robo_de_day_trade_mostra_so_o_swing_e_o_form(
    isolated_journal, client,
):
    """Estado inicial de quem nunca criou nada: nenhum cartao de day trade, e
    o formulario para criar o primeiro JA' VISIVEL.

    O formulario nao recolhe (pedido do dono, 2026-08-22): abrir a secao "Day
    trade" ja tem de mostrar os selects, o botao e quantos ativos sobram. Sem
    robo nenhum ele e' a unica coisa que a secao tem para oferecer -- esconde-lo
    atras de um segundo clique deixaria a secao aparentemente vazia."""
    html = client.get("/operacao").text

    assert '<form class="ops-new-robot-form"' in html
    assert "data-ops-robot-select" in html          # select de robô
    assert 'name="symbol"' in html                  # select de ativo
    assert "Criar robô" in html                     # botão
    assert "livre" in html                          # contagem de ativos livres
    # o form NAO fica dentro de um <details> proprio
    assert 'data-ops-key="novo"' not in html
    assert "/operacao/swing/caixa" in html
    assert "/operacao/dt-" not in html   # nenhum cartao de day trade ainda


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

    params = dict((n, v) for n, v, _, _ in robot_view.detail("liqflop").params)

    # 2% e 40 pregoes sao os EFETIVOS; 3% e 20 sao os defaults de `BuyTheDip`
    assert params["dip_pct"] == "2%"
    assert params["high_window"] == "40"
    # e a fracao chega na tela como percentual, nao como "0.02" cru
    assert "2%" in client.get("/strategies/liqflop").text


def test_ficha_de_day_trade_mostra_TODOS_os_ativos_calibrados(client):
    """Erro reportado pelo dono (2026-08-22): a ficha do `gremah` citava UM
    ativo quando ele aceita varios, "cada um com seus parametros e capital
    minimo". A causa era o registry instanciar o robo com os defaults (PMAM3) e
    a pagina tratar `robo.symbol` como "o ativo do robo".

    A contagem sai da TABELA, nao de um numero escrito aqui: ela cresceu de 3
    para 10 no mesmo dia (2026-08-22), e um literal so' faria este teste
    quebrar a cada papel novo sem apontar defeito nenhum."""
    from strategy.daytrade.lab.gremah import _CALIBRATION_BY_SYMBOL

    html = client.get("/strategies/gremah").text

    for symbol in _CALIBRATION_BY_SYMBOL:
        assert symbol in html, f"ativo calibrado ausente da ficha: {symbol}"
    # o fato do topo CONTA os ativos, nao nomeia um
    assert f"{len(_CALIBRATION_BY_SYMBOL)} calibrados" in html


def test_ficha_de_day_trade_mostra_capital_minimo_POR_ativo(client):
    """A segunda metade da reclamacao: cada ativo exige um caixa minimo
    diferente (lote inteiro de 100 acoes), e e' isso que decide se ele e'
    operavel com o dinheiro que existe. PMAM3 (~R$0,14) pede ~R$50; CSAN3
    (~R$3,64) pede ~R$400 -- se os dois aparecerem com o MESMO numero, a
    coluna esta lendo o preco de um ativo so."""
    from dashboard import robot_view

    porto = {a.symbol: a for a in robot_view.detail("gremah").assets}

    from strategy.daytrade.lab.gremah import _CALIBRATION_BY_SYMBOL

    assert set(porto) == set(_CALIBRATION_BY_SYMBOL)
    # preco vem do parquet local; sem dado salvo o caixa minimo e' None (a
    # pagina mostra a falta) -- entao a comparacao so vale com os dois presentes
    if porto["PMAM3"].min_capital and porto["CSAN3"].min_capital:
        assert porto["PMAM3"].min_capital < porto["CSAN3"].min_capital
        # piso = DOBRO do lote (regra do dono 2026-08-22, ver
        # `strategy.daytrade.base.capital_minimo_brl`) -- nao mais arredondar
        # pro proximo multiplo de R$50, que dava folga desigual por preco.
        for a in porto.values():
            assert a.min_capital == pytest.approx(a.lot_cost * 2)


def test_ficha_nao_anuncia_calibracao_de_UM_ativo_como_se_fosse_do_robo(client):
    """`profit_pct`/`stop_multiplier`/`symbol` valem POR ATIVO. A tabela plana
    de parametros mostra UMA instancia (a default, PMAM3), entao exibi-los la
    afirmava "o robo usa alvo de 0,32%" -- que e' o alvo da PMAM3 e nao vale
    para os outros dois. Quem carrega os tres e' a tabela de ativos."""
    from dashboard import robot_view

    params = dict((n, v) for n, v, _, _ in robot_view.detail("gremah").params)

    for por_ativo in ("profit_pct", "stop_multiplier", "symbol"):
        assert por_ativo not in params, (
            f"{por_ativo} e' por ativo e nao pode aparecer como parametro do robo"
        )
    # e um parametro que E' do robo continua na tabela
    assert "max_trades_per_side" in params


def test_ficha_mostra_o_horario_em_UTC_com_brasilia_ao_lado(client):
    """Pedido do dono (2026-08-22): a tabela mostrava "14:00:00" cru na mesma
    pagina em que o texto fala "11h de Brasilia" -- dois numeros para a mesma
    hora, sem nada explicando a diferenca.

    O UTC e' o valor PRINCIPAL (decisao do dono, depois de ver a primeira
    versao com Brasilia na frente): e' o numero que `on_bar` compara e o que se
    confere contra o codigo/log. Brasilia e' a traducao, em corpo menor."""
    from dashboard import robot_view

    linhas = {n: (v, nota) for n, v, nota, _ in robot_view.detail("gremah").params}
    valor, nota = linhas["fixed_anchor_until"]

    assert valor == "14:00 UTC"          # o que o robo usa
    assert nota == "11:00 Brasília"      # traducao (UTC-3 fixo desde 2019)
    # o valor cru do dataclass nao vai mais para a tela sem unidade nenhuma
    assert "14:00:00" not in client.get("/strategies/gremah").text


def test_ficha_do_liqflop_nao_inverte_a_regra_de_saida_da_lista(client):
    """Erro encontrado ao revisar (2026-08-22): a ficha afirmava que papel que
    sai do top-20 liquido e' VENDIDO. Este robo roda `evict_on_refresh=False`
    (grandfathering, ver `strategy/liquid_sleeve.py`) -- o refresh proibe
    COMPRAR fora da lista, nao segurar o que ja se tem. Uma regra invertida na
    tela e' pior que regra nenhuma."""
    from strategy.registry import get_strategy

    robo = get_strategy("liqflop").factory()
    # o comportamento REAL que o texto tem de descrever
    assert robo._sleeves[0].evict_on_refresh is False

    html = client.get("/strategies/liqflop").text
    assert "NÃO é vendida por isso" in html
    # a frase antiga, que afirmava o oposto, nao pode voltar
    assert "deixar de girar é motivo de saída" not in html


def test_ficha_do_liqflop_nao_diz_que_reranqueia_a_bolsa_todo_mes(client):
    """A lista de 20 sai de um pool FIXO de 63 tickers e e' revista a cada 12
    meses (`universe_n=20`, `refresh_months=12`). "As 20 mais negociadas da
    bolsa" sugeria re-selecao mensal em todo o mercado -- duas afirmacoes
    erradas numa frase."""
    from strategy.registry import get_strategy

    sleeve = get_strategy("liqflop").factory()._sleeves[0]
    assert sleeve.universe_n == 20
    assert sleeve.refresh_months == 12

    html = client.get("/strategies/liqflop").text
    assert "mais negociadas da bolsa" not in html
    assert "uma vez por ano" in html


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
    _create_mt5_account(isolated_journal, capital=1_000.0, slot=DAYTRADE)

    resp = client.get("/operacao")

    assert resp.status_code == 200
    assert "gremah" not in chamado


def test_secoes_recolhem_e_credenciais_abre_sozinha_quando_falta_o_mt5(
    isolated_journal, client, monkeypatch,
):
    """Recolher tudo so' e' aceitavel se o que BLOQUEIA a operacao ainda se
    impuser. Sem credencial do MT5 nenhum robo inicia, entao a secao 01 abre
    sozinha e o cabecalho diz o motivo -- em vez de esconder o impedimento
    atras de um `+` que o dono nao tem razao para clicar."""
    monkeypatch.setattr(live_control, "credential_status",
                        lambda: {"telegram": False, "smtp": False, "mt5": False})

    html = client.get("/operacao").text

    assert '<details data-ops-key="cred" open>' in html
    assert "MT5 pendente" in html

    monkeypatch.setattr(live_control, "credential_status",
                        lambda: {"telegram": True, "smtp": True, "mt5": True})
    html = client.get("/operacao").text
    assert '<details data-ops-key="cred" open>' not in html
    assert 'data-ops-key="cred"' in html


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
    _create_mt5_account(isolated_journal, capital=100.0, slot=DAYTRADE)

    html = client.get(f"/operacao/{DAYTRADE}/fragment").text

    assert f'id="ops-slot-live-{DAYTRADE}"' in html
    assert "ops-slot-live-swing" not in html
    # credencial e caixa ficam FORA do no com polling
    assert "Acesso e credenciais" not in html
    assert "/operacao/daytrade/caixa" not in html


def test_aba_velha_pedindo_slot_que_nao_existe_mais_recarrega(isolated_journal, client):
    """Visto ao vivo em 2026-08-22: uma aba aberta antes de os slots virarem
    dinamicos ficou pedindo `/operacao/daytrade/fragment` a cada 20s e levando
    404 para sempre -- o cartao congelou exibindo o estado antigo de um robo
    que nao existe mais. `HX-Refresh` faz a aba se corrigir sozinha."""
    r = client.get("/operacao/daytrade/fragment")

    assert r.status_code == 200
    assert r.headers["HX-Refresh"] == "true"
    assert r.text == ""


def test_conta_removida_em_outra_janela_recarrega_a_aba_aberta(isolated_journal, client):
    """O mesmo buraco pelo caminho que o painel de fato oferece: o dono clica
    "Remover" numa janela com outra aberta. O id dinamico continua PARSEANDO
    (ele carrega robo e ativo dentro de si), entao sem esta checagem o poll
    responderia 200 com um cartao vazio para sempre, em vez de 404."""
    _create_mt5_account(isolated_journal, capital=0.0, slot=DAYTRADE)
    assert client.get(f"/operacao/{DAYTRADE}/fragment").status_code == 200

    with live_store.live_journal(isolated_journal) as conn:
        live_store.delete_account(conn, DAYTRADE)

    r = client.get(f"/operacao/{DAYTRADE}/fragment")
    assert r.headers.get("HX-Refresh") == "true"


def test_banco_doente_nao_vira_laco_de_reload(isolated_journal, client, monkeypatch):
    """Se consultar os slots falhar, o poll segue o caminho normal (que sabe
    degradar num banner) em vez de mandar recarregar -- senao um banco travado
    viraria uma aba recarregando em loop, que e' pior."""
    _create_mt5_account(isolated_journal, capital=100.0, slot=DAYTRADE)
    monkeypatch.setattr(
        "dashboard.slots.all_slots",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("database is locked")),
    )

    r = client.get(f"/operacao/{DAYTRADE}/fragment")

    assert r.status_code == 200
    assert "HX-Refresh" not in r.headers
    assert f'id="ops-slot-live-{DAYTRADE}"' in r.text


def test_botao_iniciar_desabilitado_sem_caixa_no_ledger(isolated_journal, client, monkeypatch):
    """O piso tambem aparece na tela: botao desabilitado + a dica que diz o
    numero. (O servidor recusa de qualquer forma -- ver
    `tests/test_live_control.py`.)

    `min_cash_for` e' mockado (nao lido do parquet real) porque, desde
    2026-08-22, o piso do slot de day trade e' `capital_minimo_brl` do robo
    -- varia com o PRECO do papel, e um teste que dependesse do preco real da
    PMAM3 quebraria sozinho quando ela mudasse de faixa (ja aconteceu: caiu
    de R$1,31 pra R$0,14 no periodo desta pesquisa)."""
    monkeypatch.setattr(live_control, "credential_status",
                        lambda: {"telegram": False, "smtp": False, "mt5": True})
    monkeypatch.setattr(live_control, "min_cash_for", lambda slot, robot_key=None: 777.0)
    # Conta com caixa ZERO, e nao ausencia de conta: um cartao de day trade so'
    # existe porque a conta existe (e' ela que cria o slot), entao "sem caixa"
    # ao vivo e' sempre um ledger zerado.
    _create_mt5_account(isolated_journal, capital=0.0, slot=DAYTRADE)

    # A PAGINA, e nao o fragmento: desde 2026-08-22 a barra de controle divide
    # a linha com o campo de caixa e por isso vive FORA do no com polling (o
    # `<select>` de modo de execucao teria a escolha resetada a cada refresh).
    html = client.get("/operacao").text

    assert "disabled" in html
    assert "777" in html               # o piso aparece ao lado do proprio caixa
    assert "ops-sum-hint is-blocked" in html   # cor vermelha marca o bloqueio


def test_tabela_de_ativos_vem_ordenada_pelo_caixa_minimo(client):
    """A primeira pergunta de quem lê a tabela é "qual eu consigo operar?".

    A ordem original era a de medição (lucro OOS decrescente), que responde
    outra pergunta. Nesta família o caixa mínimo vai de ~R$ 28 (PMAM3) a
    ~R$ 30.390 (CLSC4) — mais de mil vezes — então a ordem decide se a tabela
    é útil ou se o dono precisa varrer dez linhas para achar o que cabe no
    bolso. Ativo sem preço salvo (caixa `None`) fica no fim: sem preço não há
    como ordená-lo, e tratá-lo como zero o poria em primeiro lugar.
    """
    from dashboard.robot_view import detail

    ativos = detail("gremah").assets
    assert len(ativos) > 1

    com_caixa = [a for a in ativos if a.min_capital is not None]
    sem_caixa = [a for a in ativos if a.min_capital is None]
    valores = [a.min_capital for a in com_caixa]
    assert valores == sorted(valores), f"tabela fora de ordem: {valores}"
    # Os sem preço vêm depois de todos os que têm.
    if sem_caixa:
        assert ativos.index(sem_caixa[0]) > ativos.index(com_caixa[-1])

    # E a ordem tem de chegar na página, não só no view-model.
    html = client.get("/strategies/gremah").text
    posicoes = [html.index(a.symbol) for a in com_caixa]
    assert posicoes == sorted(posicoes)


def test_hora_br_converte_o_carimbo_utc_do_diario():
    """O diário grava UTC; a tela mostra Brasília (pedido do dono, 2026-08-25).

    Cobre as três formas que chegam ao template: texto do SQLite (sem fuso —
    lido como UTC, que é o que todo `ts` do diário é), ISO com fuso explícito
    (`started_at` de `live_process.json`) e `datetime` já com fuso.
    """
    from datetime import datetime, timezone

    hora_br = dashboard_app.hora_br

    # o evento do print do dono: 19:55 UTC é 16:55 em Brasília
    assert hora_br("2026-08-25 19:55:14") == "2026-08-25 16:55:14"
    # vira o dia para trás quando o UTC já está na madrugada seguinte
    assert hora_br("2026-08-26 01:00:00") == "2026-08-25 22:00:00"
    # ISO com fuso, e formato curto do "Ativo desde"
    assert hora_br("2026-08-25T12:56:39+00:00", "%Y-%m-%d %H:%M") == "2026-08-25 09:56"
    # datetime já ciente de fuso não é reinterpretado como UTC
    assert hora_br(datetime(2026, 8, 25, 19, 55, tzinfo=timezone.utc)) == "2026-08-25 16:55:00"


def test_hora_br_nao_engole_valor_que_nao_e_data():
    """Vazio vira travessão; o que não parseia volta cru.

    Esconder uma linha do diário porque o carimbo veio estranho seria pior que
    mostrar o valor como está — o console existe justamente para o dono ver o
    que aconteceu.
    """
    hora_br = dashboard_app.hora_br

    assert hora_br(None) == "—"
    assert hora_br("") == "—"
    assert hora_br("t0") == "t0"


def test_console_de_eventos_mostra_hora_de_brasilia(isolated_journal, client):
    """Ponta a ponta: o evento gravado em UTC sai no HTML em hora de Brasília.

    O teste grava o `ts` na mão (o default do schema é `datetime('now')`, que
    seria a hora da máquina que roda o teste) e pede o "Diário Completo", que
    ignora o corte por dia — assim a asserção não depende de o teste rodar
    hoje.
    """
    _create_mt5_account(isolated_journal, capital=100.0, slot=DAYTRADE)
    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, DAYTRADE)
        conn.execute(
            "INSERT INTO live_events (account_id, ts, level, source, message, payload)"
            " VALUES (?, '2026-08-25 19:55:14', 'info', 'daytrade',"
            " 'ordem #01 cancelada (fim do pregao)', '{}')",
            (conta.id,),
        )

    html = client.get(f"/operacao/{DAYTRADE}/fragment?eventos_full=1").text

    assert "[2026-08-25 16:55:14] INFO daytrade:" in html
    assert "2026-08-25 19:55:14" not in html
