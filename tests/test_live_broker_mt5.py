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

import pytest

from live.broker_mt5 import MT5Broker
from core.live_models import Order, OrderSide, OrderStatus


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
):
    """Monta um `types.ModuleType` que imita a superficie do pacote
    `MetaTrader5` usada por `MT5Broker`, com constantes arbitrarias (o
    codigo sob teste nunca deveria depender do VALOR numerico delas, so de
    igualdade/desigualdade) e um registro de chamadas (`calls`) para
    verificar, por exemplo, que `order_send` nunca e chamado com volume 0."""
    calls = {"order_send": [], "initialize": 0, "initialize_kwargs": [], "history_deals_get": []}

    mod = types.ModuleType("MetaTrader5")
    mod.TRADE_ACTION_DEAL = 101
    mod.ORDER_TYPE_BUY = 102
    mod.ORDER_TYPE_SELL = 103
    mod.ORDER_TIME_GTC = 104
    mod.ORDER_FILLING_IOC = 105
    mod.TRADE_RETCODE_DONE = 106

    def initialize(**kwargs):
        calls["initialize"] += 1
        calls["initialize_kwargs"].append(kwargs)
        return initialize_ok

    def order_send(request):
        calls["order_send"].append(request)
        return order_send_result

    def history_deals_get(ticket=None):
        calls["history_deals_get"].append(ticket)
        if history_deals_raises:
            raise RuntimeError("falha simulada ao consultar historico")
        return history_deals if history_deals is not None else []

    mod.initialize = initialize
    mod.last_error = lambda: last_error
    mod.symbol_select = lambda symbol, enable=True: True
    mod.symbol_info = lambda symbol: symbol_info
    mod.symbol_info_tick = lambda symbol: tick
    mod.order_send = order_send
    mod.history_deals_get = history_deals_get
    # `positions`/`orders` fixos, ignorando `symbol=` de proposito -- os
    # testes que usam isto ja montam so' o que importa pro simbolo testado,
    # imitando `mt5.positions_get(symbol=...)`/`orders_get(symbol=...)`.
    mod.positions_get = lambda symbol=None: positions if positions is not None else []
    mod.orders_get = lambda symbol=None: orders if orders is not None else []

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
