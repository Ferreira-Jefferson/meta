"""Testes do robô de day trade ser ESCOLHÍVEL, e do ativo ser propriedade do
ROBÔ — não do slot (`core.config.Slot` não declara `symbol` desde
2026-08-21).

Antes desta mudança, `/operacao` sempre montava `Gremah(symbol=slot.symbol)`
direto, ignorando qualquer robô gravado na conta e qualquer form: o slot de
day trade era, na prática, hardcoded num robô só. Este arquivo cobre o
caminho simétrico ao que já existia para SWING (`test_dashboard_app.py`):
robô vem do registry (`strategy.daytrade.registry`) numa conta NOVA, e da
CONTA numa conta já existente — nunca do form nesse segundo caso.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dashboard import app as dashboard_app
from dashboard import live_control, live_service
from journal import live_store

# Slot de day trade DINAMICO desde 2026-08-22: o id carrega robo+ativo
# (`dt-<robo>-<ativo>`) e o painel abre quantos o dono quiser. Nao existe
# mais um slot fixo chamado "daytrade" em `core.config.SLOTS`.
SYMBOL = "PMAM3"
DAYTRADE = "dt-gremah-pmam3"


@pytest.fixture
def isolated_journal(tmp_path, monkeypatch):
    """Mesmo isolamento de `test_dashboard_app.py::isolated_journal` — ver a
    docstring de lá para o motivo de `__wrapped__.__defaults__` ser o único
    jeito de mudar o default de `live_journal()` sem argumento.

    `live.intraday_runtime.LIVE_DB_PATH` precisa de patch PRÓPRIO: é um
    `from core.config import LIVE_DB_PATH` (bind estático no módulo), não
    lido dinamicamente a cada chamada como `live.runtime.DB_PATH` — sem isto,
    `IntradayLiveRuntime.status()` (chamado por `get_status("daytrade")`)
    tocaria o `db/live.sqlite` REAL."""
    from live import intraday_runtime
    from live import runtime as live_runtime

    db_path = tmp_path / "live_journal.sqlite"
    monkeypatch.setattr(live_store.live_journal.__wrapped__, "__defaults__", (db_path,))
    monkeypatch.setattr(live_runtime, "DB_PATH", db_path)
    monkeypatch.setattr(intraday_runtime, "LIVE_DB_PATH", db_path)
    return db_path


@pytest.fixture
def client():
    return TestClient(dashboard_app.app)


def _create_daytrade_account(db_path, capital: float = 100.0, investment_robot: str = "gremah") -> int:
    with live_store.live_journal(db_path) as conn:
        acc = live_store.ensure_account(
            conn, name=DAYTRADE, mode="mt5",
            initial_capital=capital, investment_robot=investment_robot,
            withdrawal_robot="", symbol=SYMBOL,
        )
        return acc.id


# ---------- registry (unidade, sem I/O) ------------------------------------

def test_list_daytrade_robots_inclui_gremah_com_o_simbolo_dele():
    from strategy.daytrade.registry import list_daytrade_robots

    robos = {r.key: r for r in list_daytrade_robots()}
    assert "gremah" in robos
    assert robos["gremah"].symbol == "PMAM3"


def test_get_daytrade_robot_desconhecido_levanta_keyerror():
    from strategy.daytrade.registry import get_daytrade_robot

    with pytest.raises(KeyError, match="gremah"):
        get_daytrade_robot("robo-que-nao-existe")


# ---------- _build_intraday_runtime le o robo da CONTA, nao hardcoded ------

def test_build_intraday_runtime_usa_o_robo_e_o_simbolo_passados():
    """REGRESSAO: antes desta correcao, `_build_intraday_runtime` sempre
    instanciava `Gremah()` direto e lia `slot.symbol` -- um painel que
    mostraria o mesmo robo/simbolo mesmo se a conta tivesse escolhido outro
    registrado."""
    from core.config import slot_by_id

    slot = slot_by_id(DAYTRADE)
    rt = live_service._build_intraday_runtime(slot, 100.0, "shadow", "gremah")

    assert rt.strategy.name == "gremah"
    assert rt.strategy.symbol == "PMAM3"


def test_build_intraday_runtime_sem_robo_gravado_recusa():
    from core.config import slot_by_id

    slot = slot_by_id(DAYTRADE)
    with pytest.raises(ValueError, match="investment_robot"):
        live_service._build_intraday_runtime(slot, 100.0, "shadow", None)


def test_build_intraday_runtime_robo_desconhecido_recusa():
    from core.config import slot_by_id

    slot = slot_by_id(DAYTRADE)
    with pytest.raises(KeyError):
        live_service._build_intraday_runtime(slot, 100.0, "shadow", "robo-que-nao-existe")


# ---------- /operacao/daytrade/iniciar: robo vem do registry, nao fixo ----

def test_operacao_iniciar_daytrade_primeira_vez_sem_robo_no_form_usa_default_do_slot(
    isolated_journal, client, monkeypatch,
):
    """Omitir o campo `robo` (form antigo, ou clique direto no botão) cai no
    default do catálogo (`Slot.robot_key`) -- mesmo comportamento que sempre
    existiu, agora passando pelo registry em vez de um valor fixo."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)

    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})
    resp = client.post(f"/operacao/{DAYTRADE}/iniciar", data={})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].strategy == "gremah"
    assert captured[0].slot == DAYTRADE


