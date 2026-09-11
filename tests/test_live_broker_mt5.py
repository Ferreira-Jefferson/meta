"""Testes de `live/broker_mt5.py` — MT5Broker, 100% mockado, sem rede.

O pacote `MetaTrader5` real NAO esta instalado neste ambiente (de proposito:
a classe le documentacao de terceiros, nao um SDK instalado). Por isso o
`import live.broker_mt5` no topo deste arquivo — feito ANTES de qualquer
`sys.modules` mockado — ja e a primeira prova de que o import do pacote
`MetaTrader5` dentro de `broker_mt5.py` e sempre LAZY (dentro de metodo):
se estivesse no topo do modulo, este import teria explodido com
`ModuleNotFoundError` antes mesmo do primeiro teste rodar.

Cada teste que precisa do terminal MT5 injeta seu proprio modulo FALSO em
`sys.modules["MetaTrader5"]` via a fixture `fake_mt5` (usa `monkeypatch`, que
desfaz a injecao sozinho ao final do teste — nenhum estado vaza entre
testes)."""
from __future__ import annotations

import importlib.util
import inspect
import sys
import types
from datetime import date

import pytest

from live.broker_mt5 import MT5Broker
from core.live_models import Order, OrderSide, OrderStatus, OrderType


# ---------- prova de import lazy (roda antes de qualquer mock) ------------

@pytest.mark.skipif(
    importlib.util.find_spec("MetaTrader5") is not None,
    reason="pacote MetaTrader5 real instalado nesta maquina (operacao ao vivo) — "
           "a premissa 'ausente' nao vale aqui; o invariante do import lazy "
           "continua coberto por test_import_de_metatrader5_nunca_no_topo_do_modulo, "
           "que e checagem estatica e nao depende do pacote existir ou nao",
)
def test_pacote_mt5_real_nao_instalado_e_import_ja_funcionou():
    """Confirma a premissa: o pacote real `MetaTrader5` de fato nao esta
    instalado neste ambiente, e mesmo assim `from live.broker_mt5 import
    MT5Broker` no topo deste arquivo ja funcionou sem erro — unica forma
    disso acontecer e o `import MetaTrader5` estar dentro de metodo, nunca no
    topo de `broker_mt5.py`.

    SKIPADO na maquina que opera de verdade: la o pacote esta instalado de
    proposito (o terminal MT5 e local, ver `MT5Broker.connect`). Manter o
    teste falhando ali treinaria o dono a ignorar suite vermelha — que custa
    mais caro que este teste vale. Em CI, onde o pacote nao existe, ele roda e
    prova o que sempre provou.
    """
    assert "MetaTrader5" not in sys.modules
    assert importlib.util.find_spec("MetaTrader5") is None


def test_import_de_metatrader5_nunca_no_topo_do_modulo():
    """Checagem estatica complementar: nenhuma linha em coluna 0 (escopo de
    modulo) de `broker_mt5.py` importa `MetaTrader5` — só dentro de corpos de
    metodo (indentados)."""
    import live.broker_mt5 as mod

    source = inspect.getsource(mod)
    for line in source.splitlines():
        if line.startswith("import MetaTrader5") or line.startswith("from MetaTrader5"):
            pytest.fail(f"import de MetaTrader5 fora de metodo (coluna 0): {line!r}")


# ---------- fake MetaTrader5 -------------------------------------------

def _make_fake_mt5(
    *,
    initialize_ok: bool = True,
    symbol_info=None,
    tick=None,
    order_send_result=None,
    history_deals=None,
    history_deals_raises: bool = False,
    last_error=(0, "sem erro"),
    positions=None,
    orders=None,
    positions_get_none: bool = False,
    orders_by_ticket=None,
    # ---- gap medido ao vivo 2026-09-04 (`order_history_state`/
    # `deals_for_position`) -- ver a docstring dos dois metodos.
    #
    # `history_orders_by_ticket`: dict ticket -> lista de registros
    # (`history_orders_get(ticket=...)`) — `None` (default) imita "ticket
    # nao esta no historico" (lista vazia), igual ao pacote real quando a
    # ordem ainda esta pendente. `history_orders_get_none` imita a FALHA de
    # consulta (devolve `None`), distinta de "perguntei e nao ha nada".
    history_orders_by_ticket=None,
    history_orders_get_none: bool = False,
    # `history_deals_by_position`: dict position_id -> lista de deals
    # (`history_deals_get(position=...)`) -- SEPARADO de `history_deals`
    # (que so' responde a `ticket=`, usado por `MT5Broker._resolve_fees`).
    # `history_deals_get_position_none` imita a FALHA de consulta desse
    # lado (`position=`).
    history_deals_by_position=None,
    history_deals_get_position_none: bool = False,
):
    """Monta um `types.ModuleType` que imita a superficie do pacote
    `MetaTrader5` usada por `MT5Broker`, com constantes arbitrarias (o
    codigo sob teste nunca deveria depender do VALOR numerico delas, so de
    igualdade/desigualdade) e um registro de chamadas (`calls`) para
    verificar, por exemplo, que `order_send` nunca e chamado com volume 0."""
    calls = {"order_send": [], "initialize": 0, "initialize_kwargs": [], "history_deals_get": [],
             "history_orders_get": [], "history_deals_get_by_position": []}

    mod = types.ModuleType("MetaTrader5")
    mod.TRADE_ACTION_DEAL = 101
    mod.ORDER_TYPE_BUY = 102
    mod.ORDER_TYPE_SELL = 103
    mod.ORDER_TIME_GTC = 104
    mod.ORDER_FILLING_IOC = 105
    mod.TRADE_RETCODE_DONE = 106
    # SLTP (gap c, `MT5Broker.set_protection`) -- valor arbitrario, mesma
    # regra do resto: o codigo sob teste so compara igualdade, nunca o
    # numero em si.
    mod.TRADE_ACTION_SLTP = 107

    def initialize(**kwargs):
        calls["initialize"] += 1
        calls["initialize_kwargs"].append(kwargs)
        return initialize_ok

    def order_send(request):
        calls["order_send"].append(request)
        # Gap 1.15: `order_send_result` pode ser uma FUNCAO de `request` (em
        # vez de um resultado fixo) para simular respostas DIFERENTES entre a
        # 1a tentativa (com `"position"`) e o reenvio de fallback (sem ele) --
        # os testes de retry precisam disso; todo teste anterior continua
        # passando um valor fixo (nao-chamavel), comportamento inalterado.
        if callable(order_send_result):
            return order_send_result(request)
        return order_send_result

    def history_deals_get(ticket=None, position=None):
        if position is not None:
            calls["history_deals_get_by_position"].append(position)
            if history_deals_raises:
                raise RuntimeError("falha simulada ao consultar historico")
            if history_deals_get_position_none:
                return None
            if history_deals_by_position is None:
                return []
            return history_deals_by_position.get(position, [])
        calls["history_deals_get"].append(ticket)
        if history_deals_raises:
            raise RuntimeError("falha simulada ao consultar historico")
        return history_deals if history_deals is not None else []

    def history_orders_get(ticket=None):
        calls["history_orders_get"].append(ticket)
        if history_orders_get_none:
            return None
        if history_orders_by_ticket is None:
            return []
        return history_orders_by_ticket.get(ticket, [])

    mod.initialize = initialize
    mod.last_error = lambda: last_error
    mod.symbol_select = lambda symbol, enable=True: True
    mod.symbol_info = lambda symbol: symbol_info
    mod.symbol_info_tick = lambda symbol: tick
    mod.order_send = order_send
    mod.history_deals_get = history_deals_get
    mod.history_orders_get = history_orders_get
    mod.ORDER_STATE_FILLED = 4
    mod.ORDER_STATE_PARTIAL = 3
    mod.ORDER_STATE_CANCELED = 2
    mod.ORDER_STATE_REJECTED = 5
    mod.ORDER_STATE_EXPIRED = 6
    mod.TRADE_ACTION_REMOVE = 108
    mod.TRADE_ACTION_PENDING = 109
    mod.ORDER_TYPE_BUY_LIMIT = 110
    mod.ORDER_TYPE_SELL_LIMIT = 111
    mod.ORDER_TIME_DAY = 112
    mod.ORDER_FILLING_RETURN = 113
    mod.POSITION_TYPE_BUY = 0
    # Gap 1.15 (`MT5Broker.place_pending(position_ticket=...)`, fallback):
    # valor REAL do pacote MT5 ("Invalid request"), usado pelos testes de
    # fallback -- o codigo sob teste resolve isto por NOME
    # (`getattr(mt5, "TRADE_RETCODE_INVALID", None)`), entao o numero exato
    # so' importa para os proprios testes montarem um `order_send_result`
    # que bata com ele.
    mod.TRADE_RETCODE_INVALID = 10013

    # `positions`/`orders` fixos, ignorando `symbol=` de proposito -- os
    # testes que usam isto ja montam so' o que importa pro simbolo testado,
    # imitando `mt5.positions_get(symbol=...)`/`orders_get(symbol=...)`.
    #
    # `positions_get_none` imita a FALHA de consulta do pacote real, que
    # devolve `None` -- diferente da tupla vazia de "perguntei e nao ha
    # nada". Ver `MT5Broker.position_state`.
    def positions_get(symbol=None):
        if positions_get_none:
            return None
        return positions if positions is not None else []

    # `ticket=` e' como `MT5Broker._pending_order_alive` pergunta se UM
    # ticket especifico continua vivo no book (`cancel` depende disso para
    # nao mentir). `orders_by_ticket` mapeia ticket -> lista devolvida;
    # `None` como valor imita a falha de consulta.
    def orders_get(symbol=None, ticket=None):
        if ticket is not None:
            if orders_by_ticket is None:
                return []
            return orders_by_ticket.get(ticket, [])
        return orders if orders is not None else []

    mod.positions_get = positions_get
    mod.orders_get = orders_get

    return mod, calls


@pytest.fixture
def fake_mt5(monkeypatch):
    """Instala um `MetaTrader5` fake em `sys.modules`. `monkeypatch` reverte
    sozinho ao final do teste, entao cada teste parte de um `sys.modules`
    limpo (sem vazamento de estado entre testes)."""

    def _install(**kwargs):
        mod, calls = _make_fake_mt5(**kwargs)
        monkeypatch.setitem(sys.modules, "MetaTrader5", mod)
        return mod, calls

    return _install


def _tick(bid=49.9, ask=50.1):
    return types.SimpleNamespace(bid=bid, ask=ask, time=0)


def _symbol_info(volume_min=0.01, volume_max=100.0, volume_step=0.01):
    return types.SimpleNamespace(
        volume_min=volume_min, volume_max=volume_max, volume_step=volume_step,
        point=0.01, trade_contract_size=1.0,
    )


def _order_send_result(retcode, price=50.1, volume=1.0, deal=42, order=888, comment="ok"):
    return types.SimpleNamespace(
        retcode=retcode, price=price, volume=volume, deal=deal, order=order, comment=comment,
    )


# ---------- symbol_for ---------------------------------------------------

def test_symbol_for_remove_sufixo_sa_por_padrao():
    broker = MT5Broker()
    assert broker.symbol_for("WEGE3.SA") == "WEGE3"


def test_symbol_for_sem_sufixo_mantem_como_esta():
    broker = MT5Broker()
    assert broker.symbol_for("PETR4") == "PETR4"


def test_symbol_for_respeita_symbol_map_customizado():
    broker = MT5Broker(symbol_map={"WEGE3.SA": "WEGE3F"})
    assert broker.symbol_for("WEGE3.SA") == "WEGE3F"
    # ticker fora do map continua caindo no default
    assert broker.symbol_for("PETR4.SA") == "PETR4"


# ---------- conexao ------------------------------------------------------

def test_connect_sucesso(fake_mt5):
    mod, calls = fake_mt5(initialize_ok=True)
    broker = MT5Broker()

    assert broker.connect() is True
    assert broker.is_connected() is True
    assert calls["initialize"] == 1


def test_connect_idempotente_nao_reinicializa_se_ja_conectado(fake_mt5):
    mod, calls = fake_mt5(initialize_ok=True)
    broker = MT5Broker()

    broker.connect()
    broker.connect()
    broker.connect()

    assert calls["initialize"] == 1  # so a primeira chamada de fato inicializa


def test_connect_sem_credenciais_chama_initialize_sem_argumentos(fake_mt5):
    mod, calls = fake_mt5(initialize_ok=True)
    broker = MT5Broker()

    broker.connect()

    assert calls["initialize_kwargs"] == [{}]


def test_connect_com_credenciais_repassa_login_senha_servidor(fake_mt5):
    mod, calls = fake_mt5(initialize_ok=True)
    broker = MT5Broker(login=12345, password="segredo", server="Corretora-Live")

    broker.connect()

    assert calls["initialize_kwargs"] == [
        {"login": 12345, "password": "segredo", "server": "Corretora-Live"}
    ]


