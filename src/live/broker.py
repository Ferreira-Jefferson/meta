"""Execucao de ordem, atras de um port.

Regra de fronteira (AGENTS.md #6): um `Broker` executa, NUNCA decide e NUNCA
persiste. Ele muta e devolve a `Order` recebida (`status`, `filled_qty`,
`avg_price`, `fees`, `slippage`, `broker_ref`) — quem grava essa `Order` no
diario e quem atualiza `AccountState` e o RUNTIME, nunca o broker. Motivo:
se o broker tivesse acesso a escrita, um bug de execucao poderia corromper o
diario sem passar pelo unico lugar que sabe como fazer isso direito
(`journal/writer.py`), e o broker deixaria de ser uma peca trocavel (paper
hoje, corretora real amanha) para virar um segundo dono de estado de conta.

Implementacoes de producao (`src/`), nesta ordem:

  - `ManualBroker` — para quem opera na mao pela corretora: gera um ticket
    legivel, e um humano confirma o fill depois via `confirm()`.
  - Corretora real (`live.broker_mt5.MT5Broker`, via pip `MetaTrader5`) fala
    com um terminal MT5 ja aberto na mesma maquina.

Nenhuma classe que preenche sozinha contra um feed (simulacao) mora em
`src/` — isso e, por definicao, um dublê de teste, nunca uma corretora real
(ver `tests/doubles.py::PaperBroker`, movida para la em FEAT-001: mante-la
aqui era o que permitia o dashboard/CLI cair nela por um fallback silencioso
sempre que o modo pedido nao batia com nenhum broker real). Esse e o ponto de
existir o port: nem o runtime nem os robos de `strategy/` precisam mudar uma
linha para trocar de broker — so troca qual `Broker` e instanciado.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from core.live_models import Order, OrderSide, OrderStatus, OrderType


class Broker(ABC):
    """Port de execucao. Contrato: recebe uma `Order`, devolve a MESMA
    `Order` mutada com o resultado. Nao guarda historico, nao escreve banco."""

    name: str
    mode: str  # 'manual' | 'mt5' (ver core.live_models.BrokerMode)
    # `True` só em dublês de teste (ex.: `tests/doubles.PaperBroker`) — nunca
    # em broker de produção. `LiveRuntime.__init__` recusa instanciar um
    # dublê apontando para o banco de produção (`core.config.LIVE_DB_PATH`),
    # ver `live/runtime.py` (item 0.3 herdado de FEAT-000).
    is_test_double: bool = False

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

    def cash_balance(self) -> Optional[float]:
        """Saldo de caixa segundo uma fonte EXTERNA e independente da conta
        interna (`AccountState.cash`), se este broker tiver uma. Default
        `None`: `ManualBroker` (nao fala com corretora nenhuma) nao tem algo
        para comparar — `None` significa "nao tenta reconciliar deposito
        contra este broker", nunca "saldo zero". So uma conexao de corretora
        de verdade (ver `MT5Broker.cash_balance`) sabe responder isto de
        fato."""
        return None


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
