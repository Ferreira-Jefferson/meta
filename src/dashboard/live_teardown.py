"""Desmontar um robô de day trade sem deixar rastro vivo na corretora.

Existe por um buraco que só aparece na hora de apagar: "Remover robô" apagava
a linha do banco e nada mais. O processo supervisor continuava rodando (o
endpoint recusava justamente por isso, empurrando o problema para o dono), e
o que estivesse pendurado no MT5 — ordem-limite esperando fila, posição
aberta — continuava lá, agora **invisível**, porque o cartão que o mostrava
tinha acabado de sumir da tela. Ordem órfã não é hipótese: em 25/08/2026 o
slot `dt-gremah_tick-pmam3-live` passou o pregão inteiro com uma limite viva
na Rico sendo reancorada a cada 30 min.

A regra que organiza este módulo: **conferir antes, agir depois, e nunca agir
sobre o que não deu para conferir**. `inspecionar()` só lê — é o que alimenta
o popup de confirmação; `remover()` só roda depois de o dono ver aquela lista
e confirmar. Entre uma e outra o mundo pode ter mudado (uma limite preencheu
no meio), então `remover()` relê tudo em vez de confiar no que a tela mostrou.

POR QUE ISTO FALA COM A CORRETORA DE DENTRO DO DASHBOARD

`live_service.get_status()` tem proibição explícita de disparar I/O na
corretora: ele roda a cada poll de 20s, em toda aba aberta. Aqui é o oposto
disso — uma ação única, iniciada por um clique, que só faz sentido contra o
estado REAL do terminal. É o mesmo caminho que `live_control.
_broker_for_detection()` já usa para descobrir `shares_per_lot` no clique de
"Iniciar operação".

O QUE ESTE MÓDULO NÃO É

Não é regra de trade. Não decide quando sair, a que preço, nem se vale a pena
— quem manda é o dono, com o número na frente. A única ordem que ele emite é
o fechamento a mercado do que o dono confirmou encerrar (decisão dele,
2026-08-25), e o P&L mostrado antes é ESTIMATIVA pelo último preço, nunca
promessa de execução.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from core.live_models import Fill, Order, OrderSide, OrderStatus, OrderType

#: Abaixo disto o caixa é considerado zerado — mesma tolerância que
#: `dashboard/app.py::operacao_caixa` usa no ledger manual (capital pequeno:
#: o default de R$1,00 de `reconcile_cash` engoliria meio real de um caixa de
#: R$30).
_TOLERANCIA_CAIXA = 0.005


@dataclass(frozen=True)
class OrdemPendurada:
    """Uma ordem-limite viva na corretora, como ela é lá — não como o nosso
    diário acha que ela está."""

    ticket: str
    side: str
    quantity: int
    price: float
    symbol: str

    @property
    def descricao(self) -> str:
        return (f"#{self.ticket} — {self.side} de {self.quantity} {self.symbol} "
                f"a R$ {self.price:.2f}".replace(".", ","))


@dataclass(frozen=True)
class Pendencias:
    """Tudo que sobreviveria à remoção deste robô se ninguém fizesse nada.

    Os três `Optional` do meio carregam uma distinção que o painel precisa
    respeitar: `[]`/`None` em `ordens` não é a mesma coisa. `[]` é "perguntei
    à corretora e não há nenhuma"; `None` é "não consegui perguntar" — e
    apagar um robô real sem conseguir perguntar é exatamente como se cria uma
    ordem órfã."""

    slot_id: str
    label: str
    symbol: str
    modo: Optional[str]
    processo_pid: Optional[int]
    #: O saldo que o dono VÊ no cartão — `cash_for(modo)`, ou seja
    #: `cash_sombra` num robô de sombra e `cash` num real. É este que o
    #: diálogo nomeia: mostrar outro número aqui obrigaria o dono a decidir
    #: sobre um valor que ele nunca viu na tela (achado em 2026-08-26 no banco
    #: real: `dt-gremah-pmam3-shadow` tinha cash=20,00 e cash_sombra=35,92, e
    #: o cartão mostrava 35,92).
    caixa: float
    #: O ledger de dinheiro REAL alocado a este robô. Igual a `caixa` num robô
    #: real; num de sombra é a outra metade — e é o que `remover()` zera antes
    #: de apagar a conta, porque é o que `delete_account` guarda.
    caixa_real: float = 0.0
    ordens: Optional[list[OrdemPendurada]] = None
    posicao: Optional[dict] = None
    preco_atual: Optional[float] = None
    erro_corretora: Optional[str] = None
    erro_processo: Optional[str] = None

    @property
    def consultou_corretora(self) -> bool:
        return self.erro_corretora is None

    @property
    def e_sombra(self) -> bool:
        """Robô em modo sombra nunca mandou ordem para a corretora — é
        invariante do sistema (`IntradayLiveRuntime` nasce sem `executor` em
        sombra), não suposição otimista. Por isso um sombra pode ser apagado
        mesmo com o terminal fechado."""
        return self.modo == "shadow"

    @property
    def pl_estimado(self) -> Optional[float]:
        """Resultado que encerrar a posição a mercado realizaria, pelo último
        preço negociado. `None` quando não há posição ou não há preço.

        Bruto, sem corretagem: o valor existe para o dono decidir com ordem
        de grandeza na tela, e inventar uma taxa aqui daria falsa precisão a
        um número que já é estimativa (o preço de execução real depende da
        fila)."""
        if not self.posicao or not self.preco_atual:
            return None
        entrada = float(self.posicao.get("price") or 0.0)
        qtd = int(self.posicao.get("quantity") or 0)
        if entrada <= 0 or qtd <= 0:
            return None
        delta = self.preco_atual - entrada
        if self.posicao.get("side") == "short":
            delta = -delta
        return round(delta * qtd, 2)

    @property
    def tem_o_que_desfazer(self) -> bool:
        """Há algo além de apagar uma linha do banco? É o que decide se o
        clique abre o popup de confirmação ou remove direto."""
        return bool(self.processo_pid
                    or self.ordens
                    or self.posicao
                    or abs(self.caixa) >= _TOLERANCIA_CAIXA
                    or abs(self.caixa_real) >= _TOLERANCIA_CAIXA)

    @property
    def impedimento(self) -> Optional[str]:
        """Motivo para NÃO deixar remover agora, ou `None`.

        Só um caso: robô que pôde mandar ordem de verdade e cuja corretora
        não respondeu. Aí "remover" não sabe o que está apagando."""
        if self.e_sombra or self.consultou_corretora:
            return None
        return (
            f"não consegui perguntar à corretora o que {self.label} tem pendurado "
            f"({self.erro_corretora}). Como ele opera em modo real, remover agora "
            "poderia deixar ordem ou posição viva no MT5 e invisível aqui — abra o "
            "terminal MT5 e tente de novo."
        )


@dataclass
class ResultadoRemocao:
    """O que de fato aconteceu, para a tela contar em vez de prometer."""

    slot_id: str
    label: str
    processo_encerrado: Optional[int] = None
    ordens_canceladas: list[str] = field(default_factory=list)
    posicao_encerrada: Optional[dict] = None
    caixa_zerado: Optional[float] = None
    conta_apagada: bool = False
    #: Removido do painel COM o histórico guardado (`archived_at`), em vez de
    #: apagado. Mutuamente exclusivo com `conta_apagada`: os dois são o mesmo
    #: fim de linha (o cartão sai da tela, o ativo fica livre) por caminhos
    #: diferentes.
    conta_arquivada: bool = False
    avisos: list[str] = field(default_factory=list)

    @property
    def removido(self) -> bool:
        """O robô saiu do painel? É o que separa "deu certo" de "parei no
        meio" — e não interessa por qual dos dois caminhos ele saiu."""
        return self.conta_apagada or self.conta_arquivada

    @property
    def resumo(self) -> str:
        partes = [f"Robô {self.label} removido" if self.removido
                  else f"Robô {self.label} NÃO foi removido"]
        if self.processo_encerrado:
            partes.append(f"processo {self.processo_encerrado} encerrado")
        if self.ordens_canceladas:
            partes.append(f"{len(self.ordens_canceladas)} ordem(ns) cancelada(s)")
        if self.posicao_encerrada:
            pl = self.posicao_encerrada.get("pl")
            preco = self.posicao_encerrada.get("price")
            texto = f"posição encerrada a R$ {preco:.2f}" if preco else "posição encerrada"
            if pl is not None:
                texto += f" ({'lucro' if pl >= 0 else 'prejuízo'} de R$ {abs(pl):.2f})"
            partes.append(texto)
        if self.caixa_zerado:
            partes.append(f"caixa de R$ {self.caixa_zerado:.2f} zerado")
        if self.conta_arquivada:
            partes.append("histórico guardado (recrie o mesmo robô neste ativo "
                          "para restaurá-lo)")
        return " · ".join(partes) + "."