def test_connect_com_path_repassa_caminho_do_terminal(fake_mt5):
    mod, calls = fake_mt5(initialize_ok=True)
    broker = MT5Broker(path=r"C:\MT5\terminal64.exe")

    broker.connect()

    assert calls["initialize_kwargs"] == [{"path": r"C:\MT5\terminal64.exe"}]


def test_connect_falha_devolve_false_sem_excecao(fake_mt5):
    fake_mt5(initialize_ok=False, last_error=(10004, "terminal nao encontrado"))
    broker = MT5Broker()

    assert broker.connect() is False
    assert broker.is_connected() is False


def test_place_rejeita_sem_excecao_quando_conexao_falha(fake_mt5):
    fake_mt5(initialize_ok=False, last_error=(10004, "terminal nao encontrado"))
    broker = MT5Broker()
    order = Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100)

    result = broker.place(order)

    assert result.status == OrderStatus.REJECTED
    assert "10004" in result.note
    assert result.filled_qty == 0


# ---------- volume: acao -> lote ------------------------------------------

def test_place_converte_quantidade_em_volume_respeitando_step(fake_mt5):
    info = _symbol_info(volume_min=0.01, volume_max=100.0, volume_step=0.01)
    result = _order_send_result(retcode=106, price=50.1, volume=1.0)
    mod, calls = fake_mt5(symbol_info=info, tick=_tick(), order_send_result=result, history_deals=[])

    broker = MT5Broker(shares_per_lot=1.0)
    broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=1))

    assert len(calls["order_send"]) == 1
    assert calls["order_send"][0]["volume"] == pytest.approx(1.0)


def test_place_arredonda_volume_para_baixo_nunca_para_cima(fake_mt5):
    info = _symbol_info(volume_min=0.1, volume_max=100.0, volume_step=0.1)
    result = _order_send_result(retcode=106, price=10.0, volume=0.9)
    mod, calls = fake_mt5(symbol_info=info, tick=_tick(bid=10.0, ask=10.0),
                           order_send_result=result, history_deals=[])

    # 99 acoes / 100 acoes-por-lote = 0.99 lote -> deve virar 0.9 (step 0.1),
    # NUNCA 1.0 (isso seria arredondar pra cima e mandar mais do que o pedido).
    broker = MT5Broker(shares_per_lot=100.0)
    broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=99))

    assert calls["order_send"][0]["volume"] == pytest.approx(0.9)


def test_place_volume_abaixo_do_lote_minimo_rejeita_sem_chamar_order_send(fake_mt5):
    info = _symbol_info(volume_min=1.0, volume_max=100.0, volume_step=1.0)
    mod, calls = fake_mt5(symbol_info=info, tick=_tick())

    # 5 acoes / 100 acoes-por-lote = 0.05 lote < volume_min (1.0)
    broker = MT5Broker(shares_per_lot=100.0)
    order = Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=5)

    result = broker.place(order)

    assert result.status == OrderStatus.REJECTED
    assert result.filled_qty == 0
    assert calls["order_send"] == []  # nunca monta/envia request com volume 0
    assert "volume 0" in result.note or "lote" in result.note.lower()


# ---------- fill bem-sucedido ---------------------------------------------

def test_place_fill_sucesso_preenche_campos_a_partir_do_resultado(fake_mt5):
    info = _symbol_info()
    result = _order_send_result(retcode=106, price=50.1, volume=1.0, deal=999, order=888, comment="ok")
    mod, calls = fake_mt5(symbol_info=info, tick=_tick(bid=49.9, ask=50.1),
                           order_send_result=result, history_deals=[])

    broker = MT5Broker(shares_per_lot=1.0)
    order = Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=1)

    filled = broker.place(order)

    assert filled is order  # muta e devolve o MESMO objeto, como os outros brokers
    assert filled.status == OrderStatus.FILLED
    assert filled.filled_qty == 1
    assert filled.avg_price == pytest.approx(50.1)
    assert filled.broker_ref == "888"
    assert calls["order_send"][0]["price"] == pytest.approx(50.1)  # ask p/ compra
    assert calls["order_send"][0]["type"] == mod.ORDER_TYPE_BUY


def test_place_venda_usa_preco_bid(fake_mt5):
    info = _symbol_info()
    result = _order_send_result(retcode=106, price=49.9, volume=1.0)
    mod, calls = fake_mt5(symbol_info=info, tick=_tick(bid=49.9, ask=50.1),
                           order_send_result=result, history_deals=[])

    broker = MT5Broker(shares_per_lot=1.0)
    broker.place(Order(ticker="WEGE3.SA", side=OrderSide.SELL, quantity=1))

    assert calls["order_send"][0]["price"] == pytest.approx(49.9)  # bid p/ venda
    assert calls["order_send"][0]["type"] == mod.ORDER_TYPE_SELL


def test_place_usa_filling_type_default_ou_customizado(fake_mt5):
    info = _symbol_info()
    result = _order_send_result(retcode=106)
    mod, calls = fake_mt5(symbol_info=info, tick=_tick(), order_send_result=result, history_deals=[])

    default_broker = MT5Broker()
    default_broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=1))
    assert calls["order_send"][0]["type_filling"] == mod.ORDER_FILLING_IOC

    custom_broker = MT5Broker(filling_type=999)
    custom_broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=1))
    assert calls["order_send"][1]["type_filling"] == 999


# ---------- retcode de recusa ----------------------------------------------

def test_place_retcode_diferente_de_done_rejeita_com_comment_no_note(fake_mt5):
    info = _symbol_info()
    result = _order_send_result(retcode=999999, comment="margem insuficiente")
    fake_mt5(symbol_info=info, tick=_tick(), order_send_result=result)

    broker = MT5Broker()
    order = Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100)

    result_order = broker.place(order)

    assert result_order.status == OrderStatus.REJECTED
    assert "margem insuficiente" in result_order.note
    assert result_order.filled_qty == 0


def test_place_order_send_devolve_none_rejeita_sem_excecao(fake_mt5):
    info = _symbol_info()
    fake_mt5(symbol_info=info, tick=_tick(), order_send_result=None,
             last_error=(10018, "mercado fechado"))

    broker = MT5Broker()
    result = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100))

    assert result.status == OrderStatus.REJECTED
    assert "10018" in result.note


def test_place_simbolo_nao_encontrado_rejeita(fake_mt5):
    fake_mt5(symbol_info=None)
    broker = MT5Broker()

    result = broker.place(Order(ticker="NAOEXISTE3.SA", side=OrderSide.BUY, quantity=10))

    assert result.status == OrderStatus.REJECTED
    assert "NAOEXISTE3" in result.note


def test_place_sem_tick_rejeita(fake_mt5):
    fake_mt5(symbol_info=_symbol_info(), tick=None)
    broker = MT5Broker()

    result = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=10))

    assert result.status == OrderStatus.REJECTED


# ---------- gap (b), incidente 2026-08-28: retcode=DONE sem fill real ------
#
# Log real do slot `dt-wdo_grid_reload_maker-wdo@-live`: fill devolvido a
# preco 0.0 e deal=0 (comment="Request executed") no contrato WDO em vigor
# naquele dia -- a corretora devolveu retcode=TRADE_RETCODE_DONE ("sucesso")
# mas sem preco nem deal de verdade.
# `_send` tem de recusar isso, nunca inventar um fill com preco 0.

def test_place_retcode_done_sem_fill_nao_inventa_e_nao_declara_recusa(fake_mt5):
    """`DONE` sem `price`/`deal` e sem como confirmar = INDETERMINADO (`SENT`).

    Este teste guardava, ate 2026-09-09, a assercao `status == REJECTED`. O
    invariante que ele protegia continua de pe' e esta abaixo -- nao inventar
    preco de execucao. O que mudou e' a outra metade: REJECTED significa "a
    corretora NAO executou", e isso o robo nao sabia. `retcode=DONE` diz que o
    servidor ACEITOU o pedido; campos de confirmacao vazios dizem que a
    RESPOSTA veio incompleta.

    Tratar um como o outro custou R$80,00 numa posicao em 2026-09-09 (item
    1.24 de LICOES_DE_PRODUCAO.md): o fechamento executou 2s depois, o robo
    seguiu se achando comprado, reverteu, e a ordem-limite orfa de saida
    virou o segundo contrato de um short numa conta de 1."""
    info = _symbol_info()
    result = _order_send_result(retcode=106, price=0.0, deal=0, comment="Request executed")
    # Sem `history_orders_by_ticket`: a consulta do desfecho nao acha nada.
    fake_mt5(symbol_info=info, tick=_tick(), order_send_result=result, history_deals=[])

    broker = MT5Broker()
    resultado = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=10))

    assert resultado.status == OrderStatus.SENT
    assert resultado.status != OrderStatus.REJECTED
    assert resultado.filled_qty == 0
    assert resultado.avg_price is None  # o invariante original: nada inventado
    assert "INDETERMINADO" in resultado.note


def test_place_retcode_done_com_deal_zero_mas_price_valido_nao_vira_filled(fake_mt5):
    """Mesmo com preco > 0, `deal=0` nao pode virar FILLED -- os dois sinais
    sao checados independentes. Vira INDETERMINADO, nao recusa."""
    info = _symbol_info()
    result = _order_send_result(retcode=106, price=50.1, deal=0)
    fake_mt5(symbol_info=info, tick=_tick(), order_send_result=result, history_deals=[])

    broker = MT5Broker()
    resultado = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=10))

    assert resultado.status == OrderStatus.SENT
    assert resultado.avg_price is None


def test_place_done_sem_fill_mas_historico_confirma_execucao_usa_o_preco_REAL(fake_mt5):
    """O CASO DO INCIDENTE (2026-09-09): a ordem executou, a resposta e' que
    nao contou. Perguntando ao historico, o robo descobre o preco de verdade.

    E' tambem o que faz o diario refletir o MT5 em vez da crenca do robo: no
    incidente o diario gravou "+R$9,50 @ 5114,00" quando a corretora tinha
    executado "@ 5113,50" (+R$5,00)."""
    info = _symbol_info()
    result = _order_send_result(retcode=106, price=0.0, deal=0, order=777,
                                comment="Request executed")
    registro = types.SimpleNamespace(state=4, position_id=555)  # ORDER_STATE_FILLED
    deal_meu = types.SimpleNamespace(
        ticket=1, order=777, entry=1, type=1, price=5113.5, volume=10.0,
        profit=0.0, commission=0.0, swap=0.0, fee=0.0, time=0, time_msc=0, comment="")
    # Deal de OUTRA ordem na MESMA posicao: em NETTING isso acontece, e usar
    # a media da POSICAO daria um preco que nenhuma ordem pagou (foi assim
    # que o incidente produziu `price_open` 5113,75).
    deal_alheio = types.SimpleNamespace(
        ticket=2, order=999, entry=0, type=1, price=5114.0, volume=10.0,
        profit=0.0, commission=0.0, swap=0.0, fee=0.0, time=0, time_msc=0, comment="")
    fake_mt5(symbol_info=info, tick=_tick(), order_send_result=result,
             history_deals=[], history_orders_by_ticket={777: [registro]},
             history_deals_by_position={555: [deal_alheio, deal_meu]})

    broker = MT5Broker()
    resultado = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=10))

    assert resultado.status == OrderStatus.FILLED
    assert resultado.avg_price == pytest.approx(5113.5)  # o MEU deal, nao a media
    assert resultado.broker_ref == "777"


def test_place_done_sem_fill_com_historico_de_cancelamento_ai_sim_rejeita(fake_mt5):
    """REJECTED continua existindo -- mas agora e' afirmacao CONFIRMADA pelo
    historico, nao palpite tirado de campos vazios."""
    info = _symbol_info()
    result = _order_send_result(retcode=106, price=0.0, deal=0, order=777)
    registro = types.SimpleNamespace(state=2, position_id=None)  # ORDER_STATE_CANCELED
    fake_mt5(symbol_info=info, tick=_tick(), order_send_result=result,
             history_deals=[], history_orders_by_ticket={777: [registro]})

    broker = MT5Broker()
    resultado = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=10))

    assert resultado.status == OrderStatus.REJECTED
    assert "canceled" in resultado.note


def test_place_retcode_done_com_price_e_deal_validos_continua_filled(fake_mt5):
    """Regressao do caminho feliz: nao pode ficar mais restritivo do que
    devia."""
    info = _symbol_info()
    result = _order_send_result(retcode=106, price=50.1, volume=10.0, deal=42)
    fake_mt5(symbol_info=info, tick=_tick(bid=49.9, ask=50.1),
             order_send_result=result, history_deals=[])

    broker = MT5Broker()
    resultado = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=10))

    assert resultado.status == OrderStatus.FILLED
    assert resultado.avg_price == pytest.approx(50.1)


# ---------- gap (a), incidente 2026-08-28: fechamento leva o campo "position" -

