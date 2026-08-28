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

import re

import pytest
from fastapi.testclient import TestClient

from dashboard import app as dashboard_app
from dashboard import live_control, live_service
from journal import live_store

# Slot de day trade DINAMICO desde 2026-08-22: o id carrega robo+ativo+modo
# (`dt-<robo>-<ativo>-<modo>`, modo fixo no id desde 2026-08-24) e o painel
# abre quantos o dono quiser. Nao existe mais um slot fixo chamado
# "daytrade" em `core.config.SLOTS`.
SYMBOL = "PMAM3"
DAYTRADE = "dt-gremah-pmam3-shadow"
# Par de slots do MESMO robô+ativo em modos diferentes (2026-08-24): dois
# cartões/contas/processos independentes -- ver alguns testes abaixo que
# exercitam justamente essa coexistência.
DAYTRADE_LIVE = "dt-gremah-pmam3-live"


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


def _create_daytrade_account(
    db_path, capital: float = 100.0, investment_robot: str = "gremah", name: str = DAYTRADE,
) -> int:
    with live_store.live_journal(db_path) as conn:
        acc = live_store.ensure_account(
            conn, name=name, mode="mt5",
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


def test_list_daytrade_robots_inclui_wdo_grid_reload_maker_como_futuro():
    """`wdo_grid_reload_maker` (TOP-1 desde 2026-08-27) é o primeiro robô de
    FUTURO a entrar neste catálogo -- `is_futuro=True` é o que faz o form de
    "novo robô" em `/operacao` usar margem em vez de lote de ação para o
    caixa mínimo (ver `dashboard/robot_view.py::capital_minimo_para`)."""
    from strategy.daytrade.registry import list_daytrade_robots

    robos = {r.key: r for r in list_daytrade_robots()}
    assert "wdo_grid_reload_maker" in robos
    assert robos["wdo_grid_reload_maker"].symbol == "WDO@"
    assert robos["wdo_grid_reload_maker"].is_futuro is True
    assert robos["wdo_grid_reload_maker"].feed_kind == "tick"


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
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda slot, robot_key=None: None)

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
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda slot, robot_key=None: None)

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
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda slot, robot_key=None: None)

    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})
    resp = client.post(f"/operacao/{DAYTRADE}/iniciar", data={"robo": "gremah"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].mt5_fractional_map is None


def test_operacao_iniciar_daytrade_usa_mapa_de_futuro_detectado_no_config(
    isolated_journal, client, monkeypatch,
):
    """Contraprova do teste anterior: day trade É o único slot que consulta
    `detect_futures_symbol_map()` (só ele opera futuro, WIN@/WDO@) -- achado
    ao vivo em 2026-08-28 (slot do WDO F1: ordem em `WDO@` recusada pelo
    servidor, "Trade disabled", porque o `"@"` contínuo só dá cotação). O
    mapa detectado (ex. `WDO@` -> `WDOU26`, contrato com vencimento em
    aberto) tem de chegar até `ProcessConfig` -- é ele que faz
    `MT5Broker.symbol_for()` traduzir pro contrato que o servidor de fato
    aceita ordem."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(live_control, "detect_futures_symbol_map",
                        lambda slot, robot_key=None: {"WDO@": "WDOU26"})

    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})
    resp = client.post(f"/operacao/{DAYTRADE}/iniciar", data={"robo": "gremah"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].mt5_symbol_map == {"WDO@": "WDOU26"}


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
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(live_control, "min_cash_for", lambda slot, robot_key=None: 900.0)

    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})
    resp = client.post(f"/operacao/{DAYTRADE}/iniciar", data={"robo": "gremah"})

    assert resp.status_code == 200
    assert "900" in resp.text
    assert called == []


def test_operacao_iniciar_daytrade_usa_o_modo_fixo_do_slot(
    isolated_journal, client, monkeypatch,
):
    """O modo vem do PRÓPRIO SLOT (fixo desde a criação, 2026-08-24) --
    `DAYTRADE` termina em '-shadow', então "Iniciar" tem de rodar em sombra
    mesmo sem nenhum campo de modo no form (não existe mais)."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda slot, robot_key=None: None)

    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})
    resp = client.post(f"/operacao/{DAYTRADE}/iniciar", data={"robo": "gremah"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].execution_mode == "shadow"


def test_operacao_iniciar_daytrade_slot_live_ignora_campo_de_form_forjado(
    isolated_journal, client, monkeypatch,
):
    """O ponto central da mudança (2026-08-24): o modo não é mais escolhido
    no form de "Iniciar" -- é o `slot.id`. Um campo `execution_mode` forjado
    no POST (form adulterado, ou o antigo comportamento tentando voltar) é
    simplesmente ignorado; o slot `-live` roda em live mesmo pedindo
    "shadow" no form, e vice-versa (ver o teste seguinte)."""
    _create_daytrade_account(isolated_journal, capital=100.0, name=DAYTRADE_LIVE)
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda slot, robot_key=None: None)

    resp = client.post(f"/operacao/{DAYTRADE_LIVE}/iniciar",
                       data={"robo": "gremah", "execution_mode": "shadow"})

    assert resp.status_code == 200
    assert len(captured) == 1, resp.text
    assert captured[0].execution_mode == "live"
    assert captured[0].slot == DAYTRADE_LIVE