def test_operacao_iniciar_daytrade_robo_explicito_no_form_e_respeitado(
    isolated_journal, client, monkeypatch,
):
    """O ponto central do pedido: o painel tem de aceitar ESCOLHER o robô de
    day trade, não assumir sempre o mesmo."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    detect_calls: list = []

    def _detect(slot, robot_key=None):
        detect_calls.append(robot_key)
        return 1.0

    monkeypatch.setattr(live_control, "detect_shares_per_lot", _detect)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)

    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})
    resp = client.post(f"/operacao/{DAYTRADE}/iniciar", data={"robo": "gremah"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].strategy == "gremah"
    # a deteccao de "acoes por lote" tem de saber qual robo foi escolhido
    # ANTES de rodar -- senao ela resolveria o simbolo do robo errado.
    assert detect_calls == ["gremah"]


def test_operacao_iniciar_daytrade_nunca_repassa_mapa_fracionario(
    isolated_journal, client, monkeypatch,
):
    """Pedido explicito do dono (2026-08-22): day trade nao pode conhecer
    mercado fracionario, nem como fallback -- mesmo que o terminal TENHA um
    simbolo `*F` para o papel, `ProcessConfig.mt5_fractional_map` tem de
    chegar `None` no slot `daytrade`. Contraste com
    `test_dashboard_app.py::test_operacao_iniciar_usa_mapa_fracionario_detectado_no_config`,
    que confirma o comportamento OPOSTO (repassar) no slot `swing`."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    # Se o handler chamasse isto para um slot intradiario, o teste pegaria: o
    # mock devolve um mapa NAO-vazio de proposito.
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map",
                        lambda slot, robot_key=None: {"PMAM3": "PMAM3F"})

    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})
    resp = client.post(f"/operacao/{DAYTRADE}/iniciar", data={"robo": "gremah"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].mt5_fractional_map is None


def test_operacao_iniciar_daytrade_usa_piso_do_robo_nao_o_piso_generico_do_slot(
    isolated_journal, client, monkeypatch,
):
    """Pedido do dono (2026-08-22): `Slot.min_cash_brl` (R$50) parou de valer
    pro day trade -- o piso e' `capital_minimo_brl` do robo ESCOLHIDO. Caixa
    de R$100 cobre o piso generico antigo mas nao cobre um robo cujo lote
    custe mais que isso -- tem de bloquear, e a mensagem tem de citar o piso
    REAL, nao R$50."""
    called: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: called.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(live_control, "min_cash_for", lambda slot, robot_key=None: 900.0)

    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})
    resp = client.post(f"/operacao/{DAYTRADE}/iniciar", data={"robo": "gremah"})

    assert resp.status_code == 200
    assert "900" in resp.text
    assert called == []