def test_close_position_inclui_o_ticket_no_request(fake_mt5):
    """O coracao do gap (a): fechar tem de dizer pra corretora QUAL posicao
    esta sendo abatida (`request["position"]`) -- sem isto o motor de risco
    trata como abertura nova e recusa com margem esgotada (retcode=10006
    [MG51], o incidente real)."""
    info = _symbol_info()
    result = _order_send_result(retcode=106, price=49.9, volume=100.0, deal=77)
    mod, calls = fake_mt5(symbol_info=info, tick=_tick(bid=49.9, ask=50.1),
                          order_send_result=result, history_deals=[])

    broker = MT5Broker()
    fechamento = Order(ticker="WEGE3.SA", side=OrderSide.SELL, quantity=100)
    resultado = broker.close_position(fechamento, position_ticket=123456)

    assert resultado.status == OrderStatus.FILLED
    assert calls["order_send"][0]["position"] == 123456


def test_place_normal_de_abertura_nao_leva_campo_position(fake_mt5):
    """`place()` (abertura, comportamento de sempre) NUNCA deve incluir
    `"position"` -- so' `close_position()` (fechamento dedicado) leva."""
    info = _symbol_info()
    result = _order_send_result(retcode=106, price=50.1, deal=42)
    mod, calls = fake_mt5(symbol_info=info, tick=_tick(bid=49.9, ask=50.1),
                          order_send_result=result, history_deals=[])

    broker = MT5Broker()
    broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100))

    assert "position" not in calls["order_send"][0]


def test_close_position_retcode_recusado_vira_rejected(fake_mt5):
    info = _symbol_info()
    result = _order_send_result(retcode=999999, comment="[MG51] Para abrir novas posicoes")
    fake_mt5(symbol_info=info, tick=_tick(), order_send_result=result)

    broker = MT5Broker()
    resultado = broker.close_position(
        Order(ticker="WDO@", side=OrderSide.BUY, quantity=1), position_ticket=999)

    assert resultado.status == OrderStatus.REJECTED
    assert "MG51" in resultado.note


def test_close_position_sem_conexao_rejeita_sem_excecao(fake_mt5):
    fake_mt5(initialize_ok=False, last_error=(10004, "terminal nao encontrado"))
    broker = MT5Broker()

    resultado = broker.close_position(
        Order(ticker="WDO@", side=OrderSide.BUY, quantity=1), position_ticket=999)

    assert resultado.status == OrderStatus.REJECTED
    assert "10004" in resultado.note


# ---------- comissao -------------------------------------------------------

def test_comissao_soma_commission_swap_fee_do_primeiro_deal(fake_mt5):
    info = _symbol_info()
    result = _order_send_result(retcode=106, deal=42)
    deal = types.SimpleNamespace(commission=-1.5, swap=-0.2, fee=-0.1)
    mod, calls = fake_mt5(symbol_info=info, tick=_tick(), order_send_result=result,
                           history_deals=[deal])

    broker = MT5Broker()
    filled = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=1))

    assert filled.fees == pytest.approx(-1.8)
    assert calls["history_deals_get"] == [42]


def test_comissao_fallback_zero_quando_history_deals_vazio(fake_mt5):
    info = _symbol_info()
    result = _order_send_result(retcode=106, deal=42)
    fake_mt5(symbol_info=info, tick=_tick(), order_send_result=result, history_deals=[])

    broker = MT5Broker()
    filled = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=1))

    assert filled.status == OrderStatus.FILLED  # fill nao e afetado pela falha de custo
    assert filled.fees == 0.0


def test_comissao_fallback_zero_quando_history_deals_lanca_excecao(fake_mt5):
    info = _symbol_info()
    result = _order_send_result(retcode=106, deal=42)
    fake_mt5(symbol_info=info, tick=_tick(), order_send_result=result,
              history_deals_raises=True)

    broker = MT5Broker()
    filled = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=1))

    assert filled.status == OrderStatus.FILLED
    assert filled.fees == 0.0


# ---------- fill parcial (FEAT-004, item 4.4b) ------------------------------

def test_place_fill_parcial_vira_partial_nao_filled(fake_mt5):
    """MT5 devolve `volume=1.0` (metade do lote pedido, quantity=2) -- a
    ordem tem de virar PARTIAL, nao FILLED, e `is_terminal` tem de ser
    `False` (o restante ainda pode ser reconciliado)."""
    info = _symbol_info(volume_min=0.01, volume_max=100.0, volume_step=0.01)
    result = _order_send_result(retcode=106, price=50.1, volume=1.0)
    mod, calls = fake_mt5(symbol_info=info, tick=_tick(bid=49.9, ask=50.1),
                          order_send_result=result, history_deals=[])

    broker = MT5Broker(shares_per_lot=1.0)
    order = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=2))

    assert order.status == OrderStatus.PARTIAL
    assert order.filled_qty == 1
    assert order.is_terminal is False
    assert order.leaves_qty == 1


def test_place_fill_total_continua_filled(fake_mt5):
    """Regressao do caminho feliz: fill completo continua FILLED."""
    info = _symbol_info(volume_min=0.01, volume_max=100.0, volume_step=0.01)
    result = _order_send_result(retcode=106, price=50.1, volume=2.0)
    mod, calls = fake_mt5(symbol_info=info, tick=_tick(bid=49.9, ask=50.1),
                          order_send_result=result, history_deals=[])

    broker = MT5Broker(shares_per_lot=1.0)
    order = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=2))

    assert order.status == OrderStatus.FILLED
    assert order.filled_qty == 2
    assert order.is_terminal is True
    assert order.leaves_qty == 0


# ---------- poll / metadados do broker -------------------------------------

def test_poll_e_no_op_sincrono(fake_mt5):
    info = _symbol_info()
    result = _order_send_result(retcode=106)
    fake_mt5(symbol_info=info, tick=_tick(), order_send_result=result, history_deals=[])

    broker = MT5Broker()
    order = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=1))

    polled = broker.poll(order)

    assert polled is order
    assert polled.status == OrderStatus.FILLED


def test_supports_automation_true_e_metadados():
    broker = MT5Broker()
    assert broker.supports_automation() is True
    assert broker.mode == "mt5"
    assert broker.name == "mt5"


# ---------- cash_balance (reconciliacao de deposito) -----------------------

def test_cash_balance_conectado_devolve_balance_da_conta(fake_mt5):
    mod, calls = fake_mt5(initialize_ok=True)
    mod.account_info = lambda: types.SimpleNamespace(balance=12_345.67, equity=13_000.0)
    broker = MT5Broker()

    assert broker.cash_balance() == pytest.approx(12_345.67)


def test_cash_balance_falha_de_conexao_devolve_none_sem_excecao(fake_mt5):
    fake_mt5(initialize_ok=False, last_error=(10004, "terminal nao encontrado"))
    broker = MT5Broker()

    assert broker.cash_balance() is None


def test_cash_balance_account_info_none_devolve_none(fake_mt5):
    mod, calls = fake_mt5(initialize_ok=True)
    mod.account_info = lambda: None
    broker = MT5Broker()

    assert broker.cash_balance() is None


# ---------- gap (e), incidente 2026-08-28: freio duro de equity/margem -----

def test_account_risk_state_devolve_equity_margem_livre_balance_e_margem_usada(fake_mt5):
    """`margin` (margem JA COMPROMETIDA) entrou em 2026-09-08: e' o unico
    campo daqui que nao deriva do saldo, e por isso o unico que o portao de
    envio (`_check_margem_da_conta`) pode usar para decidir. Os outros tres
    sao diagnostico -- o saldo da Rico nao acompanha o da corretora."""
    mod, calls = fake_mt5(initialize_ok=True)
    mod.account_info = lambda: types.SimpleNamespace(
        balance=300.0, equity=-298.60, margin_free=-150.0, margin=450.0)
    broker = MT5Broker()

    estado = broker.account_risk_state()

    assert estado == {"equity": -298.60, "margin_free": -150.0, "balance": 300.0,
                      "margin": 450.0}


def test_account_risk_state_falha_de_conexao_devolve_none_sem_excecao(fake_mt5):
    fake_mt5(initialize_ok=False, last_error=(10004, "terminal nao encontrado"))
    broker = MT5Broker()

    assert broker.account_risk_state() is None


def test_account_risk_state_account_info_none_devolve_none(fake_mt5):
    mod, calls = fake_mt5(initialize_ok=True)
    mod.account_info = lambda: None
    broker = MT5Broker()

    assert broker.account_risk_state() is None


# ---------- gap (c), incidente 2026-08-28: SL/TP registrado na corretora ---

def _symbol_info_protecao(trade_tick_size=0.5, point=0.5, trade_stops_level=10):
    return types.SimpleNamespace(
        trade_tick_size=trade_tick_size, point=point, trade_stops_level=trade_stops_level,
    )


def test_set_protection_manda_sltp_com_position_e_niveis_arredondados(fake_mt5):
    mod, calls = fake_mt5(symbol_info=_symbol_info_protecao(), tick=_tick(bid=5200.0, ask=5200.5),
                          order_send_result=_order_send_result(retcode=106))
    broker = MT5Broker()

    resultado = broker.set_protection("WDO@", position_ticket=555, side="long",
                                      stop=5187.3, target=5220.2)

    assert resultado["ok"] is True
    enviado = calls["order_send"][0]
    assert enviado["action"] == mod.TRADE_ACTION_SLTP
    assert enviado["position"] == 555
    # 5187.3 arredondado pro tick 0.5 mais proximo -> 5187.5; 5220.2 -> 5220.0.
    assert enviado["sl"] == pytest.approx(5187.5)
    assert enviado["tp"] == pytest.approx(5220.0)


def test_set_protection_afasta_nivel_colado_no_preco_pelo_stops_level(fake_mt5):
    """`trade_stops_level=10` pontos, `point=0.5` -> distancia minima 5.0. Um
    stop pedido a 5199.9 (a 0.1 do bid=5200.0, bem dentro do minimo) tem de
    ser AFASTADO para o limite, nao enviado colado -- a corretora recusaria
    por granularidade/distancia."""
    mod, calls = fake_mt5(symbol_info=_symbol_info_protecao(), tick=_tick(bid=5200.0, ask=5200.5),
                          order_send_result=_order_send_result(retcode=106))
    broker = MT5Broker()

    broker.set_protection("WDO@", position_ticket=555, side="long", stop=5199.9, target=None)

    enviado = calls["order_send"][0]
    # limite = bid(5200.0) - distancia(5.0) = 5195.0
    assert enviado["sl"] == pytest.approx(5195.0)
    assert enviado["tp"] == pytest.approx(0.0)  # sem alvo -> TP zerado, nunca inventado


def test_set_protection_recusa_da_corretora_devolve_ok_false_sem_excecao(fake_mt5):
    mod, calls = fake_mt5(
        symbol_info=_symbol_info_protecao(), tick=_tick(bid=5200.0, ask=5200.5),
        order_send_result=_order_send_result(retcode=999999, comment="invalid stops"))
    broker = MT5Broker()

    resultado = broker.set_protection("WDO@", position_ticket=555, side="long", stop=5100.0)

    assert resultado["ok"] is False
    assert "invalid stops" in resultado["note"]


def test_set_protection_falha_de_conexao_devolve_ok_false_sem_excecao(fake_mt5):
    fake_mt5(initialize_ok=False, last_error=(10004, "terminal nao encontrado"))
    broker = MT5Broker()

    resultado = broker.set_protection("WDO@", position_ticket=1, side="long", stop=5100.0)

    assert resultado["ok"] is False


def test_open_position_reporta_sl_tp_atuais(fake_mt5):
    """`_ensure_protecao` (runtime) precisa saber o que JA esta registrado
    na corretora pra nao reenviar SLTP toda barra -- `open_position` tem de
    devolver `sl`/`tp` junto do resto."""
    mod, calls = fake_mt5(initialize_ok=True)
    mod.POSITION_TYPE_BUY = 0
    posicao = types.SimpleNamespace(
        magic=20260817, volume=1.0, type=0, price_open=5200.0, ticket=42,
        sl=5187.5, tp=5220.0,
    )
    mod.positions_get = lambda symbol=None: [posicao]
    broker = MT5Broker(magic=20260817)

    resultado = broker.open_position("WDO@")

    assert resultado["sl"] == pytest.approx(5187.5)
    assert resultado["tp"] == pytest.approx(5220.0)


# ---------- cancel: so' marca CANCELLED o que a corretora CONFIRMOU morto --
#
# Estes cinco testes guardam a invariante que estava QUEBRADA ate 2026-08-28:
# `cancel` marcava `CANCELLED` nos dois ramos (sucesso e falha). Como
# `CANCELLED` e' terminal e todo o rastreamento de orfa filtra por
# `not is_terminal`, nenhuma ordem orfa era rastreada NUNCA -- e
# `live_teardown` apagava a conta dando a corretora por limpa.

def _pendente(ticket="777"):
    return Order(ticker="WDO@", side=OrderSide.BUY, quantity=1,
                 broker_ref=ticket, status=OrderStatus.SENT)