# ---------- montagem do broker deste slot ----------------------------------

def _broker_do_slot(slot):
    """`MT5Broker` com o `magic` DESTE slot — sem isso a consulta enxergaria
    (e cancelaria) as ordens do robô vizinho, que divide a mesma conta
    NETTING. `shares_per_lot` sai da última config do processo para a
    quantidade aparecer em AÇÕES na tela, igual ao resto do painel."""
    from dashboard import live_control
    from live.broker_mt5 import MT5Broker

    creds = live_control.load_credentials()
    login = creds.get("mt5_login")
    config = live_control.last_config(slot.id) or {}
    return MT5Broker(
        magic=slot.magic,
        shares_per_lot=float(config.get("mt5_shares_per_lot") or 1.0),
        login=int(login) if login else None,
        password=creds.get("mt5_password"),
        server=creds.get("mt5_server"),
        path=creds.get("mt5_terminal_path"),
    )


def _modo_do_slot(slot, processo) -> Optional[str]:
    """`"live"`/`"shadow"` deste robô, na ordem em que essas fontes merecem
    confiança: o próprio slot (o modo é parte da IDENTIDADE dele desde
    2026-08-24, fixo na criação), depois o processo que está rodando agora,
    depois a última config gravada. `None` = nenhuma das três sabe, e aí
    `Pendencias` trata como real, que é o lado seguro."""
    from dashboard import live_control

    if slot.execution_mode:
        return slot.execution_mode
    if processo is not None and processo.execution_mode:
        return processo.execution_mode
    config = live_control.last_config(slot.id) or {}
    return config.get("execution_mode")


