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
     Ticker de futuro continuo (sufixo `"@"`, ex. `"WDO@"`) e' um caso
     PARTICULAR de `symbol_map` que NAO precisa ser digitado a mao:
     `detect_futures_symbol_map()` descobre sozinho, a cada chamada, qual e'
     o contrato com vencimento em aberto no terminal (ver a docstring do
     metodo) — o `"@"` normalmente so' da cotacao, o servidor recusa ordem
     nele (retcode 10017 `TRADE_DISABLED`).
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

import logging
import math
import re
from typing import Optional

from core.live_models import Order, OrderSide, OrderStatus
from live.broker import Broker

# So' para o fallback do item 1.15 de LICOES_DE_PRODUCAO.md (`place_pending`
# com `position_ticket`, campo cuja aceitacao em `TRADE_ACTION_PENDING` nunca
# foi confirmada contra terminal real). Nenhum outro caminho deste modulo usa
# `logging` -- o resto sempre devolve o motivo em `order.note` (que o RUNTIME
# journaliza), porque `live/broker.py` proibe o broker de escrever no diario.
# Este e' o UNICO caso em que a nota sozinha nao bastava: o texto pedido
# precisa aparecer no log do PROCESSO (stdout/stderr, capturado pelo servico
# NSSM) mesmo que ninguem abra o dashboard depois -- `logging.warning` sem
# `basicConfig` ja imprime em `sys.stderr` via o `lastResort` handler padrao
# do Python, entao isto nao depende de nenhuma configuracao externa nova.
_logger = logging.getLogger(__name__)


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

    def close_position(self, order: Order, position_ticket) -> Order:
        """Fecha uma posicao EXISTENTE, identificada por `position_ticket` --
        SEMPRE o `"ticket"` que `open_position()` leu da corretora agora
        mesmo, nunca um numero que o robo guardou em memoria (ver a checagem
        de lado que `live/intraday_execution.py::MT5IntradayExecution.
        exit_market` faz antes de chamar isto).

        Existe separada de `place()` por causa do incidente REAL de
        2026-08-28 (slot `dt-wdo_grid_reload_maker-wdo@-live`, conta com
        margem para 1 contrato e 2 abertos): o robo tentou fechar ~24 vezes
        e a corretora recusou TODAS com `retcode=10006 [MG51] Para abrir
        novas posicoes`. Causa raiz -- `place()`/`_send()` sempre montavam
        `TRADE_ACTION_DEAL` SEM o campo `"position"`; sem ele, o motor de
        risco da corretora nao sabe que a ordem ABATE uma posicao existente
        e trata como ABERTURA NOVA, que a margem esgotada recusa. A posicao
        ficou presa, sem stop, sem alvo, atravessando reinicios de processo.

        `place()` continua existindo do jeito que estava (chamado por quem
        abre posicao, e' o unico ponto de entrada do resto do sistema) --
        este metodo e' o caminho DEDICADO de fechamento, chamado so por
        `MT5IntradayExecution.exit_market`."""
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
            return self._send(mt5, order, position_ticket=position_ticket)
        except Exception as exc:
            order.status = OrderStatus.REJECTED
            order.note = f"erro inesperado na traducao para MT5 (fechamento): {exc}"
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

    def _send(self, mt5, order: Order, position_ticket: Optional[int] = None) -> Order:
        """`position_ticket` (gap fechado 2026-08-28, incidente do slot
        `dt-wdo_grid_reload_maker-wdo@-live`): quando informado, entra no
        `request` como `"position"` -- o campo que diz ao motor de risco da
        corretora que esta ordem ABATE uma posicao EXISTENTE, em vez de abrir
        uma nova. Sem ele, `place()` sempre montava `TRADE_ACTION_DEAL` como
        se fosse abertura -- e um fechamento de VERDADE, contra margem ja
        esgotada (o robo tinha 2 contratos numa conta dimensionada pra 1),
        era recusado com `retcode=10006 [MG51] Para abrir novas posicoes`. A
        posicao ficou presa ~24 tentativas, sem stop, sem alvo, atravessando
        reinicios. `place()` continua chamando isto SEM ticket (abertura
        normal, comportamento de sempre); `close_position()` e' quem sempre
        passa o ticket -- ver a docstring dele."""
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
        if position_ticket is not None:
            # Ver a docstring de `_send` e de `close_position` -- e' o campo
            # que faz esta ordem ABATER a posicao em vez de tentar abrir uma
            # nova (incidente 2026-08-28, `retcode=10006 [MG51]`).
            request["position"] = int(position_ticket)
        elif order.stop_price is not None or order.target_price is not None:
            # PROTECAO ATOMICA (incidente 2026-08-28): `sl`/`tp` viajam no
            # MESMO request que ABRE a posicao. A corretora amarra os dois no
            # instante do fill -- nao existe instante nenhum em que a posicao
            # esteja viva e desprotegida, nem que o processo morra entre uma
            # coisa e outra. Enquanto a protecao era um segundo request
            # (`TRADE_ACTION_SLTP` no passo seguinte do loop), essa janela
            # tinha segundos no caso bom e HORAS no caso ruim, que foi o que
            # aconteceu de verdade. `set_protection` continua existindo como
            # REDE (protecao que sumiu, stop que a maquina moveu depois),
            # nunca como o caminho principal.
            #
            # So' na ABERTURA: uma ordem de FECHAMENTO (`position_ticket`
            # preenchido) nao abre nada que precise de protecao, e mandar
            # `sl`/`tp` nela mexeria na posicao que esta sendo encerrada.
            sl, tp, _avisos = self._niveis_protecao(
                mt5, symbol, "long" if is_buy else "short",
                order.stop_price, order.target_price, price, info=info,
            )
            if sl > 0.0:
                request["sl"] = float(sl)
            if tp > 0.0:
                request["tp"] = float(tp)

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

        # Gap fechado 2026-08-28 (mesmo incidente do slot
        # `dt-wdo_grid_reload_maker-wdo@-live`, achado JUNTO com o bug do
        # `position`): a corretora as vezes devolve `retcode=TRADE_RETCODE_
        # DONE` ("Request executed") sem ter de fato preenchido nada --
        # `price=0.0` e `deal=0` no mesmo log real ("fill @ 0.0000 ...
        # deal=0, comment=Request executed"). Um "sucesso" sem preco nem
        # deal e' informacao que a corretora nao confirmou de verdade; tratar
        # como FILLED inventaria um preco de execucao (e um P&L) que nunca
        # aconteceu. Vira REJECTED com o motivo explicito -- quem chama
        # (`live/intraday_execution.py`) ja sabe tratar REJECTED como "tenta
        # de novo", nunca como "nao preencheu".
        preco_resultado = float(getattr(result, "price", 0.0) or 0.0)
        deal_resultado = getattr(result, "deal", None)
        if preco_resultado <= 0.0 or not deal_resultado:
            order.status = OrderStatus.REJECTED
            order.note = (
                f"MT5 devolveu retcode=DONE mas sem confirmacao real de fill "
                f"(price={preco_resultado}, deal={deal_resultado}, "
                f"comment={getattr(result, 'comment', '')}) -- nao vou tratar "
                "como execucao"
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

    # Retcodes que indicam "a corretora rejeitou o FORMATO/campo do request",
    # nao o MERITO da ordem (preco, margem, mercado fechado). So' este tipo de
    # recusa dispara o fallback do `position_ticket` em `place_pending` --
    # qualquer outro motivo (sem dinheiro, preco mudou, mercado fechado)
    # continua indo direto para REJECTED, porque reenviar sem o campo nao
    # resolveria nada e esconderia o motivo real da recusa atras de um
    # fallback que nao tem relacao com ele.
    #
    # Resolvidos por NOME (via `getattr(mt5, nome, None)`), nunca por numero
    # fixo: os dois vem do pacote `MetaTrader5` (real ou fake de teste), e o
    # ponto 3 da docstring do modulo ja explica por que constantes desse
    # pacote so' existem depois do import lazy.
    _RETCODES_REQUEST_INVALIDO = (
        "TRADE_RETCODE_INVALID",        # 10013 -- "Invalid request"
        "TRADE_RETCODE_INVALID_ORDER",  # 10035 -- "Invalid order filling type"/campo
    )

    def _retcode_sugere_campo_nao_suportado(self, mt5, retcode) -> bool:
        for nome in self._RETCODES_REQUEST_INVALIDO:
            codigo = getattr(mt5, nome, None)
            if codigo is not None and retcode == codigo:
                return True
        return False

    def place_pending(self, order: Order, position_ticket: Optional[int] = None) -> Order:
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
        processo morrer.

        `position_ticket` (gap fechado 2026-09-03, item 1.15 de
        LICOES_DE_PRODUCAO.md): o MESMO papel que `_send`/`close_position` ja
        davam ao campo `"position"` para fechamento a MERCADO depois do
        incidente 2026-08-28 (MG51) -- diz ao motor de risco da corretora que
        esta ordem ABATE uma posicao EXISTENTE, agora tambem no caminho
        PENDENTE. Quem usa isto e' `MT5IntradayExecution.place_exit_limit`,
        para a fatia de SAIDA por alvo (`exit_split_unit`) que os robos
        `gremah`/`gremah_tick` armam sempre que `dividir_entrada=True` (o
        default). Antes deste campo existir, a ordem-limite de FECHAMENTO
        nunca dizia qual posicao estava abatendo -- exatamente a lacuna que
        MG51 explorou do lado da ordem A MERCADO.

        Quando `position_ticket` esta preenchido, `sl`/`tp` do PROPRIO `order`
        NAO viajam neste request (mesma exclusao que `_send` ja faz): uma
        ordem que FECHA posicao nao abre nada para proteger, e mandar sl/tp
        nela mexeria na posicao que esta sendo encerrada.

        **Risco NAO resolvido, documentado no proprio item 1.15**: nunca foi
        possivel confirmar contra um terminal MT5 real se `TRADE_ACTION_
        PENDING` aceita `"position"` do mesmo jeito que `TRADE_ACTION_DEAL`
        aceitou depois do incidente -- o comportamento pode divergir entre os
        dois tipos de acao, e ninguem testou. Por isso este metodo NUNCA
        assume que o campo e' aceito: se a corretora recusar com um retcode
        que sugere "request invalido" (`_retcode_sugere_campo_nao_suportado`),
        ele tenta UMA UNICA VEZ de novo sem o campo -- nunca um laco de
        retry -- e registra (`logging.warning`, nivel ALTO, nunca em
        silencio) que esta plataforma pode nao aceitar `position` numa ordem
        pendente. Qualquer outro motivo de recusa (preco, margem, mercado
        fechado) NAO aciona o fallback -- vai direto para REJECTED, porque
        reenviar sem o campo nao mudaria nada."""
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
            if position_ticket is not None:
                # Ver a docstring do metodo -- item 1.15 de
                # LICOES_DE_PRODUCAO.md. Mesmo campo que `_send`/
                # `close_position` usam para fechamento a MERCADO (incidente
                # 2026-08-28, MG51); aqui e' o caminho PENDENTE equivalente.
                request["position"] = int(position_ticket)
            protegida = ""
            if position_ticket is None and (
                order.stop_price is not None or order.target_price is not None
            ):
                # PROTECAO ATOMICA -- ver o bloco equivalente em `_send`. Numa
                # ordem PENDENTE o ganho e' ainda maior: entre registrar a
                # ordem e ela preencher podem passar minutos ou horas, e o
                # processo pode morrer no meio. Com `sl`/`tp` amarrados aqui,
                # a protecao nasce COM a posicao, mesmo que ninguem esteja
                # vivo para reagir ao fill. A distancia minima da corretora e'
                # medida contra o proprio nivel da limite (nao contra o preco
                # corrente) -- e' onde a posicao vai nascer.
                #
                # So' numa ordem de ABERTURA (`position_ticket is None`): uma
                # ordem que FECHA posicao existente nao abre nada para
                # proteger, e mandar sl/tp nela mexeria na posicao que esta
                # sendo encerrada -- mesma exclusao que `_send` ja faz para
                # `TRADE_ACTION_DEAL`.
                sl, tp, avisos = self._niveis_protecao(
                    mt5, symbol, "long" if is_buy else "short",
                    order.stop_price, order.target_price,
                    float(order.limit_price), info=info,
                )
                if sl > 0.0:
                    request["sl"] = float(sl)
                if tp > 0.0:
                    request["tp"] = float(tp)
                protegida = (f", sl={sl:.4f} tp={tp:.4f} amarrados na propria ordem"
                             + ("; " + "; ".join(avisos) if avisos else ""))

            result = mt5.order_send(request)
            if result is None:
                code, desc = self._last_error(mt5)
                order.status = OrderStatus.REJECTED
                order.note = f"order_send (pendente) devolveu None (last_error={code}: {desc})"
                return order

            fallback_nota = ""
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                if position_ticket is not None and self._retcode_sugere_campo_nao_suportado(
                    mt5, result.retcode
                ):
                    # FALLBACK (item 1.15) -- ver a docstring do metodo. Uma
                    # UNICA tentativa extra, nunca um laco: se esta tambem
                    # falhar, cai no REJECTED normal la embaixo com as DUAS
                    # recusas na nota.
                    recusa_com_ticket = (
                        f"retcode={result.retcode}: {getattr(result, 'comment', '')}"
                    )
                    _logger.warning(
                        "MT5Broker.place_pending: a corretora RECUSOU a ordem-limite de "
                        "fechamento com o campo 'position'=%s (%s) -- reenviando UMA vez "
                        "sem o campo. Isto sugere que esta plataforma nao aceita "
                        "'position' em TRADE_ACTION_PENDING; confirme contra o terminal "
                        "MT5 real antes de assumir que o fallback e' permanente -- ver "
                        "item 1.15 de LICOES_DE_PRODUCAO.md.",
                        position_ticket, recusa_com_ticket,
                    )
                    request_sem_ticket = dict(request)
                    request_sem_ticket.pop("position", None)
                    retry = mt5.order_send(request_sem_ticket)
                    if retry is not None and retry.retcode == mt5.TRADE_RETCODE_DONE:
                        result = retry
                        fallback_nota = (
                            f" [FALLBACK item 1.15: reenviada SEM 'position' apos recusa "
                            f"com o campo ({recusa_com_ticket}) -- esta plataforma parece "
                            "nao aceitar 'position' em ordem pendente; a posicao fechada "
                            "por esta ordem nao ficou identificada no request, confirme "
                            "manualmente contra o terminal]"
                        )
                    else:
                        recusa_sem_ticket = (
                            f"retcode={getattr(retry, 'retcode', None)}: "
                            f"{getattr(retry, 'comment', '')}" if retry is not None
                            else "order_send devolveu None"
                        )
                        order.status = OrderStatus.REJECTED
                        order.note = (
                            f"MT5 recusou a ordem-limite pendente de fechamento tanto COM "
                            f"'position' ({recusa_com_ticket}) quanto SEM ('{recusa_sem_ticket}'"
                            ") -- a causa nao e' o campo novo, e' outro motivo (preco, "
                            "margem, mercado fechado)."
                        )
                        return order
                else:
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
                f"{order.limit_price:.4f} (ticket={order.broker_ref}){protegida}{fallback_nota}"
            )
            return order
        except Exception as exc:
            order.status = OrderStatus.REJECTED
            order.note = f"erro inesperado ao registrar ordem pendente no MT5: {exc}"
            return order

    def _pending_order_alive(self, mt5, broker_ref) -> Optional[bool]:
        """A ordem pendente `broker_ref` ainda esta VIVA no terminal?
        `True`/`False`, ou `None` quando nao deu para perguntar -- e "nao deu
        para perguntar" NUNCA pode virar `False` (ver `cancel`)."""
        try:
            ticket = int(broker_ref)
        except (TypeError, ValueError):
            return None
        consulta = getattr(mt5, "orders_get", None)
        if consulta is None:  # pragma: no cover - fake antigo sem o metodo
            return None
        try:
            ordens = consulta(ticket=ticket)
        except Exception:
            return None
        if ordens is None:
            return None
        return len(ordens) > 0

    def cancel(self, order: Order) -> Order:
        """Remove do terminal a ordem-limite pendente de `order.broker_ref`.

        **So' marca `CANCELLED` o que a corretora CONFIRMOU morto.** Esta
        regra e' o metodo inteiro, e ela custou caro para ser escrita: a
        versao anterior marcava `CANCELLED` nos DOIS ramos -- no sucesso e na
        falha -- "para nao virar retry infinito". Como `CANCELLED` e' estado
        terminal e todo o rastreamento de ordem orfa filtra por
        `not is_terminal` (`live/intraday_execution.py::orphan_refs`), o
        efeito real era que NENHUMA orfa era rastreada nunca: `pending_entry_
        refs` ficava vazio por construcao, `_drena_orfas_de_saida` nao tinha
        o que drenar, e `dashboard/live_teardown.py` dava a corretora por
        limpa e APAGAVA a conta com ordem viva no book. Um cancelamento que
        falhou e' uma ordem que pode preencher sozinha depois, abrindo
        posicao sem stop que ninguem esta vigiando.

        Tres desfechos, e a diferenca entre eles e' o ponto:

          - `TRADE_RETCODE_DONE` -> `CANCELLED`. A corretora removeu.
          - Recusou, e o terminal confirma que o ticket NAO esta mais na
            lista de pendentes (preencheu, expirou, alguem cancelou na mao)
            -> `CANCELLED`. O objetivo ja' esta cumprido; nao ha o que
            remover, e insistir seria retry infinito de verdade.
          - Recusou, e o ticket AINDA esta vivo -- ou nao deu nem para
            perguntar (terminal fora do ar, pacote ausente, excecao) ->
            status INTOCADO (nao-terminal), motivo na nota. Quem chama ja
            sabe o que fazer com isso: `orphan_refs` recolhe o ticket e o
            runtime tenta de novo a cada barra ate a corretora confirmar.

        Sem `broker_ref` (nunca chegou a ser registrada) cai no default do
        port (`Broker.cancel`, so' marca `CANCELLED` localmente) -- ai' e'
        honesto: nao existe ordem na corretora para sobrar."""
        if not order.broker_ref:
            return super().cancel(order)
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception as exc:  # pragma: no cover - ambiente sem o pacote
            order.note = (f"pacote MetaTrader5 indisponivel ao cancelar: {exc} -- ordem "
                          f"{order.broker_ref} NAO confirmada morta, segue vigiada")
            return order

        try:
            if not self.connect():
                code, desc = self._last_error(mt5)
                order.note = (f"falha ao conectar para cancelar (last_error={code}: {desc}) "
                              f"-- ordem {order.broker_ref} NAO confirmada morta, segue vigiada")
                return order
            result = mt5.order_send({
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": int(order.broker_ref),
            })
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                order.status = OrderStatus.CANCELLED
                order.note = f"ordem pendente {order.broker_ref} removida do terminal"
                return order

            recusa = (f"retcode={getattr(result, 'retcode', None)}: "
                      f"{getattr(result, 'comment', '')}")
            viva = self._pending_order_alive(mt5, order.broker_ref)
            if viva is False:
                order.status = OrderStatus.CANCELLED
                order.note = (
                    f"ordem pendente {order.broker_ref} ja nao estava viva no terminal "
                    f"({recusa}) -- confirmado contra a lista de pendentes, nada a remover"
                )
                return order
            if viva is True:
                order.note = (
                    f"a corretora RECUSOU remover a ordem pendente {order.broker_ref} "
                    f"({recusa}) e ela CONTINUA VIVA no terminal -- pode preencher "
                    "sozinha e abrir posicao; segue vigiada para nova tentativa"
                )
                return order
            order.note = (
                f"a corretora recusou remover a ordem pendente {order.broker_ref} "
                f"({recusa}) e nao deu para confirmar se ela ainda esta viva -- "
                "tratada como VIVA (segue vigiada), porque 'nao sei' nunca pode "
                "virar 'ja morreu'"
            )
            return order
        except Exception as exc:
            order.note = (f"erro inesperado ao cancelar ordem pendente {order.broker_ref}: "
                          f"{exc} -- NAO confirmada morta, segue vigiada")
            return order

    def order_history_state(self, ticket) -> dict:
        """Desfecho de uma ordem que deixou de estar no book -- tri-estado
        `{"ok": bool, "state": Optional[str], "position_id": Optional[int],
        "note": str}`.

        Existe para o gap medido ao vivo em 2026-09-04 (slot
        `dt-wdo_grid_reload_maker-wdo@-live`): uma ordem-limite pode
        preencher E a posicao pode ser fechada pela protecao SL/TP atomica
        da propria corretora, as DUAS coisas dentro do MESMO intervalo de
        poll do supervisor (5s) -- `orders_get`/`positions_get` sozinhos nao
        contam essa historia, porque no proximo poll a ordem ja nao esta no
        book (preencheu) E a posicao ja nao existe (fechou). So' o
        HISTORICO (`history_orders_get`) guarda o desfecho de uma ordem que
        ja saiu do book -- `mt5.history_orders_get` so' devolve algo para
        ordens que JA chegaram a estado terminal (por definicao do proprio
        pacote: uma ordem ainda pendente mora em `orders_get`, nunca em
        `history_orders_get`).

        `state` (nunca um codigo numerico -- traduzido aqui, unica vez, na
        mesma politica do resto do modulo de nao vazar tipo do pacote MT5
        pra fora): `"pending"` (ainda no book), `"filled"`, `"partial"`,
        `"canceled"`, `"rejected"`, `"expired"`, ou `"unknown"` (achou no
        historico mas o codigo de estado nao bate nenhum dos conhecidos --
        nunca inventa um dos nomes acima). `position_id` (so' presente para
        `"filled"`/`"partial"`) e' a chave para `deals_for_position` --
        numa posicao NETTING recem aberta e' o mesmo numero do ticket que a
        abriu, mas lido do proprio historico, nunca assumido.

        `ok=False` e' SEMPRE "nao consegui perguntar" (pacote ausente, sem
        conexao, consulta que devolveu `None`) -- nunca "a ordem morreu sem
        preencher". Quem chama trata `ok=False` como "fica tudo como
        esta" (item 1.6 de LICOES_DE_PRODUCAO.md): nunca declara uma ordem
        cancelada ou uma entrada perdida so' porque a consulta falhou."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception as exc:  # pragma: no cover - ambiente sem o pacote
            return {"ok": False, "state": None, "position_id": None,
                    "note": f"pacote MetaTrader5 indisponivel: {exc}"}
        try:
            if not self.connect():
                code, desc = self._last_error(mt5)
                return {"ok": False, "state": None, "position_id": None,
                        "note": f"falha ao conectar ao terminal MT5 (last_error={code}: {desc})"}
            try:
                ticket_int = int(ticket)
            except (TypeError, ValueError):
                return {"ok": False, "state": None, "position_id": None,
                        "note": f"ticket invalido: {ticket!r}"}

            # Caminho RAPIDO primeiro (`orders_get`, um ticket so'): e' o
            # caso comum -- ordem ainda pendente, poll apos poll, enquanto
            # espera o preco chegar -- e evita pagar `history_orders_get`
            # (consulta mais cara) em toda chamada normal. So' cai para o
            # historico quando o book confirma que a ordem NAO esta mais
            # la' (ou quando nem essa confirmacao deu certo).
            vivo = self._pending_order_alive(mt5, ticket_int)
            if vivo is True:
                return {"ok": True, "state": "pending", "position_id": None, "note": ""}

            historico = mt5.history_orders_get(ticket=ticket_int)
            if historico is None:
                code, desc = self._last_error(mt5)
                return {"ok": False, "state": None, "position_id": None,
                        "note": (f"history_orders_get(ticket={ticket_int}) devolveu None "
                                 f"(last_error={code}: {desc})")}
            if historico:
                registro = historico[0]
                nomes = {
                    getattr(mt5, "ORDER_STATE_FILLED", 4): "filled",
                    getattr(mt5, "ORDER_STATE_PARTIAL", 3): "partial",
                    getattr(mt5, "ORDER_STATE_CANCELED", 2): "canceled",
                    getattr(mt5, "ORDER_STATE_REJECTED", 5): "rejected",
                    getattr(mt5, "ORDER_STATE_EXPIRED", 6): "expired",
                }
                estado = nomes.get(getattr(registro, "state", None), "unknown")
                position_id = getattr(registro, "position_id", None)
                return {"ok": True, "state": estado,
                        "position_id": (int(position_id) if position_id else None),
                        "note": ""}

            # Nem no book (`orders_get`) nem no historico. Se a checagem
            # rapida tinha CONFIRMADO ausencia (`vivo is False`), o ticket e'
            # mesmo desconhecido -- nunca aconteceu, ou o historico ainda nao
            # tem (raro, mas nao inventa "cancelada"). Se a checagem rapida
            # nem tinha dado certo (`vivo is None`), a resposta e' "nao sei".
            if vivo is False:
                return {"ok": True, "state": "unknown", "position_id": None,
                        "note": (f"ordem {ticket_int} nao esta no book nem no historico "
                                 "-- desfecho desconhecido")}
            code, desc = self._last_error(mt5)
            return {"ok": False, "state": None, "position_id": None,
                    "note": (f"orders_get(ticket={ticket_int}) falhou (last_error={code}: "
                             f"{desc}) e a ordem nao esta no historico -- nao consegui "
                             "confirmar se ainda esta pendente")}
        except Exception as exc:
            return {"ok": False, "state": None, "position_id": None,
                    "note": f"erro inesperado ao consultar historico da ordem {ticket}: {exc}"}

    def deals_for_position(self, position_id) -> dict:
        """Todos os deals (entrada E saida) de uma posicao, pela CORRETORA
        -- tri-estado `{"ok": bool, "deals": Optional[list[dict]], "note":
        str}`.

        Cada deal: `{"ticket", "order", "entry" (0=IN, 1=OUT, 2=INOUT,
        3=OUT_BY), "type" (0=compra, 1=venda), "price", "quantity" (JA
        convertida de lote para acoes/contratos via `shares_per_lot`, a
        mesma unidade de `Order.quantity` no resto do modulo), "profit",
        "commission", "swap", "fee", "time" (epoch, segundos), "comment"}`.

        `position_id`, numa conta NETTING, e' o identificador ESTAVEL da
        posicao -- sobrevive do deal de entrada ao de saida mesmo que sejam
        ordens/tickets diferentes (ver `order_history_state`). E' a chave
        certa para reconstruir o ciclo de vida inteiro de uma posicao que
        ja fechou, quando `positions_get`/`open_position` nao tem mais nada
        para mostrar (ver `MT5IntradayExecution.resolve_orphaned_entry` e
        `exit_market`, gap medido ao vivo 2026-09-04).

        `ok=False` e' "nao consegui perguntar" (pacote ausente, sem
        conexao, `history_deals_get` devolveu `None`) -- NUNCA "nao ha
        deals". Uma lista vazia com `ok=True` e' a resposta "perguntei e
        nao ha nada" -- quem chama nunca pode inventar um preco de saida
        quando a resposta e' `ok=False`; a unica acao segura e' tratar como
        'ainda nao sei' e tentar de novo depois (item 1.6)."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception as exc:  # pragma: no cover - ambiente sem o pacote
            return {"ok": False, "deals": None, "note": f"pacote MetaTrader5 indisponivel: {exc}"}
        try:
            if not self.connect():
                code, desc = self._last_error(mt5)
                return {"ok": False, "deals": None,
                        "note": f"falha ao conectar ao terminal MT5 (last_error={code}: {desc})"}
            try:
                pos_id = int(position_id)
            except (TypeError, ValueError):
                return {"ok": False, "deals": None,
                        "note": f"position_id invalido: {position_id!r}"}

            deals = mt5.history_deals_get(position=pos_id)
            if deals is None:
                code, desc = self._last_error(mt5)
                return {"ok": False, "deals": None,
                        "note": (f"history_deals_get(position={pos_id}) devolveu None "
                                 f"(last_error={code}: {desc})")}
            saida = []
            for d in deals:
                volume = float(getattr(d, "volume", 0.0) or 0.0)
                saida.append({
                    "ticket": getattr(d, "ticket", None),
                    "order": getattr(d, "order", None),
                    "entry": getattr(d, "entry", None),
                    "type": getattr(d, "type", None),
                    "price": float(getattr(d, "price", 0.0) or 0.0),
                    "quantity": int(round(volume * self._shares_per_lot)),
                    "profit": float(getattr(d, "profit", 0.0) or 0.0),
                    "commission": float(getattr(d, "commission", 0.0) or 0.0),
                    "swap": float(getattr(d, "swap", 0.0) or 0.0),
                    "fee": float(getattr(d, "fee", 0.0) or 0.0),
                    "time": getattr(d, "time", None),
                    "comment": str(getattr(d, "comment", "") or ""),
                })
            return {"ok": True, "deals": saida, "note": ""}
        except Exception as exc:
            return {"ok": False, "deals": None,
                    "note": f"erro inesperado ao consultar deals da posicao {position_id}: {exc}"}

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
        sua.

        **Achata o tri-estado**: devolve `None` tanto para "nao ha posicao"
        quanto para "nao consegui perguntar". Quem precisa distinguir os dois
        -- e todo caminho que vai MANDAR ORDEM precisa -- usa
        `position_state()`, que este metodo apenas embrulha. Continua
        existindo com esta assinatura porque o painel e os dublês de teste
        so' querem "o que tem aberto", e para eles a diferenca nao muda
        nada."""
        estado = self.position_state(ticker)
        return estado["position"] if estado["ok"] else None

    def position_state(self, ticker: str) -> dict:
        """Ver `Broker.position_state` -- a versao que de fato distingue
        "nao ha posicao" (`ok=True, position=None`) de "nao consegui
        perguntar" (`ok=False`).

        A distincao nao e' teorica. `mt5.positions_get()` devolve `None`
        quando a consulta FALHA e uma tupla vazia quando ela deu certo e nao
        ha nada -- e o codigo anterior tratava os dois como "nao ha nada",
        junto com todo `except Exception`. Um terminal fechado ficava
        indistinguivel de uma conta zerada, e quem lia isso decidia mandar
        ordem em cima da resposta errada."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception as exc:  # pragma: no cover - ambiente sem o pacote
            return {"ok": False, "position": None,
                    "note": f"pacote MetaTrader5 indisponivel: {exc}"}
        try:
            if not self.connect():
                code, desc = self._last_error(mt5)
                return {"ok": False, "position": None,
                        "note": f"sem conexao com o terminal MT5 (last_error={code}: {desc})"}
            symbol = self.symbol_for(ticker)
            posicoes = mt5.positions_get(symbol=symbol)
            if posicoes is None:
                # `None` aqui e' FALHA de consulta, nao ausencia de posicao --
                # a resposta de "perguntei e nao ha nada" e' uma tupla vazia.
                code, desc = self._last_error(mt5)
                return {"ok": False, "position": None,
                        "note": (f"positions_get({symbol}) devolveu None "
                                 f"(last_error={code}: {desc}) -- consulta falhou, "
                                 "nao e' 'nao ha posicao'")}
            minhas = [p for p in posicoes if getattr(p, "magic", None) == self._magic]
            if not minhas:
                return {"ok": True, "position": None, "note": ""}
            p = minhas[0]
            volume = float(getattr(p, "volume", 0.0) or 0.0)
            if volume <= 0:
                return {"ok": True, "position": None, "note": ""}
            # `type` 0 = POSITION_TYPE_BUY, 1 = POSITION_TYPE_SELL.
            comprado = getattr(p, "type", 0) == getattr(mt5, "POSITION_TYPE_BUY", 0)
            return {"ok": True, "note": "", "position": {
                "side": "long" if comprado else "short",
                "price": float(getattr(p, "price_open", 0.0) or 0.0),
                "quantity": int(round(volume * self._shares_per_lot)),
                "ticket": getattr(p, "ticket", None),
                # SL/TP REGISTRADOS na corretora agora -- 0.0 (ou ausente) e'
                # o mesmo estado da posicao NUA do incidente 2026-08-28
                # (ficou com `sl=0.0, tp=0.0` por horas, atravessando 3
                # reinicios). `_ensure_protecao` (`live/intraday_runtime.py`)
                # le isto pra' decidir se precisa (re)enviar `set_protection`
                # -- sem isto ela reenviaria SLTP toda barra, mesmo quando ja
                # esta' certo.
                "sl": float(getattr(p, "sl", 0.0) or 0.0),
                "tp": float(getattr(p, "tp", 0.0) or 0.0),
            }}
        except Exception as exc:
            return {"ok": False, "position": None,
                    "note": f"erro inesperado ao ler posicao de {ticker}: {exc}"}

    def _niveis_protecao(self, mt5, symbol: str, side: str,
                         stop: Optional[float], target: Optional[float],
                         preco_ref: Optional[float],
                         sl_atual: float = 0.0, tp_atual: float = 0.0,
                         info=None) -> tuple:
        """Traduz os niveis que a MAQUINA decidiu para o par `(sl, tp)` que a
        corretora aceita. Devolve `(sl, tp, avisos)`; `0.0` e' a codificacao
        do proprio MT5 para "sem nivel deste lado".

        UM SO' lugar calcula isto, e os TRES caminhos que registram protecao
        usam este metodo -- ordem a mercado (`_send`), ordem-limite pendente
        (`place_pending`) e o reforco por `TRADE_ACTION_SLTP`
        (`set_protection`). Ter tres copias da regra era como um caminho
        acabava mais frouxo que o outro sem ninguem perceber.

        Nada aqui e' DECISAO (regra 6 do AGENTS.md): `stop`/`target` chegam
        prontos da estrategia/maquina. O que este metodo faz e' so' o ajuste
        MECANICO que a corretora exige, com tres invariantes que valem para
        QUALQUER robo (nenhum deles conhece estrategia):

          1. **Nunca apaga.** Um lado sem pedido (`None`) preserva o que ja'
             esta registrado na posicao, em vez de mandar `0.0`. Num
             `TRADE_ACTION_SLTP` o campo `0.0` nao significa "deixa como
             esta": significa REMOVER a protecao daquele lado. Uma estrategia
             sem alvo (`target=None`) apagava, a cada reforco, o stop... nao:
             apagava o TP que outra rodada tinha posto -- e uma sem stop
             apagaria o SL. Preservar e' o unico default seguro.
          2. **Nunca afrouxa.** Se ja' existe SL registrado e o novo calculo
             daria mais espaco de perda (long: SL mais BAIXO; short: mais
             ALTO), fica o mais protetor. Mesma regra de `AdjustStop` que
             vale no motor inteiro -- stop anda numa direcao so'.
          3. **Respeita a distancia minima da corretora** (`trade_stops_
             level`) medida contra `preco_ref` -- o preco de execucao numa
             ordem a mercado, o proprio nivel da limite numa pendente, o
             bid/ask corrente num reforco. SL/TP colado demais e' recusado
             pelo servidor, e uma protecao recusada e' protecao nenhuma.
             Quando precisa afastar, ANOTA em `avisos`: o nivel registrado
             ficou diferente do que a maquina pediu, e isso tem de aparecer
             no diario em vez de sumir.
        """
        if info is None:
            info = mt5.symbol_info(symbol)
        tick_size = 0.0
        distancia_min = 0.0
        if info is not None:
            tick_size = float(getattr(info, "trade_tick_size", 0.0) or 0.0) or \
                float(getattr(info, "point", 0.0) or 0.0)
            passos = getattr(info, "trade_stops_level", None)
            if not passos:
                passos = getattr(info, "stops_level", 0) or 0
            ponto = float(getattr(info, "point", 0.0) or 0.0) or tick_size
            distancia_min = float(passos) * float(ponto)

        avisos: list[str] = []
        sl_atual = float(sl_atual or 0.0)
        tp_atual = float(tp_atual or 0.0)

        def _arredonda(preco: float) -> float:
            if not tick_size:
                return float(preco)
            return round(round(float(preco) / tick_size) * tick_size, 8)

        def _afasta(preco: float, e_stop: bool) -> float:
            # SL de posicao LONG e TP de posicao SHORT ficam ABAIXO do preco
            # de referencia; o par oposto (TP long / SL short) fica ACIMA --
            # `abaixo` da' as duas combinacoes com um XOR.
            preco = float(preco)
            if preco_ref is None or distancia_min <= 0:
                return preco
            abaixo = (side == "long") == e_stop
            limite = (float(preco_ref) - distancia_min) if abaixo \
                else (float(preco_ref) + distancia_min)
            if (abaixo and preco > limite) or (not abaixo and preco < limite):
                avisos.append(
                    f"{'stop' if e_stop else 'alvo'} pedido {preco:.4f} estava mais perto "
                    f"que a distancia minima da corretora ({distancia_min:.4f}) e foi "
                    f"afastado para {limite:.4f}"
                )
                return limite
            return preco

        # Invariante 1: lado sem pedido PRESERVA o que ja' esta registrado.
        sl = _arredonda(_afasta(float(stop), True)) if stop is not None else sl_atual
        tp = _arredonda(_afasta(float(target), False)) if target is not None else tp_atual

        # Invariante 2: stop nunca afrouxa contra o que ja' esta registrado.
        if stop is not None and sl_atual > 0:
            mais_protetor = max(sl, sl_atual) if side == "long" else min(sl, sl_atual)
            if abs(mais_protetor - sl) > 1e-9:
                avisos.append(
                    f"mantido o stop mais protetor ja' registrado ({sl_atual:.4f}) em vez "
                    f"do calculado agora ({sl:.4f}) -- stop nunca afrouxa"
                )
                sl = mais_protetor

        return float(sl), float(tp), avisos

    def set_protection(self, ticker: str, position_ticket, side: str,
                       stop: Optional[float] = None, target: Optional[float] = None,
                       sl_atual: float = 0.0, tp_atual: float = 0.0) -> dict:
        """REFORCO da protecao de uma posicao que ja' existe, via
        `TRADE_ACTION_SLTP`. **E' a rede, nao o caminho principal**: o
        caminho principal e' ATOMICO -- `sl`/`tp` viajam no MESMO request
        que abre a ordem (`_send` e `place_pending`), entao a corretora
        amarra a protecao no instante do fill, sem processo nenhum no meio e
        sem janela nenhuma. Este metodo existe para os casos em que aquilo
        nao basta: protecao que sumiu (humano mexeu no terminal, corretora
        recusou o SL da abertura), stop que a maquina MOVEU depois (trailing)
        e posicao herdada de um processo anterior.

        `sl_atual`/`tp_atual` sao o que a corretora reporta AGORA para esta
        posicao (de `open_position`) -- entram para os invariantes 1 e 2 de
        `_niveis_protecao`: sem eles, um `target=None` mandaria `tp=0.0` e
        APAGARIA o alvo registrado, e um stop recalculado poderia afrouxar o
        que ja' estava mais perto.

        Gap fechado depois do incidente 2026-08-28 (slot
        `dt-wdo_grid_reload_maker-wdo@-live`): a posicao ficou com `sl=0.0,
        tp=0.0` NA CORRETORA por HORAS, atravessando 3 reinicios do
        processo, porque o "stop" deste robo sempre foi logica do LOOP
        (dispara ordem a mercado quando o nivel rompe) -- nunca uma ordem-
        stop registrada. Processo morto/reiniciado = posicao nua. O dono:
        "nao colocou alvo e estope".

        Os tres ajustes mecanicos (arredondar para `trade_tick_size`, afastar
        pela distancia minima da corretora, nunca afrouxar/apagar) moram em
        `_niveis_protecao`, compartilhado com os dois caminhos atomicos.

        Devolve `{"ok": bool, "note": str, "sl": float, "tp": float}` --
        NUNCA levanta (mesmo padrao do resto da classe): falhar ao proteger
        nao pode derrubar o runtime que acabou de confirmar um fill de
        verdade, mas tambem nao pode desaparecer em silencio -- quem chama
        loga alto e tenta de novo no proximo passo (ver
        `IntradayLiveRuntime._ensure_protecao`). `sl`/`tp` no retorno sao os
        niveis REGISTRADOS, que podem diferir do pedido (distancia minima da
        corretora); quem chama guarda esse par para nao ficar reenviando a
        cada barra um pedido que a corretora sempre ajusta do mesmo jeito."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception as exc:  # pragma: no cover - ambiente sem o pacote
            return {"ok": False, "note": f"pacote MetaTrader5 indisponivel: {exc}"}
        try:
            if not self.connect():
                code, desc = self._last_error(mt5)
                return {"ok": False,
                        "note": f"falha ao conectar ao terminal MT5 (last_error={code}: {desc})"}
            symbol = self.symbol_for(ticker)
            info = mt5.symbol_info(symbol)
            if info is None:
                return {"ok": False, "note": f"simbolo {symbol} nao encontrado no terminal MT5"}

            tick = mt5.symbol_info_tick(symbol)
            preco_ref = None
            if tick is not None:
                bid = float(getattr(tick, "bid", 0.0) or 0.0)
                ask = float(getattr(tick, "ask", 0.0) or 0.0)
                preco_ref = (bid if side == "long" else ask) or None

            sl, tp, avisos = self._niveis_protecao(
                mt5, symbol, side, stop, target, preco_ref,
                sl_atual=sl_atual, tp_atual=tp_atual, info=info,
            )
            if sl <= 0.0 and tp <= 0.0:
                # Nada para registrar E nada registrado para preservar --
                # mandar `sl=0, tp=0` aqui seria um pedido explicito de
                # REMOVER protecao, o oposto do que este metodo existe para
                # fazer. Melhor nao enviar request nenhum.
                return {"ok": False, "sl": 0.0, "tp": 0.0,
                        "note": "nem stop nem alvo para registrar (e nada registrado a "
                                "preservar) -- nao vou mandar SLTP zerado, que APAGARIA "
                                "protecao em vez de por"}

            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": int(position_ticket),
                "symbol": symbol,
                "sl": float(sl),
                "tp": float(tp),
            }
            result = mt5.order_send(request)
            if result is None:
                code, desc = self._last_error(mt5)
                return {"ok": False, "sl": sl, "tp": tp,
                        "note": f"order_send (SLTP) devolveu None (last_error={code}: {desc})"}
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return {"ok": False, "sl": sl, "tp": tp,
                        "note": (f"MT5 recusou SL/TP (retcode={result.retcode}): "
                                 f"{getattr(result, 'comment', '')}")}
            nota = f"protecao registrada: sl={sl:.4f} tp={tp:.4f}"
            if avisos:
                nota += " (" + "; ".join(avisos) + ")"
            return {"ok": True, "note": nota, "sl": float(sl), "tp": float(tp)}
        except Exception as exc:
            return {"ok": False, "sl": 0.0, "tp": 0.0,
                    "note": f"erro inesperado ao registrar protecao: {exc}"}

    def account_risk_state(self) -> Optional[dict]:
        """Equity/margem livre da conta AGORA -- o freio duro de ruina (gap
        fechado depois do incidente 2026-08-28: a conta chegou a equity
        NEGATIVA, -R$298,60, com o processo CONTINUANDO a tentar abrir e
        fechar ordem, sem nenhum freio; o motor de BACKTEST ja tem
        `wiped_out_at` para isto, o lado ao vivo nao tinha equivalente).

        Devolve `{"equity", "margin_free", "balance"}` (todos em R$) ou
        `None` se nao deu para perguntar (terminal fechado, pacote ausente)
        -- mesma politica de erro do resto da classe: "nao sei" nunca vira
        "esta zerado" nem "esta seguro". Quem chama (`IntradayLiveRuntime.
        _check_freio_duro`) so' trava a operacao quando o numero volta e ele
        e' realmente ruim."""
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
            return {
                "equity": float(getattr(info, "equity", 0.0) or 0.0),
                "margin_free": float(getattr(info, "margin_free", 0.0) or 0.0),
                "balance": float(getattr(info, "balance", 0.0) or 0.0),
            }
        except Exception:
            return None

    def margin_required(self, ticker: str, side: str, quantity: int,
                        price: float) -> Optional[float]:
        """Quanto de MARGEM a corretora exige para abrir esta ordem, em R$.
        `None` = nao deu para perguntar (nunca "e' de graca").

        Quem responde e' o proprio terminal (`mt5.order_calc_margin`), nao
        uma conta nossa. Isso importa por dois motivos, os dois aprendidos
        no incidente 2026-08-28:

        1. **A margem real e' da CORRETORA, nao da nossa tabela.** O projeto
           documenta R$150 para WDO e R$100 para WIN, mas esses numeros sao
           de tabela e mudam (a B3 remarca margem em dia volatil). Perguntar
           evita operar contra um numero velho.
        2. **Serve para comparar com `margin_free`, que e' da CONTA INTEIRA.**
           Todos os slots de day trade usam o MESMO login MT5 -- a mesma
           conta, a mesma margem fisica. Qualquer teto calculado a partir de
           `initial_capital` local a UM processo e' cego para o que o OUTRO
           slot ja comprometeu. `margin_free` nao e': ele ja desconta tudo
           que qualquer robo (ou o proprio dono, na mao) abriu. E' a unica
           fonte que ve a conta como ela e'.

        `quantity` e' em ACOES/CONTRATOS (unidade de `Order.quantity`), como
        no resto da classe; a conversao para lote e' a mesma de qualquer
        envio (`_resolve_volume`), entao o numero devolvido corresponde a'
        ordem que de fato sairia -- nao a uma aproximacao."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception:  # pragma: no cover - ambiente sem o pacote
            return None
        try:
            if not self.connect():
                return None
            symbol = self.symbol_for(ticker)
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
            if info is None:
                return None
            volume = self._resolve_volume(quantity, info)
            if volume <= 0:
                return None
            tipo = (mt5.ORDER_TYPE_BUY if str(side).lower() == "long"
                    else mt5.ORDER_TYPE_SELL)
            valor = mt5.order_calc_margin(tipo, symbol, volume, float(price))
            if valor is None:
                return None
            return float(valor)
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
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception:  # pragma: no cover - ambiente sem o pacote
            # Era o UNICO metodo da classe com o import FORA do `try` -- numa
            # maquina sem o pacote ele levantava `ModuleNotFoundError` em vez
            # de devolver `None` como todos os outros. Quem chama
            # (`IntradayLiveRuntime._check_autotrading`) trata `None` como
            # "nao deu para saber"; uma excecao ali derrubava o passo inteiro.
            return None

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

    # Letra de mes de vencimento B3/CME: F=Jan G=Fev H=Mar J=Abr K=Mai M=Jun
    # N=Jul Q=Ago U=Set V=Out X=Nov Z=Dez. `\d{1,2}` cobre ano de 1 ou 2
    # digitos (corretoras variam).
    _PADRAO_CONTRATO_VENCIMENTO = "[FGHJKMNQUVXZ]\\d{1,2}$"

    #: Quantas barras M1 recentes somar para o desempate de liquidez em
    #: `_volume_recente_do_contrato` -- generoso o bastante pra suavizar um
    #: minuto atipico sem pedir historico caro a cada chamada (esta funcao
    #: roda a cada "Iniciar operacao", nunca em loop apertado).
    _BARRAS_VOLUME_CONTRATO = 10

    def _volume_recente_do_contrato(self, mt5, nome: str) -> float:
        """Volume de negociacao RECENTE de `nome`, para desempatar qual
        contrato concentra a liquidez em `detect_futures_symbol_map`.

        Prefere a soma de `_BARRAS_VOLUME_CONTRATO` barras M1 recentes
        (`copy_rates_from_pos`) a um tick unico: um so' negocio (ou um tick
        de BOOK sem trade nenhum) e' ruido demais pra decidir qual dos dois
        contratos e' o corrente. Cai para o volume do ULTIMO TICK
        (`symbol_info_tick(...).volume`, o criterio antigo, unico) so' se as
        barras nao vierem -- terminal sem historico pronto para o simbolo
        ainda, ou o modulo `MetaTrader5` (real ou fake de teste) nao expor
        `copy_rates_from_pos` -- nunca deixa a deteccao inteira falhar por
        causa disto."""
        copia = getattr(mt5, "copy_rates_from_pos", None)
        timeframe = getattr(mt5, "TIMEFRAME_M1", None)
        if copia is not None and timeframe is not None:
            try:
                barras = copia(nome, timeframe, 0, self._BARRAS_VOLUME_CONTRATO)
            except Exception:
                barras = None
            if barras is not None and len(barras) > 0:
                try:
                    return float(sum(float(b["tick_volume"]) for b in barras))
                except Exception:
                    pass
        tick = mt5.symbol_info_tick(nome)
        return float(getattr(tick, "volume", 0.0) or 0.0) if tick is not None else 0.0

    def detect_futures_symbol_map(self, tickers) -> Optional[dict[str, str]]:
        """Descobre, para cada ticker terminado em `"@"` (convencao do
        projeto para futuro B3 CONTINUO/ajustado -- `WDO@`, `WIN@`), qual e' o
        contrato REAL com vencimento em aberto no terminal MT5 AGORA -- sem
        depender de calendario de vencimento hardcoded em lugar nenhum,
        porque a B3 rola WDO todo mes e WIN a cada dois meses e ninguem devia
        precisar editar codigo/config toda vez que isso acontece.

        Por que isto e' preciso: o simbolo `@` normalmente so' existe no
        terminal para dar COTACAO/HISTORICO continuo -- e' dele que vem o
        preco que a estrategia usa pra decidir (dado valido, e' a mesma serie
        contra a qual o robo foi validado no backtest). Mas o SERVIDOR da
        corretora tipicamente recusa ordem nele (`trade_mode` desabilitado no
        simbolo -- retcode 10017 `TRADE_DISABLED`, achado ao vivo em
        2026-08-28 no slot do WDO F1: `mt5.symbol_info("WDO@").trade_mode`
        veio desligado enquanto a cotacao seguia chegando normal). O contrato
        que de fato negocia tem codigo de vencimento explicito -- raiz +
        LETRA DO MES + ANO (ver `_PADRAO_CONTRATO_VENCIMENTO` abaixo pra
        tabela letra->mes; a letra/ano exatos dependem so' de QUANDO isto
        roda, nunca fixos aqui).

        Estrategia de deteccao: lista todo simbolo do terminal que comeca com
        a RAIZ do ticker (`mt5.symbols_get(raiz + "*")`), filtra pelos que
        batem o padrao RAIZ+LETRA_DE_MES+ANO, descarta os com `trade_mode`
        desabilitado E os SEM BOOK DE DOIS LADOS (`bid`/`ask` -- ver abaixo),
        e entre os que sobram escolhe o de MAIOR VOLUME RECENTE (ver
        `_volume_recente_do_contrato`) -- o contrato corrente (front month)
        e' sempre o mais liquido por construcao (e' pra ele que a liquidez
        migra antes do vencimento do anterior). Nao precisa saber QUAL mes
        e' o corrente: o proprio mercado (via volume) responde isso a cada
        chamada, entao o mapa se autocorrige sozinho a cada rolagem, sem
        gente trocar codigo/config — e' chamado de novo a cada "Iniciar
        operacao" no painel (ver `dashboard/live_control.py::
        detect_futures_symbol_map`), entao um robo reiniciado no mes
        seguinte ja pega o contrato novo sozinho.

        Exigir BOOK DE DOIS LADOS (`bid > 0` E `ask > 0`) e' o gap fechado
        depois do incidente 2026-08-28: num restart, esta funcao escolheu
        `WDOQ27` (maior volume no criterio antigo, de TICK UNICO) em vez do
        contrato corrente correto -- confirmado depois, na mao, que `WDOQ27` tinha
        `bid=0.0` (sem mercado real; o "volume" veio de um negocio velho
        preso no ultimo tick). Um contrato sem book de dois lados e' um
        contrato MORTO, mesmo com `trade_mode` habilitado e um numero de
        volume qualquer no tick -- nunca deve ser escolhido, custe o que
        custar ao desempate.

        Tickers que NAO terminam em `"@"` mapeiam para `symbol_for(ticker)`
        (comportamento de sempre, sem envolver deteccao nenhuma) -- mesmo
        contrato de "mapa parcial nao quebra tudo" de
        `detect_fractional_symbol_map`: um ticker `@` sem NENHUM contrato
        tradavel (ou sem NENHUM com book de dois lados) mapeia pra ele mesmo
        (degrada pro sintoma atual, `TRADE_DISABLED` ao mandar ordem, em vez
        de escolher um contrato morto ou derrubar a deteccao inteira por
        causa de UM ticker).

        Devolve `None` so' se a conexao falhar (mesmo padrao do resto da
        classe)."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring do modulo
        except Exception:
            return None
        try:
            if not self.connect():
                return None
            result: dict[str, str] = {}
            disabled = getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", 0)
            for ticker in tickers:
                base = self.symbol_for(ticker)
                if not base.endswith("@"):
                    result[ticker] = base
                    continue
                raiz = base[:-1]
                candidatos = mt5.symbols_get(raiz + "*") or ()
                padrao = re.compile(f"^{re.escape(raiz)}{self._PADRAO_CONTRATO_VENCIMENTO}")
                melhor_nome = None
                melhor_volume = -1.0
                for info in candidatos:
                    nome = getattr(info, "name", None)
                    if not nome or not padrao.match(nome):
                        continue
                    if getattr(info, "trade_mode", disabled) == disabled:
                        continue
                    mt5.symbol_select(nome, True)
                    tick = mt5.symbol_info_tick(nome)
                    # Gap (d), incidente 2026-08-28: um contrato sem BOOK DE
                    # DOIS LADOS e' morto, mesmo tradavel e mesmo com volume
                    # no tick (negocio velho, sem ninguem comprando/vendendo
                    # agora) -- nunca escolher, ver a docstring do metodo.
                    if tick is None:
                        continue
                    bid = float(getattr(tick, "bid", 0.0) or 0.0)
                    ask = float(getattr(tick, "ask", 0.0) or 0.0)
                    if bid <= 0.0 or ask <= 0.0:
                        continue
                    volume = self._volume_recente_do_contrato(mt5, nome)
                    if volume > melhor_volume:
                        melhor_volume = volume
                        melhor_nome = nome
                result[ticker] = melhor_nome if melhor_nome is not None else base
            return result
        except Exception:
            return None
