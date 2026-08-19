"""Tradutor `Order` <-> formato de request do pacote `MetaTrader5`.

Este modulo implementa a classe de producao do port `Broker` (ver docstring
de `live/broker.py`): `MT5Broker` fala com um terminal MT5 ja aberto na
mesma maquina via o pacote pip `MetaTrader5` (`PaperBroker` e um dublê de
teste, ver `tests/doubles.py`). O trabalho aqui e 100% TRADUCAO de formato
de dado e tratamento de erro — nenhuma regra de decisao mora aqui (mesma
regra de fronteira de `core/live_models.py`): `MT5Broker` nao decide
comprar nem vender, so pega a `Order` que o runtime ja decidiu enviar e
traduz para o dicionario `request` que `mt5.order_send()` espera, depois
traduz a resposta de volta para os campos da `Order`.

Import do pacote `MetaTrader5` e SEMPRE local (dentro de metodo), nunca no
topo do arquivo. Motivo pratico, nao estetico: o pacote real so funciona
colado a um terminal MT5 rodando na mesma maquina (Windows, em geral), entao
nem todo ambiente que importa este arquivo tem — ou deveria precisar ter —
esse pacote instalado (testes deste modulo, por exemplo, rodam com um modulo
`MetaTrader5` FALSO injetado em `sys.modules`, e o pacote real nem esta
instalado). Se o import estivesse no topo, `import live.broker_mt5` quebraria
sozinho em qualquer maquina sem o terminal — inclusive em CI. Mesmo padrao de
`live/feed.py` (`YFinanceFeed`) com `import yfinance`.

Quatro decisoes de traducao que NAO tem valor universal — sao parametros do
construtor de proposito, porque variam conforme como cada corretora cadastra
cada simbolo no terminal MT5 dela. Quem for apontar esta classe para um
terminal MT5 real e mexer com volume relevante PRECISA conferir estes valores
no `symbol_info` do proprio terminal antes de operar — nada aqui assume um
numero universal:

  1. `shares_per_lot` — a relacao entre "acao" (o que `Order.quantity` conta)
     e "volume" (o que o MT5 entende, em lotes). Pode ser 1:1 ou 1:100
     dependendo de como o simbolo foi cadastrado pela corretora. O calculo e
     `volume = quantity / shares_per_lot`, sempre arredondado para BAIXO ate
     o multiplo de `symbol_info.volume_step` mais proximo (nunca para cima —
     gerar uma ordem MAIOR que a pedida e um bug de risco, nao um
     arredondamento inofensivo), e validado contra `volume_min`/`volume_max`.
     Se o resultado for 0 (pedido menor que o lote minimo do simbolo), a
     ordem e traduzida em `OrderStatus.REJECTED` com o motivo em `order.note`
     — a funcao NUNCA chega a montar (nem enviar) um `request` com
     `volume=0`.
  2. `symbol_map` — o resto do sistema usa tickers estilo `"WEGE3.SA"`; o
     terminal MT5 pode ter cadastrado o simbolo com outro nome (com ou sem
     sufixo, com um prefixo de corretora, etc). `symbol_for(ticker)` aplica o
     override de `symbol_map` quando existe; por padrao so remove o sufixo
     `.SA`.
  3. `filling_type` — o modo de preenchimento (`ORDER_FILLING_IOC` etc) que a
     corretora aceita para o simbolo varia por corretora/conta. Resolvido
     para `mt5.ORDER_FILLING_IOC` (o mais permissivo/comum) apenas no momento
     de montar o `request`, porque a constante vem do modulo `MetaTrader5`
     (real ou mockado) e esse modulo so e importado dentro do metodo.
  4. Comissao — o MT5 nao devolve custo no proprio `order_send`; e preciso
     consultar `mt5.history_deals_get(ticket=result.deal)` depois do fill e
     somar `commission + swap + fee` do primeiro deal encontrado. Qualquer
     falha nessa consulta (excecao, lista vazia, deal sem os campos) cai para
     `fees=0.0` sem propagar erro — um erro ao CONSULTAR custo depois de um
     fill que ja aconteceu de verdade na corretora nao pode fazer a `Order`
     parecer que falhou.

Conexao (`connect()`/`is_connected()`) e idempotente: `place()` so chama
`mt5.initialize()` se ainda nao estiver conectado. Qualquer falha de conexao
vira `OrderStatus.REJECTED` com `mt5.last_error()` no `note` — nunca uma
excecao correndo solta, pelo mesmo motivo do padrao de `on_error` de
`YFinanceFeed`: uma corretora fora do ar (ou um terminal fechado) e uma falha
esperada e temporaria, nao motivo para derrubar o runtime inteiro.
"""
from __future__ import annotations