def _processo_do_slot(slot_id: str):
    """`ProcessoRobo` deste slot, ou `(None, erro)`. Usa o inventário do
    sistema operacional, e não `status()`: o caso que motivou tudo isto é
    justamente o processo que o arquivo de estado NÃO conhece mais."""
    from dashboard import live_control

    try:
        for processo in live_control.listar_processos():
            if processo.slot == slot_id:
                return processo, None
    except live_control._TasklistUnavailable as e:  # noqa: SLF001
        return None, str(e)
    return None, None


# ---------- leitura ---------------------------------------------------------

def inspecionar(slot) -> Pendencias:
    """O que este robô deixaria para trás. NÃO muta nada, nem no banco nem na
    corretora — é o que o popup mostra antes de o dono confirmar."""
    from journal import live_store

    processo, erro_processo = _processo_do_slot(slot.id)
    modo = _modo_do_slot(slot, processo)

    caixa = caixa_real = 0.0
    posicao_sombra = None
    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, slot.id)
        if conta is not None:
            # `modo` pode ser `None` (nenhuma das três fontes sabe); aí vale o
            # lado seguro, o mesmo que `Pendencias.impedimento` assume: real.
            caixa = float(conta.cash_for(modo or "live"))
            caixa_real = float(conta.cash)
            if slot.symbol:
                posicao_sombra = conta.positions.get(slot.symbol)

    base = dict(
        slot_id=slot.id, label=slot.label, symbol=slot.symbol or "",
        modo=modo, processo_pid=processo.pid if processo else None,
        caixa=caixa, caixa_real=caixa_real, erro_processo=erro_processo,
    )

    # Sombra nunca mandou ordem: perguntar à corretora custaria uma conexão
    # para receber, por construção, lista vazia. Mas uma posição SIMULADA
    # (`live_positions`, a mesma tabela que o robô real usa) pode existir de
    # verdade -- ela é o que `delete_account`/`archive_account` recusam se
    # ninguém a encerrar antes (achado em 2026-08-28: robô de sombra parado
    # há um dia com posição aberta no registro, e a remoção falhava com uma
    # mensagem que fala de MT5 num robô que nunca chegou perto de um). Expor
    # aqui é o que faz o popup avisar e `remover()` saber o que fechar.
    if modo == "shadow" or not slot.symbol:
        if posicao_sombra is None:
            return Pendencias(ordens=[], **base)
        from dashboard.robot_view import _ultimo_preco

        preco_atual, _ = _ultimo_preco(slot.symbol)
        posicao = {
            "side": posicao_sombra.metadata.get("side") or "long",
            "quantity": posicao_sombra.quantity,
            "price": posicao_sombra.entry_price,
        }
        return Pendencias(ordens=[], posicao=posicao, preco_atual=preco_atual, **base)

    broker = _broker_do_slot(slot)
    try:
        if not broker.connect():
            return Pendencias(erro_corretora="terminal MT5 não respondeu", **base)
        ordens = broker.pending_orders(slot.symbol)
        if ordens is None:
            return Pendencias(
                erro_corretora="a consulta de ordens pendentes não voltou", **base)
        # `position_state`, não `open_position`: aquele achata "não há posição"
        # e "não consegui perguntar" no mesmo `None`, e aqui a diferença decide
        # se o dono pode apagar o robô. Ler errado deixaria uma posição real
        # órfã no terminal, que é a falha nº 1 da lista no topo deste arquivo.
        estado = broker.position_state(slot.symbol)
        if not estado.get("ok"):
            return Pendencias(
                erro_corretora=f"a leitura da posição não voltou: {estado.get('note', '')}",
                **base)
        posicao = estado.get("position")
        preco = broker.last_price(slot.symbol) if posicao else None
    except Exception as e:  # noqa: BLE001 - qualquer falha aqui é "não sei"
        return Pendencias(erro_corretora=f"{type(e).__name__}: {e}", **base)

    return Pendencias(
        ordens=[OrdemPendurada(**o) for o in ordens],
        posicao=posicao, preco_atual=preco, **base,
    )


