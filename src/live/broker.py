"""Execucao de ordem, atras de um port.

Regra de fronteira (AGENTS.md #6): um `Broker` executa, NUNCA decide e NUNCA
persiste. Ele muta e devolve a `Order` recebida (`status`, `filled_qty`,
`avg_price`, `fees`, `slippage`, `broker_ref`) — quem grava essa `Order` no
diario e quem atualiza `AccountState` e o RUNTIME, nunca o broker. Motivo:
se o broker tivesse acesso a escrita, um bug de execucao poderia corromper o
diario sem passar pelo unico lugar que sabe como fazer isso direito
(`journal/writer.py`), e o broker deixaria de ser uma peca trocavel (paper
hoje, corretora real amanha) para virar um segundo dono de estado de conta.

Implementacoes nesta ordem:

  - `PaperBroker`  — preenche contra um `QuoteFeed`, aplicando o MESMO
    `CostModel` do backtest (`backtest/costs.py`). Ver docstring da classe
    para o porque disso ser inegociavel.
  - `ManualBroker` — para quem opera na mao pela corretora: gera um ticket
    legivel, e um humano confirma o fill depois via `confirm()`.

  - Corretora real (MetaTrader5 via pip `MetaTrader5`, ou API REST de uma
    corretora) entraria aqui como uma TERCEIRA classe que implementa o mesmo
    port (`place`/`poll`/`cancel`). Esse e o ponto de existir o port: nem o
    runtime nem os robos de `strategy/` precisam mudar uma linha para trocar
    de paper para corretora real — so troca qual `Broker` e instanciado.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from backtest.costs import apply_slippage, fees_for_leg
from core.config import CostModel
from core.live_models import Order, OrderSide, OrderStatus, OrderType
from live.feed import QuoteFeed


class Broker(ABC):
    """Port de execucao. Contrato: recebe uma `Order`, devolve a MESMA
    `Order` mutada com o resultado. Nao guarda historico, nao escreve banco."""

    name: str
    mode: str  # 'paper' | 'manual' | 'broker'

    @abstractmethod
    def place(self, order: Order) -> Order:
        """Envia a ordem. Muta e devolve `order` com o resultado (fill
        imediato para paper; `SENT` + ticket para manual)."""
        raise NotImplementedError

    @abstractmethod
    def poll(self, order: Order) -> Order:
        """Atualiza o status de uma ordem ja enviada. Para brokers sincronos
        (paper), e um no-op que devolve a ordem como esta — o fill ja
        aconteceu em `place`."""
        raise NotImplementedError

    def cancel(self, order: Order) -> Order:
        """Cancela uma ordem viva. Default: marca `CANCELLED` se ainda nao
        terminal; ordens ja terminais (`is_terminal`) ficam como estao —
        cancelar um fill ja consumado nao desfaz o fill."""
        if not order.is_terminal:
            order.status = OrderStatus.CANCELLED
        return order

    def supports_automation(self) -> bool:
        """Se este broker pode operar sem confirmacao humana no meio. Paper e
        corretora real: sim. Manual: nao — por definicao, precisa de um
        humano para fechar o ciclo."""
        return True


class PaperBroker(Broker):
    """Preenche a ordem contra um `QuoteFeed`, com o MESMO custo do backtest.

    Por que reusar `apply_slippage`/`fees_for_leg` de `backtest/costs.py` em
    vez de ter uma conta propria aqui: o proposito do paper trading e validar
    a operacao contra o que o backtest promete. Se o paper usasse um modelo de
    custo diferente (mesmo que "mais realista" na opiniao de alguem), o
    resultado do paper deixaria de ser comparavel ao resultado do backtest —
    e e exatamente essa comparacao (paper bateu o backtest? ficou atras?
    quanto?) que da confianca para ligar dinheiro real. Custo tem que ser o
    mesmo numero, sempre.
    """

    name = "paper"
    mode = "paper"

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
            # compra so executa a <= limite; venda so executa a >= limite.
            # fora disso a ordem fica viva (SENT), nao rejeitada — e assim que
            # uma limitada real se comporta na corretora: espera o preco.
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


class ManualBroker(Broker):
    """Para quem executa na mao, direto na corretora.

    `place()` NUNCA inventa um fill — ninguem sabe o preco real ate um humano
    olhar o extrato da corretora e digitar. O que `place()` faz e deixar a
    ordem pronta para ser executada por um humano: status `SENT`, uma
    referencia `MANUAL-<n>` e um ticket legivel em `order.note` (o que
    comprar/vender, quanto, a que preco-alvo, e por que — para quem vai
    apertar o botao na corretora nao precisar adivinhar o motivo).

    `confirm()` e o unico jeito de fechar o ciclo: recebe o que o humano
    realmente conseguiu executar e valida antes de aceitar.
    """

    name = "manual"
    mode = "manual"

    def __init__(self) -> None:
        self._next_ref = 1
        self._pending: dict[int, Order] = {}

    def place(self, order: Order) -> Order:
        order.status = OrderStatus.SENT
        order.broker_ref = f"MANUAL-{self._next_ref}"
        self._next_ref += 1

        acao = "COMPRAR" if order.side == OrderSide.BUY else "VENDER"
        alvo = (
            f"a mercado" if order.order_type == OrderType.MARKET
            else f"a {order.limit_price}" if order.order_type == OrderType.LIMIT
            else "no leilao de abertura"
        )
        motivo = f" — motivo: {order.note}" if order.note else ""
        order.note = f"{acao} {order.quantity} {order.ticker} {alvo}{motivo}"

        self._pending[id(order)] = order
        return order

    def poll(self, order: Order) -> Order:
        """Manual nao tem como consultar a corretora sozinho: devolve a
        ordem como esta ate um humano chamar `confirm()`."""
        return order

    def confirm(
        self, order: Order, filled_qty: int, avg_price: float, fees: float = 0.0
    ) -> Order:
        """Um humano relata o que a corretora realmente executou.

        `filled_qty` precisa ser > 0 e <= `order.quantity` — fill zero nao e
        confirmacao (e nao-evento) e fill acima do pedido e impossivel numa
        corretora real, entao e sinal de erro de digitacao."""
        if filled_qty <= 0 or filled_qty > order.quantity:
            raise ValueError(
                f"filled_qty invalido: {filled_qty} (pedido: {order.quantity})"
            )
        if avg_price <= 0:
            raise ValueError(f"avg_price invalido: {avg_price}")

        order.filled_qty = filled_qty
        order.avg_price = avg_price
        order.fees = fees
        order.status = OrderStatus.FILLED if filled_qty == order.quantity else OrderStatus.PARTIAL
        self._pending.pop(id(order), None)
        return order

    def supports_automation(self) -> bool:
        return False

    def pending_tickets(self) -> list[Order]:
        """Ordens enviadas que ainda esperam confirmacao humana."""
        return list(self._pending.values())
