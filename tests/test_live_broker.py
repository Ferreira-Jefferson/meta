"""Testes da camada de execucao (`live/broker.py`) — sem rede.

Foco: `PaperBroker` reusa o MESMO custo do backtest (slippage + fees de
`backtest/costs.py`), rejeita sem cotacao, respeita limite em ordens LIMIT
sem rejeitar (fica `SENT`). `ManualBroker` gera ticket legivel e so fecha o
ciclo via `confirm()` com validacao.
"""
from __future__ import annotations

import pytest

from core.config import CostModel
from core.live_models import Order, OrderSide, OrderStatus, OrderType
from live.broker import Broker, ManualBroker, PaperBroker
from live.feed import ReplayFeed


def _feed_with(ticker: str, price: float) -> ReplayFeed:
    feed = ReplayFeed()
    feed.set(ticker, price)
    return feed


def test_paper_broker_compra_aplica_slippage_e_fees_para_cima():
    feed = _feed_with("WEGE3.SA", 50.0)
    broker = PaperBroker(feed, cost_model=CostModel())
    order = Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100)

    filled = broker.place(order)

    assert filled is order  # muta e devolve o MESMO objeto
    assert filled.status == OrderStatus.FILLED
    assert filled.filled_qty == 100
    assert filled.avg_price > 50.0          # compra paga slippage para cima
    assert filled.fees > 0.0
    assert filled.slippage > 0.0
    assert filled.broker_ref is not None


def test_paper_broker_venda_aplica_slippage_para_baixo():
    feed = _feed_with("WEGE3.SA", 50.0)
    broker = PaperBroker(feed, cost_model=CostModel())
    order = Order(ticker="WEGE3.SA", side=OrderSide.SELL, quantity=100)

    filled = broker.place(order)

    assert filled.status == OrderStatus.FILLED
    assert filled.avg_price < 50.0          # venda recebe menos por slippage
    assert filled.fees > 0.0


def test_paper_broker_rejeita_sem_cotacao():
    feed = ReplayFeed()  # sem nenhum ticker carregado
    broker = PaperBroker(feed)
    order = Order(ticker="NAOEXISTE3.SA", side=OrderSide.BUY, quantity=10)

    result = broker.place(order)

    assert result.status == OrderStatus.REJECTED
    assert "sem cotacao" in result.note.lower()
    assert result.filled_qty == 0


def test_paper_broker_limit_compra_nao_atendida_fica_sent_nao_rejeitada():
    feed = _feed_with("WEGE3.SA", 55.0)
    broker = PaperBroker(feed)
    order = Order(
        ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100,
        order_type=OrderType.LIMIT, limit_price=50.0,  # preco de mercado > limite
    )

    result = broker.place(order)

    assert result.status == OrderStatus.SENT
    assert result.filled_qty == 0
    assert not result.is_terminal


def test_paper_broker_limit_compra_atendida_preenche():
    feed = _feed_with("WEGE3.SA", 45.0)
    broker = PaperBroker(feed)
    order = Order(
        ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100,
        order_type=OrderType.LIMIT, limit_price=50.0,  # preco de mercado <= limite
    )

    result = broker.place(order)

    assert result.status == OrderStatus.FILLED


def test_paper_broker_limit_venda_nao_atendida_fica_sent():
    feed = _feed_with("WEGE3.SA", 45.0)
    broker = PaperBroker(feed)
    order = Order(
        ticker="WEGE3.SA", side=OrderSide.SELL, quantity=100,
        order_type=OrderType.LIMIT, limit_price=50.0,  # preco de mercado < limite
    )

    result = broker.place(order)

    assert result.status == OrderStatus.SENT
    assert result.filled_qty == 0


def test_paper_broker_poll_e_no_op_sincrono():
    feed = _feed_with("WEGE3.SA", 50.0)
    broker = PaperBroker(feed)
    order = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100))

    polled = broker.poll(order)

    assert polled is order
    assert polled.status == OrderStatus.FILLED


def test_paper_broker_cancel_ordem_viva_fica_cancelled():
    feed = _feed_with("WEGE3.SA", 50.0)
    broker = PaperBroker(feed)
    order = Order(
        ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100,
        order_type=OrderType.LIMIT, limit_price=1.0,  # nunca atendida -> SENT
    )
    broker.place(order)
    assert order.status == OrderStatus.SENT

    cancelled = broker.cancel(order)

    assert cancelled.status == OrderStatus.CANCELLED


def test_paper_broker_cancel_ordem_terminal_nao_muda():
    feed = _feed_with("WEGE3.SA", 50.0)
    broker = PaperBroker(feed)
    order = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100))
    assert order.status == OrderStatus.FILLED

    result = broker.cancel(order)

    assert result.status == OrderStatus.FILLED  # fill consumado nao se desfaz


def test_paper_broker_supports_automation():
    broker = PaperBroker(ReplayFeed())
    assert broker.supports_automation() is True
    assert broker.mode == "paper"


def test_manual_broker_place_gera_ticket_legivel_e_broker_ref():
    broker = ManualBroker()
    order = Order(
        ticker="WEGE3.SA", side=OrderSide.SELL, quantity=300,
        note="rotation_out",
    )

    sent = broker.place(order)

    assert sent.status == OrderStatus.SENT
    assert sent.broker_ref.startswith("MANUAL-")
    assert "VENDER" in sent.note
    assert "300" in sent.note
    assert "WEGE3.SA" in sent.note
    assert "rotation_out" in sent.note
    assert order in broker.pending_tickets()


def test_manual_broker_nao_inventa_fill_no_poll():
    broker = ManualBroker()
    order = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100))

    polled = broker.poll(order)

    assert polled.status == OrderStatus.SENT
    assert polled.filled_qty == 0


def test_manual_broker_confirm_total():
    broker = ManualBroker()
    order = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100))

    confirmed = broker.confirm(order, filled_qty=100, avg_price=51.2, fees=3.5)

    assert confirmed.status == OrderStatus.FILLED
    assert confirmed.filled_qty == 100
    assert confirmed.avg_price == pytest.approx(51.2)
    assert confirmed.fees == pytest.approx(3.5)
    assert confirmed.leaves_qty == 0
    assert order not in broker.pending_tickets()


def test_manual_broker_confirm_parcial():
    broker = ManualBroker()
    order = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100))

    confirmed = broker.confirm(order, filled_qty=40, avg_price=51.0)

    assert confirmed.status == OrderStatus.PARTIAL
    assert confirmed.filled_qty == 40
    assert confirmed.leaves_qty == 60
    assert not confirmed.is_terminal


def test_manual_broker_confirm_quantidade_invalida_levanta_valueerror():
    broker = ManualBroker()
    order = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100))

    with pytest.raises(ValueError):
        broker.confirm(order, filled_qty=0, avg_price=50.0)

    with pytest.raises(ValueError):
        broker.confirm(order, filled_qty=200, avg_price=50.0)


def test_manual_broker_confirm_preco_invalido_levanta_valueerror():
    broker = ManualBroker()
    order = broker.place(Order(ticker="WEGE3.SA", side=OrderSide.BUY, quantity=100))

    with pytest.raises(ValueError):
        broker.confirm(order, filled_qty=100, avg_price=0.0)


def test_manual_broker_supports_automation_false():
    broker = ManualBroker()
    assert broker.supports_automation() is False
    assert broker.mode == "manual"


def test_broker_e_abstrata():
    with pytest.raises(TypeError):
        Broker()