# ---------- ação ------------------------------------------------------------

def remover(slot, apagar_historico: bool = False) -> ResultadoRemocao:
    """Desmonta o robô inteiro, nesta ordem — e a ordem importa:

      1. **mata o processo** primeiro. Enquanto ele vive, ele reancora
         ordem-limite a cada poucos segundos: cancelar antes de matar é
         cancelar algo que o robô recria em seguida;
      2. **cancela as ordens pendentes**, para nada mais poder virar posição;
      3. **encerra a posição a mercado**, se houver (decisão do dono,
         2026-08-25: remover não pode deixar posição órfã viva no MT5);
      4. tira o robô do painel — **guardando** ou **apagando** o histórico.

    Os passos 1 a 3 são iguais nos dois casos, e não são negociáveis: eles
    tratam de dinheiro exposto na corretora, não de registro. `apagar_historico`
    decide só o destino do que está no NOSSO banco (pedido do dono,
    2026-08-26):

      * `False` (padrão) — `archive_account`: a conta continua inteira, com
        diário, trades e caixa. O cartão sai da tela, o ativo fica livre, e
        recriar o mesmo trio (robô, ativo, modo) oferece restaurar tudo. O
        padrão é este porque é o único dos dois que dá para desfazer;
      * `True` — o de sempre: zera o caixa e `delete_account`, que leva junto
        tudo que pende da conta (`ON DELETE CASCADE`).

    Relê a corretora em vez de confiar na inspeção que alimentou o popup: um
    limite pode ter preenchido entre a tela e o clique, e cancelar por uma
    lista velha deixaria a posição nova para trás.

    Levanta `ValueError` — sem ter tocado em nada — quando o robô é real e a
    corretora não respondeu. Meio caminho é o pior desfecho possível aqui.
    """
    from journal import live_store

    pend = inspecionar(slot)
    if pend.impedimento:
        raise ValueError(pend.impedimento)

    resultado = ResultadoRemocao(slot_id=slot.id, label=slot.label)

    if pend.processo_pid is not None:
        from dashboard import live_control

        try:
            live_control.encerrar_processo(pend.processo_pid)
            resultado.processo_encerrado = pend.processo_pid
        except ValueError:
            # Morreu sozinho entre a inspeção e agora — o objetivo já está
            # cumprido, não é falha.
            resultado.avisos.append(
                f"o processo {pend.processo_pid} já não estava mais rodando.")

    if pend.e_sombra:
        # Sombra nunca teve corretora: a "posição" aqui é só uma linha em
        # `live_positions`, a mesma tabela que o robô real usa para
        # bookkeeping -- sem encerrá-la, `delete_account`/`archive_account`
        # recusam com o MESMO guard que protege um robô real de virar posição
        # órfã no MT5, só que não há MT5 nenhum para essa exposição existir.
        if pend.posicao:
            _encerrar_posicao_sombra(slot, resultado)
    elif pend.consultou_corretora and not pend.posicao:
        # A corretora CONFIRMOU que não há posição. Se o banco ainda tem uma,
        # os dois discordam -- e sem reconciliar aqui a remoção fica presa
        # para sempre (ver `_descartar_posicao_fantasma`). Ordens pendentes,
        # se houver, continuam sendo canceladas logo abaixo.
        _descartar_posicao_fantasma(slot, resultado)
        if pend.ordens and not _limpar_na_corretora(slot, resultado):
            resultado.avisos.append(
                f"a conta de {slot.label} NÃO foi apagada: sobrou ordem viva na "
                "corretora.")
            return resultado
    elif pend.ordens or pend.posicao:
        if not _limpar_na_corretora(slot, resultado):
            # Posição que não fechou é o único desfecho em que apagar a conta
            # seria PIOR que parar no meio: o robô sai da tela e a exposição
            # continua no MT5, que é exatamente a órfã invisível que este
            # módulo existe para impedir. O processo já morreu e as ordens já
            # foram canceladas — todo o progresso é no sentido seguro — e o
            # cartão continua ali para o dono ver e tentar de novo.
            resultado.avisos.append(
                f"a conta de {slot.label} NÃO foi apagada: enquanto houver posição "
                "aberta na corretora, remover o robô a deixaria viva e invisível "
                "aqui.")
            return resultado

    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, slot.id)
        if conta is None:
            resultado.conta_apagada = True
            return resultado
        if not apagar_historico:
            live_store.archive_account(conn, slot.id)
            resultado.conta_arquivada = True
            return resultado
        if abs(conta.cash) >= _TOLERANCIA_CAIXA:
            anterior = float(conta.cash)
            live_store.reconcile_cash(
                conn, conta, 0.0, date.today(), origin="remocao_robo",
                note=f"caixa zerado ao remover o robô {slot.label}",
                tolerance=_TOLERANCIA_CAIXA,
            )
            resultado.caixa_zerado = anterior
        live_store.delete_account(conn, slot.id)
        resultado.conta_apagada = True

    # A linha deste slot em `db/live_process.json` vira lixo no instante em
    # que a conta deixa de existir: ela guarda a config de retomada de um robô
    # que não tem mais para onde retomar. `stop()` só zera o `pid` (de
    # propósito -- ver a docstring dele: o formulário continua pré-preenchido
    # depois de parar), então quem apaga de vez é aqui.
    #
    # Só no caminho que APAGA. Com o histórico guardado, esta linha é parte do
    # que foi guardado: é ela que traz de volta capital, `shares_per_lot` e o
    # resto da config quando o dono restaurar o robô — sem ela, restaurar
    # devolveria o diário mas mandaria o dono redigitar a configuração.
    from dashboard import live_control

    live_control.esquecer(slot.id)
    return resultado