import math
from typing import Optional

from core.live_models import Order, OrderSide, OrderStatus
from live.broker import Broker


class MT5Broker(Broker):
    """Broker real via terminal MT5 ja aberto na maquina (pacote `MetaTrader5`).

    `poll()` e sincrono como `PaperBroker`: `mt5.order_send()` ja resolve o
    fill (ou a rejeicao) na hora, entao nao ha nada assincrono para consultar
    depois — `poll()` so devolve a `Order` como esta.
    """

    name = "mt5"
    mode = "mt5"

    def __init__(
        self,
        magic: int = 20260817,
        shares_per_lot: float = 1.0,
        deviation: int = 20,
        filling_type: Optional[int] = None,
        symbol_map: Optional[dict[str, str]] = None,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        path: Optional[str] = None,
    ) -> None:
        self._magic = magic
        # AJUSTAVEL conforme a config do simbolo na corretora — o chamador
        # deve conferir isso (symbol_info do terminal) antes de operar com
        # volume relevante. Ver ponto 1 da docstring do modulo.
        self._shares_per_lot = shares_per_lot
        self._deviation = deviation
        self._filling_type = filling_type
        self._symbol_map = dict(symbol_map) if symbol_map else {}
        # Credenciais de LOGIN na corretora (opcionais): sem elas, `connect()`
        # so anexa a um terminal MT5 que um humano ja abriu e logou na mesma
        # maquina. Com elas, `mt5.initialize()` faz o login sozinho — preciso
        # para operar sem depender de alguem manter o terminal logado (ex.:
        # o loop rodando como servico). Resolvidas de variavel de ambiente
        # pelo chamador (`scripts/run_live.py`/`dashboard/live_control.py`),
        # nunca de argv — mesma regra do `_build_notifier`.
        self._login = login
        self._password = password
        self._server = server
        self._path = path
        self._connected = False

    # ---------- mapeamento de simbolo --------------------------------------

    def symbol_for(self, ticker: str) -> str:
        """Ticker interno (`"WEGE3.SA"`) -> nome do simbolo no terminal MT5.

        Default: remove o sufixo `.SA` (convencao B3 do resto do sistema).
        `symbol_map` (passado no construtor) tem prioridade sobre o default —
        e o jeito de lidar com corretoras que cadastram o simbolo com outro
        nome (prefixo, sufixo diferente, etc)."""
        if ticker in self._symbol_map:
            return self._symbol_map[ticker]
        if ticker.endswith(".SA"):
            return ticker[: -len(".SA")]
        return ticker

    # ---------- conexao ------------------------------------------------

    def connect(self) -> bool:
        """Inicializa a conexao com o terminal MT5, de forma IDEMPOTENTE: se
        ja estamos conectados, nao chama `mt5.initialize()` de novo — chamar
        de novo sem necessidade e, na pratica de alguns terminais, um jeito
        de perder estado de ordens em voo a toa.

        Sem `login`/`password`/`server` no construtor, so anexa a um
        terminal ja aberto e logado (`mt5.initialize()` puro). Com eles,
        pede pro proprio `initialize()` fazer o login — necessario quando
        nao ha um humano ali para manter o terminal logado."""
        if self._connected:
            return True
        import MetaTrader5 as mt5  # lazy: ver docstring do modulo

        kwargs = {}
        if self._path:
            kwargs["path"] = self._path
        if self._login is not None:
            kwargs["login"] = self._login
            kwargs["password"] = self._password
            kwargs["server"] = self._server

        try:
            ok = bool(mt5.initialize(**kwargs))
        except Exception:
            ok = False
        self._connected = ok
        return ok

    def is_connected(self) -> bool:
        return self._connected

    def _last_error(self, mt5) -> tuple:
        try:
            return mt5.last_error()
        except Exception:
            return (None, "desconhecido")

    # ---------- volume ---------------------------------------------------

    def _resolve_volume(self, quantity: int, symbol_info) -> float:
        """`Order.quantity` e em ACOES; MT5 quer `volume` em LOTES. Ver ponto
        1 da docstring do modulo: a razao acao/lote e `shares_per_lot`, e o
        resultado e sempre arredondado para BAIXO ate o multiplo de
        `volume_step` mais proximo — nunca para cima, para nunca gerar uma
        ordem maior do que a que foi pedida."""
        step = getattr(symbol_info, "volume_step", None) or 1.0
        vol_min = getattr(symbol_info, "volume_min", 0.0) or 0.0
        vol_max = getattr(symbol_info, "volume_max", None)

        raw = quantity / self._shares_per_lot
        if step > 0:
            # +1e-9 so para nao perder um passo inteiro por ruido de ponto
            # flutuante (ex.: 0.99999999 vira 0 passos em vez de 1) — nunca
            # o suficiente para arredondar um passo A MAIS.
            steps = math.floor(raw / step + 1e-9)
            volume = steps * step
        else:
            volume = raw
        volume = round(volume, 8)  # limpa ruido tipo 0.6000000000000001

        if volume < vol_min:
            return 0.0
        if vol_max is not None and volume > vol_max:
            volume = vol_max
        return volume

    # ---------- execucao ---------------------------------------------------

    def place(self, order: Order) -> Order:
        """Traduz `order` para um `request` do MT5, envia, traduz a resposta
        de volta. Nenhuma excecao de biblioteca externa (import ausente,
        terminal fechado, resposta em formato inesperado) escapa daqui — vira
        `OrderStatus.REJECTED` com o motivo em `order.note`, igual ao padrao
        de `on_error` de `YFinanceFeed` em `live/feed.py`."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception as exc:  # pragma: no cover - ambiente sem o pacote
            order.status = OrderStatus.REJECTED
            order.note = f"pacote MetaTrader5 indisponivel: {exc}"
            return order

        try:
            if not self.connect():
                code, desc = self._last_error(mt5)
                order.status = OrderStatus.REJECTED
                order.note = (
                    f"falha ao conectar ao terminal MT5 "
                    f"(last_error={code}: {desc})"
                )
                return order
            return self._send(mt5, order)
        except Exception as exc:
            # Qualquer coisa inesperada (campo ausente no fake/real, terminal
            # que caiu no meio, etc) vira ordem REJECTED, nunca uma excecao
            # correndo solta ate derrubar o runtime.
            order.status = OrderStatus.REJECTED
            order.note = f"erro inesperado na traducao para MT5: {exc}"
            return order

    def _send(self, mt5, order: Order) -> Order:
        symbol = self.symbol_for(order.ticker)
        mt5.symbol_select(symbol, True)

        info = mt5.symbol_info(symbol)
        if info is None:
            order.status = OrderStatus.REJECTED
            order.note = f"simbolo {symbol} nao encontrado no terminal MT5"
            return order

        volume = self._resolve_volume(order.quantity, info)
        if volume <= 0:
            order.status = OrderStatus.REJECTED
            order.note = (
                f"quantidade {order.quantity} acoes (shares_per_lot="
                f"{self._shares_per_lot}) resulta em volume 0 apos "
                f"arredondar para o volume_step de {symbol} "
                f"({getattr(info, 'volume_step', '?')}) — abaixo do lote "
                f"minimo ({getattr(info, 'volume_min', '?')}); ordem nao "
                f"enviada ao MT5"
            )
            return order

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            order.status = OrderStatus.REJECTED
            order.note = f"sem cotacao (tick) para {symbol} no terminal MT5"
            return order

        is_buy = order.side == OrderSide.BUY
        # compra executa no ask, venda no bid — o preco que a corretora de
        # fato cobraria/pagaria num fill a mercado.
        price = tick.ask if is_buy else tick.bid
        order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        # resolvido aqui (nao no __init__) porque a constante so existe depois
        # do import lazy do modulo — ver ponto 3 da docstring do modulo.
        filling = (
            self._filling_type if self._filling_type is not None
            else mt5.ORDER_FILLING_IOC
        )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": self._deviation,
            "magic": self._magic,
            "comment": "meta-live",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }

        result = mt5.order_send(request)
        if result is None:
            code, desc = self._last_error(mt5)
            order.status = OrderStatus.REJECTED
            order.note = f"order_send devolveu None (last_error={code}: {desc})"
            return order

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            order.status = OrderStatus.REJECTED
            order.note = (
                f"MT5 recusou a ordem (retcode={result.retcode}): "
                f"{getattr(result, 'comment', '')}"
            )
            return order

        filled_volume = getattr(result, "volume", volume)
        order.filled_qty = int(round(filled_volume * self._shares_per_lot))
        # Fill parcial de verdade da corretora (result.volume < volume pedido)
        # vira PARTIAL, nunca FILLED. `Order.is_terminal` ja exclui PARTIAL
        # corretamente (FEAT-004, item 4.4b).
        order.status = (
            OrderStatus.FILLED if order.filled_qty >= order.quantity else OrderStatus.PARTIAL
        )
        order.avg_price = float(result.price)
        order.broker_ref = str(getattr(result, "order", None) or "")
        order.fees = self._resolve_fees(mt5, result)
        order.note = (
            f"fill @ {order.avg_price:.4f} via MT5 "
            f"(deal={getattr(result, 'deal', None)}, "
            f"comment={getattr(result, 'comment', '')})"
        )
        return order

    def _resolve_fees(self, mt5, result) -> float:
        """Soma `commission + swap + fee` do primeiro deal reportado pelo
        historico. Ver ponto 4 da docstring do modulo: qualquer falha aqui
        (excecao, lista vazia, ticket ausente) cai para `fees=0.0` sem
        propagar — o fill em si ja aconteceu de verdade, um erro ao consultar
        o CUSTO dele depois nao pode desfazer ou mascarar esse fill."""
        ticket = getattr(result, "deal", None)
        if not ticket:
            return 0.0
        try:
            deals = mt5.history_deals_get(ticket=ticket)
        except Exception:
            return 0.0
        if not deals:
            return 0.0
        deal = deals[0]
        try:
            commission = float(getattr(deal, "commission", 0.0) or 0.0)
            swap = float(getattr(deal, "swap", 0.0) or 0.0)
            fee = float(getattr(deal, "fee", 0.0) or 0.0)
            return commission + swap + fee
        except Exception:
            return 0.0

    def poll(self, order: Order) -> Order:
        """Sincrono como `PaperBroker`: `place()` (via `mt5.order_send`) ja
        resolveu o fill (ou a rejeicao) na hora — nao ha nada assincrono para
        reprocessar aqui."""
        return order

    def supports_automation(self) -> bool:
        return True

    def cash_balance(self) -> Optional[float]:
        """Saldo real de caixa reportado pelo terminal, para o runtime
        detectar deposito externo (ver `live.runtime.reconcile_broker_cash`).

        Usa `balance`, NUNCA `equity`: numa conta de acoes a vista (nao
        CFD/margem), `balance` e o caixa REALIZADO (depositos, saques,
        proventos de venda ja fechada) e exclui o P&L flutuante de posicao
        aberta — exatamente o que `AccountState.cash` representa aqui dentro
        (caixa NAO investido). `equity` misturaria isso com dinheiro que ja
        esta alocado em acoes, e faria o runtime "ver" deposito onde so
        houve valorizacao de posicao.

        Mesmo padrao de erro do resto do arquivo: falha de conexao, pacote
        ausente ou resposta inesperada viram `None`, nunca uma excecao solta
        — quem chama (`reconcile_broker_cash`) trata `None` como "esta
        corretora nao tem saldo externo para comparar agora", nao como erro.
        """
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception:
            return None
        try:
            if not self.connect():
                return None
            info = mt5.account_info()
            if info is None:
                return None
            return float(info.balance)
        except Exception:
            return None
