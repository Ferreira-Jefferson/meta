"""Maquina de estados de UMA sessao intradiaria — o corpo "por barra" que
antes vivia dentro do laco de `run_intraday_backtest`.

Existe por um motivo de OPERACAO, nao de estetica: a partir de 2026-08-21 a
mesma logica precisa rodar em dois lugares (backtest e operacao ao vivo, ver
`live/intraday_runtime.py`). Reescrever a maquina dentro de `live/`
garantiria divergencia silenciosa — o robo validado no backtest deixaria de
ser o robo que opera, e ninguem descobriria por um extrato. Extrair para uma
classe unica torna essa divergencia impossivel por construcao: quem executa
ao vivo alimenta `on_closed_bar` com a barra M1 que o MT5 acabou de fechar,
e o backtest alimenta com a barra do parquet — o resto e' identico.

O contrato e' deliberadamente "empurra barra fechada, recebe eventos":

    machine.begin_session(session_date)       # ou resume_session(...)
    for bar in barras_fechadas:
        for evento in machine.on_closed_bar(bar, is_last_bar=...):
            ...  # backtest: acumula trade; ao vivo: journaliza / manda ordem

`begin_session` chama `IntradayStrategy.on_session_start`; `resume_session`
NAO chama (ver `strategy/daytrade/base.py::warm_start_calibration` — o robo
ja foi calibrado por fora e chamar de novo apagaria a calibracao).

Prioridades (as MESMAS de antes, e as mesmas do motor diario):
  (1) stop/target automatico vence qualquer acao filada pelo robo;
  (2) flatten forcado no fim da sessao vence tudo — nenhuma estrategia pode
      escolher carregar posicao overnight;
  (3) acao filada executa na ABERTURA da barra seguinte a decisao, nunca na
      barra que a gerou (anti-look-ahead, regra 4 do AGENTS.md).

Este arquivo NAO conhece pandas.DataFrame, sessao nem broker: so barras. Quem
agrupa barras em sessoes e' o driver (`engine.py` no backtest,
`live/intraday_runtime.py` ao vivo). A unica excecao e' o CORTE DE FLATTEN,
que consulta o calendario (`core.b3_session`) quando
`session_end_policy="b3_equities"` — o fim do pregao a vista da B3 anda 1h com
o horario de verao dos EUA, e um numero fixo aqui faria o robo achatar 1h
antes do fechamento durante ~4 meses do ano.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import Literal, Optional, Union

import pandas as pd

from core import b3_session
from backtest.intraday.costs import (
    IntradayCostModel,
    apply_intraday_slippage,
    fees_round_trip_brl,
)
from core.models import IntradayExitReason
from strategy.daytrade.base import (
    AdjustStop,
    AdjustTarget,
    Bar,
    Enter,
    EnterLimit,
    Exit,
    IntradayOpenPosition,
    IntradayStrategy,
    Side,
)


@dataclass
class _Position:
    side: Side
    entry_ts: pd.Timestamp
    entry_price: float
    quantity: int
    current_stop: float | None
    current_target: float | None
    bars_held: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class IntradayBacktestConfig:
    costs: IntradayCostModel
    initial_capital: float = 20_000.0
    default_quantity: int = 1
    # Corte de flatten forcado — dispara na PRIMEIRA barra cujo horario seja
    # >= este valor, ou na ultima barra da sessao, o que vier primeiro.
    # So vale com `session_end_policy="fixed"`.
    session_end_time: time = time(17, 50)
    # De onde sai o corte de flatten:
    #   "b3_equities" -> `core.b3_session.closing_bar_minute_utc(dia)`, que
    #                    anda 1h com o horario de verao dos EUA. E' o correto
    #                    para ACAO: o pregao a vista da B3 fecha 16:55 sob DST
    #                    americano e 17:55 fora dele (hora de Brasilia).
    #   "fixed"       -> `session_end_time`, igual todo dia. Para um
    #                    instrumento cujo fechamento NAO segue esse calendario
    #                    (futuro, medido sem deslocamento) e para relogio
    #                    sintetico de teste.
    # Um corte fixo numa acao acha 1h antes do fechamento durante ~4 meses do
    # ano — sem erro nenhum, so deixando de operar a ultima hora. Medido no
    # campeao: era isso que jogava fora +R$58 de P&L out-of-sample.
    session_end_policy: Literal["fixed", "b3_equities"] = "fixed"
    # Quando stop E target caem dentro da MESMA barra (o M1 nao tem
    # resolucao para saber qual tocou primeiro): "stop_first" e a hipotese
    # PESSIMISTA (mesmo espirito do default `stop_or_open` do motor diario);
    # "target_first" e a hipotese otimista, para comparar os dois bracos.
    ambiguous_bar_resolution: Literal["stop_first", "target_first"] = "stop_first"
    # `True`: a saida por TARGET (unica saida voluntaria/planejada — stop,
    # flatten forcado e Exit por sinal continuam pagando `slippage_ticks`
    # normalmente, pois sao saidas por URGENCIA/protecao, nao um "tirar
    # lucro com calma") e' modelada como ordem-limite (maker, sem
    # slippage) em vez de ordem a mercado. Reflete quem coloca a saida de
    # lucro como limite ja no nivel (a mesma logica de `EnterLimit` para
    # entradas) e usa stop a mercado so pra proteger — default `False`
    # preserva o comportamento antigo (todo fechamento paga slippage).
    target_fills_as_maker: bool = False


@dataclass
class IntradayTrade:
    symbol: str
    strategy_name: str
    strategy_version: str
    side: Side
    entry_ts: pd.Timestamp
    entry_price: float
    exit_ts: pd.Timestamp
    exit_price: float
    quantity: int
    exit_reason: IntradayExitReason
    point_value_brl: float
    capital_base: float
    fees_total: float = 0.0
    slippage_total: float = 0.0

    @property
    def pnl_brl(self) -> float:
        points = (self.exit_price - self.entry_price) if self.side == "long" else (self.entry_price - self.exit_price)
        gross = points * self.point_value_brl * self.quantity
        return gross - self.fees_total

    @property
    def pnl_pct(self) -> float:
        if self.capital_base == 0:
            return 0.0
        return self.pnl_brl / self.capital_base


# ---------- eventos devolvidos por `on_closed_bar` -------------------------

@dataclass(frozen=True)
class LimitPlaced:
    """Uma `EnterLimit` passou a ser a ordem-limite VIGIADA (substituindo
    qualquer anterior). No backtest e' so informacao; ao vivo e' o gatilho
    para registrar/enviar uma ordem pendente na corretora."""

    order: EnterLimit
    ts: pd.Timestamp
    replaced: Optional[EnterLimit] = None


@dataclass(frozen=True)
class LimitCancelled:
    """A ordem-limite vigiada deixou de valer sem ter preenchido.
    `reason`: "flatten" (fim da sessao), "ttl" (expirou por `ttl_bars`),
    "superseded" (o robo devolveu outra ordem / uma entrada a mercado
    venceu)."""

    order: EnterLimit
    ts: pd.Timestamp
    reason: str


@dataclass(frozen=True)
class PositionOpened:
    """Entrou posicao de verdade. `order_kind`: "market" (`Enter`, pagou
    slippage na abertura) ou "limit" (`EnterLimit`, preencheu no nivel
    exato). `bar` e' a barra em que o fill aconteceu — ao vivo, e' dela que
    sai a medicao de penetracao do nivel (ver
    `live/intraday_runtime.py`)."""

    ts: pd.Timestamp
    side: Side
    price: float
    quantity: int
    stop: float | None
    target: float | None
    order_kind: str
    reason: str
    bar: Bar


@dataclass(frozen=True)
class PositionClosed:
    """Fechou posicao. `trade` carrega tudo (precos, custos, motivo) — e' o
    MESMO objeto que o backtest acumula em `IntradayBacktestResult.trades`."""

    trade: IntradayTrade
    pnl_brl: float


MachineEvent = Union[LimitPlaced, LimitCancelled, PositionOpened, PositionClosed]


# ---------- helpers de preenchimento (portados de `engine.py` sem mudanca) --

def _position_view(pos: _Position) -> IntradayOpenPosition:
    return IntradayOpenPosition(
        side=pos.side,
        entry_ts=pos.entry_ts,
        entry_price=pos.entry_price,
        quantity=pos.quantity,
        current_stop=pos.current_stop,
        current_target=pos.current_target,
        bars_held=pos.bars_held,
        metadata=dict(pos.metadata),
    )


def _resolve_stop_target_hit(pos: _Position, bar: Bar, ambiguous_bar_resolution: str) -> Optional[str]:
    """`"stop"`, `"target"` ou `None`. Quando os DOIS tocam na mesma barra,
    `ambiguous_bar_resolution` decide — nao ha como saber qual veio primeiro
    so com OHLC de 1 minuto."""
    stop_hit = pos.current_stop is not None and (
        bar.low <= pos.current_stop if pos.side == "long" else bar.high >= pos.current_stop
    )
    target_hit = pos.current_target is not None and (
        bar.high >= pos.current_target if pos.side == "long" else bar.low <= pos.current_target
    )
    if stop_hit and target_hit:
        return "stop" if ambiguous_bar_resolution == "stop_first" else "target"
    if stop_hit:
        return "stop"
    if target_hit:
        return "target"
    return None


def _exit_fill_price(pos: _Position, bar: Bar, kind: str) -> float:
    """Preco de referencia (ANTES de slippage) do fechamento por stop/target
    nesta barra. Se a barra abriu ja alem do nivel (gap), o fill e no
    `open` (pior para stop, melhor para target); senao, exatamente no
    nivel — mesmo espirito de `stop_or_open` do motor diario."""
    level = pos.current_stop if kind == "stop" else pos.current_target
    if pos.side == "long":
        # stop = venda no pior caso (min); target = venda no melhor caso (max)
        return min(bar.open, level) if kind == "stop" else max(bar.open, level)
    # short: stop = compra no pior caso (max); target = compra no melhor caso (min)
    return max(bar.open, level) if kind == "stop" else min(bar.open, level)


def _exit_side(pos: _Position) -> Literal["buy", "sell"]:
    """Lado da ORDEM de fechamento — inverso do lado da posicao."""
    return "sell" if pos.side == "long" else "buy"


def _limit_touched(order: EnterLimit, bar: Bar) -> bool:
    """`True` se esta barra tocou o preco da ordem-limite pendente (mesmo
    mecanismo de toque de `_resolve_stop_target_hit`, intrabar via
    high/low). Compra: `bar.low <= limit_price`; venda: `bar.high >=
    limit_price`."""
    return bar.low <= order.limit_price if order.side == "long" else bar.high >= order.limit_price


class IntradaySessionMachine:
    """Estado + transicoes de uma sessao intradiaria. Ver docstring do modulo.

    Nao guarda historico de trades nem curva de patrimonio — quem quer isso
    acumula os `PositionClosed` que `on_closed_bar` devolve. O que a maquina
    guarda e' so o que a PROXIMA barra precisa: posicao aberta, acao filada,
    ordem-limite vigiada, P&L da sessao (para o robo ver em `on_bar`) e P&L
    realizado acumulado (para marcar patrimonio).
    """

    def __init__(self, strategy: IntradayStrategy, config: IntradayBacktestConfig,
                 execution=None):
        self.strategy = strategy
        self.config = config
        # `None` (backtest, e tambem o modo sombra ao vivo) = os fills sao
        # SIMULADOS a partir do OHLC da barra: uma ordem-limite preenche se a
        # barra tocou o nivel, ao preco exato do nivel.
        #
        # Um objeto aqui (operacao REAL, `live/intraday_execution.py`) inverte
        # a fonte de verdade: a barra deixa de decidir se preencheu -- quem
        # decide e' a CORRETORA, e o preco que entra no trade e' o preco que
        # ela de fato executou. Isso existe porque a simulacao e' otimista por
        # construcao: ela assume que uma ordem parada no nivel X preenche
        # sempre que o preco TOCA X, ignorando fila de ofertas. Confiar nela
        # com dinheiro real faria o robo se achar posicionado (e comecar a
        # contar alvo e stop) enquanto a ordem ainda esta parada no book sem
        # ter executado nada.
        #
        # A logica de DECISAO nao muda entre os dois modos -- e' o mesmo
        # `on_closed_bar`, o mesmo robo, as mesmas prioridades. So a resposta
        # a "preencheu? a que preco?" troca de fonte.
        self.execution = execution
        self.position: _Position | None = None
        self.pending: Enter | Exit | None = None
        self.resting_limit: EnterLimit | None = None
        self.resting_limit_bars_waited = 0
        self.flattened = False
        self.session_pnl = 0.0
        self.realized_pnl = 0.0
        self.session_date = None

    # ---------- ciclo de vida da sessao ----------------------------------

    def begin_session(self, session_date) -> None:
        """Comeca uma sessao NOVA: reseta o estado por-dia e avisa o robo
        (`on_session_start`)."""
        self.strategy.on_session_start(session_date)
        self._reset_session(session_date)

    def resume_session(self, session_date, seed_pending: Enter | EnterLimit | None = None) -> None:
        """Retoma uma sessao JA EM ANDAMENTO sem tocar no estado interno do
        robo — usar quando ele acabou de ser calibrado por fora
        (`warm_start_calibration`) e um `on_session_start` apagaria essa
        calibracao. `seed_pending` e' a ordem que o robo deixou em pe no fim
        do replay: passa a ser vigiada desde a PRIMEIRA barra, em vez de
        precisar de uma barra extra so para o robo redecidir o mesmo.
        `None` NAO limpa uma ordem que ja estivesse vigiada (reconectar no
        meio do pregao nao deve cancelar o que ja estava de pe)."""
        self._reset_session(session_date, clear_resting=False)
        if isinstance(seed_pending, Enter):
            self.pending = seed_pending
        elif isinstance(seed_pending, EnterLimit):
            self.resting_limit = seed_pending
            self.resting_limit_bars_waited = 0

    def _reset_session(self, session_date, clear_resting: bool = True) -> None:
        self.session_date = session_date
        self.session_pnl = 0.0
        self.flattened = False
        if clear_resting:
            self.resting_limit = None
            self.resting_limit_bars_waited = 0

    # ---------- persistencia (so a operacao ao vivo usa) ------------------

    def state(self) -> dict:
        """Snapshot serializavel do que a maquina precisa para continuar
        DEPOIS de o processo reiniciar no meio do pregao.

        O backtest nunca chama isto (roda de ponta a ponta em memoria); ao
        vivo e' obrigatorio: sem persistir a posicao, um reinicio as 11h
        esqueceria que existe posicao aberta e o robo abriria outra. O estado
        interno da ESTRATEGIA nao entra aqui de proposito — ele e'
        reconstruido do dado real por `warm_start_calibration` (ver
        `strategy/daytrade/base.py`), que e' a unica forma de garantir que a
        calibracao ao voltar e' a mesma que teria sido sem a queda."""
        pos = self.position
        return {
            "session_date": self.session_date.isoformat() if self.session_date else None,
            "session_pnl": self.session_pnl,
            "realized_pnl": self.realized_pnl,
            "flattened": self.flattened,
            "position": None if pos is None else {
                "side": pos.side,
                "entry_ts": pos.entry_ts.isoformat(),
                "entry_price": pos.entry_price,
                "quantity": pos.quantity,
                "current_stop": pos.current_stop,
                "current_target": pos.current_target,
                "bars_held": pos.bars_held,
                "metadata": dict(pos.metadata),
            },
        }

    def restore(self, state: dict) -> None:
        """Inverso de `state()`. Nao restaura a ordem-limite vigiada de
        proposito: `resting_limit` e' uma DECISAO do robo, e o robo acabou de
        ser recalibrado — a ordem certa vem do `seed_pending` do warm start,
        nao de um snapshot velho."""
        from datetime import date as _date

        if not state:
            return
        sd = state.get("session_date")
        self.session_date = _date.fromisoformat(sd) if sd else None
        self.session_pnl = float(state.get("session_pnl") or 0.0)
        self.realized_pnl = float(state.get("realized_pnl") or 0.0)
        self.flattened = bool(state.get("flattened"))
        bloco = state.get("position")
        if not bloco:
            self.position = None
            return
        self.position = _Position(
            side=bloco["side"],
            entry_ts=pd.Timestamp(bloco["entry_ts"]),
            entry_price=float(bloco["entry_price"]),
            quantity=int(bloco["quantity"]),
            current_stop=bloco.get("current_stop"),
            current_target=bloco.get("current_target"),
            bars_held=int(bloco.get("bars_held") or 0),
            metadata=dict(bloco.get("metadata") or {}),
        )

    # ---------- marcacao de patrimonio -----------------------------------

    def unrealized_brl(self, price: float) -> float:
        """Marcacao a mercado da posicao aberta a `price` (0.0 sem posicao)."""
        if self.position is None:
            return 0.0
        pos = self.position
        points = (price - pos.entry_price) if pos.side == "long" else (pos.entry_price - price)
        return points * self.config.costs.point_value_brl * pos.quantity

    def position_view(self) -> IntradayOpenPosition | None:
        return _position_view(self.position) if self.position is not None else None

    # ---------- o passo ---------------------------------------------------

    def session_end_time_for(self, ts: pd.Timestamp) -> time:
        """Corte de flatten forcado que vale no pregao da barra `ts`.

        Depende do DIA, e nao so da config, porque o pregao a vista da B3
        desloca 1h com o horario de verao dos EUA — ver `session_end_policy`
        em `IntradayBacktestConfig` e a medicao em `core.b3_session`."""
        if self.config.session_end_policy == "b3_equities":
            return b3_session.closing_bar_minute_utc(ts.date())
        return self.config.session_end_time

    def on_closed_bar(self, bar: Bar, is_last_bar: bool = False) -> list[MachineEvent]:
        """Processa UMA barra ja FECHADA. `is_last_bar=True` forca o flatten
        nesta barra (ultima barra da sessao no dado); o corte por horario
        (`config.session_end_time`) e' avaliado de qualquer forma."""
        cfg = self.config
        ts = bar.ts
        events: list[MachineEvent] = []

        # (1) stop/target automatico tem prioridade sobre qualquer acao filada.
        if self.position is not None:
            hit = _resolve_stop_target_hit(self.position, bar, cfg.ambiguous_bar_resolution)
            if hit is not None:
                ref_price = _exit_fill_price(self.position, bar, hit)
                reason = IntradayExitReason.STOP if hit == "stop" else IntradayExitReason.TARGET
                events.append(self._close_position(ts, ref_price, reason))
                self.pending = None  # decisao pendente do robo para este ticker fica obsoleta

        # (2) flatten forcado — primeira barra da sessao cujo horario >= corte,
        # ou a ultima barra da sessao. Nenhuma entrada nova depois disso.
        if not self.flattened and (ts.time() >= self.session_end_time_for(ts) or is_last_bar):
            if self.position is not None:
                events.append(self._close_position(ts, bar.close, IntradayExitReason.FORCED_FLATTEN))
            self.pending = None
            if self.resting_limit is not None:
                events.append(LimitCancelled(order=self.resting_limit, ts=ts, reason="flatten"))
                self.resting_limit = None
            self.flattened = True

        if not self.flattened:
            # (3) executa acao filada na ABERTURA desta barra.
            if isinstance(self.pending, Exit) and self.position is not None:
                events.append(self._close_position(ts, bar.open, IntradayExitReason.SIGNAL))
                self.pending = None
            elif isinstance(self.pending, Enter) and self.position is None:
                pending = self.pending
                if self.execution is not None:
                    # Entrada A MERCADO ao vivo nao esta implementada de
                    # proposito: nenhum robo intradiario em operacao emite
                    # `Enter` (a familia `gremah` so' usa `EnterLimit`, que e'
                    # o proprio ponto do desenho -- ser maker). Falhar alto
                    # aqui e' melhor que simular o fill a mercado com o `open`
                    # da barra e mandar dinheiro real contra um preco
                    # inventado.
                    raise NotImplementedError(
                        "entrada a mercado (`Enter`) nao suportada em execucao real -- "
                        f"o robo {self.strategy.name!r} pediu uma. So `EnterLimit` "
                        "(ordem-limite pendente) tem caminho de execucao confirmado "
                        "pela corretora; ver `live/intraday_execution.py`."
                    )
                entry_side: Literal["buy", "sell"] = "buy" if pending.side == "long" else "sell"
                entry_px = apply_intraday_slippage(bar.open, entry_side, cfg.costs)
                self.position = _Position(
                    side=pending.side,
                    entry_ts=ts,
                    entry_price=entry_px,
                    quantity=pending.quantity or cfg.default_quantity,
                    current_stop=pending.initial_stop,
                    current_target=pending.initial_target,
                    metadata=dict(pending.metadata or {}),
                )
                self.pending = None
                events.append(PositionOpened(
                    ts=ts, side=self.position.side, price=entry_px,
                    quantity=self.position.quantity, stop=self.position.current_stop,
                    target=self.position.current_target, order_kind="market",
                    reason=pending.reason, bar=bar,
                ))
                # entrada a mercado supera qualquer ordem-limite ainda pendente
                if self.resting_limit is not None:
                    events.append(LimitCancelled(order=self.resting_limit, ts=ts, reason="superseded"))
                    self.resting_limit = None
            else:
                self.pending = None  # Enter com posicao ja aberta (ou Exit sem posicao): descartado

            # (3b) ordem-limite (maker) pendente: preenche no PRIMEIRO
            # toque de `bar.low`/`bar.high`, ao preco exato do nivel —
            # sem slippage, essa e' a diferenca de proposito frente a
            # `Enter` (que sempre paga `slippage_ticks` na abertura).
            # Persiste por varias barras (nao so a proxima), ate
            # tocar, expirar por `ttl_bars`, ou a sessao acabar.
            if self.resting_limit is not None and self.position is None:
                order = self.resting_limit
                fill = self._resolve_limit_fill(order, bar)
                if fill is not None:
                    fill_price, fill_qty = fill
                    self.position = _Position(
                        side=order.side,
                        entry_ts=ts,
                        entry_price=fill_price,
                        quantity=fill_qty,
                        current_stop=order.initial_stop,
                        current_target=order.initial_target,
                        metadata=dict(order.metadata or {}),
                    )
                    self.resting_limit = None
                    self.resting_limit_bars_waited = 0
                    events.append(PositionOpened(
                        ts=ts, side=order.side, price=fill_price,
                        quantity=fill_qty, stop=order.initial_stop,
                        target=order.initial_target, order_kind="limit",
                        reason=order.reason, bar=bar,
                    ))
                else:
                    self.resting_limit_bars_waited += 1
                    if order.ttl_bars is not None and self.resting_limit_bars_waited >= order.ttl_bars:
                        self.resting_limit = None
                        self.resting_limit_bars_waited = 0
                        events.append(LimitCancelled(order=order, ts=ts, reason="ttl"))

        # (5) decisao do robo para a PROXIMA barra — nao roda mais depois do flatten.
        if not self.flattened:
            actions = self.strategy.on_bar(ts, bar, self.position_view(), self.session_pnl)
            for action in actions:
                if isinstance(action, AdjustStop) and self.position is not None:
                    pos = self.position
                    if pos.current_stop is None:
                        pos.current_stop = action.new_stop
                    elif pos.side == "long" and action.new_stop >= pos.current_stop:
                        pos.current_stop = action.new_stop
                    elif pos.side == "short" and action.new_stop <= pos.current_stop:
                        pos.current_stop = action.new_stop
                elif isinstance(action, AdjustTarget) and self.position is not None:
                    self.position.current_target = action.new_target
                elif isinstance(action, (Enter, Exit)):
                    self.pending = action
                    if self.resting_limit is not None:
                        # substitui qualquer ordem-limite pendente
                        events.append(LimitCancelled(order=self.resting_limit, ts=ts, reason="superseded"))
                    self.resting_limit = None
                    self.resting_limit_bars_waited = 0
                elif isinstance(action, EnterLimit) and self.position is None:
                    # substitui (nao acumula) qualquer ordem-limite ja pendente
                    events.append(LimitPlaced(order=action, ts=ts, replaced=self.resting_limit))
                    self.resting_limit = action
                    self.resting_limit_bars_waited = 0

        if self.position is not None:
            self.position.bars_held += 1

        return events

    def force_flatten(self, ts: pd.Timestamp, price: float) -> list[MachineEvent]:
        """Achata a posicao (se houver) e cancela a ordem-limite vigiada, SEM
        consumir barra e sem consultar o robo.

        So a operacao ao vivo usa: quando o processo volta depois de um buraco
        grande de barras, reprocessar o buraco seria tomar decisoes velhas
        contra precos que ja passaram (regra 7 do AGENTS.md), e ignorar o
        buraco deixaria uma posicao real orfa. Achatar no preco mais recente
        e' a leitura honesta das duas coisas. No backtest nao existe buraco: a
        ultima barra da sessao ja dispara o flatten dentro de
        `on_closed_bar`."""
        eventos: list[MachineEvent] = []
        if self.position is not None:
            eventos.append(self._close_position(ts, price, IntradayExitReason.FORCED_FLATTEN))
        if self.resting_limit is not None:
            eventos.append(LimitCancelled(order=self.resting_limit, ts=ts, reason="flatten"))
            self.resting_limit = None
        self.resting_limit_bars_waited = 0
        self.pending = None
        self.flattened = True
        return eventos

    # ---------- preenchimento: simulado (backtest) ou real (corretora) ------

    def _resolve_limit_fill(self, order: EnterLimit, bar: Bar) -> Optional[tuple[float, int]]:
        """`(preco, quantidade)` se a ordem-limite vigiada preencheu nesta
        barra, `None` se continua parada. Ver `self.execution`.

        Backtest/sombra: a barra decide (tocou o nivel -> preencheu no nivel).
        Real: a CORRETORA decide, e o preco/quantidade sao os dela. Uma falha
        em CONSULTAR a corretora nao vira `None` (isso seria ler "nao consegui
        perguntar" como "nao preencheu", e o robo re-armaria uma ordem sobre
        uma posicao que talvez ja exista) -- a excecao sobe."""
        if self.execution is None:
            if not _limit_touched(order, bar):
                return None
            return order.limit_price, (order.quantity or self.config.default_quantity)
        fill = self.execution.limit_fill(order, bar)
        if fill is None:
            return None
        return fill["price"], fill["quantity"]

    # ---------- fechamento -------------------------------------------------

    def _close_position(self, exit_ts: pd.Timestamp, exit_ref_price: float,
                        reason: IntradayExitReason) -> PositionClosed:
        assert self.position is not None
        position = self.position
        cfg = self.config
        is_maker_target = reason == IntradayExitReason.TARGET and cfg.target_fills_as_maker
        exec_px = (exit_ref_price if is_maker_target
                   else apply_intraday_slippage(exit_ref_price, _exit_side(position), cfg.costs))
        if self.execution is not None:
            # Execucao real: manda a ordem de fechamento AGORA e usa o preco
            # que a corretora executou, nao o estimado acima. Vem ANTES de
            # qualquer mutacao de estado de proposito -- se o envio falhar, a
            # excecao sobe com a posicao ainda aberta na maquina, coerente com
            # a posicao que continua aberta na corretora. Marcar como fechada
            # aqui e falhar depois deixaria as duas visoes divergentes, que e'
            # o pior estado possivel para um robo que decide sozinho.
            #
            # Sai a MERCADO inclusive no alvo: `target_fills_as_maker` e' uma
            # premissa de MODELAGEM do backtest, e uma saida por alvo que
            # dependesse de nova ordem-limite poderia simplesmente nao
            # preencher, deixando a posicao aberta contra o proprio stop. O
            # custo dessa diferenca e' real e conhecido -- e' parte do que a
            # corrida em sombra existe para medir.
            exec_px = float(self.execution.exit_market(position, exit_ts, reason)["price"])
        fees = fees_round_trip_brl(position.quantity, position.entry_price, exec_px, cfg.costs)
        trade = IntradayTrade(
            symbol=self.strategy.symbol,
            strategy_name=self.strategy.name,
            strategy_version=self.strategy.version,
            side=position.side,
            entry_ts=position.entry_ts,
            entry_price=position.entry_price,
            exit_ts=exit_ts,
            exit_price=exec_px,
            quantity=position.quantity,
            exit_reason=reason,
            point_value_brl=cfg.costs.point_value_brl,
            capital_base=cfg.initial_capital,
            fees_total=fees,
            slippage_total=abs(exec_px - exit_ref_price) * position.quantity * cfg.costs.point_value_brl,
        )
        pnl = trade.pnl_brl
        self.session_pnl += pnl
        self.realized_pnl += pnl
        self.position = None
        return PositionClosed(trade=trade, pnl_brl=pnl)
