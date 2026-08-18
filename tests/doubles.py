"""Test doubles do ambiente ao vivo — nunca importados por `src/` (FEAT-001).

`PaperBroker` e `ReplayFeed` moravam em `src/live/broker.py`/`src/live/feed.py`
até esta feature. Uma corretora que preenche sozinha contra um feed é, por
definição, uma SIMULAÇÃO — não existe em nenhuma corretora real, e mantê-la em
`src/` era o que permitia ao dashboard/CLI cair nela por um fallback silencioso
(`else: PaperBroker(...)`) sempre que o modo pedido não batia com nenhum dos
brokers reais. Movida para cá, ela só pode ser usada onde é chamada
explicitamente por nome (testes e `scripts/run_live_sim.py`, que documenta por
que é uma exceção deliberada).

`PaperBroker.mode` — decisão obrigatória do plan-reviewer (ACTION-PLAN FEAT-001,
seção 2): o vocabulário canônico só tem `manual`/`mt5` (`BrokerMode`). Como o
dublê simula uma corretora AUTOMÁTICA (preenche sozinho, `supports_automation()
-> True`, ao contrário de `ManualBroker`), ele declara `mode = BrokerMode.MT5.value`
— nunca um terceiro valor "paper" que o schema (`live_accounts.mode` CHECK)
não aceitaria mais.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from backtest.costs import apply_slippage, fees_for_leg
from core.config import CostModel
from core.live_models import BrokerMode, Order, OrderSide, OrderStatus, OrderType, Quote
from live.broker import Broker
from live.feed import QuoteFeed


class PaperBroker(Broker):
    """Preenche a ordem contra um `QuoteFeed`, com o MESMO custo do backtest.

    Ver docstring do módulo para o porquê de viver aqui (não em `src/`) e para
    a decisão sobre `mode`. `is_test_double = True`: nunca pode operar sobre o
    banco de produção (`LiveRuntime` recusa isso no `__init__`, ver
    `live/runtime.py`).
    """

    name = "paper"
    mode = BrokerMode.MT5.value
    is_test_double = True

    def __init__(self, feed: QuoteFeed, cost_model: Optional[CostModel] = None) -> None:
        self._feed = feed
        self._costs = cost_model or CostModel()
        self._next_ref = 1

    def place(self, order: Order) -> Order:
        quote = self._feed.quote(order.ticker)
        if quote is None:
            order.status = OrderStatus.REJECTED
            order.note = f"sem cotacao para {order.ticker} no feed {self._feed.name}"
            return order

        price = quote.price
        if order.order_type == OrderType.LIMIT and order.limit_price is not None:
            if order.side == OrderSide.BUY and price > order.limit_price:
                order.status = OrderStatus.SENT
                order.note = (
                    f"limite {order.limit_price} nao atingido "
                    f"(cotacao {price} > limite)"
                )
                return order
            if order.side == OrderSide.SELL and price < order.limit_price:
                order.status = OrderStatus.SENT
                order.note = (
                    f"limite {order.limit_price} nao atingido "
                    f"(cotacao {price} < limite)"
                )
                return order

        side = "buy" if order.side == OrderSide.BUY else "sell"
        fill_price = apply_slippage(price, side, self._costs)
        gross = fill_price * order.quantity
        fees = fees_for_leg(gross, self._costs)

        order.status = OrderStatus.FILLED
        order.filled_qty = order.quantity
        order.avg_price = fill_price
        order.slippage = abs(fill_price - price) * order.quantity
        order.fees = fees
        order.broker_ref = f"PAPER-{self._next_ref}"
        self._next_ref += 1
        order.note = f"fill @ {fill_price:.4f} contra cotacao {price:.4f} ({quote.source})"
        return order

    def poll(self, order: Order) -> Order:
        """Paper e sincrono: `place` ja decidiu tudo. `poll` so devolve o
        estado atual, sem reprocessar."""
        return order


class ReplayFeed(QuoteFeed):
    """Feed dirigido a mao — para teste e para simulacao deterministica.

    `set(ticker, price, ts=None)` define/atualiza a cotacao corrente de um
    ticker. `advance()` avanca uma sequencia pre-carregada (se usada nesse
    modo) — util para simular varias barras em teste sem precisar de rede
    nem de parquet."""

    name = "replay"
    source = "replay"

    def __init__(self, now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self._now_fn = now_fn
        self._quotes: dict[str, Quote] = {}
        self._sequences: dict[str, list[tuple[float, Optional[datetime]]]] = {}

    @property
    def delay_seconds(self) -> float:
        return 0.0

    def set(self, ticker: str, price: float, ts: Optional[datetime] = None) -> None:
        """Define a cotacao corrente de `ticker`."""
        resolved_ts = ts if ts is not None else self._now_fn()
        self._quotes[ticker] = Quote(
            ticker=ticker,
            price=float(price),
            ts=resolved_ts,
            source=self.source,
            delay_seconds=0.0,
        )

    def queue(self, ticker: str, sequence: list[tuple[float, Optional[datetime]]]) -> None:
        """Carrega uma sequencia de (preco, ts) a ser consumida por `advance()`."""
        self._sequences[ticker] = list(sequence)

    def advance(self, ticker: str) -> Optional[Quote]:
        """Consome o proximo (preco, ts) da fila de `ticker`, se houver, e o
        torna a cotacao corrente. Devolve `None` se a fila estiver vazia."""
        seq = self._sequences.get(ticker)
        if not seq:
            return None
        price, ts = seq.pop(0)
        self.set(ticker, price, ts)
        return self._quotes[ticker]

    def quotes(self, tickers: Sequence[str]) -> dict[str, Quote]:
        return {t: self._quotes[t] for t in tickers if t in self._quotes}