def _limpar_na_corretora(slot, resultado: ResultadoRemocao) -> bool:
    """Cancela as pendentes e encerra a posição, relendo a corretora agora.
    Devolve se a corretora ficou LIMPA — é o que autoriza apagar a conta.

    Falha de ordem vira AVISO em vez de exceção: uma que não cancelou não
    pode impedir que as outras cancelem nem que a posição seja encerrada, e o
    dono precisa terminar sabendo o que ficou para trás. Mas ela também
    **impede a conta de ser apagada** (`False`), junto com a posição aberta.

    Isso é uma CORREÇÃO de premissa (2026-08-28). O texto que estava aqui
    dizia que "ordem pendurada que sobrou não tem risco de mercado enquanto
    não preenche" — e é exatamente ao contrário: uma ordem-limite viva no
    book preenche sozinha, sem ninguém clicar em nada, e abre uma posição
    real. Apagar a conta nesse estado deixa essa posição nascendo sem robô,
    sem stop, sem diário e sem linha no painel. "Enquanto não preenche" não
    é uma garantia, é o intervalo antes do problema.

    Piorava por um segundo motivo, já corrigido: `MT5Broker.cancel` marcava
    `CANCELLED` mesmo quando a corretora RECUSAVA o cancelamento, então este
    laço via sucesso onde não houve e nunca chegava a avisar nada."""
    broker = _broker_do_slot(slot)
    if not broker.connect():
        resultado.avisos.append(
            "não consegui reconectar ao terminal MT5 para limpar a corretora — "
            "confira ordens e posição no MT5.")
        return False

    limpo = True
    ordens = broker.pending_orders(slot.symbol)
    if ordens is None:
        resultado.avisos.append(
            "a corretora não respondeu a lista de ordens pendentes — confira no MT5.")
        ordens = []
        # `None` é "não consegui perguntar", não "não há nenhuma" (ver a
        # docstring de `pending_orders`). Sem saber o que existe, não dá para
        # afirmar que a corretora ficou limpa.
        limpo = False
    for o in ordens:
        pedido = Order(
            ticker=slot.symbol,
            side=OrderSide.BUY if o["side"] == "compra" else OrderSide.SELL,
            quantity=int(o["quantity"]),
            order_type=OrderType.LIMIT,
            limit_price=float(o["price"]),
            broker_ref=str(o["ticket"]),
            sent_at=datetime.now(timezone.utc),
        )
        devolvida = broker.cancel(pedido)
        if devolvida.status == OrderStatus.CANCELLED:
            resultado.ordens_canceladas.append(str(o["ticket"]))
        else:
            resultado.avisos.append(
                f"a ordem #{o['ticket']} NÃO foi cancelada e pode preencher sozinha, "
                f"abrindo posição sem robô nenhum vigiando: {devolvida.note}")
            limpo = False

    estado = broker.position_state(slot.symbol)
    if not estado.get("ok"):
        # "Não consegui perguntar" nunca vira "não há posição" — apagar a
        # conta aqui deixaria uma posição real órfã no terminal.
        resultado.avisos.append(
            f"não consegui ler a posição de {slot.symbol} na corretora "
            f"({estado.get('note', '')}) — confira no MT5.")
        return False
    posicao = estado.get("position")
    if not posicao:
        return limpo
    fechamento = Order(
        ticker=slot.symbol,
        side=OrderSide.SELL if posicao["side"] == "long" else OrderSide.BUY,
        quantity=int(posicao["quantity"]),
        order_type=OrderType.MARKET,
        sent_at=datetime.now(timezone.utc),
    )
    # `close_position` (com o ticket), NUNCA `place()`: sem o campo
    # `"position"` no request o motor de risco da corretora trata a ordem
    # como ABERTURA nova e recusa quando a margem está esgotada -- foi
    # exatamente isso que travou ~24 tentativas de fechamento no incidente de
    # 2026-08-28 (`retcode=10006 [MG51] Para abrir novas posições`). Este era
    # o mesmo bug, no caminho de remover um robô: o lugar em que ele dói mais,
    # porque é o momento em que o dono está tentando sair de tudo.
    fechar_com_ticket = getattr(broker, "close_position", None)
    ticket = posicao.get("ticket")
    if fechar_com_ticket is not None and ticket is not None:
        executada = fechar_com_ticket(fechamento, ticket)
    else:
        executada = broker.place(fechamento)
    if executada.status not in (OrderStatus.FILLED, OrderStatus.PARTIAL) or not executada.avg_price:
        resultado.avisos.append(
            f"a posição de {posicao['quantity']} {slot.symbol} NÃO foi encerrada "
            f"({executada.note or executada.status.value}) — ela continua aberta no "
            "MT5 e precisa ser fechada na mão.")
        return False
    preco = float(executada.avg_price)
    entrada = float(posicao.get("price") or 0.0)
    delta = preco - entrada
    if posicao["side"] == "short":
        delta = -delta
    resultado.posicao_encerrada = {
        "quantity": int(posicao["quantity"]),
        "side": posicao["side"],
        "price": preco,
        "pl": round(delta * int(posicao["quantity"]), 2) if entrada > 0 else None,
    }
    if executada.status == OrderStatus.PARTIAL:
        resultado.avisos.append(
            f"o fechamento preencheu só {executada.filled_qty} de "
            f"{posicao['quantity']} ações — o resto continua aberto no MT5.")
        return False
    return limpo