def test_cancel_confirmado_pela_corretora_fica_cancelled(fake_mt5):
    mod, calls = fake_mt5(initialize_ok=True,
                          order_send_result=_order_send_result(retcode=106))
    broker = MT5Broker()

    devolvida = broker.cancel(_pendente())

    assert devolvida.status == OrderStatus.CANCELLED
    assert calls["order_send"][0]["action"] == mod.TRADE_ACTION_REMOVE


def test_cancel_recusado_com_ordem_AINDA_VIVA_nao_fica_cancelled(fake_mt5):
    """O caso que custou caro: a corretora recusa remover e a ordem CONTINUA
    no book. Marcar `CANCELLED` aqui apagava o ticket do rastreamento de
    orfas -- e essa ordem preenche sozinha depois, abrindo posicao sem stop
    que ninguem esta vigiando."""
    viva = types.SimpleNamespace(ticket=777, volume_current=1.0)
    fake_mt5(initialize_ok=True,
             order_send_result=_order_send_result(retcode=999, comment="recusado"),
             orders_by_ticket={777: [viva]})
    broker = MT5Broker()

    devolvida = broker.cancel(_pendente("777"))

    assert devolvida.status != OrderStatus.CANCELLED
    assert not devolvida.is_terminal, "ordem viva tem de continuar rastreavel como orfa"
    assert "CONTINUA VIVA" in devolvida.note


def test_cancel_recusado_mas_ordem_sumiu_do_book_fica_cancelled(fake_mt5):
    """Recusa porque o ticket ja nao existe (preencheu, expirou, cancelado na
    mao) e' objetivo CUMPRIDO -- ai `CANCELLED` e' honesto, e insistir seria
    retry infinito de verdade."""
    fake_mt5(initialize_ok=True,
             order_send_result=_order_send_result(retcode=999, comment="nao existe"),
             orders_by_ticket={777: []})
    broker = MT5Broker()

    devolvida = broker.cancel(_pendente("777"))

    assert devolvida.status == OrderStatus.CANCELLED
    assert "confirmado contra a lista de pendentes" in devolvida.note


def test_cancel_sem_conseguir_confirmar_trata_como_VIVA(fake_mt5):
    """"Nao sei" nunca pode virar "ja morreu": se nem da' pra perguntar se a
    ordem existe, ela segue vigiada."""
    mod, _ = fake_mt5(initialize_ok=True,
                      order_send_result=_order_send_result(retcode=999))

    def explode(symbol=None, ticket=None):
        raise RuntimeError("terminal caiu no meio da consulta")

    mod.orders_get = explode
    broker = MT5Broker()

    devolvida = broker.cancel(_pendente("777"))

    assert not devolvida.is_terminal
    assert "nao sei" in devolvida.note


def test_cancel_sem_conexao_nao_fica_cancelled(fake_mt5):
    fake_mt5(initialize_ok=False, last_error=(10004, "terminal fechado"))
    broker = MT5Broker()

    devolvida = broker.cancel(_pendente())

    assert not devolvida.is_terminal
    assert "NAO confirmada morta" in devolvida.note


# ---------- protecao ATOMICA: sl/tp no MESMO request que abre a ordem -------

def test_place_pending_leva_sl_e_tp_no_proprio_request(fake_mt5):
    """A invariante central depois do incidente 2026-08-28: entre registrar a
    ordem-limite e ela preencher podem passar horas, e o processo pode morrer
    no meio. Com `sl`/`tp` amarrados na PROPRIA ordem, a corretora protege a
    posicao no instante do fill -- sem processo nenhum no meio."""
    mod, calls = fake_mt5(initialize_ok=True, symbol_info=_symbol_info(),
                          order_send_result=_order_send_result(retcode=106, order=555))
    broker = MT5Broker()
    order = Order(ticker="WDO@", side=OrderSide.BUY, quantity=1,
                  order_type=OrderType.LIMIT, limit_price=5200.0,
                  stop_price=5180.0, target_price=5205.0)

    devolvida = broker.place_pending(order)

    enviado = calls["order_send"][0]
    assert enviado["action"] == mod.TRADE_ACTION_PENDING
    assert enviado["sl"] == pytest.approx(5180.0)
    assert enviado["tp"] == pytest.approx(5205.0)
    assert devolvida.status == OrderStatus.SENT


def test_place_pending_sem_niveis_nao_manda_sl_nem_tp(fake_mt5):
    """Estrategia que nao declara stop/alvo continua funcionando como antes --
    a protecao atomica e' oportunista, nao um requisito novo."""
    _mod, calls = fake_mt5(initialize_ok=True, symbol_info=_symbol_info(),
                           order_send_result=_order_send_result(retcode=106, order=555))
    broker = MT5Broker()

    broker.place_pending(Order(ticker="WDO@", side=OrderSide.BUY, quantity=1,
                               order_type=OrderType.LIMIT, limit_price=5200.0))

    assert "sl" not in calls["order_send"][0]
    assert "tp" not in calls["order_send"][0]


# ---------- gap 1.15 (2026-09-03): `position` na ordem-limite PENDENTE -----
#
# A correcao do campo `position` depois do incidente MG51 (item 1.1) so'
# cobriu `_send`/`close_position` (fechamento a MERCADO). `place_pending`
# nunca ganhou o campo nem o parametro -- e' o caminho que `place_exit_limit`
# usa para a fatia de SAIDA por alvo dos robos `gremah`/`gremah_tick`. Estes
# testes fecham a lacuna do lado do REQUEST; `test_intraday_live_runtime.py`
# (secao "gap 1.15") fecha do lado de QUEM chama `place_pending` com o
# ticket certo.

def test_place_pending_com_position_ticket_leva_o_campo_no_request(fake_mt5):
    """O caso central do gap: informado `position_ticket`, o request da
    ordem-limite pendente leva `"position"` -- o MESMO campo que
    `close_position` ja leva no fechamento a MERCADO (item 1.1)."""
    _mod, calls = fake_mt5(initialize_ok=True, symbol_info=_symbol_info(),
                           order_send_result=_order_send_result(retcode=106, order=555))
    broker = MT5Broker()

    devolvida = broker.place_pending(
        Order(ticker="WDO@", side=OrderSide.SELL, quantity=1,
              order_type=OrderType.LIMIT, limit_price=5200.0),
        position_ticket=4242,
    )

    assert calls["order_send"][0]["position"] == 4242
    assert devolvida.status == OrderStatus.SENT


def test_place_pending_sem_position_ticket_nao_leva_o_campo(fake_mt5):
    """Sem `position_ticket` (o caso de sempre -- ordem-limite de ENTRADA),
    nada muda: nenhum campo `"position"` novo vaza para o request."""
    _mod, calls = fake_mt5(initialize_ok=True, symbol_info=_symbol_info(),
                           order_send_result=_order_send_result(retcode=106, order=555))
    broker = MT5Broker()

    broker.place_pending(Order(ticker="WDO@", side=OrderSide.BUY, quantity=1,
                               order_type=OrderType.LIMIT, limit_price=5200.0))

    assert "position" not in calls["order_send"][0]


def test_place_pending_de_FECHAMENTO_nunca_leva_sl_tp(fake_mt5):
    """Uma ordem-limite que FECHA posicao (`position_ticket` preenchido) nao
    abre nada que precise de protecao -- mandar sl/tp nela mexeria na
    posicao que esta sendo encerrada. Mesma exclusao que `_send` ja faz para
    `TRADE_ACTION_DEAL` (`test_ordem_de_FECHAMENTO_nunca_leva_sl_tp`)."""
    _mod, calls = fake_mt5(initialize_ok=True, symbol_info=_symbol_info(),
                           order_send_result=_order_send_result(retcode=106, order=555))
    broker = MT5Broker()

    broker.place_pending(
        Order(ticker="WDO@", side=OrderSide.SELL, quantity=1,
              order_type=OrderType.LIMIT, limit_price=5200.0,
              stop_price=5180.0, target_price=5205.0),
        position_ticket=4242,
    )

    enviado = calls["order_send"][0]
    assert enviado["position"] == 4242
    assert "sl" not in enviado and "tp" not in enviado


def test_place_pending_com_ticket_recusado_reenvia_UMA_vez_sem_o_campo(fake_mt5):
    """RESTRICAO NAO-NEGOCIAVEL do gap 1.15: nunca foi confirmado contra
    terminal real se `TRADE_ACTION_PENDING` aceita `"position"`. Se a
    corretora recusar com um retcode que sugere "campo/formato invalido"
    (`TRADE_RETCODE_INVALID`), o metodo tenta UMA UNICA vez sem o campo --
    nunca falha em silencio (sucesso final ainda carrega a nota do
    fallback) e nunca vira laco de retry (so' 2 chamadas a `order_send`)."""
    invalido = _order_send_result(retcode=10013, comment="Invalid request")
    done = _order_send_result(retcode=106, order=777)

    def sequencia(request):
        return invalido if "position" in request else done

    mod, calls = fake_mt5(initialize_ok=True, symbol_info=_symbol_info(),
                          order_send_result=sequencia)
    # `TRADE_RETCODE_INVALID` do fake ja e' 10013 (ver `_make_fake_mt5`) e
    # `TRADE_RETCODE_DONE` e' 106 -- fixados aqui em vez de lidos de `mod`
    # porque `sequencia` precisa existir ANTES do modulo fake ser instalado.
    assert mod.TRADE_RETCODE_INVALID == 10013
    assert mod.TRADE_RETCODE_DONE == 106
    broker = MT5Broker()

    devolvida = broker.place_pending(
        Order(ticker="WDO@", side=OrderSide.SELL, quantity=1,
              order_type=OrderType.LIMIT, limit_price=5200.0),
        position_ticket=4242,
    )

    assert len(calls["order_send"]) == 2, "tem de tentar exatamente UMA vez a mais, nunca um laco"
    assert calls["order_send"][0]["position"] == 4242
    assert "position" not in calls["order_send"][1]
    assert devolvida.status == OrderStatus.SENT
    assert devolvida.broker_ref == "777"
    assert "FALLBACK" in devolvida.note
    assert "1.15" in devolvida.note


def test_place_pending_com_ticket_recusado_dos_dois_jeitos_fica_REJECTED(fake_mt5):
    """A recusa persiste mesmo sem o campo (nao era o campo, era outra
    coisa -- preco, margem, mercado fechado): fica REJECTED, com as DUAS
    recusas na nota, e sem terceira tentativa nenhuma."""
    invalido = _order_send_result(retcode=10013, comment="Invalid request")
    mod, calls = fake_mt5(initialize_ok=True, symbol_info=_symbol_info(),
                          order_send_result=lambda request: invalido)
    assert mod.TRADE_RETCODE_INVALID == 10013
    broker = MT5Broker()

    devolvida = broker.place_pending(
        Order(ticker="WDO@", side=OrderSide.SELL, quantity=1,
              order_type=OrderType.LIMIT, limit_price=5200.0),
        position_ticket=4242,
    )

    assert len(calls["order_send"]) == 2, "nunca mais que UMA tentativa extra"
    assert devolvida.status == OrderStatus.REJECTED
    assert "COM 'position'" in devolvida.note
    assert "SEM" in devolvida.note


def test_place_pending_com_ticket_recusado_por_outro_motivo_nao_reenvia(fake_mt5):
    """Recusa que NAO sugere "campo invalido" (aqui: motivo generico de
    negocio, ex. preco/margem) nao aciona o fallback -- reenviar sem o
    campo nao mudaria nada, e mascarar o motivo real seria pior que nao
    tentar. So' UMA chamada a `order_send`."""
    _mod, calls = fake_mt5(initialize_ok=True, symbol_info=_symbol_info(),
                           order_send_result=_order_send_result(
                               retcode=999999, comment="No money"))
    broker = MT5Broker()

    devolvida = broker.place_pending(
        Order(ticker="WDO@", side=OrderSide.SELL, quantity=1,
              order_type=OrderType.LIMIT, limit_price=5200.0),
        position_ticket=4242,
    )

    assert len(calls["order_send"]) == 1, "motivo nao e' o campo -- nao reenvia"
    assert devolvida.status == OrderStatus.REJECTED
    assert "No money" in devolvida.note


def test_ordem_a_mercado_de_ABERTURA_leva_sl_tp(fake_mt5):
    _mod, calls = fake_mt5(initialize_ok=True, symbol_info=_symbol_info(),
                           tick=_tick(bid=5199.5, ask=5200.0),
                           order_send_result=_order_send_result(retcode=106, price=5200.0))
    broker = MT5Broker()

    broker.place(Order(ticker="WDO@", side=OrderSide.BUY, quantity=1,
                       stop_price=5180.0, target_price=5210.0))

    assert calls["order_send"][0]["sl"] == pytest.approx(5180.0)
    assert calls["order_send"][0]["tp"] == pytest.approx(5210.0)


