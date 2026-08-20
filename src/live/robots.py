"""Adaptador entre os objetos de decisao e o ambiente ao vivo (`Intent`).

Dois objetos ja existem e ja sao validados por backtest: o robo de
investimento (`strategy.base.Strategy`) e o robo de saque
(`backtest.withdrawal.WithdrawalPolicy`). Nenhum dos dois fala a lingua do
ambiente ao vivo — um devolve `Action` (`Enter`/`Exit`/`AdjustStop`), o outro
devolve um `float` (valor a sacar). Este modulo so TRADUZ essas respostas em
`Intent` (ver `core.live_models`); a decisao em si e sempre do objeto
decisor, nunca deste modulo.

Regra 6 do AGENTS.md, aplicada literalmente: se algum metodo aqui comecasse a
ler preco, comparar contra um limiar, ou decidir "nao, hoje nao" por conta
propria, deixaria de ser adaptador e passaria a ser um fork da estrategia —
exatamente o que o backtest deixaria de descrever. Cada metodo publico deste
arquivo delega a decisao a `strategy.on_bar(...)`, `policy.on_close(...)` ou
`policy.on_liquidity_event(...)` e so converte o retorno.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import date

import pandas as pd

from backtest.withdrawal import WithdrawalPolicy
from core.live_models import Intent, IntentKind, RobotContext, RobotRole
from strategy.base import AdjustStop, Enter, Exit, OpenPosition, Strategy


def _payload_safe(metadata: dict | None) -> dict:
    """`Enter.metadata` -> dict garantidamente serializavel em JSON.

    Guarda deliberada, nao paranoia decorativa: `metadata` e campo LIVRE da
    estrategia, e `live_store.record_intent` serializa o payload com
    `json.dumps`. Um robo que guardar um `numpy.float64` ali (o retorno cru de
    `series.loc[date]` e exatamente isso) faria a gravacao da intencao levantar
    `TypeError` — ou seja: uma decisao real do robo seria PERDIDA por causa do
    tipo de um numero de registro. Registro nunca pode derrubar decisao, entao
    o que nao for JSON nativo vira float (se der) ou string (se nao der).

    Nao mexe em `Enter.metadata` em si — o engine de backtest continua
    recebendo o dict original em `OpenPosition.metadata`.
    """
    if not metadata:
        return {}
    out: dict = {}
    for k, v in metadata.items():
        chave = str(k)
        # Escalares de numpy/pandas expoem `.item()`, que devolve o tipo
        # NATIVO equivalente. Normalizar por aqui antes dos testes de tipo
        # preserva a natureza do numero: sem isto, um `numpy.bool_(True)`
        # cairia no `float(v)` la embaixo e seria gravado como `1.0` — um
        # booleano de auditoria virando numero e ruido gratuito no diario.
        if hasattr(v, "item") and not isinstance(v, (bool, int, float, str)):
            try:
                v = v.item()
            except (AttributeError, ValueError):
                pass
        if v is None or isinstance(v, (bool, int, str)):
            out[chave] = v
        elif isinstance(v, float):
            # NaN/inf sao JSON invalido em parser estrito (o proprio sqlite
            # devolve o texto de volta, mas quem le com json.loads estrito
            # quebra) — viram None, que e o que "sem valor" significa aqui.
            out[chave] = v if math.isfinite(v) else None
        else:
            try:
                f = float(v)
                out[chave] = f if math.isfinite(f) else None
            except (TypeError, ValueError):
                out[chave] = str(v)
    return out


class LiveRobot(ABC):
    """Contrato comum aos dois papeis (`RobotRole.INVESTMENT`/`WITHDRAWAL`).

    `execute_on` chega de FORA (do runtime, que conhece o calendario de
    pregao) em vez de o robo calcular sozinho: o robo nao deve saber que dia
    e hoje nem qual e o proximo pregao — isso e relogio (regra 6 do
    AGENTS.md), e relogio mora em `live.clock`, nao aqui.
    """

    key: str
    role: RobotRole

    @abstractmethod
    def prepare(self, panels: dict[str, pd.DataFrame], ibov: pd.DataFrame) -> None:
        """Pre-calculo unico, antes do robo comecar a decidir dia a dia."""

    @abstractmethod
    def on_close(self, ctx: RobotContext, execute_on: date) -> list[Intent]:
        """Decisao do fecho de `ctx.session`, valida para `execute_on`."""

    def on_liquidity(self, ctx: RobotContext, reason: str) -> list[Intent]:
        """Reacao a um evento de liquidez (venda que acabou de creditar caixa).

        Default vazio: nem todo robo tem algo a dizer sobre isso (o de
        investimento normalmente nao; o de saque, sim).
        """
        return []

    def on_intraday(self, ctx: RobotContext) -> list[Intent]:
        """Reacao a cotacao intra-dia (ex.: stop). Default vazio."""
        return []

    def on_missed_bars(self, missed: list[date]) -> None:
        """Pregoes que passaram sem `on_close`. Default: nao faz nada."""

    def on_executed(self, intent: Intent, executed: float) -> None:
        """Confirmacao do que saiu de fato para uma intencao emitida. Default: nada."""
        return None

    def state(self) -> dict:
        """Estado a persistir para sobreviver a um restart. Default: nenhum."""
        return {}

    def restore(self, state: dict) -> None:
        """Reidrata o estado devolvido por `state()`. Default: nada a fazer."""
        return None


class InvestmentRobot(LiveRobot):
    """Adapta uma `Strategy` (`strategy/`) ao ambiente ao vivo.

    So traduz: quem decide entrar, sair ou mover o stop e sempre
    `strategy.on_bar(...)`. `key` usa `strategy.name` porque e essa mesma
    string que identifica o robo no diario e no registry de backtest — um
    robo ao vivo e o mesmo robo testado, com o mesmo nome.
    """

    role = RobotRole.INVESTMENT

    def __init__(self, strategy: Strategy) -> None:
        self.strategy = strategy
        self.key = strategy.name

    def prepare(self, panels: dict[str, pd.DataFrame], ibov: pd.DataFrame) -> None:
        self.strategy.initialize(panels, ibov)

    def on_close(self, ctx: RobotContext, execute_on: date) -> list[Intent]:
        # Espelha `_positions_view` de `engine_portfolio.py`: o robo so enxerga
        # a posicao PRINCIPAL. O robo oficial (`portfolio_dip2_hw40`) roda com
        # `satellite_pct=0.00` — satelite nao existe nesta operacao. O filtro
        # fica explicito aqui, e nao removido, para o dia em que um robo com
        # satelite ativo for ligado ao vivo (ele teria de ganhar tratamento
        # proprio, nao herdar este silenciosamente).
        views = {
            ticker: OpenPosition(
                ticker=pos.ticker,
                entry_date=pd.Timestamp(pos.entry_date),
                entry_price=pos.entry_price,
                quantity=pos.quantity,
                current_stop=pos.current_stop,
                bars_held=pos.bars_held,
                metadata=dict(pos.metadata),
            )
            for ticker, pos in ctx.account.positions.items()
            if pos.kind == "main"
        }
        actions = self.strategy.on_bar(pd.Timestamp(ctx.session), views, ctx.account.cash)

        intents: list[Intent] = []
        for act in actions:
            if isinstance(act, Enter):
                # `reason`/`payload` vem PRONTOS da estrategia (ver `Enter`
                # em `strategy/base.py`) — este wrapper so transporta. Deduzir
                # aqui o motivo de uma compra seria `live/` opinando sobre
                # decisao, o que a regra 6 do AGENTS.md proibe.
                intents.append(Intent(
                    robot=self.key, role=self.role, kind=IntentKind.ENTER,
                    decided_on=ctx.session, execute_on=execute_on,
                    ticker=act.ticker, size_hint=act.size_hint,
                    stop_price=act.initial_stop,
                    reason=act.reason,
                    payload=_payload_safe(act.metadata),
                ))
            elif isinstance(act, Exit):
                intents.append(Intent(
                    robot=self.key, role=self.role, kind=IntentKind.EXIT,
                    decided_on=ctx.session, execute_on=execute_on,
                    ticker=act.ticker, reason=act.reason.value,
                ))
            elif isinstance(act, AdjustStop):
                # Custo zero: nao espera D+1. O engine de backtest tambem
                # aplica o novo stop na hora (ver `engine_portfolio.py`), e
                # `Intent.is_immediate` cobre exatamente este caso.
                intents.append(Intent(
                    robot=self.key, role=self.role, kind=IntentKind.ADJUST_STOP,
                    decided_on=ctx.session, execute_on=ctx.session,
                    ticker=act.ticker, stop_price=act.new_stop,
                ))
        return intents

    def on_missed_bars(self, missed: list[date]) -> None:
        """Conta a estrategia quais pregoes passaram sem decisao.

        So TRANSPORTA o fato — nao interpreta. O que um pregao perdido
        significa e decisao da estrategia (`Strategy.on_missed_bars`), nunca
        deste modulo: um `live/` que decidisse "entao rebalanceia hoje" por
        conta propria seria regra de decisao fora de `strategy/`, proibido
        pela regra 6 do AGENTS.md, e o backtest deixaria de descrever a
        operacao.
        """
        self.strategy.on_missed_bars([pd.Timestamp(d) for d in missed])

    def on_intraday(self, ctx: RobotContext) -> list[Intent]:
        """Stop intra-dia, verificado contra a cotacao observada.

        Divergencia HONESTA com o backtest, e precisa estar escrita aqui: no
        backtest o stop dispara quando `low[D] <= current_stop` — o engine
        enxerga a barra inteira de uma vez, de trás para frente, porque o
        dado ja fechou (`engine_portfolio.py`, secao "Stop principal"). Ao
        vivo nao existe "a barra inteira": so existe o PRECO OBSERVADO no
        momento em que o feed entregou uma cotacao. Se o feed atrasar (ver
        `Quote.delay_seconds` em `core.live_models`) ou a frequencia de
        amostragem for baixa, o stop so dispara quando uma cotacao chega
        abaixo do nivel — ou seja, depois do movimento real, num preco pior
        do que o backtest teria capturado. Isso e limitacao de EXECUCAO
        (qualidade/latencia do dado disponivel), nao um defeito da
        estrategia nem uma regra de decisao nova sendo inventada aqui: o
        nivel de stop em si continua vindo inteiramente de `current_stop`,
        que o robo de investimento decidiu via `AdjustStop`/`Enter`.
        """
        intents: list[Intent] = []
        for ticker, pos in ctx.account.positions.items():
            if pos.kind != "main" or pos.current_stop is None:
                continue
            quote = ctx.quotes.get(ticker)
            if quote is None or quote.price > pos.current_stop:
                continue
            intents.append(Intent(
                robot=self.key, role=self.role, kind=IntentKind.EXIT,
                decided_on=ctx.session, execute_on=ctx.session,
                ticker=ticker, reason="stop",
            ))
        return intents

    def state(self) -> dict:
        return self.strategy.state()

    def restore(self, state: dict) -> None:
        self.strategy.restore(state)


class WithdrawalRobot(LiveRobot):
    """Adapta uma `WithdrawalPolicy` (`backtest/withdrawal.py`) ao ambiente ao vivo.

    `key` inclui `policy.label` (que ja carrega os parametros da politica,
    ver `FloorSkim.__init__`) para que trocar de parametrizacao apareca como
    um robo diferente na auditoria, nao como o mesmo robo mudando de
    comportamento silenciosamente.
    """

    role = RobotRole.WITHDRAWAL

    def __init__(self, policy: WithdrawalPolicy) -> None:
        self.policy = policy
        self.key = f"withdrawal:{policy.label}"

    def prepare(self, panels: dict[str, pd.DataFrame], ibov: pd.DataFrame) -> None:
        # A politica de saque decide sobre equity/caixa, nao sobre historico
        # de preco — nao ha nada para pre-calcular. Metodo existe so para
        # cumprir o contrato de `LiveRobot`.
        return None

    def on_close(self, ctx: RobotContext, execute_on: date) -> list[Intent]:
        equity = ctx.account.equity(ctx.marks)
        invested = ctx.account.invested(ctx.marks)
        amount = float(self.policy.on_close(pd.Timestamp(ctx.session), equity, invested))
        if amount <= 0.0:
            return []
        return [Intent(
            robot=self.key, role=self.role, kind=IntentKind.WITHDRAW,
            decided_on=ctx.session, execute_on=execute_on,
            amount=amount, reason=self.policy.label,
        )]

    def on_liquidity(self, ctx: RobotContext, reason: str) -> list[Intent]:
        # Mesma barra, nao D+1: o robo de investimento acabou de vender, o
        # caixa ja esta na mao (exatamente como no engine de backtest, ver
        # `withdrawal_policy.on_liquidity_event` em `engine_portfolio.py`).
        equity = ctx.account.equity(ctx.marks)
        amount = float(self.policy.on_liquidity_event(pd.Timestamp(ctx.session), equity, reason))
        if amount <= 0.0:
            return []
        return [Intent(
            robot=self.key, role=self.role, kind=IntentKind.WITHDRAW,
            decided_on=ctx.session, execute_on=ctx.session,
            amount=amount, reason=self.policy.label,
        )]

    def on_executed(self, intent: Intent, executed: float) -> None:
        self.policy.on_executed(pd.Timestamp(intent.execute_on), executed)

    def state(self) -> dict:
        return self.policy.state()

    def restore(self, state: dict) -> None:
        self.policy.restore(state)


def build_robots(strategy: Strategy, policy: WithdrawalPolicy) -> dict[RobotRole, LiveRobot]:
    """Monta o par de robos (um por `RobotRole`) que o runtime ao vivo precisa.

    Fabrica simples — nao ha decisao aqui, so composicao. Mantida porque o
    runtime nao deveria saber construir `InvestmentRobot`/`WithdrawalRobot`
    diretamente; ele so pede "os robos para esta estrategia e esta politica".
    """
    investment = InvestmentRobot(strategy)
    withdrawal = WithdrawalRobot(policy)
    return {investment.role: investment, withdrawal.role: withdrawal}