def test_operacao_iniciar_daytrade_slot_shadow_ignora_campo_de_form_forjado(
    isolated_journal, client, monkeypatch,
):
    """Contraprova do teste anterior: o slot `-shadow` roda em sombra mesmo
    que o form (adulterado) peça "live"."""
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda slot, robot_key=None: None)

    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})
    resp = client.post(f"/operacao/{DAYTRADE}/iniciar",
                       data={"robo": "gremah", "execution_mode": "live"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].execution_mode == "shadow"


def test_operacao_iniciar_daytrade_sombra_usa_cash_sombra_para_piso_e_capital(
    isolated_journal, client, monkeypatch,
):
    """O pedido do dono (2026-08-23): "o backend deve ser capaz de rodar com
    o seu saldo". Caixa REAL insuficiente para o piso do robô não pode
    bloquear um início em SOMBRA se o saldo de sombra cobre -- e o capital
    que dimensiona a posição tem de vir desse mesmo saldo de sombra, não do
    caixa real (nem de `initial_capital` congelado)."""
    _create_daytrade_account(isolated_journal, capital=10.0)  # cash=cash_sombra=10
    with live_store.live_journal(isolated_journal) as conn:
        conta = live_store.load_account(conn, DAYTRADE)
        conta.cash_sombra = 500.0  # so' o saldo de sombra sobe
        live_store.save_account(conn, conta)
    monkeypatch.setattr(live_control, "min_cash_for", lambda slot, robot_key=None: 100.0)
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda slot, robot_key=None: None)

    resp = client.post(f"/operacao/{DAYTRADE}/iniciar",
                       data={"robo": "gremah", "execution_mode": "shadow"})

    assert resp.status_code == 200
    assert len(captured) == 1, resp.text
    assert captured[0].capital == pytest.approx(500.0)
    with live_store.live_journal(isolated_journal) as conn:
        conta = live_store.load_account(conn, DAYTRADE)
    assert conta.cash == pytest.approx(10.0)  # caixa real nunca mexido


def test_operacao_iniciar_daytrade_live_usa_cash_real_mesmo_com_sombra_alto(
    isolated_journal, client, monkeypatch,
):
    """Contraprova: no slot `-live`, o saldo de sombra generoso na MESMA
    linha (herdado do schema que ainda guarda os dois campos, ver
    `AccountState.cash_for`) é irrelevante -- o piso e o capital continuam
    vindo do caixa real."""
    _create_daytrade_account(isolated_journal, capital=10.0, name=DAYTRADE_LIVE)  # cash=cash_sombra=10
    with live_store.live_journal(isolated_journal) as conn:
        conta = live_store.load_account(conn, DAYTRADE_LIVE)
        conta.cash_sombra = 500.0
        live_store.save_account(conn, conta)
    monkeypatch.setattr(live_control, "min_cash_for", lambda slot, robot_key=None: 100.0)
    called: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: called.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda slot, robot_key=None: None)

    resp = client.post(f"/operacao/{DAYTRADE_LIVE}/iniciar", data={"robo": "gremah"})

    assert resp.status_code == 200
    assert "100" in resp.text
    assert called == []


