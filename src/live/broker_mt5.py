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
     `.SA`. `fractional_map` e um mapa SEPARADO (ticker -> simbolo do mercado
     FRACIONARIO, sufixo `"F"` na B3), so para tickers que realmente tem essa
     versao no terminal (ver `detect_fractional_symbol_map`) — `_resolve_
     execution` decide, a cada ORDEM, qual dos dois usar: lote padrao
     primeiro (na Rico e GRATUITO, 2026-08-21), fracionario (custa
     R$1,90/ordem na Rico) so quando a quantidade pedida nao fecha o lote
     padrao minimo. Sem valor universal tambem: outra corretora pode nao ter
     fracionario, ou cobrar diferente — confirmar sempre no terminal real.
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
        fractional_map: Optional[dict[str, str]] = None,
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
        # Mapa ticker -> simbolo do mercado FRACIONARIO (sufixo `"F"` na B3),
        # SO PARA quem realmente tem essa versao no terminal (ver
        # `_resolve_execution`) -- diferente de `symbol_map`, que resolve o
        # simbolo de LOTE PADRAO. Os dois convivem: `_resolve_execution`
        # decide, a cada ordem, qual dos dois usar, com base na quantidade
        # pedida (lote padrao primeiro quando a quantidade alcanca o
        # `volume_min` dele -- na Rico isso e GRATUITO contra R$1,90/ordem no
        # fracionario, 2026-08-21 -- fracionario so como alternativa para
        # quantidade que nao fecha lote padrao). Populado por quem monta o
        # broker (`dashboard/live_control.py::detect_fractional_symbol_map`),
        # nunca digitado pelo usuario.
        self._fractional_map = dict(fractional_map) if fractional_map else {}
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

    def _resolve_execution(self, mt5, order: Order):
        """Decide qual simbolo/volume usar para esta ordem: lote padrao
        (GRATUITO na Rico, 2026-08-21) quando a quantidade pedida alcanca o
        `volume_min` dele, senao o mercado FRACIONARIO (`_fractional_map`,
        custa R$1,90/ordem na Rico) quando existir para este ticker e a
        quantidade fechar volume la.

        Tenta lote padrao PRIMEIRO: se a quantidade pedida nao fecha o lote
        minimo (`_resolve_volume` devolve 0), cai pro fracionario sozinho —
        sem exigir que quem chama saiba de antemao qual dos dois vale. Uma
        quantidade que nao fecha NEM lote padrao NEM fracionario (ou fica
        abaixo do minimo dos dois, ou o ticker nao tem fracionario no
        terminal) devolve `None` -- `_send` traduz isso em `REJECTED` com um
        motivo que distingue "sem fracionario disponivel" de "fracionario
        tambem nao aceitou o volume", em vez de um so "volume 0" generico.

        Devolve `(symbol, info, volume)` ou `None`."""
        base_symbol = self.symbol_for(order.ticker)
        mt5.symbol_select(base_symbol, True)
        base_info = mt5.symbol_info(base_symbol)

        if base_info is not None:
            base_volume = self._resolve_volume(order.quantity, base_info)
            if base_volume > 0:
                return base_symbol, base_info, base_volume

        frac_symbol = self._fractional_map.get(order.ticker)
        if frac_symbol is not None:
            mt5.symbol_select(frac_symbol, True)
            frac_info = mt5.symbol_info(frac_symbol)
            if frac_info is not None:
                frac_volume = self._resolve_volume(order.quantity, frac_info)
                if frac_volume > 0:
                    return frac_symbol, frac_info, frac_volume

        return None

    def _send(self, mt5, order: Order) -> Order:
        base_symbol = self.symbol_for(order.ticker)
        resolved = self._resolve_execution(mt5, order)
        if resolved is None:
            base_info = mt5.symbol_info(base_symbol)
            if base_info is None:
                order.status = OrderStatus.REJECTED
                order.note = f"simbolo {base_symbol} nao encontrado no terminal MT5"
                return order
            frac_symbol = self._fractional_map.get(order.ticker)
            motivo_fracionario = (
                "sem mercado fracionario disponivel para este papel" if frac_symbol is None
                else f"o mercado fracionario ({frac_symbol}) tambem nao aceitou o volume"
            )
            order.status = OrderStatus.REJECTED
            order.note = (
                f"quantidade {order.quantity} acoes (shares_per_lot="
                f"{self._shares_per_lot}) resulta em volume 0 apos "
                f"arredondar para o volume_step de {base_symbol} "
                f"({getattr(base_info, 'volume_step', '?')}) — abaixo do lote "
                f"minimo ({getattr(base_info, 'volume_min', '?')}), e {motivo_fracionario}; "
                f"ordem nao enviada ao MT5"
            )
            return order

        symbol, info, volume = resolved
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
            f"fill @ {order.avg_price:.4f} via MT5 em {symbol} "
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

    # ---------- ordem-limite PENDENTE (day trade maker) --------------------
    #
    # `place()` acima manda ordem A MERCADO (`TRADE_ACTION_DEAL`): preenche na
    # hora, pagando o spread. Os tres metodos abaixo existem para o caso
    # oposto, que e' o centro do desenho da familia `gremah`: uma ordem-limite
    # PARADA no nivel, esperando o preco vir ate ela (maker, captura o spread
    # em vez de paga-lo). Sao um ciclo de vida diferente -- a ordem fica viva
    # entre chamadas, pode ser cancelada, e o fill chega DEPOIS -- entao nao
    # cabem em `place()`/`poll()`, que assumem resposta imediata.

    def place_pending(self, order: Order) -> Order:
        """Registra uma ordem-limite PENDENTE no terminal e devolve `order`
        com `broker_ref` = ticket da ordem pendente (nao um fill).

        `status` vira `SENT` no sucesso -- nunca `FILLED`: uma ordem-limite
        recem-registrada NAO executou nada ainda, e tratar registro como fill
        e' exatamente o erro que este metodo existe para nao cometer. Quem
        descobre o fill e' `open_position()`, contra o que a corretora de fato
        reporta.

        `type_time=ORDER_TIME_DAY` (nao GTC como em `place`): day trade nunca
        carrega nada para o dia seguinte, e uma pendente esquecida viva de um
        pregao para o outro dispararia uma entrada que nenhum robo decidiu.
        O robo tambem cancela explicitamente (`cancel`), mas o terminal
        expirando sozinho e' a segunda linha de defesa que sobrevive ao
        processo morrer."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception as exc:  # pragma: no cover - ambiente sem o pacote
            order.status = OrderStatus.REJECTED
            order.note = f"pacote MetaTrader5 indisponivel: {exc}"
            return order

        if order.limit_price is None:
            order.status = OrderStatus.REJECTED
            order.note = "place_pending exige limit_price -- ordem sem nivel nao e' limite"
            return order

        try:
            if not self.connect():
                code, desc = self._last_error(mt5)
                order.status = OrderStatus.REJECTED
                order.note = f"falha ao conectar ao terminal MT5 (last_error={code}: {desc})"
                return order

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
                    f"{self._shares_per_lot}) resulta em volume 0 no lote padrao de "
                    f"{symbol} (volume_min={getattr(info, 'volume_min', '?')}) -- "
                    "day trade nao usa mercado fracionario, ordem nao enviada"
                )
                return order

            is_buy = order.side == OrderSide.BUY
            request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": symbol,
                "volume": volume,
                "type": mt5.ORDER_TYPE_BUY_LIMIT if is_buy else mt5.ORDER_TYPE_SELL_LIMIT,
                "price": float(order.limit_price),
                "magic": self._magic,
                "comment": "meta-live",
                "type_time": mt5.ORDER_TIME_DAY,
                "type_filling": (self._filling_type if self._filling_type is not None
                                 else mt5.ORDER_FILLING_RETURN),
            }
            result = mt5.order_send(request)
            if result is None:
                code, desc = self._last_error(mt5)
                order.status = OrderStatus.REJECTED
                order.note = f"order_send (pendente) devolveu None (last_error={code}: {desc})"
                return order
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                order.status = OrderStatus.REJECTED
                order.note = (
                    f"MT5 recusou a ordem-limite pendente (retcode={result.retcode}): "
                    f"{getattr(result, 'comment', '')}"
                )
                return order

            order.status = OrderStatus.SENT
            order.broker_ref = str(getattr(result, "order", None) or "")
            order.note = (
                f"ordem-limite pendente registrada em {symbol} @ "
                f"{order.limit_price:.4f} (ticket={order.broker_ref})"
            )
            return order
        except Exception as exc:
            order.status = OrderStatus.REJECTED
            order.note = f"erro inesperado ao registrar ordem pendente no MT5: {exc}"
            return order

    def cancel(self, order: Order) -> Order:
        """Remove do terminal a ordem-limite pendente de `order.broker_ref`.

        Sem `broker_ref` (nunca chegou a ser registrada) cai no default do
        port (`Broker.cancel`, so marca `CANCELLED` localmente). Uma ordem que
        o terminal ja nao tem mais -- porque preencheu, expirou ou foi
        cancelada na mao -- NAO e' erro: o objetivo ("nao existe mais pendente
        neste ticket") ja esta cumprido, entao vira `CANCELLED` com o motivo
        na nota, para nao virar um retry infinito a cada barra."""
        if not order.broker_ref:
            return super().cancel(order)
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception as exc:  # pragma: no cover - ambiente sem o pacote
            order.note = f"pacote MetaTrader5 indisponivel ao cancelar: {exc}"
            return order

        try:
            if not self.connect():
                code, desc = self._last_error(mt5)
                order.note = f"falha ao conectar para cancelar (last_error={code}: {desc})"
                return order
            result = mt5.order_send({
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": int(order.broker_ref),
            })
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                order.status = OrderStatus.CANCELLED
                order.note = f"ordem pendente {order.broker_ref} removida do terminal"
                return order
            order.status = OrderStatus.CANCELLED
            order.note = (
                f"ordem pendente {order.broker_ref} ja nao estava viva no terminal "
                f"(retcode={getattr(result, 'retcode', None)}: "
                f"{getattr(result, 'comment', '')}) -- nada a remover"
            )
            return order
        except Exception as exc:
            order.note = f"erro inesperado ao cancelar ordem pendente: {exc}"
            return order

    def open_position(self, ticker: str) -> Optional[dict]:
        """O que a CORRETORA diz que esta aberto neste papel para ESTE robo
        (`magic`) -- a fonte de verdade de "a ordem-limite preencheu ou nao".

        Devolve `{"side", "price", "quantity"}` ou `None` (nada aberto).
        `side` e' `"long"`/`"short"`; `quantity` e' em ACOES (`volume *
        shares_per_lot`), na mesma unidade de `Order.quantity`.

        Por que ler posicao e nao o ticket da ordem: numa conta NETTING o
        terminal consolida tudo do simbolo numa posicao so, e e' esse numero
        (preco medio e volume REAIS) que representa o que se tem de verdade.
        Perguntar "o ticket X preencheu?" responderia sobre uma ordem; esta
        pergunta responde sobre o dinheiro.

        Filtra por `magic` porque a conta e' NETTING e compartilhada entre os
        dois slots -- sem o filtro, um robo enxergaria a posicao do outro como
        sua. Qualquer falha (terminal fechado, resposta inesperada) devolve
        `None`, e quem chama trata isso como "nao consegui confirmar agora",
        NUNCA como "esta zerado" (ver `live/intraday_execution.py`)."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception:  # pragma: no cover - ambiente sem o pacote
            return None
        try:
            if not self.connect():
                return None
            symbol = self.symbol_for(ticker)
            posicoes = mt5.positions_get(symbol=symbol)
            if not posicoes:
                return None
            minhas = [p for p in posicoes if getattr(p, "magic", None) == self._magic]
            if not minhas:
                return None
            p = minhas[0]
            volume = float(getattr(p, "volume", 0.0) or 0.0)
            if volume <= 0:
                return None
            # `type` 0 = POSITION_TYPE_BUY, 1 = POSITION_TYPE_SELL.
            comprado = getattr(p, "type", 0) == getattr(mt5, "POSITION_TYPE_BUY", 0)
            return {
                "side": "long" if comprado else "short",
                "price": float(getattr(p, "price_open", 0.0) or 0.0),
                "quantity": int(round(volume * self._shares_per_lot)),
                "ticket": getattr(p, "ticket", None),
            }
        except Exception:
            return None

    def pending_orders(self, ticker: str) -> Optional[list[dict]]:
        """Ordens-limite PENDENTES deste robo (`magic`) neste papel, como a
        corretora as ve. `None` = nao deu para perguntar (terminal fechado,
        pacote ausente) -- que NAO e' a mesma coisa que `[]` ("perguntei, nao
        ha nenhuma"): quem apaga um robo precisa distinguir "confirmei que
        nao ha nada pendurado" de "nao consegui confirmar".

        Cada item: `{"ticket", "side", "quantity", "price", "symbol"}`.
        `quantity` em ACOES (`volume * shares_per_lot`), a mesma unidade de
        `Order.quantity`, para o painel nao ter de converter lote.

        Complementa `open_position()`: aquela responde "quanto eu TENHO",
        esta responde "o que ainda pode virar posicao sem ninguem clicar em
        nada". Uma limpeza que so' olhasse posicao deixaria viva uma ordem
        que preenche depois do robo ja ter sido apagado do painel."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception:  # pragma: no cover - ambiente sem o pacote
            return None
        try:
            if not self.connect():
                return None
            symbol = self.symbol_for(ticker)
            ordens = mt5.orders_get(symbol=symbol)
            if ordens is None:
                return None
            compras = {getattr(mt5, "ORDER_TYPE_BUY_LIMIT", 2),
                       getattr(mt5, "ORDER_TYPE_BUY_STOP", 4)}
            saida = []
            for o in ordens:
                if getattr(o, "magic", None) != self._magic:
                    continue
                volume = float(getattr(o, "volume_current", 0.0) or 0.0)
                saida.append({
                    "ticket": str(getattr(o, "ticket", "") or ""),
                    "side": "compra" if getattr(o, "type", None) in compras else "venda",
                    "quantity": int(round(volume * self._shares_per_lot)),
                    "price": float(getattr(o, "price_open", 0.0) or 0.0),
                    "symbol": symbol,
                })
            return saida
        except Exception:
            return None

    def foreign_activity(self, ticker: str) -> Optional[dict]:
        """Ha' posicao ou ordem pendente neste papel com `magic` DIFERENTE
        do deste robo -- sinal de que alguem (o dono, na mao, ou outro robo)
        mexeu na mesma conta/simbolo por fora. Devolve um resumo para o
        runtime LOGAR um alerta (nunca para decidir nada -- ver a docstring
        do modulo: nenhuma regra de decisao mora aqui), ou `None` quando so'
        existe (ou nao existe nada) o que e' deste robo.

        Nao substitui `open_position()`/`pending_orders()` (que so' enxergam
        o que e' DESTE `magic`, de proposito -- contra a mesma conta NETTING
        compartilhada entre slots, ver as docstrings la): aquelas respondem
        "quanto eu tenho", esta responde "tem mais alguem aqui alem de mim".
        Motivado pelo teste manual de 2026-08-27 (compra/venda a mercado de
        PMAM3 direto no terminal, enquanto o robo real rodava no mesmo papel)
        -- o robo nunca soube que aquilo tinha acontecido.

        `None` tambem quando nao deu para perguntar (terminal fechado,
        pacote ausente): "nao sei" nao pode virar alarme de atividade
        estranha, mesma regra de `open_position`/`pending_orders`."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception:  # pragma: no cover - ambiente sem o pacote
            return None
        try:
            if not self.connect():
                return None
            symbol = self.symbol_for(ticker)
            posicoes = mt5.positions_get(symbol=symbol)
            if posicoes is None:
                return None
            ordens = mt5.orders_get(symbol=symbol)
            if ordens is None:
                return None
            itens = []
            for p in posicoes:
                magic = getattr(p, "magic", None)
                volume = float(getattr(p, "volume", 0.0) or 0.0)
                if magic != self._magic and volume > 0:
                    itens.append({
                        "tipo": "posicao", "magic": magic,
                        "quantity": int(round(volume * self._shares_per_lot)),
                    })
            for o in ordens:
                magic = getattr(o, "magic", None)
                volume = float(getattr(o, "volume_current", 0.0) or 0.0)
                if magic != self._magic and volume > 0:
                    itens.append({
                        "tipo": "ordem", "magic": magic,
                        "quantity": int(round(volume * self._shares_per_lot)),
                    })
            if not itens:
                return None
            return {"symbol": symbol, "itens": itens}
        except Exception:
            return None

    def last_price(self, ticker: str) -> Optional[float]:
        """Ultimo preco negociado do papel, ou `None` se nao deu para ler.

        `last` primeiro (negocio de verdade); se o terminal devolver 0 --
        acontece fora do pregao e em papel sem negocio no dia -- cai para o
        meio do book (`bid`/`ask`). Serve para ESTIMAR quanto uma posicao
        aberta valeria se fosse encerrada agora; nao e' preco de execucao, e
        quem mostra isso na tela tem de dizer que e' estimativa."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception:  # pragma: no cover - ambiente sem o pacote
            return None
        try:
            if not self.connect():
                return None
            symbol = self.symbol_for(ticker)
            mt5.symbol_select(symbol, True)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            ultimo = float(getattr(tick, "last", 0.0) or 0.0)
            if ultimo > 0:
                return ultimo
            bid = float(getattr(tick, "bid", 0.0) or 0.0)
            ask = float(getattr(tick, "ask", 0.0) or 0.0)
            if bid > 0 and ask > 0:
                return (bid + ask) / 2.0
            return bid or ask or None
        except Exception:
            return None

    def supports_automation(self) -> bool:
        return True

    def autotrading_allowed(self) -> Optional[bool]:
        """O botao AutoTrading (Algo Trading) do terminal esta LIGADO?
        `None` = nao deu para saber (terminal fora do ar).

        Com ele desligado o terminal recusa TODA ordem enviada pela API, com
        `retcode=10027 AutoTrading disabled by client` -- foi o que matou a
        primeira ordem do pregao de 25/08/2026 no slot
        `dt-gremah_tick-pmam3-live`.

        So' LEITURA, e nao por preguica: a API do MetaTrader5 nao expoe
        nenhuma funcao para LIGAR (`terminal_info()` e' o unico caminho, e
        `RES_E_AUTO_TRADING_DISABLED` e' so' o codigo de erro do lado de
        quem tenta operar). Medido em 2026-08-25, nesta maquina, os dois
        caminhos de contorno tambem nao servem:

          - `PostMessage(Ctrl+E)` na janela `MetaQuotes::MetaTrader::5.00`:
            o terminal ignora (acelerador confere o teclado REAL, que
            `PostMessage` nao muda);
          - `SendInput(Ctrl+E)`: o envio funciona, mas o Windows recusa dar
            o foco ao terminal para um processo de segundo plano
            (`SetForegroundWindow` -> 0, trava de foreground), entao as
            teclas caem na janela que o dono estiver usando. Injetar tecla as
            cegas na janela errada e' pior que nao operar.

        O estado mora em `config/common.ini`, secao `[Experts]`, chave
        `Enabled` -- lida na ABERTURA do terminal e reescrita quando ele
        fecha. Ligar por ali so' funciona com o terminal FECHADO, valendo na
        proxima abertura."""
        import MetaTrader5 as mt5  # lazy: ver docstring do modulo

        try:
            info = mt5.terminal_info()
        except Exception:
            return None
        if info is None:
            return None
        return bool(info.trade_allowed)

    def cash_balance(self) -> Optional[float]:
        """Saldo real de caixa reportado pelo terminal.

        NAO e' mais a fonte de verdade do caixa da conta (era, ate
        2026-08-21, via `LiveRuntime.reconcile_broker_cash` — removido): o
        terminal atrasa em relacao ao saldo real da Rico, e com dois robos
        dividindo a mesma conta um numero atrasado viraria dois livros-caixa
        errados. Hoje o caixa de cada robo e' um ledger manual (ver
        `dashboard/app.py::operacao_caixa`) e este metodo fica como
        instrumento de DIAGNOSTICO/conferencia, nunca de sincronizacao
        automatica.

        Usa `balance`, NUNCA `equity`: numa conta de acoes a vista (nao
        CFD/margem), `balance` e o caixa REALIZADO (depositos, saques,
        proventos de venda ja fechada) e exclui o P&L flutuante de posicao
        aberta — exatamente o que `AccountState.cash` representa aqui dentro
        (caixa NAO investido). `equity` misturaria isso com dinheiro que ja
        esta alocado em acoes, e faria o runtime "ver" deposito onde so
        houve valorizacao de posicao.

        Mesmo padrao de erro do resto do arquivo: falha de conexao, pacote
        ausente ou resposta inesperada viram `None`, nunca uma excecao solta
        — quem chama trata `None` como "esta corretora nao tem saldo externo
        para comparar agora", nao como erro.
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

    def detect_shares_per_lot(self, tickers) -> Optional[float]:
        """Descobre `shares_per_lot` sozinho, consultando `symbol_info` de
        cada ticker no terminal MT5 conectado — o usuario nao precisa mais
        abrir o terminal e conferir isso na mao (ver ponto 1 da docstring do
        modulo).

        `trade_contract_size` E o `shares_per_lot`: e o numero de unidades do
        ativo que 1.0 de `volume` representa, exatamente a razao que
        `_resolve_volume` usa (`volume = quantity / shares_per_lot`). Devolve
        `None` se a conexao falhar, se algum ticker nao existir no terminal,
        ou se os tickers pedidos nao concordarem num unico valor — o resto do
        sistema assume UM `shares_per_lot` global pro portfolio inteiro (ver
        `__init__`), entao um portfolio com contract_size misto nao tem
        resposta automatica unica; quem chama decide como bloquear, nunca
        inventa um valor default."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception:
            return None
        try:
            if not self.connect():
                return None
            sizes = set()
            for ticker in tickers:
                symbol = self.symbol_for(ticker)
                mt5.symbol_select(symbol, True)
                info = mt5.symbol_info(symbol)
                if info is None:
                    return None
                sizes.add(float(info.trade_contract_size))
            if len(sizes) != 1:
                return None
            return sizes.pop()
        except Exception:
            return None

    def detect_fractional_symbol_map(self, tickers) -> Optional[dict[str, str]]:
        """Descobre, para cada ticker, se o terminal MT5 tem o simbolo do
        MERCADO FRACIONARIO (convencao B3 via MT5: sufixo `"F"` — ex.
        `"WEGE3F"`) alem do de lote padrao (`"WEGE3"`, `volume_min`
        tipicamente 100 acoes). Sem essa deteccao, `symbol_for()` sempre
        resolve para o simbolo de lote padrao (ver docstring do modulo) e
        qualquer ordem abaixo do lote minimo vira `OrderStatus.REJECTED` em
        `_resolve_volume` — o que torna operar com capital pequeno (poucas
        centenas de reais) inviavel mesmo quando a corretora aceita
        fracionario.

        Mesmo padrao de `detect_shares_per_lot()` (consulta o terminal em vez
        de pedir pro usuario conferir na mao), mas SEM exigir um valor unico
        entre os tickers: o mapa e por ticker, e um ticker sem simbolo
        fracionario simplesmente mapeia para o simbolo de lote padrao (mesmo
        comportamento de hoje para ele) — nunca faz o mapa inteiro falhar por
        causa de UM ticker sem versao fracionaria.

        Devolve `None` so se a conexao falhar (mesmo padrao de erro do resto
        da classe) — nunca deixa faltar uma entrada no mapa devolvido."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception:
            return None
        try:
            if not self.connect():
                return None
            result: dict[str, str] = {}
            for ticker in tickers:
                base = self.symbol_for(ticker)
                fractional = base + "F"
                mt5.symbol_select(fractional, True)
                info = mt5.symbol_info(fractional)
                result[ticker] = fractional if info is not None else base
            return result
        except Exception:
            return None