def test_ordem_de_FECHAMENTO_nunca_leva_sl_tp(fake_mt5):
    """Uma ordem que ABATE posicao nao abre nada que precise de protecao, e
    mandar `sl`/`tp` nela mexeria na posicao que esta sendo encerrada."""
    _mod, calls = fake_mt5(initialize_ok=True, symbol_info=_symbol_info(),
                           tick=_tick(bid=5199.5, ask=5200.0),
                           order_send_result=_order_send_result(retcode=106, price=5200.0))
    broker = MT5Broker()

    broker.close_position(
        Order(ticker="WDO@", side=OrderSide.SELL, quantity=1,
              stop_price=5180.0, target_price=5210.0),
        position_ticket=99)

    enviado = calls["order_send"][0]
    assert enviado["position"] == 99
    assert "sl" not in enviado and "tp" not in enviado


# ---------- set_protection: nunca APAGA, nunca AFROUXA ---------------------

def test_set_protection_sem_alvo_PRESERVA_o_tp_registrado(fake_mt5):
    """Num `TRADE_ACTION_SLTP`, `tp=0.0` nao e' "deixa como esta": e' REMOVER
    o alvo. Uma estrategia sem alvo apagava, a cada reforco, o TP que ja
    estava registrado na posicao."""
    _mod, calls = fake_mt5(initialize_ok=True, symbol_info=_symbol_info(),
                           tick=_tick(bid=5199.5, ask=5200.0),
                           order_send_result=_order_send_result(retcode=106))
    broker = MT5Broker()

    resultado = broker.set_protection("WDO@", position_ticket=42, side="long",
                                      stop=5180.0, target=None,
                                      sl_atual=0.0, tp_atual=5220.0)

    assert resultado["ok"] is True
    assert calls["order_send"][0]["tp"] == pytest.approx(5220.0), \
        "o alvo ja registrado tem de ser preservado, nunca zerado"


def test_set_protection_nunca_AFROUXA_o_stop_ja_registrado(fake_mt5):
    """Long com SL em 5190 nao pode ter o stop recuado para 5180 -- stop anda
    numa direcao so', mesma regra de `AdjustStop` no motor inteiro."""
    _mod, calls = fake_mt5(initialize_ok=True, symbol_info=_symbol_info(),
                           tick=_tick(bid=5199.5, ask=5200.0),
                           order_send_result=_order_send_result(retcode=106))
    broker = MT5Broker()

    broker.set_protection("WDO@", position_ticket=42, side="long",
                          stop=5180.0, target=None, sl_atual=5190.0, tp_atual=0.0)

    assert calls["order_send"][0]["sl"] == pytest.approx(5190.0)


def test_set_protection_sem_nada_a_registrar_nao_manda_request(fake_mt5):
    """Sem stop, sem alvo e sem nada registrado a preservar, um SLTP zerado
    seria um pedido explicito de REMOVER protecao -- o oposto do que este
    metodo existe para fazer."""
    _mod, calls = fake_mt5(initialize_ok=True, symbol_info=_symbol_info(),
                           tick=_tick(), order_send_result=_order_send_result(retcode=106))
    broker = MT5Broker()

    resultado = broker.set_protection("WDO@", position_ticket=42, side="long")

    assert resultado["ok"] is False
    assert calls["order_send"] == []


# ---------- position_state: "nao ha posicao" != "nao consegui perguntar" ----

def test_position_state_consulta_que_falha_devolve_ok_false(fake_mt5):
    """`positions_get` devolve `None` quando a CONSULTA falha e tupla vazia
    quando ela deu certo e nao ha nada. Confundir as duas fazia um terminal
    fora do ar virar "conta zerada" -- e o robo decidia mandar ordem em cima
    disso."""
    fake_mt5(initialize_ok=True, positions_get_none=True)
    broker = MT5Broker()

    estado = broker.position_state("WDO@")

    assert estado["ok"] is False
    assert estado["position"] is None
    assert broker.open_position("WDO@") is None


def test_position_state_sem_posicao_devolve_ok_true(fake_mt5):
    fake_mt5(initialize_ok=True, positions=[])
    broker = MT5Broker()

    estado = broker.position_state("WDO@")

    assert estado["ok"] is True
    assert estado["position"] is None


def test_position_state_sem_conexao_devolve_ok_false(fake_mt5):
    fake_mt5(initialize_ok=False, last_error=(10004, "terminal fechado"))
    broker = MT5Broker()

    assert broker.position_state("WDO@")["ok"] is False


# ---------- detect_shares_per_lot (nao digitado, detectado do terminal) ----

def test_detect_shares_per_lot_todos_tickers_com_mesmo_contract_size(fake_mt5):
    mod, calls = fake_mt5(initialize_ok=True)
    mod.symbol_info = lambda symbol: types.SimpleNamespace(trade_contract_size=1.0)
    broker = MT5Broker()

    assert broker.detect_shares_per_lot(["WEGE3.SA", "BRAP4.SA"]) == pytest.approx(1.0)


def test_detect_shares_per_lot_contract_size_divergente_devolve_none(fake_mt5):
    """O sistema assume UM `shares_per_lot` global pro portfolio inteiro
    (ver `_resolve_volume`) -- se os tickers pedidos nao concordam num unico
    valor, nao ha resposta automatica correta e a funcao recusa a inventar
    uma."""
    mod, calls = fake_mt5(initialize_ok=True)
    sizes = {"WEGE3": 1.0, "BRAP4": 100.0}
    mod.symbol_info = lambda symbol: types.SimpleNamespace(trade_contract_size=sizes[symbol])
    broker = MT5Broker()

    assert broker.detect_shares_per_lot(["WEGE3.SA", "BRAP4.SA"]) is None


def test_detect_shares_per_lot_simbolo_ausente_no_terminal_devolve_none(fake_mt5):
    mod, calls = fake_mt5(initialize_ok=True)
    mod.symbol_info = lambda symbol: None
    broker = MT5Broker()

    assert broker.detect_shares_per_lot(["WEGE3.SA"]) is None


def test_detect_shares_per_lot_falha_de_conexao_devolve_none_sem_excecao(fake_mt5):
    fake_mt5(initialize_ok=False, last_error=(10004, "terminal nao encontrado"))
    broker = MT5Broker()

    assert broker.detect_shares_per_lot(["WEGE3.SA"]) is None


def test_detect_shares_per_lot_usa_symbol_map_na_consulta(fake_mt5):
    """`detect_shares_per_lot` traduz o ticker interno pro nome do simbolo no
    terminal (`symbol_for`) antes de consultar, igual ao resto da classe."""
    mod, calls = fake_mt5(initialize_ok=True)
    mod.symbol_info = lambda symbol: (
        types.SimpleNamespace(trade_contract_size=1.0) if symbol == "WEGE3F" else None
    )
    broker = MT5Broker(symbol_map={"WEGE3.SA": "WEGE3F"})

    assert broker.detect_shares_per_lot(["WEGE3.SA"]) == pytest.approx(1.0)


# ---------- detect_fractional_symbol_map (mercado fracionario, sufixo F) --

def test_detect_fractional_symbol_map_usa_sufixo_f_quando_existe(fake_mt5):
    """Ticker com simbolo `*F` no terminal (mercado fracionario, ex. Rico)
    mapeia para ele -- e nao para o simbolo de lote padrao."""
    mod, calls = fake_mt5(initialize_ok=True)
    existentes = {"WEGE3F", "BRAP4F"}
    mod.symbol_info = lambda symbol: (
        types.SimpleNamespace() if symbol in existentes else None
    )
    broker = MT5Broker()

    assert broker.detect_fractional_symbol_map(["WEGE3.SA", "BRAP4.SA"]) == {
        "WEGE3.SA": "WEGE3F", "BRAP4.SA": "BRAP4F",
    }


def test_detect_fractional_symbol_map_sem_sufixo_f_cai_no_simbolo_padrao(fake_mt5):
    """Ticker SEM simbolo fracionario no terminal mapeia para o simbolo de
    lote padrao -- mesmo comportamento de hoje pra ele, um mapa parcial nao
    faz o mapa inteiro falhar (diferente de `detect_shares_per_lot`, que
    exige um valor unico entre todos os tickers)."""
    mod, calls = fake_mt5(initialize_ok=True)
    mod.symbol_info = lambda symbol: None  # nenhum *F existe no terminal
    broker = MT5Broker()

    assert broker.detect_fractional_symbol_map(["WEGE3.SA", "EMAE4.SA"]) == {
        "WEGE3.SA": "WEGE3", "EMAE4.SA": "EMAE4",
    }


def test_detect_fractional_symbol_map_mistura_com_e_sem_fracionario(fake_mt5):
    """Um pool largo de tickers (ex. universo por liquidez) pode ter alguns
    com mercado fracionario e outros sem -- o mapa cobre cada um
    independentemente, sem exigir uniformidade."""
    mod, calls = fake_mt5(initialize_ok=True)
    existentes = {"WEGE3F"}
    mod.symbol_info = lambda symbol: (
        types.SimpleNamespace() if symbol in existentes else None
    )
    broker = MT5Broker()

    assert broker.detect_fractional_symbol_map(["WEGE3.SA", "CSMG3.SA"]) == {
        "WEGE3.SA": "WEGE3F", "CSMG3.SA": "CSMG3",
    }


def test_detect_fractional_symbol_map_respeita_symbol_map_customizado_na_base(fake_mt5):
    """Se o broker ja tem um `symbol_map` customizado (ex. corretora que
    cadastra o simbolo com outro nome), a deteccao fracionaria parte desse
    nome customizado como base -- nao do default `.SA` removido."""
    mod, calls = fake_mt5(initialize_ok=True)
    existentes = {"WEGEX_F"}  # base customizada "WEGEX" + sufixo "F"
    mod.symbol_info = lambda symbol: (
        types.SimpleNamespace() if symbol in existentes else None
    )
    broker = MT5Broker(symbol_map={"WEGE3.SA": "WEGEX_"})

    assert broker.detect_fractional_symbol_map(["WEGE3.SA"]) == {"WEGE3.SA": "WEGEX_F"}


def test_detect_fractional_symbol_map_falha_de_conexao_devolve_none_sem_excecao(fake_mt5):
    fake_mt5(initialize_ok=False, last_error=(10004, "terminal nao encontrado"))
    broker = MT5Broker()

    assert broker.detect_fractional_symbol_map(["WEGE3.SA"]) is None


# ---------- fractional_map: escolha dinamica lote padrao (gratis) x fracionario (paga) --

def _lote_padrao_info():
    return types.SimpleNamespace(volume_min=100.0, volume_max=1e7, volume_step=100.0,
                                  point=0.01, trade_contract_size=1.0)


def _fracionario_info():
    return types.SimpleNamespace(volume_min=1.0, volume_max=1e7, volume_step=1.0,
                                  point=0.01, trade_contract_size=1.0)


def test_place_prefere_lote_padrao_gratuito_quando_quantidade_alcanca_o_minimo(fake_mt5):
    """Quantidade que fecha lote padrao (>=100 acoes) usa o simbolo BASE (lote
    padrao, GRATUITO na Rico, 2026-08-21) mesmo com fracionario disponivel
    pra esse ticker -- fracionario custa R$1,90/ordem, so vale a pena quando
    o lote padrao nao fecha."""
    infos = {"WEGE3": _lote_padrao_info(), "WEGE3F": _fracionario_info()}
    mod, calls = fake_mt5(tick=_tick(),
                          order_send_result=_order_send_result(retcode=106, volume=100.0),
                          history_deals=[])
    mod.symbol_info = lambda symbol: infos.get(symbol)

    broker = MT5Broker(fractional_map={"WEGE3.SA": "WEGE3F"})
    broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=150))

    assert calls["order_send"][0]["symbol"] == "WEGE3"
    assert calls["order_send"][0]["volume"] == pytest.approx(100.0)  # arredondado pro lote


def test_place_usa_fracionario_quando_lote_padrao_nao_fecha(fake_mt5):
    """Quantidade abaixo do minimo do lote padrao (100), mas o ticker TEM
    fracionario no mapa -- usa o fracionario (paga R$1,90) em vez de
    rejeitar a ordem."""
    infos = {"WEGE3": _lote_padrao_info(), "WEGE3F": _fracionario_info()}
    mod, calls = fake_mt5(tick=_tick(),
                          order_send_result=_order_send_result(retcode=106, volume=3.0),
                          history_deals=[])
    mod.symbol_info = lambda symbol: infos.get(symbol)

    broker = MT5Broker(fractional_map={"WEGE3.SA": "WEGE3F"})
    broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=3))

    assert calls["order_send"][0]["symbol"] == "WEGE3F"
    assert calls["order_send"][0]["volume"] == pytest.approx(3.0)