def test_operacao_iniciar_colisao_de_simbolo_mostra_modal_com_botao_de_parar(
    isolated_journal, client, monkeypatch,
):
    """Pedido do dono (2026-08-25): colisão de símbolo (`_assert_slots_
    disjuntos`) não pode mais só escrever um banner de texto lá em cima do
    painel — vira um card centralizado (`partials/operacao_colisao.html`)
    com o robô que está no caminho e um botão pra parar ELE, direto dali.
    `live_control.start` é monkeypatchado pra levantar o erro estruturado
    direto (o cenário de colisão em si já tem cobertura própria em
    `test_live_control.py`; aqui o que se testa é o app.py + template)."""
    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})

    def _start(cfg):
        raise live_control.SlotSymbolCollisionError(
            "colisão de símbolo de teste",
            slot_id="dt-gremah_tick-pmam3-live", slot_label="PMAM3 · gremah_tick",
            symbols=["PMAM3"], pode_parar=True, motivo_bloqueio=None,
        )

    monkeypatch.setattr(live_control, "start", _start)
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda slot, robot_key=None: None)

    resp = client.post(f"/operacao/{DAYTRADE}/iniciar", data={"robo": "gremah"})

    assert resp.status_code == 200
    assert 'data-ops-modal' in resp.text
    assert "PMAM3 · gremah_tick" in resp.text
    assert '/operacao/dt-gremah_tick-pmam3-live/parar' in resp.text
    # Sem `erro` no topo -- o card já explica sozinho, repetir seria ruído.
    assert 'class="ops-alert stagger"' not in resp.text


def test_operacao_iniciar_colisao_de_simbolo_com_ordens_desabilita_parar(
    isolated_journal, client, monkeypatch,
):
    """Contraprova: com o outro robô tendo posição/ordem em aberto
    (`pode_parar=False`), o modal não pode oferecer um botão de Parar que
    funcione -- vira `disabled` com a explicação do motivo."""
    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})

    def _start(cfg):
        raise live_control.SlotSymbolCollisionError(
            "colisão de símbolo de teste",
            slot_id="dt-gremah_tick-pmam3-live", slot_label="PMAM3 · gremah_tick",
            symbols=["PMAM3"], pode_parar=False,
            motivo_bloqueio="este robô tem ordens posicionadas ou abertas agora — aguarde.",
        )

    monkeypatch.setattr(live_control, "start", _start)
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda slot, robot_key=None: None)

    resp = client.post(f"/operacao/{DAYTRADE}/iniciar", data={"robo": "gremah"})

    assert resp.status_code == 200
    assert 'data-ops-modal' in resp.text
    assert "aguarde" in resp.text
    assert "disabled" in resp.text
    # O form com hx-post pra /parar não pode existir neste ramo -- só o
    # botão desabilitado, senão um clique acidental (ou um replay do POST)
    # pararia o robô com ordem em aberto.
    assert 'hx-post="/operacao/dt-gremah_tick-pmam3-live/parar"' not in resp.text


