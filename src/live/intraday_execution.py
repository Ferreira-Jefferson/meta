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
    tentar de novo na proxima barra, jamais assumir um resultado.

    `orphan_refs` carrega os tickets que o ROLLBACK tambem nao conseguiu
    confirmar mortos (ver `place_limit`). Vazio no caso normal; quando vem
    cheio, quem captura NAO pode esquecer esses tickets -- eles podem
    seguir vivos no book.

    `kind` (gap f, incidente 2026-08-28): distingue DUAS familias bem
    diferentes de "nao sei", que `live/intraday_runtime.py` trata de jeito
    OPOSTO:

      - `FECHAMENTO_RECUSADO` -- a corretora recusou uma ordem de SAIDA
        (fechamento a mercado ou ordem-limite de saida), mas a posicao
        continua EXATAMENTE como a maquina ja sabia que estava -- nenhuma
        divergencia de dado, so' uma ordem que nao passou. SEGURO de
        capturar e tentar de novo na proxima barra (`IntradayLiveRuntime.
        _registra_falha_de_fechamento`); e' o caso do incidente real (MG51,
        ~24 recusas seguidas).
      - `FALHA_ALTO` (default) -- qualquer coisa que signifique "o que a
        maquina acha que tem e o que a corretora reporta DIVERGEM" (lado
        errado, sem conexao pra sequer perguntar) -- capturar e seguir em
        frente aqui arriscaria operar sobre um estado que ninguem confirmou.
        Tem de propagar e travar o passo, mesmo comportamento de sempre
        (antes deste campo existir, TODO `BrokerExecutionError` era assim).
        Deliberadamente o DEFAULT: um raise novo que esquecer de marcar
        `kind` cai no lado seguro (propaga), nunca no lado que engole erro."""

    FECHAMENTO_RECUSADO = "fechamento_recusado"
    FALHA_ALTO = "falha_alto"
    #: A maquina decidiu alvo/stop e a protecao REGISTRADA NA CORRETORA
    #: ainda nao fechou a posicao. NAO e' recusa nem erro -- e' o estado
    #: normal de esperar o nivel ser tocado. Quem captura mantem a posicao
    #: aberta e reavalia na proxima barra, SEM contar como recusa (ver
    #: `MAX_CLOSE_REFUSALS_BEFORE_HALT`) e sem alarme.
    AGUARDANDO_PROTECAO = "aguardando_protecao"

    def __init__(self, *args, orphan_refs: Optional[list[str]] = None,
                kind: str = FALHA_ALTO):
        super().__init__(*args)
        self.orphan_refs: list[str] = list(orphan_refs or [])
        self.kind = kind


def orphan_refs(canceladas: list[Order]) -> list[str]:
    """Dos cancelamentos tentados, quais tickets NAO ficaram resolvidos.

    `MT5Broker.cancel` nao levanta quando falha: sem o pacote MT5, sem
    conexao, com excecao inesperada ou com um retcode que nao e' `DONE`,
    ele devolve a `Order` com o motivo na nota e o status INTOCADO. Ordem
    que nao chegou a estado terminal (`FILLED`/`CANCELLED`/`REJECTED`)
    pode, portanto, seguir viva no book -- e' exatamente o que precisa
    sobreviver em `pending_entry_refs` em vez de ser esquecido.

    Sem `broker_ref` nao ha o que reconciliar depois (a ordem nunca chegou
    a existir na corretora), entao fica de fora."""
    return [o.broker_ref for o in canceladas
            if o.broker_ref and not o.is_terminal]


def descarta_confirmados(refs: list[str], canceladas: list[Order]) -> list[str]:
    """`refs` menos os tickets que a corretora CONFIRMOU resolvidos.

    Contraparte de `orphan_refs` para quem ja mantinha uma lista de
    vigilancia (`pending_entry_refs`): some da lista so' o ticket que
    chegou a estado terminal. O que o cancelamento nao confirmou fica --
    esquece-lo e' que deixaria uma ordem viva sem dono. Ticket que nao
    estava na tentativa de cancelamento tambem fica, intocado."""
    mortos = {o.broker_ref for o in canceladas if o.broker_ref and o.is_terminal}
    return [r for r in refs if r not in mortos]


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
        # Setado por `exit_por_protecao` quando ela teve de cair para o
        # fechamento a MERCADO porque a corretora nao tinha o nivel
        # registrado. O runtime le e alarma -- posicao sem protecao e' o
        # incidente de 2026-08-28, nao pode passar em silencio.
        self.protecao_ausente_no_fechamento: Optional[tuple] = None
        self._exit_baseline_qty: float = 0.0
        # Recibos do ultimo fill de entrada e da ultima saida, para o runtime
        # gravar `broker_ref`/`fees` REAIS no diario em vez de `None`. A
        # maquina so devolve preco e quantidade (o que ela precisa para o
        # trade); estes campos sao rastreabilidade, e sem eles uma linha do
        # diario nao poderia ser cruzada com o extrato da corretora.
        self.last_entry_ref: Optional[str] = None
        self.last_exit_order: Optional[Order] = None
        # Tickets de SAIDA que `cancel_exit_limit` nao conseguiu confirmar
        # mortos. O runtime drena isto a cada barra (`_drena_orfas_de_saida`):
        # aqui e' so' o deposito, porque quem tem `conn`/`account` para
        # journalizar e' ele.
        self.exit_orphan_refs: list[str] = []

    # ---------- ordem-limite pendente (ENTRADA) -----------------------------

    def place_limit(self, side: str, limit_price: float, quantities: list[int],
                    ts: pd.Timestamp, stop: Optional[float] = None,
                    target: Optional[float] = None) -> list[Order]:
        """Registra UMA ordem-limite REAL por elemento de `quantities` (ver
        `EnterLimit.children`) no MESMO nivel. Devolve a lista de `Order`
        (para o runtime journalizar) e guarda os tickets para cancelamento.

        `stop`/`target` sao `EnterLimit.initial_stop`/`initial_target` -- os
        niveis que a ESTRATEGIA ja decidiu, transportados ate a corretora
        para viajarem no MESMO request que registra a ordem (ver
        `MT5Broker.place_pending`). E' o caminho ATOMICO: quando esta ordem
        preencher, a posicao ja nasce com SL/TP amarrados pela corretora, sem
        depender de nenhum processo estar vivo naquele instante. Vale para
        QUALQUER robo -- `initial_stop`/`initial_target` sao o contrato de
        `EnterLimit`, nao de uma estrategia especifica; quem nao declarar
        nivel manda `None` e cai no comportamento de antes.

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
                stop_price=stop,
                target_price=target,
                sent_at=ts.to_pydatetime(),
            )
            enviada = self.broker.place_pending(order)
            if enviada.status == OrderStatus.REJECTED:
                # O retorno de `cancel` E' a resposta: ele nao levanta quando
                # falha (ver `orphan_refs`). Descarta-lo era o que transformava
                # um rollback frustrado numa ordem viva que ninguem vigiava.
                orfas = orphan_refs([self.broker.cancel(f) for f in enviadas])
                self.pending_orders = []
                # Curto de proposito: este texto cai INTEIRO no diario
                # ("RECUSADA #01: {erro}", ver `IntradayLiveRuntime.
                # _recusa_de_envio`) e o dono pediu (2026-08-25) linha direta
                # la'. Sobra o que muda de uma recusa pra outra -- qual fatia e
                # o que a corretora respondeu. O rollback BEM-SUCEDIDO nao
                # entra: e' o caso normal, e caso normal nao e' noticia. Um
                # rollback FRUSTRADO entra, porque muda o que o dono precisa
                # fazer: ha um ticket possivelmente vivo no terminal.
                sobrou = (f" -- ticket {', '.join(orfas)} pode seguir vivo"
                          if orfas else "")
                raise BrokerExecutionError(
                    f"fatia {i + 1}/{len(quantities)} de {side} {self.symbol} "
                    f"@ {limit_price:.4f}: {enviada.note}{sobrou}",
                    orphan_refs=orfas,
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

    def resolve_orphaned_entry(self, broker_refs: list[str]) -> Optional[dict]:
        """A ordem-limite de ENTRADA identificada por `broker_refs` (os
        tickets em `IntradayLiveRuntime._snapshot.pending_entry_refs` -- a
        lista que sobrevive a restart, NAO `self.pending_orders`, que nasce
        vazia numa instancia nova) terminou o ciclo de vida inteiro SEM que
        a deteccao por crescimento de posicao (`limit_fill`) tivesse a
        chance de perceber.

        Caso medido ao vivo em 2026-09-04 (slot
        `dt-wdo_grid_reload_maker-wdo@-live`): a ordem preencheu as 14:18:31
        e a posicao fechou pelo alvo ATOMICO da propria corretora as
        14:18:32 -- os DOIS dentro do MESMO intervalo de poll do
        supervisor (5s). No poll seguinte a posicao mostra ZERO de novo
        (0 -> N -> 0 entre duas leituras): o crescimento nunca aparece,
        `limit_fill` nunca devolve nada, e a maquina fica vigiando pra
        sempre um ticket que a corretora ja resolveu ha' minutos.

        Devolve:
          - `None`: pelo menos um ticket ainda esta VIVO no book, ou nao
            deu para confirmar algum deles (consulta falhou -- item 1.6 de
            LICOES_DE_PRODUCAO.md, "nao sei" nunca autoriza). Fica tudo
            como esta, sem inventar desfecho.
          - `{"outcome": "dead"}`: nenhum ticket esta mais no book, e o
            historico confirma que NENHUM chegou a preencher (cancelada,
            recusada ou expirada) -- nenhum trade aconteceu, so' libera a
            vigilancia.
          - `{"outcome": "already_open"}`: preencheu, mas a posicao AINDA
            esta aberta (ou so' fechou PARCIALMENTE) -- deixa o caminho
            normal (`limit_fill`, na proxima chamada) descobrir isso pelo
            crescimento de posicao, como sempre; este metodo nao antecipa
            nada nesse caso.
          - `{"outcome": "round_trip", "entry_price", "entry_qty",
            "exit_price", "exit_qty", "exit_comment"}`: preencheu E fechou
            por inteiro entre dois polls -- os numeros vem DIRETO dos deals
            da corretora (`MT5Broker.deals_for_position`), nunca do nivel
            teorico da ordem (stop/alvo)."""
        tickets = [str(r) for r in broker_refs if r]
        if not tickets:
            return None
        consulta_estado = getattr(self.broker, "order_history_state", None)
        consulta_deals = getattr(self.broker, "deals_for_position", None)
        if consulta_estado is None or consulta_deals is None:
            return None  # broker sem os metodos novos (dublê antigo) -- nada a reconciliar

        estados = []
        for ticket in tickets:
            estado = consulta_estado(ticket)
            if not estado.get("ok"):
                return None
            estados.append(estado)
        if any(e.get("state") == "pending" for e in estados):
            return None

        algum_preencheu = any(e.get("state") in ("filled", "partial") for e in estados)
        position_ids = {e.get("position_id") for e in estados if e.get("position_id")}
        entradas: list[dict] = []
        saidas: list[dict] = []
        for pos_id in position_ids:
            resposta = consulta_deals(pos_id)
            if not resposta.get("ok"):
                return None
            for d in (resposta.get("deals") or []):
                if d.get("entry") == 0:
                    entradas.append(d)
                elif d.get("entry") == 1:
                    saidas.append(d)

        if not entradas:
            if algum_preencheu:
                # O proprio registro da ordem diz "preencheu", mas o deal
                # ainda nao apareceu no historico -- atraso de replicacao,
                # nao ausencia de fato. Fica esperando (item 1.6).
                return None
            return {"outcome": "dead"}

        qtd_entrada = sum(d["quantity"] for d in entradas)
        if qtd_entrada <= 0:
            return None
        preco_entrada = sum(d["price"] * d["quantity"] for d in entradas) / qtd_entrada

        qtd_saida = sum(d["quantity"] for d in saidas)
        if qtd_saida < qtd_entrada:
            # Nao fechou por inteiro (ou nao fechou nada ainda) -- a leitura
            # de posicao normal (`limit_fill`) ja vai mostrar essa
            # quantidade aberta no proximo poll, sem precisar deste caminho.
            return {"outcome": "already_open"}

        preco_saida = sum(d["price"] * d["quantity"] for d in saidas) / qtd_saida
        ultima_saida = max(saidas, key=lambda d: d.get("time") or 0)
        return {
            "outcome": "round_trip",
            "entry_price": preco_entrada, "entry_qty": int(round(qtd_entrada)),
            "exit_price": preco_saida, "exit_qty": int(round(qtd_saida)),
            "exit_comment": ultima_saida.get("comment", ""),
        }

    # ---------- ordem-limite pendente (SAIDA dividida, Fase 2) --------------

    def _exit_position_ticket(self, position_side: str) -> Optional[int]:
        """Ticket da posicao que esta fatia de SAIDA vai fechar, para
        `broker.place_pending(position_ticket=...)` -- gap 1.15 de
        LICOES_DE_PRODUCAO.md: a mesma amarracao que `exit_market`/
        `close_position` ja fazem para fechamento a MERCADO (incidente
        2026-08-28, MG51), agora tambem na ordem-limite PENDENTE de saida.

        Le a corretora AGORA (`_read_position`) em vez de confiar em
        `self.last_entry_ref` -- esse campo so' e' populado por `limit_fill`
        NESTA instancia, e um restart no meio do pregao herda a posicao sem
        nunca ter chamado `limit_fill`; ficaria sem ticket para sempre se
        dependesse dele.

        **Nunca levanta e nunca bloqueia o envio da ordem.** Se a consulta
        falhar ou a posicao lida nao bater o lado esperado, devolve `None` --
        e a ordem sai exatamente como saia ANTES deste campo existir, sem
        `"position"` no request. Isto e' so' plumbing de execucao (uma tag a
        mais no request), nao uma decisao sobre se a posicao existe: quem
        decide isso e' `exit_fill`/`_read_position`, chamados por quem
        precisa mesmo de uma resposta confiavel -- eles continuam propagando
        divergencia real como excecao, sem mudanca nenhuma aqui. Perder o
        ticket so' devolve este metodo ao comportamento anterior a
        2026-09-03, nunca a um comportamento pior."""
        try:
            posicao = self._read_position()
            if posicao is None or posicao.get("side") != position_side:
                return None
            ticket = posicao.get("ticket")
            return int(ticket) if ticket is not None else None
        except Exception:
            # `except Exception`, nao so' `BrokerExecutionError`, para o codigo
            # dizer o mesmo que a docstring promete. Com `MT5Broker` a unica
            # excecao possivel HOJE e' `BrokerExecutionError` (`position_state`
            # tem `except Exception` que devolve `ok=False`, e `_read_position`
            # traduz isso), mas essa garantia mora em OUTRA classe: qualquer
            # `Broker` novo, ou uma mudanca la, viraria excecao nova AQUI --
            # num caminho que antes de 2026-09-03 nem consultava a corretora.
            # Nao ter o ticket e' aceitavel (a ordem sai como saia antes);
            # derrubar o armamento da fatia de SAIDA por causa de uma consulta
            # que e' so' uma TAG a mais no request nao e'.
            return None

    def place_exit_limit(self, position_side: str, quantity: int, limit_price: float,
                         current_position_qty: float, ts: pd.Timestamp) -> Order:
        """Registra UMA ordem-limite REAL de fechamento (fatia de
        `_Position.exit_split_unit`) no terminal -- o oposto de `place_limit`,
        do lado da saida. `current_position_qty` e' o que a MAQUINA sabe que
        a posicao tem ANTES desta fatia (baseline para `exit_fill` medir o
        quanto encolheu depois) -- lido da propria maquina, nao da corretora
        de novo, para nao arriscar uma leitura atrasada/adiantada no
        instante exato do armamento.

        `position_ticket` (gap 1.15, 2026-09-03) viaja no request desta
        ordem-limite via `_exit_position_ticket` -- ver a docstring dele e a
        de `MT5Broker.place_pending`. Antes desta mudanca, a fatia de SAIDA
        por alvo nunca dizia qual posicao estava abatendo, a mesma lacuna
        estrutural que MG51 explorou do lado da ordem a MERCADO (item 1.1)."""
        order = Order(
            ticker=self.symbol,
            side=OrderSide.SELL if position_side == "long" else OrderSide.BUY,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            sent_at=ts.to_pydatetime(),
        )
        ticket = self._exit_position_ticket(position_side)
        enviada = self.broker.place_pending(order, position_ticket=ticket)
        if enviada.status == OrderStatus.REJECTED:
            raise BrokerExecutionError(
                f"corretora recusou a ordem-limite de SAIDA ({quantity} {self.symbol} @ "
                f"{limit_price:.4f}): {enviada.note}. A posicao continua aberta na "
                "corretora, sem fatia nenhuma cancelada.",
                # Nenhuma divergencia de dado -- a posicao continua EXATAMENTE
                # como a maquina ja sabia, so' uma ordem-limite de SAIDA que nao
                # passou. Mesma familia de "recusa" do gap (f).
                kind=BrokerExecutionError.FECHAMENTO_RECUSADO,
            )
        self.pending_exit_order = enviada
        self._exit_baseline_qty = float(current_position_qty)
        return enviada

    def cancel_exit_limit(self, ts: pd.Timestamp, reason: str) -> Optional[Order]:
        """Remove do terminal a ordem-limite de saida corrente, se houver.
        Mesma garantia de no-op seguro de `cancel_limit`.

        Quem chama (`machine.py`, 4 sites) fecha a posicao A MERCADO logo
        depois. Se o cancelamento nao for confirmado, as duas ordens ficam
        vivas pela mesma posicao -- e numa conta NETTING a limite orfa
        preenchendo DEPOIS do flatten inverte a posicao. Por isso o que nao
        confirmou vai para `exit_orphan_refs` em vez de ser esquecido; o
        runtime avisa e tenta de novo.

        ISSO ACONTECEU (2026-09-09, -R$80,00 numa posicao -- item 1.24 de
        LICOES_DE_PRODUCAO.md). O paragrafo acima ja descrevia o risco com
        precisao, e a mitigacao escolhida na epoca ("anota como orfa, o
        runtime avisa depois") nao impedia o que importa: quem chama seguia
        e mandava a ordem a MERCADO no mesmo passo, com a limite ainda viva
        no book. A limite orfa de saida (5114,00) preencheu 30 segundos
        depois e abriu o SEGUNDO contrato de um short numa conta de 1.

        Duas mudancas por causa disso:

         1. `pending_exit_order` so' e' esquecido quando o cancelamento
            CONFIRMA estado terminal. Antes era zerado incondicionalmente,
            entao a tentativa seguinte nao tinha mais o que cancelar --
            achava que estava tudo limpo e a orfa seguia viva, invisivel.
         2. O retorno passa a ser a resposta a "pode mandar ordem por cima?".
            Quem chama TEM de olhar (`machine._resolve_live_split_exit`, ramo
            do prazo): cancelamento nao confirmado significa ESPERAR, nunca
            empilhar uma segunda ordem. A posicao continua protegida pelo SL
            registrado na corretora enquanto isso -- esperar uma barra e'
            barato, inverter a posicao nao."""
        order = self.pending_exit_order
        if order is None:
            return None
        devolvida = self.broker.cancel(order)
        if bool(getattr(devolvida, "is_terminal", False)):
            self.pending_exit_order = None
            return devolvida
        # Nao confirmou: MANTEM `pending_exit_order` para a proxima barra
        # tentar de novo, e registra o ticket para o runtime vigiar. `dict.
        # fromkeys` em vez de `set` para nao duplicar em cada retentativa
        # sem perder a ordem de chegada.
        novas = orphan_refs([devolvida])
        self.exit_orphan_refs[:] = list(dict.fromkeys(self.exit_orphan_refs + novas))
        return devolvida

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

    def exit_por_protecao(self, position, ts: pd.Timestamp,
                          reason: IntradayExitReason) -> dict:
        """Alvo/stop: NAO manda ordem nenhuma -- confirma que a protecao
        REGISTRADA NA CORRETORA ja fechou a posicao, e devolve o preco que
        ela executou.

        Ordem do dono, 2026-09-08, depois do pregao que perdeu R$116,00:
        "deve posicionar o target e o stop assim que abre a posicao, nao e'
        para sair a mercado, a posicao deve ser fechada ou quando bate no
        alvo, ou quando bate no stop".

        O que isto substitui, e por que era errado. Ate' hoje `_close_
        position` mandava `exit_market` tambem no ALVO (ver o comentario que
        ficou la'), com a justificativa de que uma saida limitada poderia nao
        preencher e deixar a posicao contra o proprio stop. Ninguem pediu
        isso, e o custo medido e' estrutural, nao residual: venda a mercado
        executa no BID, compra no ASK, e o spread do WDO e' 1 tick. Com alvo
        de 2 ticks, sair a mercado entrega no MAXIMO metade do alvo -- e
        entrega -1 tick sempre que o preco nao andou. No pregao de 2026-09-08
        foram 14 fechamentos a mercado dos 23 contratos, e a distribuicao
        realizada (+R$5,00 x7 / R$0,00 x3 / -R$5,00 x11) nao tem relacao
        nenhuma com a geometria configurada (alvo +R$10,00 / stop -R$80,00):
        era so' onde estava o bid quando a ordem saiu.

        Alem do custo, era `live/` DECIDINDO -- a estrategia declarou alvo
        maker (`EnterLimit.initial_target`, que viaja no mesmo request da
        entrada e vira TP da corretora, ver `_alvo_atomico`), e a execucao
        trocava por outra coisa. Regra 6 do AGENTS.md.

        Quem fecha agora e' a corretora, no nivel exato que a estrategia
        pediu. Este metodo so' OLHA:
          - posicao ainda aberta la' -> `AGUARDANDO_PROTECAO`. A maquina
            mantem a posicao e reavalia na proxima barra. Nao e' erro.
          - posicao sumiu -> confirma o deal no historico
            (`_resolve_exit_from_history`, preco REAL) e devolve.
          - sumiu mas o deal ainda nao apareceu -> `AGUARDANDO_PROTECAO`
            tambem: "nao sei" nunca autoriza um preco (item 1.6).

        NAO cobre `FORCED_FLATTEN`/`MANUAL`/`SIGNAL`: para esses nao existe
        ordem registrada na corretora, e o fechamento do fim do pregao
        continua sendo `exit_market` -- e' ele que garante que a posicao
        morre no dia mesmo que nenhum nivel seja tocado."""
        real = self._read_position()
        if real is not None:
            # SO' espera se a protecao REALMENTE estiver registrada. Esperar
            # por um nivel que a corretora nao tem deixaria a posicao NUA
            # esperando para sempre -- e' exatamente o estado do incidente de
            # 2026-08-28 (posicao com sl=0.0/tp=0.0 por HORAS, atravessando 3
            # reinicios). `_ensure_protecao` tenta registrar a cada passo e
            # grita quando nao consegue; aqui e' a segunda linha: sem nivel
            # registrado, fecha a mercado, que e' pior preco mas e' fechado.
            nivel = (real.get("tp") if reason == IntradayExitReason.TARGET
                     else real.get("sl"))
            if float(nivel or 0.0) > 0.0:
                raise BrokerExecutionError(
                    f"{reason.value} de {self.symbol}: a corretora ainda reporta a "
                    f"posicao aberta ({real.get('quantity')} @ {real.get('price')}, "
                    f"sl={real.get('sl')} tp={real.get('tp')}). Quem fecha e' a "
                    "protecao registrada, no nivel pedido -- nao mando ordem a "
                    "mercado por cima (ordem do dono, 2026-09-08). Reavalio na "
                    "proxima barra.",
                    kind=BrokerExecutionError.AGUARDANDO_PROTECAO,
                )
            self.protecao_ausente_no_fechamento = (reason.value, self.symbol)
            return self.exit_market(position, ts, reason)
        resolvido = self._resolve_exit_from_history()
        if resolvido is not None:
            self.last_exit_order = None
            return resolvido
        raise BrokerExecutionError(
            f"{reason.value} de {self.symbol}: a corretora nao reporta mais a "
            "posicao, mas o historico de deals ainda nao confirma o preco real "
            "da saida -- nao vou aproximar pelo nivel teorico. Reavalio na "
            "proxima barra.",
            kind=BrokerExecutionError.AGUARDANDO_PROTECAO,
        )

    def exit_market(self, position, ts: pd.Timestamp, reason: IntradayExitReason) -> dict:
        """Fecha a posicao A MERCADO e devolve `{"price", "order"}` -- o
        preco que a corretora de fato executou.

        A mercado inclusive no alvo: uma saida por ordem-limite poderia nao
        preencher e deixar a posicao aberta contra o proprio stop. Ver o
        comentario em `IntradaySessionMachine._close_position`.

        Gap (a) fechado depois do incidente REAL de 2026-08-28 (slot
        `dt-wdo_grid_reload_maker-wdo@-live`, ~24 recusas seguidas com
        `retcode=10006 [MG51] Para abrir novas posicoes`): antes deste
        metodo mandava a ordem de fechamento direto via `broker.place()`
        (que monta `TRADE_ACTION_DEAL` SEM dizer qual posicao esta sendo
        abatida) -- com margem esgotada, a corretora tratava a "venda" como
        ABERTURA nova e recusava. Agora o ticket vem SEMPRE de uma leitura
        FRESCA da posicao real (`_read_position()`, nunca de um numero
        guardado em memoria) e vai para `broker.close_position()`, o
        caminho dedicado que leva `"position"` no request."""
        real = self._read_position()
        if real is None:
            # `None` aqui e' a corretora CONFIRMANDO que nao ha posicao (ver
            # `_read_position`: consulta que falha levanta, nunca devolve
            # `None`). Antes desta distincao existir, um terminal fora do ar
            # caia neste mesmo ramo e o robo registrava uma saida inventada
            # para uma posicao que continuava aberta -- e, pior, ficava sem
            # posicao na maquina, o que desarmava o freio duro.
            #
            # A posicao pode ter sido fechada pela PROPRIA protecao SL/TP
            # registrada na corretora (atomica no request de abertura, ver
            # `MT5Broker.place_pending`; ou pelo reforco `set_protection`)
            # alguns instantes antes deste passo -- corrida legitima entre
            # "a maquina decidiu fechar no fechamento desta barra" e "a
            # corretora ja tinha fechado no MESMO nivel" -- OU (gap medido ao
            # vivo em 2026-09-04, slot `dt-wdo_grid_reload_maker-wdo@-live`)
            # uma tentativa NOSSA anterior de fechamento pareceu RECUSADA
            # (`retcode=DONE` sem `price`/`deal`, ver `MT5Broker._send`) mas
            # na verdade EXECUTOU: o fechamento real saiu a 5151,5000
            # (-R$5,00), e a versao antiga deste metodo gravava o ALVO
            # teorico (5152,5000, +R$4,50) como se fosse o preco de
            # execucao -- erro de R$9,50 num trade so', na direcao
            # FAVORAVEL, que o painel nunca denunciaria por conta propria.
            #
            # NUNCA MAIS aproxima pelo nivel teorico (stop/alvo) nem pelo
            # ultimo preco negociado: preco/resultado de um fechamento SO'
            # pode vir de um deal CONFIRMADO no historico da corretora (ver
            # `MT5Broker.deals_for_position`, via `_resolve_exit_from_
            # history`). Sem esse deal, a resposta certa e' "ainda nao sei"
            # -- levanta `FECHAMENTO_RECUSADO` (a posicao continua aberta NA
            # MAQUINA, tenta de novo na proxima barra) em vez de inventar
            # QUALQUER preco.
            resolvido = self._resolve_exit_from_history()
            if resolvido is not None:
                self.last_exit_order = None
                return resolvido
            raise BrokerExecutionError(
                f"fechamento ({reason.value}) de {self.symbol}: a corretora nao "
                f"reporta posicao aberta para este magic, e o historico de deals "
                "ainda nao confirma a saida real -- nao vou aproximar pelo nivel "
                f"teorico nem pelo ultimo preco negociado. A maquina continua com "
                f"{position.quantity} {position.side} para fechar; tento de novo na "
                "proxima barra.",
                kind=BrokerExecutionError.FECHAMENTO_RECUSADO,
            )
        if real["side"] != position.side:
            raise BrokerExecutionError(
                f"a corretora reporta posicao {real['side']} em {self.symbol} "
                f"({real['quantity']} acoes @ {real['price']:.4f}) enquanto a maquina "
                f"tem uma posicao {position.side} para fechar. Nao vou fechar as "
                "cegas: confira o terminal antes de religar este slot."
            )

        # NUNCA fecha mais do que a corretora diz que existe. A maquina so'
        # decrementa `position.quantity` DEPOIS que `exit_market` volta com
        # sucesso (`machine._close_position`), entao um fechamento que
        # preencheu PELA METADE deixava a maquina achando que ainda tem o
        # total: na tentativa seguinte ela mandaria fechar o tamanho INTEIRO
        # contra a posicao que sobrou -- e numa conta NETTING uma ordem maior
        # que a posicao nao "fecha demais", ela INVERTE o lado. O robo sairia
        # de uma posicao comprada pela metade para uma vendida, sem stop, sem
        # alvo e sem ninguem ter pedido. `min()` com o numero REAL e' o que
        # torna a repeticao segura.
        qtd_real = int(real.get("quantity") or 0)
        qtd_fechar = min(int(position.quantity), qtd_real) if qtd_real > 0 else 0
        if qtd_fechar <= 0:
            raise BrokerExecutionError(
                f"fechamento ({reason.value}) de {self.symbol}: a corretora reporta "
                f"posicao de {qtd_real} enquanto a maquina tem {position.quantity} "
                f"{position.side} -- nao ha quantidade valida para fechar. Confira o "
                "terminal antes de religar este slot."
            )
        fechamento = Order(
            ticker=self.symbol,
            side=OrderSide.SELL if position.side == "long" else OrderSide.BUY,
            quantity=qtd_fechar,
            order_type=OrderType.MARKET,
            sent_at=ts.to_pydatetime(),
        )
        ticket = real.get("ticket")
        fechar_com_ticket = getattr(self.broker, "close_position", None)
        if ticket is not None and fechar_com_ticket is not None:
            executada = fechar_com_ticket(fechamento, ticket)
        else:
            # Sem ticket (posicao sem o campo, extremamente improvavel em
            # producao -- `MT5Broker.open_position` sempre devolve `ticket`)
            # ou sem `close_position` no broker (dublê de teste antigo):
            # degrada para o `place()` generico, o comportamento de antes
            # do gap (a). `MT5Broker` de producao SEMPRE tem os dois.
            executada = self.broker.place(fechamento)
        if executada.status == OrderStatus.REJECTED:
            raise BrokerExecutionError(
                f"corretora recusou o fechamento ({reason.value}) de {qtd_fechar} "
                f"{self.symbol}: {executada.note}. A posicao continua ABERTA na "
                "corretora e na maquina -- vou tentar de novo na proxima barra.",
                # O caso CENTRAL do gap (f): posicao continua exatamente como
                # estava, so' a ordem de fechamento nao passou -- seguro pra
                # `IntradayLiveRuntime` capturar, contar e tentar de novo.
                kind=BrokerExecutionError.FECHAMENTO_RECUSADO,
            )
        if executada.status == OrderStatus.PARTIAL:
            raise BrokerExecutionError(
                f"fechamento ({reason.value}) de {self.symbol} preencheu so "
                f"{executada.filled_qty} de {qtd_fechar} acoes. Sobrou posicao "
                "aberta na corretora; a maquina segue com a posicao inteira e tenta "
                "fechar o resto na proxima barra -- e a proxima tentativa vai ser "
                "capada pelo que a corretora reportar entao, nunca pelo total antigo.",
                kind=BrokerExecutionError.FECHAMENTO_RECUSADO,
            )
        if not executada.avg_price:
            raise BrokerExecutionError(
                f"fechamento de {self.symbol} voltou sem preco medio da corretora "
                f"(status={executada.status.value}, note={executada.note!r}) -- sem "
                "esse numero o P&L do trade seria inventado. Gap (b): retcode de "
                "sucesso sem preco/deal real -- MT5Broker._send ja deveria ter "
                "recusado isto como REJECTED; esta checagem e' a segunda linha de "
                "defesa.",
                kind=BrokerExecutionError.FECHAMENTO_RECUSADO,
            )
        self.last_exit_order = executada
        return {"price": float(executada.avg_price), "order": executada}

    def _resolve_exit_from_history(self) -> Optional[dict]:
        """A posicao sumiu da corretora antes de NOS mandarmos (ou de
        confirmarmos) o fechamento -- ver o comentario longo em
        `exit_market`. So' devolve algo quando o HISTORICO CONFIRMA o deal
        de saida de verdade (preco da corretora, nunca nivel teorico).
        `None` = ainda nao deu para confirmar (broker sem os metodos novos,
        consulta que falhou, ou o deal ainda nao apareceu no historico) --
        quem chama (`exit_market`) trata como recusa de fechamento e tenta
        de novo na proxima barra (item 1.6 de LICOES_DE_PRODUCAO.md: "nao
        sei" nunca autoriza um resultado).

        Usa `self.last_entry_ref` -- o ticket/position_id que `limit_fill`
        leu da corretora no fill de ENTRADA desta mesma posicao -- para
        procurar os deals dela no historico (`MT5Broker.deals_for_
        position`). Sem esse ticket (posicao herdada de um jeito que nunca
        passou por `limit_fill`), nao ha como saber QUAL posicao procurar;
        devolve `None`, mesma politica de 'nao sei'."""
        if not self.last_entry_ref:
            return None
        consulta = getattr(self.broker, "deals_for_position", None)
        if consulta is None:
            return None
        resposta = consulta(self.last_entry_ref)
        if not resposta.get("ok"):
            return None
        saidas = [d for d in (resposta.get("deals") or []) if d.get("entry") == 1]
        if not saidas:
            return None
        ultima = max(saidas, key=lambda d: d.get("time") or 0)
        preco = float(ultima.get("price") or 0.0)
        if preco <= 0.0:
            return None
        return {"price": preco, "order": None}

    # ---------- tempo de vida da posicao (OBSERVACAO, nao decisao) ---------

    def vida_da_posicao_ms(self) -> Optional[int]:
        """Quanto tempo a ultima posicao ficou ABERTA, em milissegundos, pelo
        relogio da CORRETORA (`time_msc` dos deals) -- ou `None` quando nao
        da' para saber.

        POR QUE ESTE METODO EXISTE (medido, 2026-09-08, slot
        `dt-wdo_grid_reload_maker-wdo@-live`): das 22 posicoes reais do
        pregao, **11 abriram e fecharam em menos de 1 segundo** -- 58 ms, 62,
        64, 66, 100, 109, 127, 288, 319, 342 e 561 -- e somaram **-R$40,50 dos
        -R$116,00** do prejuizo (34,9%). Todas entraram no diario como
        `exit_reason="target"`. Uma posicao de 58 ms nao expressou tese
        nenhuma sobre preco: e' round-trip de EXECUCAO, e misturada com trade
        de verdade ela derruba a taxa de acerto do pregao de 54,5% (6/11 dos
        trades reais) para 31,8% (7/22) sem que nada no diario diga por que.
        Item 4.16 de LICOES_DE_PRODUCAO.md.

        POR QUE NAO DA' PARA USAR OS RELOGIOS QUE JA' TINHAMOS -- os dois
        foram reconstruidos contra estes mesmos 11 casos:
          - carimbo de TICK (`IntradayTrade.entry_ts/exit_ts`): acha 4 dos 11
            (36%) e inventa 1 falso positivo, porque anda com a defasagem do
            feed (24 min naquele pregao) -- um round-trip de 62 ms aparece
            como 51,5 s; deixa passar -R$28,50;
          - relogio de PAREDE do supervisor (`_on_opened` -> `_on_closed`):
            acha 1 dos 11 (9%), porque abertura e fechamento caem no MESMO
            passo do poll e a conta da' ~0 -- ou, quando o poll trava, da'
            3.184 s para uma posicao que viveu 456 s.

        OBSERVACAO, NUNCA DECISAO (AGENTS.md regra 6): este numero e'
        carimbo da corretora copiado para o diario. Ele nao filtra entrada,
        nao muda tamanho, nao interrompe nada -- se mudasse, o backtest (que
        nao tem deal de corretora) deixaria de descrever a producao. Por isso
        tambem **nao existe alarme automatico em cima dele**: o piso do que
        conta como round-trip e' decisao de estrategia/dono, e um alarme
        montado sobre um relogio ainda nao validado ao vivo foi exatamente o
        erro anterior (o freio de cadencia que quebrou uma reconciliacao
        legitima). Primeiro o diario registra; depois se decide o piso.

        `None` = "nao sei" e nunca "durou zero": sem `last_entry_ref` (posicao
        herdada por restart, que nunca passou por `limit_fill`), broker sem
        `deals_for_position` (dublê antigo / `PaperBroker`), consulta que
        falhou (`ok=False`, item 1.6), deals sem `time_msc`, ou posicao que
        ainda nao tem os dois lados no historico. Nunca levanta: perder um
        campo de diagnostico nao pode derrubar o fechamento de uma posicao,
        que e' o caminho que mexe com dinheiro."""
        try:
            if not self.last_entry_ref:
                return None
            consulta = getattr(self.broker, "deals_for_position", None)
            if consulta is None:
                return None
            resposta = consulta(self.last_entry_ref)
            if not resposta.get("ok"):
                return None
            deals = resposta.get("deals") or []
            entradas = [d.get("time_msc") for d in deals if d.get("entry") == 0]
            saidas = [d.get("time_msc") for d in deals if d.get("entry") == 1]
            entradas = [t for t in entradas if t is not None]
            saidas = [t for t in saidas if t is not None]
            if not entradas or not saidas:
                return None
            # min da ENTRADA e max da SAIDA: uma posicao pode ter sido montada
            # em fatias (`EnterLimit.split_quantities`) e desmontada em outras
            # -- a vida dela vai do PRIMEIRO deal que a abriu ao ULTIMO que a
            # zerou, nao do par que por acaso veio primeiro na lista.
            vida = int(max(saidas)) - int(min(entradas))
            return vida if vida >= 0 else None
        except Exception:
            # Mesmo motivo de `_exit_position_ticket`: a garantia de que a
            # consulta nao levanta mora em OUTRA classe (`MT5Broker`), e um
            # `Broker` novo poderia trazer excecao nova para um caminho que e'
            # so' diagnostico. Sem o numero o diario fica como estava antes
            # deste campo existir -- nunca pior.
            return None

    # ---------- leitura -----------------------------------------------------

    def _read_position(self) -> Optional[dict]:
        """Posicao da corretora para este simbolo/magic, ou `None` -- e aqui
        `None` significa SO' "a corretora respondeu que nao ha posicao".

        Toda falha de CONSULTA vira excecao (`ok=False` em
        `Broker.position_state`), nunca `None`. Antes so' a conexao era
        conferida antes da leitura, e isso deixava passar todo o resto:
        `positions_get` devolvendo `None` por erro, um `except Exception`
        interno, o pacote ausente -- tudo virava "nao ha posicao". Quem le
        isto decide MANDAR ORDEM (re-armar entrada, registrar saida), entao
        confundir "nao sei" com "nao ha" e' o caminho mais curto para operar
        sobre estado imaginario. Ver a secao "Falha de CONSULTA nunca vira
        'nao preencheu'" no topo do modulo."""
        if not self.broker.connect():
            raise BrokerExecutionError(
                "sem conexao com o terminal MT5 -- nao da para saber se a ordem "
                "preencheu. Nao vou presumir que nao preencheu."
            )
        estado = self.broker.position_state(self.symbol)
        if not estado.get("ok"):
            raise BrokerExecutionError(
                f"nao consegui LER a posicao de {self.symbol} na corretora: "
                f"{estado.get('note', '')}. Isto e' 'nao sei', nunca 'esta zerado' -- "
                "nao vou decidir nada em cima de uma consulta que falhou."
            )
        return estado.get("position")
