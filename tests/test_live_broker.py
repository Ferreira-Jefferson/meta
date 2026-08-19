"""Testes da camada de execucao (`live/broker.py`) — sem rede.

Foco: `PaperBroker` reusa o MESMO custo do backtest (slippage + fees de
`backtest/costs.py`), rejeita sem cotacao, respeita limite em ordens LIMIT
sem rejeitar (fica `SENT`).
"""
from __future__ import annotations

import pytest

from core.config import CostModel
from core.live_models import Order, OrderSide, OrderStatus, OrderType
from live.broker import Broker
from tests.doubles import PaperBroker, ReplayFeed


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
    assert broker.mode == "mt5"
    assert broker.is_test_double is True


def test_broker_e_abstrata():
    with pytest.raises(TypeError):
        Broker()