def test_operacao_iniciar_daytrade_primeira_vez_em_sombra_nao_infla_initial_capital(
    isolated_journal, client, monkeypatch,
):
    """`conta.initial_capital` alimenta `ja_aportado_brl` em
    `_avaliar_sugestao_de_capital` -- quanto o dono JÁ PÔS de dinheiro DE
    VERDADE nos robôs, usado para não sugerir um aporte novo maior do que o
    que sobra de verdade. Um robô testado pela primeira vez em SOMBRA com um
    saldo de sombra bem maior que o caixa real não pode gravar esse número
    de sombra ali -- só o capital de SIZING (`ProcessConfig.capital`) segue
    o saldo do modo escolhido."""
    client.post(f"/operacao/{DAYTRADE}/caixa", data={"caixa": "100.00"})
    client.post(f"/operacao/{DAYTRADE}/caixa",
               data={"caixa": "500.00", "execution_mode": "shadow"})
    captured: list = []
    monkeypatch.setattr(live_control, "start", lambda cfg: captured.append(cfg))
    monkeypatch.setattr(live_control, "detect_shares_per_lot", lambda slot, robot_key=None: 1.0)
    monkeypatch.setattr(live_control, "detect_fractional_symbol_map", lambda slot, robot_key=None: None)
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda slot, robot_key=None: None)

    resp = client.post(f"/operacao/{DAYTRADE}/iniciar",
                       data={"robo": "gremah", "execution_mode": "shadow"})

    assert resp.status_code == 200
    assert len(captured) == 1, resp.text
    assert captured[0].capital == pytest.approx(500.0)  # sizing: saldo de sombra
    with live_store.live_journal(isolated_journal) as conn:
        conta = live_store.load_account(conn, DAYTRADE)
    assert conta.initial_capital == pytest.approx(100.0)  # persistido: caixa real
    assert conta.cash == pytest.approx(100.0)
    assert conta.cash_sombra == pytest.approx(500.0)


def test_novo_robo_fora_do_registry_nao_cria_conta(isolated_journal, client):
    """Mesmo espírito da checagem do lado swing: um form adulterado mandando
    uma chave que não está no catálogo de day trade não pode colar. A checagem
    mudou de lugar em 2026-08-22 — o robô passou a ser escolhido ao CRIAR o
    cartão, não ao iniciar (o cartão já nasce com robô+ativo no id)."""
    resp = client.post("/operacao/daytrade/novo",
                       data={"robot": "robo_fora_do_catalogo", "symbol": "PMAM3",
                             "execution_mode": "shadow"})

    assert resp.status_code == 200
    assert "desconhecido" in resp.text.lower()
    with live_store.live_journal(isolated_journal) as conn:
        assert live_store.accounts_with_symbol(conn) == []


def test_novo_robo_com_ativo_sem_calibracao_nao_cria_conta(isolated_journal, client):
    """Quem valida o ativo é o ROBÔ: `Gremah.__init__` levanta `ValueError`
    para símbolo sem calibração própria em vez de herdar a de outro papel. O
    painel não pode criar um cartão que nunca conseguiria subir."""
    resp = client.post("/operacao/daytrade/novo",
                       data={"robot": "gremah", "symbol": "PETR4",
                             "execution_mode": "shadow"})

    assert resp.status_code == 200
    assert "calibracao" in resp.text.lower() or "calibração" in resp.text.lower()
    with live_store.live_journal(isolated_journal) as conn:
        assert live_store.accounts_with_symbol(conn) == []


def test_novo_robo_aceita_ativo_ja_usado_por_outro_robo(isolated_journal, client):
    """Criar o cartão nunca manda ordem nenhuma -- dois robôs DIFERENTES no
    mesmo ativo (aqui: gremah_tick junto de um gremah já existente em PMAM3)
    é uma comparação válida (ex.: os dois em sombra), e passou a ser aceita
    (2026-08-24). O risco real (conta NETTING, dois robôs mandando ordem de
    verdade no mesmo papel) só existe no `Iniciar`, checado por
    `live_control._assert_slots_disjuntos`."""
    _create_daytrade_account(isolated_journal)

    resp = client.post("/operacao/daytrade/novo",
                       data={"robot": "gremah_tick", "symbol": SYMBOL,
                             "execution_mode": "shadow"})

    assert resp.status_code == 200, resp.text
    with live_store.live_journal(isolated_journal) as conn:
        contas = {c.investment_robot for c in live_store.accounts_with_symbol(conn)}
    assert contas == {"gremah", "gremah_tick"}