def test_place_sem_fracionario_no_mapa_e_quantidade_abaixo_do_lote_rejeita_com_motivo_claro(fake_mt5):
    """Ticker que NAO esta em `fractional_map` (ex.: BOVA11, sem versao
    fracionaria na Rico) e quantidade que nao fecha lote padrao -- rejeita
    com um motivo que deixa claro que fracionario nem era opcao, em vez de
    um "volume 0" generico que pareceria um bug de arredondamento."""
    mod, calls = fake_mt5(symbol_info=_lote_padrao_info(), tick=_tick())

    broker = MT5Broker()  # sem fractional_map
    result = broker.place(Order(ticker="BOVA11.SA", side=OrderSide.BUY, quantity=3))

    assert result.status == OrderStatus.REJECTED
    assert calls["order_send"] == []
    assert "sem mercado fracionario disponivel" in result.note


def test_place_fracionario_no_mapa_mas_tambem_nao_aceita_o_volume_rejeita_com_motivo_claro(fake_mt5):
    """Mesmo com o ticker no `fractional_map`, se o simbolo fracionario
    TAMBEM nao aceitar a quantidade pedida, o motivo da rejeicao diz isso
    explicitamente -- nao trata "sem fracionario" e "fracionario tambem
    recusou" como a mesma coisa."""
    infos = {"WEGE3": _lote_padrao_info(), "WEGE3F": types.SimpleNamespace(
        volume_min=10.0, volume_max=1e7, volume_step=10.0, point=0.01, trade_contract_size=1.0)}
    mod, calls = fake_mt5(tick=_tick())
    mod.symbol_info = lambda symbol: infos.get(symbol)

    broker = MT5Broker(fractional_map={"WEGE3.SA": "WEGE3F"})
    result = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=3))

    assert result.status == OrderStatus.REJECTED
    assert calls["order_send"] == []
    assert "tambem nao aceitou o volume" in result.note


def test_place_note_de_sucesso_menciona_o_simbolo_usado(fake_mt5):
    """Diagnostico ao vivo: a nota de uma ordem preenchida diz QUAL simbolo
    foi usado -- essencial pra saber se uma entrada saiu pelo lote padrao
    (gratis) ou pelo fracionario (pago) sem precisar abrir o terminal."""
    infos = {"WEGE3": _lote_padrao_info(), "WEGE3F": _fracionario_info()}
    mod, calls = fake_mt5(tick=_tick(bid=49.9, ask=50.1),
                          order_send_result=_order_send_result(retcode=106, price=50.1, volume=3.0),
                          history_deals=[])
    mod.symbol_info = lambda symbol: infos.get(symbol)

    broker = MT5Broker(fractional_map={"WEGE3.SA": "WEGE3F"})
    result = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=3))

    assert "WEGE3F" in result.note


def test_place_fractional_map_nao_interfere_quando_quantidade_ja_fecha_lote_sem_mapa(fake_mt5):
    """Regressao: sem `fractional_map` nenhum (default `MT5Broker()`),
    quantidade que fecha lote padrao continua indo pelo simbolo base, exatamente
    como antes desta funcionalidade existir."""
    mod, calls = fake_mt5(symbol_info=_lote_padrao_info(), tick=_tick(),
                          order_send_result=_order_send_result(retcode=106, volume=100.0),
                          history_deals=[])

    broker = MT5Broker()
    broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=150))

    assert calls["order_send"][0]["symbol"] == "WEGE3"
    assert calls["order_send"][0]["volume"] == pytest.approx(100.0)


# ---------- foreign_activity (2026-08-27) ---------------------------------
#
# Motivado pelo teste manual ao vivo do dono: comprou/vendeu PMAM3 a mercado
# direto no terminal, com o robo real rodando no mesmo papel, e o robo nunca
# soube. `open_position()`/`pending_orders()` filtram por `magic` de
# proposito (conta NETTING compartilhada) -- `foreign_activity()` e' o
# complemento que enxerga o que ELES escondem, so' pra alertar.

def _posicao(magic, volume=100.0):
    return types.SimpleNamespace(magic=magic, volume=volume)


def _ordem_pendente(magic, volume_current=100.0):
    return types.SimpleNamespace(magic=magic, volume_current=volume_current)


def test_foreign_activity_none_quando_so_tem_posicao_do_proprio_magic(fake_mt5):
    fake_mt5(positions=[_posicao(magic=20260817)])
    broker = MT5Broker(magic=20260817)

    assert broker.foreign_activity("PMAM3") is None


def test_foreign_activity_detecta_posicao_de_outro_magic(fake_mt5):
    fake_mt5(positions=[_posicao(magic=999, volume=100.0)])
    broker = MT5Broker(magic=20260817, shares_per_lot=1.0)

    resultado = broker.foreign_activity("PMAM3")

    assert resultado == {
        "symbol": "PMAM3",
        "itens": [{"tipo": "posicao", "magic": 999, "quantity": 100}],
    }


def test_foreign_activity_detecta_ordem_pendente_de_outro_magic(fake_mt5):
    fake_mt5(orders=[_ordem_pendente(magic=0, volume_current=100.0)])
    broker = MT5Broker(magic=20260817)

    resultado = broker.foreign_activity("PMAM3")

    assert resultado == {
        "symbol": "PMAM3",
        "itens": [{"tipo": "ordem", "magic": 0, "quantity": 100}],
    }


def test_foreign_activity_ignora_posicao_com_volume_zero(fake_mt5):
    """Posicao de outro magic mas ja fechada (volume 0) nao e' atividade --
    e' o mesmo cuidado que `open_position()` ja tem pro proprio magic."""
    fake_mt5(positions=[_posicao(magic=999, volume=0.0)])
    broker = MT5Broker(magic=20260817)

    assert broker.foreign_activity("PMAM3") is None


def test_foreign_activity_none_quando_positions_get_falha(fake_mt5):
    """`positions_get` devolvendo `None` (falha da consulta) NAO pode virar
    alarme -- mesma regra de `open_position`/`pending_orders`: "nao sei" nao
    e' "tem atividade estranha"."""
    mod, _calls = fake_mt5()
    mod.positions_get = lambda symbol=None: None
    broker = MT5Broker(magic=20260817)

    assert broker.foreign_activity("PMAM3") is None


def test_foreign_activity_usa_symbol_for(fake_mt5):
    """O simbolo consultado na corretora e' o traduzido (`symbol_for`), nao
    o ticker cru que o resto do sistema usa."""
    vistos = []
    mod, _calls = fake_mt5(positions=[_posicao(magic=999)])
    mod.positions_get = lambda symbol=None: vistos.append(symbol) or [_posicao(magic=999)]

    broker = MT5Broker(magic=20260817)
    broker.foreign_activity("WEGE3.SA")

    assert vistos == ["WEGE3"]


# ---------- detect_futures_symbol_map (futuro continuo "@" -> contrato real) --

def _futuro(nome, trade_mode=4, volume=0.0, bid=5200.0, ask=5200.5):
    """`trade_mode=4` imita `SYMBOL_TRADE_MODE_FULL` do pacote real; o valor
    numerico nao importa pro codigo sob teste (so' compara contra
    `SYMBOL_TRADE_MODE_DISABLED`, que o fake abaixo fixa em 0).

    `bid`/`ask` default para um book de DOIS LADOS valido (gap (d),
    incidente 2026-08-28) -- testes que precisam de um contrato MORTO (sem
    mercado, como o `WDOQ27` real que motivou a checagem) passam `bid=0.0`
    ou `ask=0.0` explicitamente."""
    return types.SimpleNamespace(name=nome, trade_mode=trade_mode), volume, bid, ask


def _instala_futuros(mod, *pares):
    """`pares`: sequencia de `(symbol_info, volume, bid, ask)` (ver
    `_futuro`) -- monta `symbols_get` (devolve todos os `symbol_info`) e
    `symbol_info_tick` (devolve volume/bid/ask daquele simbolo)."""
    infos = [info for info, _vol, _bid, _ask in pares]
    ticks = {info.name: (vol, bid, ask) for info, vol, bid, ask in pares}
    mod.SYMBOL_TRADE_MODE_DISABLED = 0
    mod.symbols_get = lambda pattern: [i for i in infos if i.name.startswith(pattern[:-1])]

    def _tick(symbol):
        vol, bid, ask = ticks.get(symbol, (0.0, 0.0, 0.0))
        return types.SimpleNamespace(volume=vol, bid=bid, ask=ask)

    mod.symbol_info_tick = _tick


def test_detect_futures_symbol_map_escolhe_contrato_de_maior_volume(fake_mt5):
    """O contrato corrente (front month) e' sempre o mais liquido -- entre
    dois vencimentos tradaveis, o mapa escolhe o de maior volume do dia, sem
    precisar saber qual mes e' "o certo"."""
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(
        mod,
        _futuro("WDOZ99", volume=120.0),
        _futuro("WDOV26", volume=9500.0),
    )
    broker = MT5Broker()

    assert broker.detect_futures_symbol_map(["WDO@"]) == {"WDO@": "WDOV26"}


def test_detect_futures_symbol_map_ignora_contrato_com_trade_mode_desabilitado(fake_mt5):
    """O simbolo continuo (`"WDO@"`) tipicamente aparece no proprio
    `symbols_get("WDO*")` com volume alto mas `trade_mode` desabilitado --
    tem de ser descartado mesmo tendo o maior volume, senao o mapa devolveria
    o proprio sintoma que motivou a deteccao."""
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(
        mod,
        _futuro("WDO@", trade_mode=0, volume=999999.0),
        _futuro("WDOZ99", trade_mode=4, volume=50.0),
    )
    broker = MT5Broker()

    assert broker.detect_futures_symbol_map(["WDO@"]) == {"WDO@": "WDOZ99"}


def test_detect_futures_symbol_map_filtra_simbolos_fora_do_padrao_de_vencimento(fake_mt5):
    """`symbols_get("WDO*")` pode devolver simbolos que comecam com a raiz
    mas nao sao um contrato de vencimento (ex. um indice ou derivado com nome
    parecido) -- o padrao RAIZ+LETRA_DE_MES+ANO exclui esses."""
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(
        mod,
        _futuro("WDOFUT", volume=99999.0),
        _futuro("WDO26", volume=99999.0),
        _futuro("WDOZ99", volume=10.0),
    )
    broker = MT5Broker()

    assert broker.detect_futures_symbol_map(["WDO@"]) == {"WDO@": "WDOZ99"}


def test_detect_futures_symbol_map_sem_contrato_tradavel_mantem_ticker_original(fake_mt5):
    """Nenhum candidato tradavel encontrado: mapeia pro proprio simbolo base
    -- degrada pro sintoma de hoje (ordem recusada) em vez de quebrar."""
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(mod, _futuro("WDOZ99", trade_mode=0, volume=10.0))
    broker = MT5Broker()

    assert broker.detect_futures_symbol_map(["WDO@"]) == {"WDO@": "WDO@"}


def test_detect_futures_symbol_map_ticker_sem_arroba_mapeia_para_symbol_for(fake_mt5):
    """Ticker que nao e' futuro continuo (sem sufixo `"@"`, ex. acao) nunca
    aciona a deteccao -- mapeia direto pro resultado de `symbol_for`."""
    mod, _calls = fake_mt5(initialize_ok=True)
    broker = MT5Broker()

    assert broker.detect_futures_symbol_map(["PMAM3.SA"]) == {"PMAM3.SA": "PMAM3"}


def test_detect_futures_symbol_map_respeita_symbol_map_customizado_na_base(fake_mt5):
    """Se `symbol_map` ja tem override pra este ticker, a deteccao parte
    dele -- um override pra algo que NAO termina em `"@"` pula a deteccao de
    futuro inteira (mesmo espirito de `detect_fractional_symbol_map`)."""
    mod, _calls = fake_mt5(initialize_ok=True)
    broker = MT5Broker(symbol_map={"WDO@": "WDOX_FIXO"})

    assert broker.detect_futures_symbol_map(["WDO@"]) == {"WDO@": "WDOX_FIXO"}


def test_detect_futures_symbol_map_mistura_futuro_e_acao(fake_mt5):
    """Universo misto (ex. slot com mais de um papel): cada ticker resolve
    de forma independente, sem exigir uniformidade entre eles."""
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(mod, _futuro("WDOZ99", volume=10.0))
    broker = MT5Broker()

    assert broker.detect_futures_symbol_map(["WDO@", "PMAM3.SA"]) == {
        "WDO@": "WDOZ99", "PMAM3.SA": "PMAM3",
    }


def test_detect_futures_symbol_map_falha_de_conexao_devolve_none_sem_excecao(fake_mt5):
    fake_mt5(initialize_ok=False, last_error=(10004, "terminal nao encontrado"))
    broker = MT5Broker()

    assert broker.detect_futures_symbol_map(["WDO@"]) is None


