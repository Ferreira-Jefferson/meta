"""Contratos da operacao ao vivo — dinheiro real, nao backtest.

Vive em `core/` (e nao em `live/`) porque duas camadas precisam destes tipos:
`live/` produz e consome, `journal/` persiste. Se morassem em `live/`, o
`journal` — que e feature — teria de importar a orquestracao, invertendo a
direcao das dependencias. Mesma razao de `Trade` morar em `core/models.py`.

Por que esta camada existe separada
-----------------------------------
O backtest e a operacao ao vivo respondem a MESMA pergunta ("o que fazer hoje?")
com a MESMA logica de decisao (`strategy/` e `backtest/withdrawal.py`), mas com
contabilidade oposta:

  - no backtest, a posicao existe porque o engine SIMULOU um fill;
  - ao vivo, a posicao existe porque a corretora CONFIRMOU um fill.

Se a camada live reimplementasse a decisao, ela divergiria do robo testado no
primeiro mes — e o backtest deixaria de dizer qualquer coisa sobre a operacao.
Entao a regra dura desta camada e:

    NENHUMA REGRA DE DECISAO VIVE AQUI.

`live/` cuida de relogio, dado fresco, estado real, ciclo de vida de ordem e
persistencia. Quem decide continua sendo o robo em `strategy/` (via `on_bar`) e a
politica em `backtest/withdrawal.py` (via `on_close`/`on_liquidity_event`) — os
mesmos objetos que o backtest usa, sem fork.

Intencao != ordem
-----------------
A auditoria e separada em duas tabelas por um motivo pratico: quando um trade da
errado, a primeira pergunta e "o robo decidiu errado ou a execucao falhou?". Se
decisao e execucao compartilham a mesma linha, essa pergunta nao tem resposta.

    Intent  -> o que o robo decidiu, no fecho de D, para executar em D+1.
               Imutavel depois de gravada. E o registro do CEREBRO.
    Order   -> o que foi enviado a corretora para cumprir uma Intent.
               Uma Intent pode gerar N Orders (retry, fatiamento, rejeicao).
               E o registro do BRACO.

Anti-look-ahead ao vivo (regra 4 do AGENTS.md, versao operacional)
------------------------------------------------------------------
No backtest, "sinal no close[D] executa no open[D+1]" e uma disciplina de
codigo. Ao vivo e uma disciplina de RELOGIO, e tem uma falha que o backtest nao
tem: o processo pode cair. Por isso `Intent.execute_on` e um campo persistido e
obrigatorio, e o runtime obedece a tres regras:

  - `execute_on > hoje`  -> ainda nao; espera.
  - `execute_on == hoje`  -> executa.
  - `execute_on < hoje`  -> EXPIRA, nunca executa atrasada.

A terceira e a que importa. Uma intencao decidida na sexta e executada na
quarta seguinte (porque a maquina ficou fora do ar) nao e a decisao do robo: e
uma decisao velha aplicada a um preco que o robo nunca viu. Executar tarde e
pior que nao executar, porque contamina o historico com um trade que nenhum
backtest reproduz.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


# ---------- fases do pregao ------------------------------------------------

class SessionPhase(str, Enum):
    """Onde o relogio esta dentro do dia de negociacao da B3.

    Usada para AGENDAR (quando acordar, quando olhar preco, quando decidir) —
    nunca para julgar se um dado esta valido. Validade de dado se checa no dado
    (ver `live.runtime`), porque o relogio da maquina mente: fuso errado,
    feriado nao mapeado, pregao estendido. Relogio agenda, dado decide.
    """

    CLOSED = "closed"                     # fora de dia de pregao
    PRE_OPEN = "pre_open"                 # leilao de abertura
    OPEN = "open"                         # negociacao continua
    CLOSING_AUCTION = "closing_auction"   # leilao de fechamento
    AFTER_HOURS = "after_hours"           # after-market
    POST_CLOSE = "post_close"             # pregao encerrado, dia ainda corrente


class BrokerMode(str, Enum):
    """Vocabulário CANÔNICO de modo de corretora — o único que existe a
    partir de FEAT-001.

    Antes desta feature o vocabulário estava fraturado em três grafias:
    `paper`/`manual`/`mt5` no CLI e no `<select>` do dashboard, mas
    `paper`/`manual`/`broker` no `Broker.mode`/`live_accounts.mode` (schema).
    Essa fratura é a causa-raiz do crítico nº1 da revisão: o botão "Iniciar"
    do dashboard emitia `--mode broker` para uma conta MT5 real, o argparse
    recusava (só aceitava `paper`/`manual`/`mt5`), o processo morria na hora,
    e o dashboard continuava mostrando "rodando". `PaperBroker` sai de
    produção junto (vira dublê de teste, ver `tests/doubles.py`) — sem
    simulação no vocabulário. O modo `MANUAL` (humano confirma cada ordem)
    foi removido depois: o usuário decidiu que o robô sempre decide E
    executa sozinho, então só sobra o modo em que a corretora executa
    sozinha (`MT5`).
    """

    MT5 = "mt5"


class RobotRole(str, Enum):
    """Papel do robo dentro da conta. Um robo por papel, no maximo."""

    INVESTMENT = "investment"   # o que compra e vende (strategy/)
    WITHDRAWAL = "withdrawal"   # o que retira lucro (backtest/withdrawal.py)


# ---------- intencao (decisao do robo) ------------------------------------

class IntentKind(str, Enum):
    ENTER = "enter"
    EXIT = "exit"
    ADJUST_STOP = "adjust_stop"   # custo zero: nao gera ordem, so muda estado
    WITHDRAW = "withdraw"         # retira caixa do sistema para o caixa externo


class IntentStatus(str, Enum):
    PENDING = "pending"       # gravada, aguardando a sessao de execucao
    EXECUTING = "executing"   # ordem(ns) no ar
    DONE = "done"             # cumprida (integral ou parcialmente, ver orders)
    EXPIRED = "expired"       # a sessao de execucao passou — nunca sera executada
    CANCELLED = "cancelled"   # cancelada por um humano ou por guarda do runtime
    REJECTED = "rejected"     # a corretora recusou tudo


@dataclass
class Intent:
    """Uma decisao de robo, pronta para executar na proxima abertura.

    `decided_on` e o pregao cujo FECHO gerou a decisao; `execute_on` e o pregao
    em que ela vale. Guardar os dois (em vez de so um "created_at") e o que
    permite auditar o anti-look-ahead depois do fato: qualquer linha com
    `execute_on <= decided_on` e bug de look-ahead, e isso da para varrer com
    uma query.
    """

    robot: str                          # chave do robo que decidiu
    role: RobotRole
    kind: IntentKind
    decided_on: date                    # pregao do fecho que gerou a decisao
    execute_on: date                    # pregao em que deve ser executada
    ticker: Optional[str] = None        # None para WITHDRAW
    reason: str = ""                    # ExitReason.value, 'floor_skim', etc.
    size_hint: Optional[float] = None   # fracao do caixa (ENTER)
    stop_price: Optional[float] = None  # stop inicial (ENTER) ou novo (ADJUST_STOP)
    amount: Optional[float] = None      # valor em R$ (WITHDRAW)
    status: IntentStatus = IntentStatus.PENDING
    id: Optional[int] = None
    payload: dict = field(default_factory=dict)

    #: Marcador de CADENCIA no `payload` de uma intencao intradiaria. Ver
    #: `is_immediate` — e' o que distingue "mesmo dia porque a cadencia do robo
    #: e' de minutos" de "mesmo dia por bug de look-ahead".
    INTRADAY_CADENCE = "intraday"

    @property
    def is_immediate(self) -> bool:
        """Intencoes que NAO esperam o dia seguinte.

        Quatro excecoes legitimas a regra do D+1: `ADJUST_STOP` nao movimenta
        dinheiro (o engine tambem aplica na hora); o stop intra-dia dispara na
        propria barra — no backtest quando `low[D] <= stop`, ao vivo quando o
        preco negociado toca o stop; uma recomendacao de `WITHDRAW` por
        evento de liquidez (`execute_on == decided_on`), que nasce na mesma
        barra em que o robo de investimento acabou de vender — paridade com
        `WithdrawalRobot.on_liquidity` (`live/robots.py`), que ja antecipa a
        data da recomendacao para o dia da venda, e com
        `policy.on_liquidity_event` no engine de backtest. Isto NAO e
        look-ahead de verdade: a recomendacao nao executa nada sozinha, so
        notifica um humano — quem move dinheiro de fato e o dono, sacando
        direto na corretora, se e quando quiser.

        A quarta (2026-08-21) e' a CADENCIA INTRADIARIA
        (`payload["cadence"] == "intraday"`, ver `INTRADAY_CADENCE`): um robo
        de day trade decide no fechamento da barra `t` e executa na barra
        `t+1` do MESMO pregao, dezenas de vezes por dia (ver
        `live/intraday_runtime.py`). Para ele, `execute_on == decided_on` e' a
        verdade — nao um bug. A disciplina anti-look-ahead nao desaparece,
        muda de UNIDADE: quem a garante e' `IntradaySessionMachine`, que
        executa toda acao na ABERTURA da barra seguinte e nunca na barra que a
        gerou. O marcador vive no `payload` (nao numa coluna nova) porque
        `payload` ja e' persistido como JSON e uma coluna exigiria migration
        para uma informacao que so a leitura desta propriedade consome.
        """
        return (
            self.kind == IntentKind.ADJUST_STOP
            or self.reason == "stop"
            or (self.kind == IntentKind.WITHDRAW and self.execute_on == self.decided_on)
            or (self.payload or {}).get("cadence") == self.INTRADAY_CADENCE
        )


# ---------- ordem (execucao na corretora) ---------------------------------

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"        # a mercado
    LIMIT = "limit"          # limitada
    ON_OPEN = "on_open"      # participa do leilao de abertura (MOA)


class OrderStatus(str, Enum):
    NEW = "new"
    SENT = "sent"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    """Uma ordem enviada (ou a enviar) para cumprir uma `Intent`."""

    ticker: str
    side: OrderSide
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    status: OrderStatus = OrderStatus.NEW
    filled_qty: int = 0
    avg_price: Optional[float] = None
    fees: float = 0.0
    slippage: float = 0.0
    broker_ref: Optional[str] = None     # id da ordem no lado da corretora
    intent_id: Optional[int] = None
    id: Optional[int] = None
    sent_at: Optional[datetime] = None
    note: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.status in (OrderStatus.FILLED, OrderStatus.CANCELLED,
                               OrderStatus.REJECTED)

    @property
    def leaves_qty(self) -> int:
        """Quantidade ainda nao executada."""
        return max(0, self.quantity - self.filled_qty)


@dataclass(frozen=True)
class Fill:
    """Execucao (parcial ou total) reportada pela corretora."""

    order_id: int
    quantity: int
    price: float
    fees: float = 0.0
    ts: Optional[datetime] = None


# ---------- cotacao --------------------------------------------------------

@dataclass(frozen=True)
class Quote:
    """Preco observado, com a PROCEDENCIA colada nele.

    `delay_seconds` e `source` nao sao metadado decorativo: e a diferenca entre
    um stop que dispara no preco e um stop que dispara 15 minutos depois, no
    fundo do movimento. O feed e obrigado a declarar o proprio atraso (ver
    `live.feed`) para que o runtime possa recusar decisao intra-dia sobre dado
    atrasado em vez de descobrir isso no extrato.
    """

    ticker: str
    price: float
    ts: datetime
    source: str
    delay_seconds: float = 0.0
    volume: Optional[float] = None

    def staleness_seconds(self, now: datetime) -> float:
        """Idade do dado somada ao atraso declarado da fonte."""
        return max(0.0, (now - self.ts).total_seconds()) + self.delay_seconds


# ---------- estado real da conta ------------------------------------------

@dataclass
class LivePosition:
    """Posicao REAL — existe porque houve fill confirmado, nao porque o robo quis.

    Espelha `backtest.engine._Position` de proposito: os mesmos campos que o
    robo enxerga no backtest (`bars_held`, `current_stop`, `metadata`) tem de
    existir aqui, senao o robo se comporta diferente ao vivo por falta de
    contexto — e a divergencia seria silenciosa.
    """

    ticker: str
    quantity: int
    entry_date: date
    entry_price: float
    capital_allocated: float
    current_stop: Optional[float] = None
    fees_paid: float = 0.0
    slippage_paid: float = 0.0
    max_price_seen: float = 0.0
    min_price_seen: float = 0.0
    bars_held: int = 0
    kind: str = "main"                  # 'main' | 'satellite'
    metadata: dict = field(default_factory=dict)
    id: Optional[int] = None

    def market_value(self, price: float) -> float:
        return float(price) * self.quantity


@dataclass
class AccountState:
    """Snapshot do que a conta E neste instante — caixa, posicoes, estado do robo.

    `policy_state` existe por um detalhe que o backtest nao enfrenta: a politica
    de saque tem memoria (fila do minimo, mes ja pago, topo historico) e ao vivo
    o processo reinicia. Sem reidratar esse estado, um restart no dia 10 zera o
    contador de pregoes do mes e a politica paga fora do dia combinado — ou
    paga duas vezes no mesmo mes. Ver `live.robots.WithdrawalRobot`.
    """

    name: str
    mode: str                            # 'mt5' (ver BrokerMode)
    initial_capital: float
    cash: float
    # Saldo PARALELO, só atualizado por trade em `execution_mode="shadow"`
    # (ver `IntradayLiveRuntime._on_closed`/`_on_closed_partial`) -- nunca
    # `cash` (dinheiro real) e nunca o inverso. Existe pra medir "o que teria
    # acontecido rodando em sombra" como um SALDO de verdade (persiste entre
    # dias, ao contrário de `_SessionSnapshot.shadow_pnl_brl`, que é só o
    # resultado de HOJE) sem qualquer risco de um número simulado vazar pro
    # caixa real quando a conta troca de sombra pra live (2026-08-23, pedido
    # do dono: "separe os dois valores"). Semeado com `initial_capital` na
    # criação da conta, nunca sincronizado com depósito/saque real depois.
    cash_sombra: float = 0.0
    investment_robot: str = ""
    withdrawal_robot: str = ""
    # Ativo que ESTA conta negocia. Vazio para swing (o robo diario escolhe o
    # papel sozinho, dentro do universo dele) e obrigatorio para day trade,
    # onde a conta E' o par robo+ativo: desde 2026-08-22 o painel abre quantas
    # contas de day trade o dono quiser, uma por ativo, cada uma com processo e
    # caixa proprios. Antes disso o ativo era propriedade do ROBO (um `Gremah`
    # por chave no registry), o que impedia dois `gremah` em papeis diferentes.
    #
    # E' tambem o que garante o invariante da conta NETTING da Rico: duas
    # contas nunca podem declarar o mesmo `symbol`, senao as posicoes se
    # fundiriam numa so na corretora e os dois livros-caixa passariam a mentir
    # (ver `dashboard.live_control._assert_slots_disjuntos`).
    symbol: str = ""
    positions: dict[str, LivePosition] = field(default_factory=dict)
    withdrawn_total: float = 0.0         # somatorio historico retirado
    external_cash: float = 0.0           # caixa fora do risco (com juros)
    policy_state: dict = field(default_factory=dict)
    # Preenchido quando o dono removeu o robo GUARDANDO o historico
    # (2026-08-26): a conta continua inteira no banco -- diario, ordens,
    # trades, caixa -- e so' sai do painel. `None` = conta viva. E' o que
    # permite "remover sem perder o que eu estava rodando" e, depois,
    # recriar o mesmo trio (robo, ativo, modo) restaurando tudo em vez de
    # comecar zerado. Quem le a lista do painel (`accounts_with_symbol`)
    # filtra por este campo; quem carrega uma conta pelo nome
    # (`load_account`) NAO filtra, senao restaurar seria impossivel.
    archived_at: Optional[str] = None
    id: Optional[int] = None

    def cash_for(self, execution_mode: str) -> float:
        """Qual dos dois saldos rege esta EXECUÇÃO -- `cash_sombra` em
        `"shadow"`, `cash` em qualquer outro valor (`"live"`).

        Ponto único da regra "sombra tem o saldo dela, real tem o dele"
        (pedido do dono, 2026-08-23, depois de perceber que o gate de início
        e o de caixa-do-dia continuavam lendo `cash` mesmo com o robô
        selecionado para rodar em sombra): quem decide se um robô PODE
        operar hoje (`live.intraday_runtime.IntradayLiveRuntime._check_capital`)
        e quem decide se ele PODE COMEÇAR (`dashboard.live_control.start`,
        `dashboard.app.operacao_iniciar`) chamam este método em vez de ler
        `cash` direto -- um lugar só para a regra, não um `if` repetido (e
        potencialmente divergente) em cada chamador."""
        return self.cash_sombra if execution_mode == "shadow" else self.cash

    def invested(self, marks: dict[str, float]) -> float:
        """Valor a mercado das posicoes. `marks` = ultimo preco por ticker."""
        return float(sum(p.market_value(marks.get(t, p.entry_price))
                         for t, p in self.positions.items()))

    def equity(self, marks: dict[str, float]) -> float:
        """Carteira = caixa + posicoes. NAO inclui o caixa externo sacado."""
        return float(self.cash) + self.invested(marks)

    def patrimonio(self, marks: dict[str, float]) -> float:
        """Carteira + caixa externo — a medida honesta de risco do overlay.

        O drawdown que importa para quem opera com saque e o desta linha, nao o
        da carteira: a carteira cai no dia do saque sem ninguem ter perdido nada.
        """
        return self.equity(marks) + float(self.external_cash)


# ---------- contexto entregue aos robos ------------------------------------

@dataclass
class RobotContext:
    """Tudo que um robo precisa para decidir — e nada mais.

    Deliberadamente NAO carrega conexao de banco, feed nem corretora: um robo
    que consegue escrever no banco ou mandar ordem sozinho deixa de ser
    testavel e deixa de ser portavel para MQL5 (regra 2 do AGENTS.md). O robo
    recebe dado e estado, devolve intencao. Quem toca o mundo e o runtime.
    """

    session: date                        # pregao de referencia da decisao
    panels: dict[str, object]            # ticker -> DataFrame OHLCV ate `session`
    ibov: object                         # DataFrame do benchmark
    account: AccountState
    marks: dict[str, float]              # ultimo preco conhecido por ticker
    phase: SessionPhase = SessionPhase.POST_CLOSE
    quotes: dict[str, Quote] = field(default_factory=dict)   # so em intra-dia