def test_novo_robo_recriar_o_mesmo_par_robo_ativo_e_modo_nao_duplica(isolated_journal, client):
    """Reenviar o MESMO par robô+ativo+modo (POST repetido, fragmento HTMX
    velho) não cria uma segunda linha nem apaga a conta existente -- o
    handler recusa com mensagem antes de chamar `ensure_account` de novo
    (2026-08-24: só o par completo, agora COM modo, precisa ser único)."""
    _create_daytrade_account(isolated_journal)

    resp = client.post("/operacao/daytrade/novo",
                       data={"robot": "gremah", "symbol": SYMBOL, "execution_mode": "shadow"})

    assert resp.status_code == 200, resp.text
    assert "já existe" in resp.text
    with live_store.live_journal(isolated_journal) as conn:
        assert len(live_store.accounts_with_symbol(conn)) == 1


def test_novo_robo_mesmo_robo_ativo_em_outro_modo_cria_cartao_novo(isolated_journal, client):
    """O ponto central do pedido (2026-08-24): o MESMO robô+ativo em sombra E
    em real coexistem como dois cartões/contas/processos independentes --
    dois slots.id diferentes, sem colisão nenhuma."""
    _create_daytrade_account(isolated_journal)  # gremah + PMAM3 em sombra

    resp = client.post("/operacao/daytrade/novo",
                       data={"robot": "gremah", "symbol": SYMBOL, "execution_mode": "live"})

    assert resp.status_code == 200, resp.text
    with live_store.live_journal(isolated_journal) as conn:
        nomes = {c.name for c in live_store.accounts_with_symbol(conn)}
    assert nomes == {DAYTRADE, DAYTRADE_LIVE}


def test_form_novo_robo_marca_os_dois_modos_ja_usados(isolated_journal, client):
    """REGRESSÃO: `_novo_robo_ctx` indexava os slots existentes só por
    `symbol`, então o segundo slot do mesmo par robô+ativo (aqui: gremah em
    PMAM3, sombra E real) apagava o primeiro no dicionário -- o formulário
    "novo robô" perdia o rastro de um dos dois modos e deixava o dono clicar
    "Criar robô" num trio (robô, ativo, modo) que já existia, pro servidor só
    recusar DEPOIS do clique (ver `test_novo_robo_recriar_o_mesmo_par_robo_
    ativo_e_modo_nao_duplica`). Com os dois slots existindo, o <option> de
    PMAM3 para 'gremah' tem que carregar os dois modos em `data-modos-
    usados`, não só o último criado."""
    _create_daytrade_account(isolated_journal, name=DAYTRADE)
    _create_daytrade_account(isolated_journal, name=DAYTRADE_LIVE)

    html = client.get("/operacao").text

    gremah_opt = re.search(rf'<option value="{SYMBOL}" data-robot="gremah"[^>]*>', html)
    assert gremah_opt
    modos = re.search(r'data-modos-usados="([^"]*)"', gremah_opt.group(0))
    assert modos and set(modos.group(1).split(",")) == {"shadow", "live"}


def test_novo_robo_cria_a_conta_com_robo_ativo_e_modo(isolated_journal, client):
    """O caminho feliz: cria a LINHA da conta (caixa zero, nada rodando) com
    robô, ativo e MODO gravados — é a conta que faz o cartão existir, e o
    modo faz parte do id desde 2026-08-24."""
    resp = client.post("/operacao/daytrade/novo",
                       data={"robot": "gremah", "symbol": "KLBN4", "execution_mode": "shadow"})

    assert resp.status_code == 200
    with live_store.live_journal(isolated_journal) as conn:
        contas = live_store.accounts_with_symbol(conn)
        assert [(c.name, c.investment_robot, c.symbol, c.cash) for c in contas] == [
            ("dt-gremah-klbn4-shadow", "gremah", "KLBN4", 0.0)
        ]


