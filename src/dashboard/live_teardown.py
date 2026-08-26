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

from core.live_models import Order, OrderSide, OrderStatus, OrderType

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
    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, slot.id)
        if conta is not None:
            # `modo` pode ser `None` (nenhuma das três fontes sabe); aí vale o
            # lado seguro, o mesmo que `Pendencias.impedimento` assume: real.
            caixa = float(conta.cash_for(modo or "live"))
            caixa_real = float(conta.cash)

    base = dict(
        slot_id=slot.id, label=slot.label, symbol=slot.symbol or "",
        modo=modo, processo_pid=processo.pid if processo else None,
        caixa=caixa, caixa_real=caixa_real, erro_processo=erro_processo,
    )

    # Sombra nunca mandou ordem: perguntar à corretora custaria uma conexão
    # para receber, por construção, uma lista vazia.
    if modo == "shadow" or not slot.symbol:
        return Pendencias(ordens=[], **base)

    broker = _broker_do_slot(slot)
    try:
        if not broker.connect():
            return Pendencias(erro_corretora="terminal MT5 não respondeu", **base)
        ordens = broker.pending_orders(slot.symbol)
        if ordens is None:
            return Pendencias(
                erro_corretora="a consulta de ordens pendentes não voltou", **base)
        posicao = broker.open_position(slot.symbol)
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

    if pend.ordens or pend.posicao:
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
    dono precisa terminar sabendo o que ficou para trás. Posição é diferente
    de ordem: ordem pendurada que sobrou não tem risco de mercado enquanto
    não preenche, posição aberta tem — por isso só ela decide o `False`."""
    broker = _broker_do_slot(slot)
    if not broker.connect():
        resultado.avisos.append(
            "não consegui reconectar ao terminal MT5 para limpar a corretora — "
            "confira ordens e posição no MT5.")
        return False

    ordens = broker.pending_orders(slot.symbol)
    if ordens is None:
        resultado.avisos.append(
            "a corretora não respondeu a lista de ordens pendentes — confira no MT5.")
        ordens = []
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
                f"a ordem #{o['ticket']} não foi cancelada: {devolvida.note}")

    posicao = broker.open_position(slot.symbol)
    if not posicao:
        return True
    fechamento = Order(
        ticker=slot.symbol,
        side=OrderSide.SELL if posicao["side"] == "long" else OrderSide.BUY,
        quantity=int(posicao["quantity"]),
        order_type=OrderType.MARKET,
        sent_at=datetime.now(timezone.utc),
    )
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
    return True
