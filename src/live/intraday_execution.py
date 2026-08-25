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

    Guarda a(s) ordem(ns) pendente(s) CORRENTE(s) para poder cancela-las;
    todo o resto do estado continua morando na maquina.

    Fase 2 (2026-08-22) -- divisao de ordem de verdade na corretora: ate
    entao esta classe SEMPRE tratava a ordem-limite como um pedido so'
    (`self.pending_order`), ignorando `EnterLimit.split_quantities` -- o robo
    pedia a divisao, mas a corretora recebia UMA ordem so' do tamanho total.
    Agora `place_limit` manda um filho REAL por elemento de `quantities`
    (`self.pending_orders`), e `limit_fill` detecta o CRESCIMENTO da posicao
    consolidada (delta), nao "existe posicao?" -- nao precisa saber QUAL
    ticket preencheu, so' quanto cresceu (o motor ja contabiliza por
    quantidade, nao por identidade de ordem, ver `backtest.intraday.machine.
    _resolve_limit_fills`). Do lado da SAIDA, `place_exit_limit`/
    `exit_fill`/`cancel_exit_limit` fazem o mesmo, espelhado, para a fatia de
    `_Position.exit_split_unit` (ver `IntradaySessionMachine.
    _resolve_live_split_exit`)."""

    def __init__(self, broker, symbol: str) -> None:
        self.broker = broker
        self.symbol = symbol
        # As `Order` das ordens-limite de ENTRADA vivas no terminal (com
        # `broker_ref` = ticket cada), uma por filho de `EnterLimit.
        # split_quantities` (`[quantity]` quando a ordem nao veio dividida).
        # Cancelar TODAS indiscriminadamente e' seguro mesmo que algumas ja
        # tenham preenchido: `MT5Broker.cancel` e' idempotente para um ticket
        # que ja nao esta mais vivo (ver a docstring dele).
        self.pending_orders: list[Order] = []
        # Ultima leitura de quantidade/preco medio da posicao desde que o
        # grupo de filhos CORRENTE foi armado (`place_limit` zera os dois) --
        # e' o que permite `limit_fill` devolver so' o DELTA (o que cresceu
        # desde a ultima checagem), nao o total, e reconstituir o preco da
        # FATIA nova invertendo a media ponderada que a corretora ja fez.
        self._last_known_qty: float = 0.0
        self._last_known_avg: float = 0.0
        # Espelho do lado da SAIDA: a ordem-limite de saida REAL vigiada
        # agora (`None` = nenhuma posicionada) e a quantidade da posicao ANTES
        # dela ser posicionada (baseline para medir o quanto encolheu).
        self.pending_exit_order: Optional[Order] = None
        self._exit_baseline_qty: float = 0.0
        # Recibos do ultimo fill de entrada e da ultima saida, para o runtime
        # gravar `broker_ref`/`fees` REAIS no diario em vez de `None`. A
        # maquina so devolve preco e quantidade (o que ela precisa para o
        # trade); estes campos sao rastreabilidade, e sem eles uma linha do
        # diario nao poderia ser cruzada com o extrato da corretora.
        self.last_entry_ref: Optional[str] = None
        self.last_exit_order: Optional[Order] = None

    # ---------- ordem-limite pendente (ENTRADA) -----------------------------

    def place_limit(self, side: str, limit_price: float, quantities: list[int],
                    ts: pd.Timestamp) -> list[Order]:
        """Registra UMA ordem-limite REAL por elemento de `quantities` (ver
        `EnterLimit.children`) no MESMO nivel. Devolve a lista de `Order`
        (para o runtime journalizar) e guarda os tickets para cancelamento.

        Se qualquer fatia for recusada, CANCELA as ja enviadas antes de
        levantar -- nunca deixa uma entrada posicionada PELA METADE na corretora
        sem o robo saber."""
        self._last_known_qty = 0.0
        self._last_known_avg = 0.0
        enviadas: list[Order] = []
        for i, qty in enumerate(quantities):
            order = Order(
                ticker=self.symbol,
                side=OrderSide.BUY if side == "long" else OrderSide.SELL,
                quantity=qty,
                order_type=OrderType.LIMIT,
                limit_price=limit_price,
                sent_at=ts.to_pydatetime(),
            )
            enviada = self.broker.place_pending(order)
            if enviada.status == OrderStatus.REJECTED:
                for feita in enviadas:
                    self.broker.cancel(feita)
                self.pending_orders = []
                raise BrokerExecutionError(
                    f"corretora recusou a fatia {i + 1}/{len(quantities)} ({qty} de "
                    f"{sum(quantities)} acoes) da ordem-limite {side} {self.symbol} @ "
                    f"{limit_price:.4f}: {enviada.note}. As {len(enviadas)} fatia(s) ja "
                    "enviada(s) foram canceladas -- nunca fica uma entrada posicionada pela "
                    "metade."
                )
            enviadas.append(enviada)
        self.pending_orders = enviadas
        return enviadas

    def cancel_limit(self, ts: pd.Timestamp, reason: str) -> list[Order]:
        """Remove do terminal TODAS as ordens-limite de entrada correntes.

        Nunca levanta: uma pendente que ja sumiu do terminal (expirou, foi
        cancelada na mao, ou ja preencheu) tem o objetivo cumprido, e
        `MT5Broker.cancel` ja traduz isso em `CANCELLED` com o motivo na
        nota -- cancelar um ticket ja preenchido e' um no-op seguro."""
        orders = self.pending_orders
        self.pending_orders = []
        return [self.broker.cancel(o) for o in orders]

    def cancel_stale_refs(self, broker_refs: list[str], ts: pd.Timestamp) -> list[Order]:
        """Cancela no terminal ordens-limite de ENTRADA cujo ticket sobrou de
        um PROCESSO ANTERIOR (restart no meio do pregao) -- `self.
        pending_orders` desta instancia nasce sempre vazio (e' um objeto
        novo), entao `cancel_limit` nao teria o que cancelar mesmo que a
        ordem ainda esteja viva no book.

        Construida so' com `broker_ref` (o unico campo que `MT5Broker.cancel`
        de fato usa para cancelar por ticket -- ver a docstring dele); os
        demais campos aqui sao so' para caber na assinatura de `Order`, nunca
        lidos pela corretora neste caminho. Mesma garantia de no-op seguro de
        `cancel_limit`: um ticket que ja preencheu ou ja sumiu do terminal
        (por qualquer motivo, inclusive ter sido cancelado por este mesmo
        metodo numa tentativa anterior) e' cancelamento idempotente."""
        canceladas = []
        for ref in broker_refs:
            order = Order(
                ticker=self.symbol, side=OrderSide.BUY, quantity=0,
                order_type=OrderType.LIMIT, broker_ref=ref, sent_at=ts.to_pydatetime(),
            )
            canceladas.append(self.broker.cancel(order))
        return canceladas

    # ---------- o que a maquina pergunta (ENTRADA) --------------------------

    def limit_fill(self, order, bar) -> Optional[dict]:
        """A ordem-limite vigiada CRESCEU desde a ultima checagem? Pergunta a
        CORRETORA, nao a barra.

        `{"price", "quantity"}` do DELTA (nao do total) se cresceu, `None` se
        nao mudou. `bar` entra na assinatura para casar com o modo simulado
        (e para o diagnostico das excecoes); o valor dela NAO participa da
        decisao aqui -- esse e' justamente o ponto.

        O `price` do delta e' reconstituido invertendo a media ponderada que
        a propria corretora ja fez (`avg_novo*qtd_novo - avg_velho*qtd_velho)
        / delta_qtd`) -- devolver a media JA misturada (`posicao['price']`)
        faria o motor misturar a mistura de novo ao fazer o proprio TOP-UP
        (ver `backtest.intraday.machine.on_closed_bar`)."""
        posicao = self._read_position()
        qtd_atual = 0.0 if posicao is None else float(posicao["quantity"])
        if qtd_atual <= self._last_known_qty:
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
        avg_atual = float(posicao["price"])
        delta_qty = qtd_atual - self._last_known_qty
        if self._last_known_qty > 0:
            delta_price = (
                (avg_atual * qtd_atual - self._last_known_avg * self._last_known_qty) / delta_qty
            )
        else:
            delta_price = avg_atual
        self._last_known_qty = qtd_atual
        self._last_known_avg = avg_atual
        self.last_entry_ref = posicao.get("ticket")
        return {"price": delta_price, "quantity": int(round(delta_qty))}

    # ---------- ordem-limite pendente (SAIDA dividida, Fase 2) --------------

    def place_exit_limit(self, position_side: str, quantity: int, limit_price: float,
                         current_position_qty: float, ts: pd.Timestamp) -> Order:
        """Registra UMA ordem-limite REAL de fechamento (fatia de
        `_Position.exit_split_unit`) no terminal -- o oposto de `place_limit`,
        do lado da saida. `current_position_qty` e' o que a MAQUINA sabe que
        a posicao tem ANTES desta fatia (baseline para `exit_fill` medir o
        quanto encolheu depois) -- lido da propria maquina, nao da corretora
        de novo, para nao arriscar uma leitura atrasada/adiantada no
        instante exato do armamento."""
        order = Order(
            ticker=self.symbol,
            side=OrderSide.SELL if position_side == "long" else OrderSide.BUY,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            sent_at=ts.to_pydatetime(),
        )
        enviada = self.broker.place_pending(order)
        if enviada.status == OrderStatus.REJECTED:
            raise BrokerExecutionError(
                f"corretora recusou a ordem-limite de SAIDA ({quantity} {self.symbol} @ "
                f"{limit_price:.4f}): {enviada.note}. A posicao continua aberta na "
                "corretora, sem fatia nenhuma cancelada."
            )
        self.pending_exit_order = enviada
        self._exit_baseline_qty = float(current_position_qty)
        return enviada

    def cancel_exit_limit(self, ts: pd.Timestamp, reason: str) -> Optional[Order]:
        """Remove do terminal a ordem-limite de saida corrente, se houver.
        Mesma garantia de no-op seguro de `cancel_limit`."""
        order = self.pending_exit_order
        if order is None:
            return None
        self.pending_exit_order = None
        return self.broker.cancel(order)

    def exit_fill(self, position_side: str, bar) -> Optional[dict]:
        """A fatia de saida vigiada (`place_exit_limit`) encolheu a posicao
        desde que foi posicionada? `{"price", "quantity"}` do que fechou (o preco
        e' o LIMITE pedido -- uma ordem-limite so' preenche nesse nivel ou
        melhor, e sem consultar deal a deal no terminal nao ha como saber
        "melhor"; usar o limite e' o numero conhecido, nunca inventado), ou
        `None` se a posicao nao mudou."""
        posicao = self._read_position()
        qtd_atual = 0.0 if posicao is None else float(posicao["quantity"])
        diminuiu = self._exit_baseline_qty - qtd_atual
        if diminuiu <= 0:
            return None
        if posicao is not None and posicao["side"] != position_side:
            raise BrokerExecutionError(
                f"a corretora reporta posicao {posicao['side']} em {self.symbol} "
                f"({posicao['quantity']} acoes) enquanto a saida vigiada era de uma "
                f"posicao {position_side}. Nao vou assumir que esta posicao e' minha "
                "nem opera-la: confira o terminal antes de religar este slot."
            )
        self._exit_baseline_qty = qtd_atual
        preco = self.pending_exit_order.limit_price if self.pending_exit_order is not None else None
        return {"price": preco, "quantity": int(round(diminuiu))}

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