def test_novo_robo_sem_modo_recusa(isolated_journal, client):
    resp = client.post("/operacao/daytrade/novo",
                       data={"robot": "gremah", "symbol": "KLBN4"})

    assert resp.status_code == 200
    assert "modo" in resp.text.lower()
    with live_store.live_journal(isolated_journal) as conn:
        assert live_store.accounts_with_symbol(conn) == []


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
    monkeypatch.setattr(live_control, "detect_futures_symbol_map", lambda slot, robot_key=None: None)

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


def test_ativo_ja_usado_aparece_marcado_so_pro_mesmo_robo(isolated_journal, client):
    """A bolinha do pedido, agora DENTRO do <select> (2026-08-22): a lista de
    ativos saiu da página — "pra ver a lista é só clicar no select".

    `em_uso` é POR ROBÔ (2026-08-24): a conta existente é de 'gremah' em
    PMAM3, então só a opção "gremah · PMAM3" carrega `data-em-uso` (o estado
    viaja na própria opção: classe de cor MAIS texto, porque cor sozinha não
    pode carregar informação) -- a opção "gremah_tick · PMAM3" (robô
    DIFERENTE) aparece livre, sem marca nenhuma, porque criar um segundo
    cartão nesse ativo com outro robô é uma combinação válida (o bloqueio de
    verdade é no `Iniciar`, não aqui). Nenhuma opção nasce `disabled` no HTML
    do servidor -- quem desabilita em cima do `data-em-uso` é o JS do robô
    escolhido no `<select>` (ver `operacao.js`)."""
    _create_daytrade_account(isolated_journal)  # gremah + PMAM3

    html = client.get("/operacao").text

    gremah_opt = re.search(rf'<option value="{SYMBOL}" data-robot="gremah"[^>]*>', html)
    gremah_tick_opt = re.search(rf'<option value="{SYMBOL}" data-robot="gremah_tick"[^>]*>', html)
    assert gremah_opt and 'data-em-uso="1"' in gremah_opt.group(0)
    assert gremah_tick_opt and 'data-em-uso' not in gremah_tick_opt.group(0)
    assert not re.search(rf'value="{SYMBOL}"[^>]*\bdisabled\b', html)
    assert 'class="is-idle"' in html          # âmbar: tem robô, está parado
    assert "· parado" in html
    # a lista impressa de todos os ativos deixou de existir
    assert "ops-asset-legend" not in html


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


def test_fragmento_daytrade_caixa_carteira_patrimonio_mostram_so_o_saldo_do_modo_fixo(
    isolated_journal, client,
):
    """O modo é fixo no slot desde 2026-08-24 -- não há mais `<select
    execution_mode>` nem par `data-cash-live`/`data-cash-sombra` pra
    alternar em runtime. `DAYTRADE` é '-shadow': o card Caixa e o resumo do
    cabeçalho têm de mostrar o saldo de SOMBRA, nunca o real, mesmo que o
    real seja diferente na mesma linha (coluna que este slot nunca usa).

    Carteira/Patrimônio saíram do painel de day trade no redesenho de
    2026-08-24 (pedido do dono: "informação repetida e com pouco valor" --
    num robô de um símbolo só, que flatten no fim do pregão, os dois quase
    sempre espelhavam o próprio Caixa). Só sobrevivem no ramo swing (`else`
    de `operacao_slot_live.html`).

    O card "Caixa" ganhou uma sub-linha "aportado" que usa `initial_capital`
    de verdade (`capital=20.0` também vira isso, de propósito) -- então a
    checagem de que o `cash` real não vaza não pode mais ser um "R$ 20,00
    não está em lugar nenhum da página" (colidiria com essa sub-linha
    LEGÍTIMA); tem que mirar especificamente o valor PRINCIPAL do card."""
    _create_daytrade_account(isolated_journal, capital=20.0)  # cash=cash_sombra=20
    with live_store.live_journal(isolated_journal) as conn:
        conta = live_store.load_account(conn, DAYTRADE)
        conta.cash_sombra = 500.0  # so' o saldo de sombra diverge do real
        live_store.save_account(conn, conta)

    html = client.get(f"/operacao/{DAYTRADE}/fragment").text

    # O card Caixa mais o resumo do cabeçalho (`ops-sum-cash`, swap
    # fora-de-banda deste mesmo fragmento) -- 2 ocorrências do MESMO valor.
    assert html.count("R$ 500,00") == 2
    # O `cash` real (nao usado neste slot) nao pode vazar como valor
    # PRINCIPAL do card -- aparecer na sub-linha "aportado" e' esperado.
    assert '<span class="v num">R$ 20,00</span>' not in html
    assert "data-cash-live" not in html