# ---------- gap (d), incidente 2026-08-28: contrato SEM MERCADO nunca vence -
#
# Mesma estrutura do bug real: num restart, a deteccao escolheu `WDOQ27`
# (maior volume no criterio de TICK UNICO) em vez do contrato corrente
# correto -- confirmado na mao que `WDOQ27` tinha `bid=0.0` (sem book de
# dois lados, contrato sem mercado). O criterio novo tem de descartar isso
# mesmo com volume alto. (`WDOQ27` e' o simbolo real do incidente; o
# contrato "correto" abaixo usa um mes generico de teste -- o literal real
# fica em `wdof1_tendencia_confirmacao_2026_08_28.py::SYMBOL_REAL`.)

def test_detect_futures_symbol_map_descarta_contrato_com_bid_zero_mesmo_com_volume_alto(fake_mt5):
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(
        mod,
        # WDOQ27: exatamente o bug real -- volume alto (tick preso de negocio
        # velho), mas SEM mercado (bid=0.0).
        _futuro("WDOQ27", volume=999999.0, bid=0.0, ask=5225.0),
        _futuro("WDOZ99", volume=50.0, bid=5224.5, ask=5225.0),
    )
    broker = MT5Broker()

    assert broker.detect_futures_symbol_map(["WDO@"]) == {"WDO@": "WDOZ99"}


def test_detect_futures_symbol_map_descarta_contrato_com_ask_zero(fake_mt5):
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(
        mod,
        _futuro("WDOQ27", volume=999999.0, bid=5224.0, ask=0.0),
        _futuro("WDOZ99", volume=50.0, bid=5224.5, ask=5225.0),
    )
    broker = MT5Broker()

    assert broker.detect_futures_symbol_map(["WDO@"]) == {"WDO@": "WDOZ99"}


def test_detect_futures_symbol_map_sem_nenhum_candidato_com_book_mantem_ticker_original(fake_mt5):
    """Todos os candidatos tradaveis estao sem book de dois lados -- degrada
    pro sintoma atual (mapeia pro proprio ticker `@`) em vez de escolher um
    contrato morto."""
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(mod, _futuro("WDOZ99", volume=10.0, bid=0.0, ask=0.0))
    broker = MT5Broker()

    assert broker.detect_futures_symbol_map(["WDO@"]) == {"WDO@": "WDO@"}


def test_detect_futures_symbol_map_usa_volume_de_barras_recentes_quando_disponivel(fake_mt5):
    """Com `copy_rates_from_pos` disponivel (terminal real), o desempate usa
    a SOMA de barras M1 recentes, nao o tick unico -- WDOZ99 tem tick.volume
    MAIOR mas WDOV26 tem mais volume ACUMULADO nas ultimas barras, que e' o
    sinal mais robusto de qual contrato concentra a liquidez agora."""
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(
        mod,
        _futuro("WDOZ99", volume=500.0),   # tick unico alto...
        _futuro("WDOV26", volume=10.0),    # ...mas tick unico baixo aqui
    )
    mod.TIMEFRAME_M1 = 1

    def _copy_rates(nome, timeframe, start, count):
        barras_por_simbolo = {
            "WDOZ99": [{"tick_volume": 5.0}] * count,       # pouco volume por barra
            "WDOV26": [{"tick_volume": 900.0}] * count,     # muito volume por barra
        }
        return barras_por_simbolo.get(nome, [])

    mod.copy_rates_from_pos = _copy_rates
    broker = MT5Broker()

    assert broker.detect_futures_symbol_map(["WDO@"]) == {"WDO@": "WDOV26"}


def test_detect_futures_symbol_map_cai_para_tick_unico_quando_barras_indisponiveis(fake_mt5):
    """Sem `copy_rates_from_pos` no modulo (nem real nem fake) -- degrada pro
    criterio antigo (tick unico) em vez de quebrar a deteccao inteira."""
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(
        mod,
        _futuro("WDOZ99", volume=120.0),
        _futuro("WDOV26", volume=9500.0),
    )
    assert not hasattr(mod, "copy_rates_from_pos")
    broker = MT5Broker()

    assert broker.detect_futures_symbol_map(["WDO@"]) == {"WDO@": "WDOV26"}


# ---------- criterio de CALENDARIO (incidente 2026-09-11) ----------------
#
# Ate 2026-09-11 o desempate era so' volume recente -- e numa madrugada de
# mercado fechado (dois slots de WDO@ iniciados as 05:48-05:49 UTC) isso
# escolheu WDOF27 (morto, vencimento jan/2027) em vez de WDOV26 (certo,
# out/2026): um artefato de barra velha e esparsa bateu por acaso o
# contrato certo, que tambem nao tinha negocio fresco aquela hora. A partir
# de agora `front_month_contract` (calendario, `core.instruments`) e' o
# criterio PRINCIPAL; volume so' entra se o contrato indicado pela data nao
# tiver book de dois lados.

def test_detect_futures_symbol_map_usa_calendario_mesmo_com_volume_menor(fake_mt5):
    """Reproduz o incidente real: um contrato MORTO (WDOF27, fora da regra
    de rolagem para 11/09/2026) tem volume MUITO maior que o certo
    (WDOV26) -- o criterio de calendario tem de escolher o certo mesmo
    assim, porque a data manda agora, nao o volume."""
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(
        mod,
        _futuro("WDOF27", volume=999999.0),  # o contrato que venceu o desempate errado
        _futuro("WDOV26", volume=12.0),       # o certo, com pouco volume (madrugada)
    )
    broker = MT5Broker()

    resultado = broker.detect_futures_symbol_map(["WDO@"], hoje=date(2026, 9, 11))

    assert resultado == {"WDO@": "WDOV26"}


def test_detect_futures_symbol_map_calendario_na_virada_do_mes(fake_mt5):
    """Mesmos candidatos, so' a DATA muda: no dia seguinte ao rollover
    (01/09/2026, mes de agosto ja fechou) o corrente e' WDOU26, nao
    WDOV26 -- confirma que quem decide e' `hoje`, nao um contrato
    preferido a priori."""
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(
        mod,
        _futuro("WDOU26", volume=10.0),
        _futuro("WDOV26", volume=9500.0),
    )
    broker = MT5Broker()

    assert broker.detect_futures_symbol_map(["WDO@"], hoje=date(2026, 8, 20)) == {
        "WDO@": "WDOU26"
    }
    assert broker.detect_futures_symbol_map(["WDO@"], hoje=date(2026, 9, 1)) == {
        "WDO@": "WDOV26"
    }


def test_detect_futures_symbol_map_win_tambem_usa_calendario(fake_mt5):
    """Mesmo criterio para WIN@ -- rolagem bimestral, meses PARES."""
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(
        mod,
        _futuro("WING27", volume=999999.0),  # fora do ciclo corrente, nao deve ganhar
        _futuro("WINV26", volume=5.0),
    )
    broker = MT5Broker()

    assert broker.detect_futures_symbol_map(["WIN@"], hoje=date(2026, 9, 11)) == {
        "WIN@": "WINV26"
    }


def test_detect_futures_symbol_map_cai_para_volume_quando_contrato_da_data_esta_morto(fake_mt5, caplog):
    """Caso raro (feriado, atraso da B3): o contrato que o calendario indica
    para `hoje` nao tem book de dois lados agora -- cai para o criterio de
    volume ANTIGO entre os candidatos que sobrarem, e o caso anomalo fica
    registrado no log (nunca silencioso)."""
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(
        mod,
        _futuro("WDOV26", volume=10.0, bid=0.0, ask=0.0),  # indicado pela data, mas MORTO
        _futuro("WDOX26", volume=500.0),                    # unico candidato com book
    )
    broker = MT5Broker()

    with caplog.at_level("WARNING", logger="live.broker_mt5"):
        resultado = broker.detect_futures_symbol_map(["WDO@"], hoje=date(2026, 9, 11))

    assert resultado == {"WDO@": "WDOX26"}
    assert "calendario" in caplog.text.lower()
    assert "WDOV26" in caplog.text


def test_detect_futures_symbol_map_raiz_sem_regra_de_rolagem_cai_para_volume(fake_mt5):
    """Uma raiz sem entrada em `FUTURES_ROLLOVER_MONTHS` (futuro novo, ainda
    nao catalogado) nunca derruba a deteccao -- degrada pro criterio de
    volume, exatamente como o resto do metodo degrada pra sintoma atual em
    vez de quebrar."""
    mod, _calls = fake_mt5(initialize_ok=True)
    _instala_futuros(mod, _futuro("XYZZ99", volume=42.0))
    broker = MT5Broker()

    # "XYZ" nao tem entrada em `core.instruments.FUTURES_ROLLOVER_MONTHS` --
    # `front_month_contract` levanta `KeyError`, capturado e tratado como
    # "sem contrato esperado", caindo pro fallback de volume.
    assert broker.detect_futures_symbol_map(["XYZ@"], hoje=date(2026, 9, 11)) == {
        "XYZ@": "XYZZ99"
    }


# ---------- order_history_state / deals_for_position (gap medido ao vivo ---
# 2026-09-04, slot `dt-wdo_grid_reload_maker-wdo@-live`): a ordem preencheu E
# a posicao fechou pelo alvo ATOMICO da corretora dentro do MESMO intervalo
# de poll do supervisor -- so' o historico sabe o desfecho de uma ordem que
# ja saiu do book.

def test_order_history_state_ainda_pendente_nao_consulta_historico(fake_mt5):
    """Caminho RAPIDO: se `orders_get(ticket=...)` confirma que a ordem
    ainda esta no book, nem chega a chamar `history_orders_get` -- e' o
    caso comum (ordem esperando o preco chegar), e nao deve pagar a
    consulta mais cara em toda chamada normal."""
    mod, calls = fake_mt5(orders_by_ticket={555: [types.SimpleNamespace(ticket=555)]})
    broker = MT5Broker()

    resp = broker.order_history_state(555)

    assert resp == {"ok": True, "state": "pending", "position_id": None, "note": ""}
    assert calls["history_orders_get"] == []


def test_order_history_state_preenchida_devolve_position_id(fake_mt5):
    mod, calls = fake_mt5(
        orders_by_ticket={},  # nao esta mais no book
        history_orders_by_ticket={555: [types.SimpleNamespace(state=4, position_id=555)]},
    )
    broker = MT5Broker()

    resp = broker.order_history_state(555)

    assert resp == {"ok": True, "state": "filled", "position_id": 555, "note": ""}
    assert calls["history_orders_get"] == [555]


def test_order_history_state_parcial_cancelada_rejeitada_expirada(fake_mt5):
    """As 4 traducoes de estado, uma por chamada -- nunca um codigo
    numerico vazando pra fora do broker."""
    casos = [(3, "partial"), (2, "canceled"), (5, "rejected"), (6, "expired")]
    for codigo, esperado in casos:
        mod, calls = fake_mt5(
            orders_by_ticket={},
            history_orders_by_ticket={555: [types.SimpleNamespace(state=codigo, position_id=None)]},
        )
        broker = MT5Broker()
        resp = broker.order_history_state(555)
        assert resp["state"] == esperado, f"codigo {codigo} devia mapear para {esperado!r}"
        assert resp["ok"] is True
        assert resp["position_id"] is None


def test_order_history_state_codigo_desconhecido_vira_unknown_nunca_inventa_nome(fake_mt5):
    mod, calls = fake_mt5(
        orders_by_ticket={},
        history_orders_by_ticket={555: [types.SimpleNamespace(state=999, position_id=None)]},
    )
    broker = MT5Broker()

    resp = broker.order_history_state(555)

    assert resp == {"ok": True, "state": "unknown", "position_id": None, "note": ""}


def test_order_history_state_nem_no_book_nem_no_historico_vira_unknown(fake_mt5):
    """Ticket confirmadamente ausente dos dois lugares -- desfecho
    desconhecido, mas a CONSULTA em si funcionou (`ok=True`)."""
    mod, calls = fake_mt5(orders_by_ticket={}, history_orders_by_ticket={})
    broker = MT5Broker()

    resp = broker.order_history_state(555)

    assert resp["ok"] is True
    assert resp["state"] == "unknown"


def test_order_history_state_falha_de_consulta_nunca_vira_desfecho(fake_mt5):
    """`orders_get` falhou (devolveu `None`) E o ticket nao esta no
    historico -- "nao sei", nunca "cancelada" nem "desconhecida com
    certeza" (item 1.6 de LICOES_DE_PRODUCAO.md).

    `orders_by_ticket={555: None}` (nao `orders_by_ticket=None`, que imita
    "perguntei e nao ha nada", sucesso vazio): a CHAVE precisa existir e
    mapear para `None`, o jeito que este dublê imita `orders_get` devolvendo
    `None` de verdade (ver a docstring de `_make_fake_mt5`)."""
    mod, calls = fake_mt5(orders_by_ticket={555: None}, history_orders_by_ticket={})
    broker = MT5Broker()

    resp = broker.order_history_state(555)

    assert resp["ok"] is False
    assert resp["state"] is None