def test_operacao_iniciar_daytrade_sem_escolha_no_form_cai_no_shadow(
    isolated_journal, client, monkeypatch,
):
    """Sem `execution_mode` no form (form antigo, ou fragmento HTMX velho),
    o default continua SEGURO -- nunca escorrega pra "live" por omissão."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)

    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})
    resp = client.post(f"/operacao/{DAYTRADE}/iniciar", data={"robo": "gremah"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].execution_mode == "shadow"


def test_operacao_iniciar_daytrade_escolha_explicita_de_live_e_respeitada(
    isolated_journal, client, monkeypatch,
):
    """O ponto central do pedido (2026-08-22): o dono escolhe na tela, não é
    mais uma decisão hardcoded no handler."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)

    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})
    resp = client.post(f"/operacao/{DAYTRADE}/iniciar",
                       data={"robo": "gremah", "execution_mode": "live"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].execution_mode == "live"


def test_operacao_iniciar_daytrade_valor_invalido_no_form_cai_no_shadow(
    isolated_journal, client, monkeypatch,
):
    """Form adulterado com um valor fora de {"shadow", "live"} nunca vira
    "live" por acidente -- cai no default seguro."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)

    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})
    resp = client.post(f"/operacao/{DAYTRADE}/iniciar",
                       data={"robo": "gremah", "execution_mode": "sim-por-favor"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].execution_mode == "shadow"


def test_novo_robo_fora_do_registry_nao_cria_conta(isolated_journal, client):
    """Mesmo espírito da checagem do lado swing: um form adulterado mandando
    uma chave que não está no catálogo de day trade não pode colar. A checagem
    mudou de lugar em 2026-08-22 — o robô passou a ser escolhido ao CRIAR o
    cartão, não ao iniciar (o cartão já nasce com robô+ativo no id)."""
    resp = client.post("/operacao/daytrade/novo",
                       data={"robot": "robo_fora_do_catalogo", "symbol": "PMAM3"})

    assert resp.status_code == 200
    assert "desconhecido" in resp.text.lower()
    with live_store.live_journal(isolated_journal) as conn:
        assert live_store.accounts_with_symbol(conn) == []


def test_novo_robo_com_ativo_sem_calibracao_nao_cria_conta(isolated_journal, client):
    """Quem valida o ativo é o ROBÔ: `Gremah.__init__` levanta `ValueError`
    para símbolo sem calibração própria em vez de herdar a de outro papel. O
    painel não pode criar um cartão que nunca conseguiria subir."""
    resp = client.post("/operacao/daytrade/novo",
                       data={"robot": "gremah", "symbol": "PETR4"})

    assert resp.status_code == 200
    assert "calibracao" in resp.text.lower() or "calibração" in resp.text.lower()
    with live_store.live_journal(isolated_journal) as conn:
        assert live_store.accounts_with_symbol(conn) == []


def test_novo_robo_recusa_ativo_ja_em_uso(isolated_journal, client):
    """Conta NETTING: dois robôs no mesmo papel viram uma posição só na
    corretora e os dois caixas passam a mentir. O `disabled` do `<select>` não
    cobre POST repetido nem fragmento velho — a recusa é do servidor."""
    _create_daytrade_account(isolated_journal)

    resp = client.post("/operacao/daytrade/novo",
                       data={"robot": "gremah", "symbol": SYMBOL})

    assert resp.status_code == 200
    assert "NETTING" in resp.text
    with live_store.live_journal(isolated_journal) as conn:
        assert len(live_store.accounts_with_symbol(conn)) == 1


def test_novo_robo_cria_a_conta_com_robo_e_ativo(isolated_journal, client):
    """O caminho feliz: cria a LINHA da conta (caixa zero, nada rodando) com
    robô e ativo gravados — é a conta que faz o cartão existir."""
    resp = client.post("/operacao/daytrade/novo",
                       data={"robot": "gremah", "symbol": "KLBN4"})

    assert resp.status_code == 200
    with live_store.live_journal(isolated_journal) as conn:
        contas = live_store.accounts_with_symbol(conn)
        assert [(c.name, c.investment_robot, c.symbol, c.cash) for c in contas] == [
            ("dt-gremah-klbn4", "gremah", "KLBN4", 0.0)
        ]


def test_operacao_iniciar_daytrade_conta_existente_ignora_robo_do_form(
    isolated_journal, client, monkeypatch,
):
    """Mesma regra do lado swing (2026-08-19): uma conta JÁ EM OPERAÇÃO nunca
    troca de robô através do form de retomada. No day trade isso é ainda mais
    forte desde 2026-08-22 — trocar o robô do cartão significaria trocar o
    ativo junto, o que é outro cartão."""
    db_path = isolated_journal
    _create_daytrade_account(db_path, investment_robot="gremah")
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)

    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))

    resp = client.post(f"/operacao/{DAYTRADE}/iniciar", data={"robo": "outro-robo-qualquer"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].strategy == "gremah"


def test_operacao_conta_existente_com_robo_desconhecido_degrada_sem_500(
    isolated_journal, client,
):
    """Uma conta cujo `investment_robot` gravado não existe mais no registry
    (robô removido do catálogo, linha corrompida) tem de degradar para "sem
    conta" com o motivo no banner -- nunca um 500."""
    _create_daytrade_account(isolated_journal, investment_robot="robo-removido-do-catalogo")

    resp = client.get("/operacao")

    assert resp.status_code == 200
    assert "robo-removido-do-catalogo" in resp.text


# ---------- HTML renderizado: select + badge de ativo ----------------------

def test_painel_mostra_o_form_de_robo_novo_com_ativos_por_capital_minimo(
    isolated_journal, client,
):
    """A escolha de robô+ativo saiu do cartão e virou o formulário "novo
    robô" (2026-08-22). Ele lista os ativos que o robô aceita, do mais barato
    ao mais caro pelo caixa mínimo de hoje — a primeira pergunta de quem
    escolhe é "qual cabe no que eu tenho?"."""
    html = client.get("/operacao").text

    assert 'hx-post="/operacao/daytrade/novo"' in html
    assert '<select name="symbol"' in html
    assert "gremah" in html
    # Todos os ativos calibrados aparecem como opção, não só o default.
    for symbol in ("PMAM3", "KLBN4", "CSAN3"):
        assert symbol in html


def test_ativo_ja_usado_aparece_marcado_e_desabilitado(isolated_journal, client):
    """A bolinha verde do pedido: um ativo que já tem robô não pode ser
    escolhido de novo, e o estado dele fica visível na lista."""
    _create_daytrade_account(isolated_journal)

    html = client.get("/operacao").text

    assert f'value="{SYMBOL}" disabled' in html
    assert "robô criado, parado" in html


def test_fragmento_daytrade_com_conta_mostra_badge_de_ativo(
    isolated_journal, client,
):
    """Com a conta já criada, o painel mostra o ATIVO que o robô escolhido
    opera — informação que não existia como badge antes (o símbolo estava
    só embutido no rótulo estático do slot)."""
    _create_daytrade_account(isolated_journal, investment_robot="gremah")

    html = client.get(f"/operacao/{DAYTRADE}/fragment").text

    assert "Ativo" in html
    assert "PMAM3" in html
