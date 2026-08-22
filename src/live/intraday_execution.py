"""Execucao REAL de um robo intradiario: a ponte entre
`backtest/intraday/machine.py::IntradaySessionMachine` e a corretora.

Por que esta camada existe
--------------------------
A maquina de estados e' a MESMA no backtest e ao vivo -- e' isso que garante
que o robo que opera e' o robo validado. Mas uma coisa nao pode ser a mesma:
a resposta a "esta ordem preencheu, e a que preco?".

No backtest a resposta so pode vir da barra: se o OHLC tocou o nivel, assume
que preencheu no nivel. E' a melhor aproximacao possivel sem livro de ofertas
-- e e' OTIMISTA por construcao, porque ignora fila. Uma ordem de compra
parada em R$3,42 num toque exato de R$3,42 pode perfeitamente nao executar:
havia gente na frente.

Com dinheiro real, herdar esse otimismo seria o pior tipo de bug: o robo se
acharia posicionado, comecaria a contar alvo e stop, mandaria uma ordem de
VENDA de algo que nunca comprou -- e numa conta NETTING isso nao da erro, abre
uma posicao vendida. Por isso, em `execution_mode="live"`, a maquina para de
perguntar para a barra e passa a perguntar para a corretora, via esta classe.

O que e' fonte de verdade aqui
------------------------------
`MT5Broker.open_position()` -- a posicao que o terminal reporta para ESTE
`magic` neste simbolo. Nao o ticket da ordem: numa conta NETTING o terminal
consolida tudo do papel numa posicao so, e e' o preco medio e o volume dela
que dizem o que se tem de verdade.

Falha de CONSULTA nunca vira "nao preencheu"
--------------------------------------------
Toda incerteza sobe como excecao, nunca como `None`/`0`. Um terminal fechado
respondendo "sem posicao" e uma conta de fato zerada sao indistinguiveis pela
resposta, mas nao pelas consequencias: tratar o primeiro como o segundo faria
o robo re-armar ordem sobre uma posicao que existe. O supervisor
(`scripts/run_live.py::cmd_loop`) ja loga e tenta de novo na proxima barra --
perder uma barra e' barato, operar sobre estado imaginario nao e'.

Divergencia declarada que ESTA camada nao resolve
-------------------------------------------------
Stop e alvo continuam sendo avaliados em barra M1 FECHADA pela maquina, entao
a ordem de saida sai ate 60s depois do toque. A correcao real e' SL/TP do lado
da corretora (trabalho separado); ate la e' custo conhecido, nao surpresa.
Ver a docstring de `live/intraday_runtime.py`.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from core.live_models import Order, OrderSide, OrderStatus, OrderType
from core.models import IntradayExitReason


class BrokerExecutionError(RuntimeError):
    """A corretora nao confirmou o que era preciso confirmar.

    Sempre significa "nao sei", nunca "nao aconteceu" -- quem captura deve
    tentar de novo na proxima barra, jamais assumir um resultado."""


class MT5IntradayExecution:
    """Ponte de execucao real para `IntradaySessionMachine.execution`.

    Guarda a ordem pendente CORRENTE (`self.pending_order`) para poder
    cancela-la; todo o resto do estado continua morando na maquina."""

    def __init__(self, broker, symbol: str) -> None:
        self.broker = broker
        self.symbol = symbol
        # A `Order` da ordem-limite viva no terminal (com `broker_ref` =
        # ticket), ou `None`. Nao e' estado de decisao -- e' so o recibo
        # necessario para cancelar depois.
        self.pending_order: Optional[Order] = None
        # Recibos do ultimo fill de entrada e da ultima saida, para o runtime
        # gravar `broker_ref`/`fees` REAIS no diario em vez de `None`. A
        # maquina so devolve preco e quantidade (o que ela precisa para o
        # trade); estes campos sao rastreabilidade, e sem eles uma linha do
        # diario nao poderia ser cruzada com o extrato da corretora.
        self.last_entry_ref: Optional[str] = None
        self.last_exit_order: Optional[Order] = None

    # ---------- ordem-limite pendente --------------------------------------

    def place_limit(self, side: str, limit_price: float, quantity: int,
                    ts: pd.Timestamp) -> Order:
        """Registra a ordem-limite no terminal. Devolve a `Order` (para o
        runtime journalizar) e guarda o ticket para o cancelamento."""
        order = Order(
            ticker=self.symbol,
            side=OrderSide.BUY if side == "long" else OrderSide.SELL,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            sent_at=ts.to_pydatetime(),
        )
        enviada = self.broker.place_pending(order)
        if enviada.status == OrderStatus.REJECTED:
            raise BrokerExecutionError(
                f"corretora recusou a ordem-limite {side} {quantity} {self.symbol} @ "
                f"{limit_price:.4f}: {enviada.note}"
            )
        self.pending_order = enviada
        return enviada

    def cancel_limit(self, ts: pd.Timestamp, reason: str) -> Optional[Order]:
        """Remove do terminal a ordem-limite corrente, se houver.

        Nunca levanta: uma pendente que ja sumiu do terminal (expirou, foi
        cancelada na mao) tem o objetivo cumprido, e `MT5Broker.cancel` ja
        traduz isso em `CANCELLED` com o motivo na nota."""
        order = self.pending_order
        if order is None:
            return None
        self.pending_order = None
        return self.broker.cancel(order)

    # ---------- o que a maquina pergunta -----------------------------------

    def limit_fill(self, order, bar) -> Optional[dict]:
        """A ordem-limite vigiada preencheu? Pergunta a CORRETORA, nao a barra.

        `{"price", "quantity"}` se sim, `None` se continua parada. `bar` entra
        na assinatura para casar com o modo simulado (e para o diagnostico das
        excecoes); o valor dela NAO participa da decisao aqui -- esse e'
        justamente o ponto."""
        posicao = self._read_position()
        if posicao is None:
            return None
        if posicao["side"] != order.side:
            raise BrokerExecutionError(
                f"a corretora reporta posicao {posicao['side']} em {self.symbol} "
                f"({posicao['quantity']} acoes @ {posicao['price']:.4f}) enquanto a "
                f"ordem-limite vigiada era {order.side} @ {order.limit_price:.4f}. "
                "Nao vou assumir que esta posicao e' minha nem opera-la: confira o "
                "terminal (posicao aberta na mao? outro robo com o mesmo magic?) "
                "antes de religar este slot."
            )
        # A pendente virou posicao -- o ticket morreu sozinho, nao ha o que
        # cancelar depois.
        self.last_entry_ref = (
            self.pending_order.broker_ref if self.pending_order is not None else None
        )
        self.pending_order = None
        return {"price": posicao["price"], "quantity": posicao["quantity"]}

    def exit_market(self, position, ts: pd.Timestamp, reason: IntradayExitReason) -> dict:
        """Fecha a posicao A MERCADO e devolve `{"price"}` -- o preco que a
        corretora de fato executou.

        A mercado inclusive no alvo: uma saida por ordem-limite poderia nao
        preencher e deixar a posicao aberta contra o proprio stop. Ver o
        comentario em `IntradaySessionMachine._close_position`."""
        fechamento = Order(
            ticker=self.symbol,
            side=OrderSide.SELL if position.side == "long" else OrderSide.BUY,
            quantity=position.quantity,
            order_type=OrderType.MARKET,
            sent_at=ts.to_pydatetime(),
        )
        executada = self.broker.place(fechamento)
        if executada.status == OrderStatus.REJECTED:
            raise BrokerExecutionError(
                f"corretora recusou o fechamento ({reason.value}) de {position.quantity} "
                f"{self.symbol}: {executada.note}. A posicao continua ABERTA na "
                "corretora e na maquina -- vou tentar de novo na proxima barra."
            )
        if executada.status == OrderStatus.PARTIAL:
            raise BrokerExecutionError(
                f"fechamento ({reason.value}) de {self.symbol} preencheu so "
                f"{executada.filled_qty} de {position.quantity} acoes. Sobrou posicao "
                "aberta na corretora; a maquina segue com a posicao inteira e tenta "
                "fechar o resto na proxima barra, em vez de registrar um trade que "
                "nao aconteceu por completo."
            )
        if not executada.avg_price:
            raise BrokerExecutionError(
                f"fechamento de {self.symbol} voltou sem preco medio da corretora "
                f"(status={executada.status.value}, note={executada.note!r}) -- sem "
                "esse numero o P&L do trade seria inventado."
            )
        self.last_exit_order = executada
        return {"price": float(executada.avg_price), "order": executada}

    # ---------- leitura -----------------------------------------------------

    def _read_position(self) -> Optional[dict]:
        """Posicao da corretora para este simbolo/magic.

        `MT5Broker.open_position` devolve `None` tanto para "nao tem posicao"
        quanto para "nao consegui falar com o terminal" -- por isso a conexao
        e' conferida ANTES: sem isso, um terminal fechado seria lido como
        conta zerada."""
        if not self.broker.connect():
            raise BrokerExecutionError(
                "sem conexao com o terminal MT5 -- nao da para saber se a ordem "
                "preencheu. Nao vou presumir que nao preencheu."
            )
        return self.broker.open_position(self.symbol)