def test_order_history_state_history_orders_get_none_e_falha(fake_mt5):
    mod, calls = fake_mt5(orders_by_ticket={}, history_orders_get_none=True)
    broker = MT5Broker()

    resp = broker.order_history_state(555)

    assert resp["ok"] is False
    assert resp["state"] is None


def test_order_history_state_ticket_invalido_e_falha_sem_excecao(fake_mt5):
    mod, calls = fake_mt5()
    broker = MT5Broker()

    resp = broker.order_history_state("nao-e-um-numero")

    assert resp["ok"] is False


def test_order_history_state_sem_conexao_e_falha(fake_mt5):
    mod, calls = fake_mt5(initialize_ok=False)
    broker = MT5Broker()

    resp = broker.order_history_state(555)

    assert resp["ok"] is False
    assert resp["state"] is None


def test_deals_for_position_traduz_e_converte_quantidade_por_shares_per_lot(fake_mt5):
    """`quantity` no dict de saida ja vem em ACOES/CONTRATOS (`volume *
    shares_per_lot`), a mesma unidade do resto do modulo -- nunca em LOTE
    cru do MT5."""
    mod, calls = fake_mt5(history_deals_by_position={
        909: [
            types.SimpleNamespace(ticket=1, order=10, entry=0, type=0, price=9.80,
                                  volume=2.0, profit=0.0, commission=-1.5, swap=0.0,
                                  fee=0.0, time=100, comment=""),
            types.SimpleNamespace(ticket=2, order=11, entry=1, type=1, price=9.89,
                                  volume=2.0, profit=18.0, commission=-1.5, swap=0.0,
                                  fee=0.0, time=101, comment="[tp 9.9000]"),
        ],
    })
    broker = MT5Broker(shares_per_lot=100.0)

    resp = broker.deals_for_position(909)

    assert resp["ok"] is True
    entrada, saida = resp["deals"]
    assert entrada["entry"] == 0 and entrada["quantity"] == 200 and entrada["price"] == 9.80
    assert saida["entry"] == 1 and saida["quantity"] == 200 and saida["price"] == 9.89
    assert saida["comment"] == "[tp 9.9000]"
    assert calls["history_deals_get_by_position"] == [909]


def test_deals_for_position_expoe_time_msc_o_unico_relogio_que_mede_a_posicao(fake_mt5):
    """`time_msc` (milissegundos da CORRETORA) tem de atravessar a traducao.

    E' o unico relogio que mede quanto tempo uma posicao ficou aberta: os
    dois do processo erram por construcao (o de TICK anda com a defasagem do
    feed, o de PAREDE colapsa quando abertura e fechamento caem no mesmo
    poll). Sem este campo, os 11 round-trips de menos de 1 segundo de
    2026-09-08 -- -R$40,50 dos -R$116,00 do pregao -- continuam
    indistinguiveis de alvo de verdade no diario (item 4.16)."""
    mod, calls = fake_mt5(history_deals_by_position={
        909: [
            types.SimpleNamespace(ticket=1, order=10, entry=0, type=0, price=5110.5,
                                  volume=1.0, profit=0.0, commission=0.0, swap=0.0,
                                  fee=0.0, time=1757340423, time_msc=1757340423155,
                                  comment=""),
            types.SimpleNamespace(ticket=2, order=11, entry=1, type=1, price=5110.0,
                                  volume=1.0, profit=-5.0, commission=0.0, swap=0.0,
                                  fee=0.0, time=1757340423, time_msc=1757340423213,
                                  comment="[tp 5111.0000]"),
        ],
    })
    broker = MT5Broker(shares_per_lot=1.0)

    entrada, saida = broker.deals_for_position(909)["deals"]

    assert entrada["time_msc"] == 1757340423155
    assert saida["time_msc"] == 1757340423213
    # O caso real de 2026-09-08 as 10:47:03: 58 ms de vida, 1 tick perdido.
    assert saida["time_msc"] - entrada["time_msc"] == 58


def test_deals_for_position_sem_time_msc_no_pacote_vira_None_nunca_zero(fake_mt5):
    """Deal sem o campo (dublê antigo, pacote que nao o exponha) tem de virar
    `None` -- "nao sei". Um `0` silencioso viraria duracao de 1970 ou, pior,
    faria toda posicao parecer um round-trip instantaneo."""
    mod, calls = fake_mt5(history_deals_by_position={
        909: [types.SimpleNamespace(ticket=1, order=10, entry=0, type=0, price=9.8,
                                    volume=1.0, profit=0.0, commission=0.0, swap=0.0,
                                    fee=0.0, time=100, comment="")],
    })

    (deal,) = MT5Broker().deals_for_position(909)["deals"]

    assert deal["time_msc"] is None


def test_deals_for_position_sem_deals_devolve_lista_vazia_ok_true(fake_mt5):
    mod, calls = fake_mt5(history_deals_by_position={})
    broker = MT5Broker()

    resp = broker.deals_for_position(909)

    assert resp == {"ok": True, "deals": [], "note": ""}


def test_deals_for_position_none_e_falha_nunca_lista_vazia(fake_mt5):
    """`history_deals_get(position=...)` devolvendo `None` (falha de
    consulta) nunca pode virar `{"ok": True, "deals": []}` -- as duas
    respostas tem consequencias opostas para quem chama (ver
    `MT5IntradayExecution.resolve_orphaned_entry`)."""
    mod, calls = fake_mt5(history_deals_get_position_none=True)
    broker = MT5Broker()

    resp = broker.deals_for_position(909)

    assert resp["ok"] is False
    assert resp["deals"] is None


def test_deals_for_position_excecao_na_consulta_e_falha_sem_propagar(fake_mt5):
    mod, calls = fake_mt5(history_deals_raises=True, history_deals_by_position={})
    broker = MT5Broker()

    resp = broker.deals_for_position(909)

    assert resp["ok"] is False


def test_deals_for_position_position_id_invalido_e_falha_sem_excecao(fake_mt5):
    mod, calls = fake_mt5()
    broker = MT5Broker()

    resp = broker.deals_for_position("nao-e-um-numero")

    assert resp["ok"] is False


def test_deals_for_position_sem_conexao_e_falha(fake_mt5):
    mod, calls = fake_mt5(initialize_ok=False)
    broker = MT5Broker()

    resp = broker.deals_for_position(909)

    assert resp["ok"] is False
    assert resp["deals"] is None


# ---------- incidente 2026-09-09: posicao real de 2 contratos SEM SL/TP -----
#
# 10:55:09 BRT, slot `dt-wdo_grid_reload_maker-wdo@-live`, conta real de
# R$375. Estado observado no terminal:
#
#     WDOV26 BUY vol=2.0 open=5122.5 SL=0.0 TP=0.0 magic=862399285
#     bid 5124.0 / ask 5124.5
#     symbol_info: trade_stops_level=0, trade_tick_size=0.5
#
# e no diario, repetido a cada passo por ~3 minutos ate' o dono zerar na mao:
#
#     NAO CONSEGUI proteger a posicao de WDO@ ... MT5 recusou SL/TP
#     (retcode=10016): Invalid stops
#
# Os dois testes abaixo cobrem as duas metades mecanicas disso.


def test_niveis_protecao_afasta_nivel_do_lado_errado_mesmo_com_stops_level_zero(fake_mt5):
    """`trade_stops_level=0` nao quer dizer "aceita nivel de qualquer lado".

    O WDOV26 na Rico reporta `trade_stops_level = 0` -- nenhuma distancia
    MINIMA exigida -- e por isso `distancia_min` dava 0,0 e o afastamento era
    pulado por inteiro. Um SL de 5131,50 numa posicao LONG com bid em 5124,00
    ia inteiro para o servidor, que respondia `10016 Invalid stops`, e como o
    `TRADE_ACTION_SLTP` e' atomico a posicao ficava NUA.

    Com o piso de 1 tick o nivel impossivel vira nivel valido (bid - 1 tick =
    5123,50) mais um aviso no diario, em vez de protecao nenhuma."""
    mod, calls = fake_mt5(
        symbol_info=_symbol_info_protecao(trade_stops_level=0),
        tick=_tick(bid=5124.0, ask=5124.5),
        order_send_result=_order_send_result(retcode=106))
    broker = MT5Broker()

    resultado = broker.set_protection("WDO@", position_ticket=555, side="long",
                                      stop=5131.5, target=None)

    enviado = calls["order_send"][0]
    assert enviado["sl"] == pytest.approx(5123.5), (
        "SL de posicao LONG tem de ficar ABAIXO do mercado -- 5131,50 e' o stop "
        "de uma posicao SHORT e o servidor recusa com 10016")
    assert resultado["ok"] is True
    assert "afastado" in resultado["note"]


def test_set_protection_recusada_reenvia_SO_o_stop_para_a_posicao_nao_ficar_nua(fake_mt5):
    """`TRADE_ACTION_SLTP` e' atomico: uma perna invalida derruba a outra.

    Sem esta segunda tentativa, um alvo que a corretora recusa deixa a posicao
    SEM STOP -- que e' o estado que zerou a conta em 2026-08-28. O alvo e'
    desejavel; o stop e' o que impede a ruina."""
    def resposta(request):
        # 1a tentativa (mexendo nas DUAS pernas) -> recusada.
        # 2a (tp = tp_atual, ou seja "deixa o alvo como esta") -> aceita.
        if request["tp"] != 0.0:
            return _order_send_result(retcode=10016, comment="Invalid stops")
        return _order_send_result(retcode=106)

    mod, calls = fake_mt5(
        symbol_info=_symbol_info_protecao(trade_stops_level=0),
        tick=_tick(bid=5200.0, ask=5200.5),
        order_send_result=resposta)
    broker = MT5Broker()

    resultado = broker.set_protection("WDO@", position_ticket=555, side="long",
                                      stop=5190.0, target=5210.0,
                                      sl_atual=0.0, tp_atual=0.0)

    assert len(calls["order_send"]) == 2, "tem de INSISTIR so' com o stop"
    assert calls["order_send"][0]["tp"] == pytest.approx(5210.0)
    assert calls["order_send"][1]["tp"] == pytest.approx(0.0)
    assert calls["order_send"][1]["sl"] == pytest.approx(5190.0)
    assert resultado["ok"] is True, "o stop entrou -- a posicao NAO ficou nua"
    assert resultado["sl"] == pytest.approx(5190.0)
    assert "SO' COM O STOP" in resultado["note"]


def test_desfecho_de_done_sem_fill_INSISTE_ate_o_deal_aparecer_no_historico(fake_mt5):
    """O historico do terminal e' ASSINCRONO -- perguntar uma vez so' e' nao
    perguntar.

    2026-09-09 10:53:31 BRT: o fechamento a mercado da SHORT #02 voltou
    `retcode=DONE` com `price=0.0, deal=0`. A consulta imediata nao achou o
    ticket, o robo registrou "RECUSA DE FECHAMENTO #1" e seguiu se achando
    vendido. A corretora tinha executado @ 5124,50. Dali sairam a ordem-limite
    orfa e, em conta NETTING, os 2 contratos.

    Aqui o historico so' responde na SEGUNDA pergunta -- exatamente o atraso
    real -- e o desfecho tem de ser FILLED com o preco do DEAL, nunca SENT."""
    class _HistoricoQueDemora(dict):
        """`.get` devolve vazio na 1a consulta e o registro FILLED da 2a em
        diante -- imita o deal que so' aparece ~2s depois do `order_send`."""

        def __init__(self, registro):
            super().__init__()
            self._registro = registro
            self.consultas = 0

        def get(self, ticket, default=None):
            self.consultas += 1
            if self.consultas <= 1:
                return []
            return [self._registro]

    historico = _HistoricoQueDemora(
        types.SimpleNamespace(state=4, position_id=7001)  # 4 = ORDER_STATE_FILLED
    )
    deal = types.SimpleNamespace(ticket=99, order=888, entry=1, type=0, price=5124.5,
                                 volume=1.0, profit=-5.0, commission=0.0, swap=0.0,
                                 fee=0.0, time=1, time_msc=1000, comment="")
    fake_mt5(symbol_info=_symbol_info(), tick=_tick(bid=5124.0, ask=5124.5),
             order_send_result=_order_send_result(retcode=106, price=0.0, deal=0,
                                                  order=888),
             history_orders_by_ticket=historico,
             history_deals_by_position={7001: [deal]})

    broker = MT5Broker()
    broker.ESPERAS_CONFIRMACAO_S = (0.0, 0.0, 0.0)  # sem dormir de verdade na suite

    executada = broker.place(
        Order(ticker="WDO@", side=OrderSide.SELL, quantity=1, order_type=OrderType.MARKET))

    assert historico.consultas >= 2, "tem de perguntar de novo depois de esperar"
    assert executada.status is OrderStatus.FILLED, (
        "o historico CONFIRMOU o fill na 2a pergunta -- SENT aqui e' o bug que "
        "fez o robo negar um fechamento que a corretora tinha executado")
    assert executada.avg_price == pytest.approx(5124.5), "preco do DEAL, nao da crenca"