def _descartar_posicao_fantasma(slot, resultado: ResultadoRemocao) -> None:
    """O banco tem posição aberta, a CORRETORA CONFIRMOU que não tem nenhuma.
    Apaga a linha do banco -- ela é registro errado, não exposição.

    O IMPASSE QUE ISTO DESFAZ (achado ao vivo em 2026-09-09, com o dono
    tentando remover o robô e não conseguindo). O slot real tinha em
    `live_positions` um short de 1 WDO@ @ 5122,50 que o MT5 não tinha:

      * `inspecionar()` pergunta a posição à CORRETORA -- não há -- então
        `remover()` não tinha o que encerrar e seguia adiante;
      * `delete_account`/`archive_account` recusam olhando o BANCO -- "feche
        na corretora antes de remover o robô".

    Ou seja, a única instrução que a tela sabia dar era impossível de
    cumprir: não existe o que fechar. O robô ficava preso no painel para
    sempre. O guard dos dois lados está certo em separado; o que faltava era
    alguém reconciliar quando eles discordam.

    POR QUE É SEGURO apagar aqui, e só aqui: `Pendencias.impedimento` já
    barra a remoção inteira quando a corretora NÃO respondeu, e
    `position_state()` distingue "não há posição" de "não consegui
    perguntar" (é o motivo de ele existir em vez de `open_position`). Então,
    neste ponto, "não há posição" é uma afirmação CONFIRMADA pela corretora,
    não silêncio. Registro que contradiz a corretora é o registro que está
    errado -- a corretora é a fonte de verdade sobre o que existe.

    NÃO inventa trade nem P&L, e NÃO mexe no caixa. Não houve negócio: fechar
    "a mercado" uma posição que não existe escreveria um preço de execução
    que ninguém pagou (o mesmo erro do item 1.24, pelo avesso). O caixa é o
    ledger digitado pelo dono (ver CLAUDE.md, "Saldo do MT5 não é confiável")
    -- reconstruí-lo aqui seria chutar. Fica um `warn` no diário com os dois
    lados da divergência, para a auditoria achar depois."""
    from journal import live_store

    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, slot.id)
        if conta is None:
            return
        pos = conta.positions.get(slot.symbol)
        if pos is None:
            return
        lado = pos.metadata.get("side") or "long"
        live_store.delete_position(conn, conta.id, slot.symbol)
        live_store.save_account(conn, conta)
        live_store.log_event(
            conn, conta.id, "warn", "teardown",
            f"posição de {pos.quantity} {slot.symbol} @ {pos.entry_price:.4f} existia "
            f"no REGISTRO mas NÃO na corretora (consulta confirmada) -- linha "
            f"descartada na remoção do robô, sem trade e sem mexer no caixa: não "
            f"houve negócio para registrar.",
            {"quantity": pos.quantity, "side": lado,
             "entry_price": pos.entry_price, "motivo": "divergencia_registro_x_corretora"},
        )

    resultado.avisos.append(
        f"o registro tinha uma posição de {pos.quantity} {slot.symbol} @ "
        f"{pos.entry_price:.4f} que a corretora NÃO tem — a linha foi descartada "
        "(sem trade, sem mexer no caixa). Confira o extrato: registro e corretora "
        "estavam divergentes."
    )