# ---------- reordenar robôs de day trade (arrastar no painel) ---------------

def test_reordenar_grava_a_ordem_e_persiste_em_nova_conexao(isolated_journal, client):
    """Pedido do dono (2026-08-24): arrastar um cartão FECHADO pra outra
    posição, e a ordem sobreviver a F5 (nova requisição) e a reiniciar o
    processo (nova conexão com o banco, sem estado nenhum em memória). O JS
    lê o DOM depois do drop e manda a ordem inteira -- aqui simulamos
    exatamente esse POST."""
    _create_daytrade_account(isolated_journal, name=DAYTRADE)
    _create_daytrade_account(isolated_journal, name="dt-gremah_tick-pmam3-shadow",
                              investment_robot="gremah_tick")
    with live_store.live_journal(isolated_journal) as conn:
        assert [c.name for c in live_store.accounts_with_symbol(conn)] == [
            DAYTRADE, "dt-gremah_tick-pmam3-shadow",
        ]

    resp = client.post("/operacao/daytrade/reordenar",
                       data={"ordem": "dt-gremah_tick-pmam3-shadow," + DAYTRADE})

    assert resp.status_code == 200, resp.text
    with live_store.live_journal(isolated_journal) as conn:
        assert [c.name for c in live_store.accounts_with_symbol(conn)] == [
            "dt-gremah_tick-pmam3-shadow", DAYTRADE,
        ]


def test_reordenar_ignora_nome_que_nao_existe_mais(isolated_journal, client):
    """Um id na ordem que não corresponde a nenhuma conta de day trade (aba
    dupla, robô removido no meio do arrasto) é ignorado em silêncio -- não
    derruba o POST nem corrompe a ordem das contas que sobraram."""
    _create_daytrade_account(isolated_journal, name=DAYTRADE)
    _create_daytrade_account(isolated_journal, name="dt-gremah_tick-pmam3-shadow",
                              investment_robot="gremah_tick")

    resp = client.post("/operacao/daytrade/reordenar",
                       data={"ordem": "dt-nao-existe-mais," + "dt-gremah_tick-pmam3-shadow," + DAYTRADE})

    assert resp.status_code == 200, resp.text
    with live_store.live_journal(isolated_journal) as conn:
        assert [c.name for c in live_store.accounts_with_symbol(conn)] == [
            "dt-gremah_tick-pmam3-shadow", DAYTRADE,
        ]


def test_reordenar_sem_ordem_nao_muda_nada(isolated_journal, client):
    """POST sem o campo `ordem` (ou vazio) não é erro -- só não reordena
    nada, o que cobre o caso de um `dragend` que nunca moveu o cartão de
    lugar (largou no mesmo ponto onde pegou)."""
    _create_daytrade_account(isolated_journal, name=DAYTRADE)
    _create_daytrade_account(isolated_journal, name="dt-gremah_tick-pmam3-shadow",
                              investment_robot="gremah_tick")

    resp = client.post("/operacao/daytrade/reordenar", data={})

    assert resp.status_code == 200, resp.text
    with live_store.live_journal(isolated_journal) as conn:
        assert [c.name for c in live_store.accounts_with_symbol(conn)] == [
            DAYTRADE, "dt-gremah_tick-pmam3-shadow",
        ]