def _encerrar_posicao_sombra(slot, resultado: ResultadoRemocao) -> None:
    """Fecha localmente a posição SIMULADA de um robô de sombra -- ele nunca
    teve corretora para consultar, então não há ordem para cancelar nem
    posição para encerrar lá fora. Sem isto, `delete_account`/
    `archive_account` recusam com o mesmo guard que protege um robô REAL de
    virar posição órfã no MT5 (`account.positions`), apesar de não haver
    nenhuma exposição de verdade -- só uma linha em `live_positions`, a
    mesma tabela que o robô real usa para bookkeeping.

    Relê a posição agora (não confia no que `inspecionar()` viu antes do
    processo morrer, mesmo motivo de `remover()` reler a corretora): o
    processo já foi encerrado no passo anterior, então nada mais está
    escrevendo nesta conta.

    Preço de saída: o último fechamento de minuto salvo (`_ultimo_preco`),
    o mesmo número que a ficha do robô usa para estimar P&L de posição
    aberta. Sem preço salvo, sai pelo próprio preço de entrada (PnL zero)
    -- estimar é melhor que travar a remoção, mas inventar um preço seria
    pior que os dois. Credita em `cash_sombra` (nunca `cash`, o ledger
    manual real) -- mesma regra de `IntradayLiveRuntime._on_closed`."""
    from dashboard.robot_view import _ultimo_preco
    from journal import live_store

    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, slot.id)
        if conta is None:
            return
        pos = conta.positions.get(slot.symbol)
        if pos is None:
            return

        preco_atual, _ = _ultimo_preco(slot.symbol)
        preco = preco_atual if preco_atual is not None else pos.entry_price
        lado = pos.metadata.get("side") or "long"
        delta = preco - pos.entry_price
        if lado == "short":
            delta = -delta
        pnl = round(delta * pos.quantity, 2)
        liberado = pos.entry_price * pos.quantity

        ordem = Order(
            ticker=slot.symbol,
            side=OrderSide.SELL if lado == "long" else OrderSide.BUY,
            quantity=pos.quantity,
            order_type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            filled_qty=pos.quantity,
            avg_price=preco,
            sent_at=datetime.now(timezone.utc),
            note="encerrada ao remover o robô (sombra, sem corretora)",
        )
        order_id = live_store.record_order(conn, conta.id, ordem)
        live_store.record_fill(conn, Fill(
            order_id=order_id, quantity=pos.quantity, price=preco,
            ts=datetime.now(timezone.utc),
        ))
        live_store.delete_position(conn, conta.id, slot.symbol)
        conta.cash_sombra += liberado + pnl
        live_store.save_account(conn, conta)
        live_store.log_event(
            conn, conta.id, "info", "teardown",
            f"posição simulada de {pos.quantity} {slot.symbol} encerrada a "
            f"R$ {preco:.2f} ao remover o robô "
            f"({'lucro' if pnl >= 0 else 'prejuízo'} de R$ {abs(pnl):.2f})",
            {"quantity": pos.quantity, "side": lado, "price": preco, "pnl_brl": pnl},
        )

    resultado.posicao_encerrada = {
        "quantity": pos.quantity, "side": lado, "price": preco, "pl": pnl,
    }
