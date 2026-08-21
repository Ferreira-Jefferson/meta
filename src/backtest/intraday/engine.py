"""Motor de backtest INTRABAR para day trade — 4o motor de `backtest/`, ao
lado de `engine.py`/`engine_portfolio.py`/`engine_satellite.py`, so que para
outro instrumento (futuro, nao acao) e outra granularidade (M1, nao D1).

Mesma disciplina anti-look-ahead do motor diario, portada para barra: uma
acao decidida no fechamento da barra `t` executa na abertura da barra
`t+1`, nunca na propria barra `t`. Mesma prioridade do motor diario tambem:
stop/target automatico do motor tem prioridade sobre qualquer acao filada
pelo robo.

Diferencas estruturais que o day trade exige e o motor diario nao tem:
- Multiplas entradas/saidas por SESSAO (o diario decide 1x por pregao).
- Flatten forcado no fim da sessao — day trade nunca carrega posicao
  overnight; isto nao e uma regra da estrategia, e do motor (nenhuma
  estrategia pode escolher nao flatten).
- `AdjustTarget` alem de `AdjustStop` (o diario nao tem alvo).

Dependencia direcional em `strategy.daytrade.base` (Bar/acoes/ABC) mirroria
a excessao ja existente em `backtest/engine.py` (que importa `strategy.
base`): quem executa depende do contrato de quem decide.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import Callable, Literal, Optional

import pandas as pd

from backtest import metrics
from backtest.intraday.costs import FuturesCostModel, apply_futures_slippage, fees_round_trip_brl, gross_pnl_brl
from core.models import IntradayExitReason
from strategy.daytrade.base import (
    AdjustStop,
    AdjustTarget,
    Bar,
    Enter,
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
    costs: FuturesCostModel
    initial_capital: float = 20_000.0
    default_quantity: int = 1
    # Corte de flatten forcado — dispara na PRIMEIRA barra cujo horario seja
    # >= este valor, ou na ultima barra da sessao, o que vier primeiro.
    # Configuravel de proposito: o horario real de encerramento do WIN varia
    # (leilao de fechamento, ajustes de calendario) e nao deve ser
    # hardcoded aqui.
    session_end_time: time = time(17, 50)
    # Quando stop E target caem dentro da MESMA barra (o M1 nao tem
    # resolucao para saber qual tocou primeiro): "stop_first" e a hipotese
    # PESSIMISTA (mesmo espirito do default `stop_or_open` do motor diario);
    # "target_first" e a hipotese otimista, para comparar os dois bracos.
    ambiguous_bar_resolution: Literal["stop_first", "target_first"] = "stop_first"


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


@dataclass
class IntradayBacktestResult:
    trades: list[IntradayTrade]
    equity_curve: pd.Series
    metrics: dict


def _bar_volume(row: pd.Series) -> float:
    """MT5 nao devolve coluna `volume` — devolve `real_volume` (volume
    negociado real, nem sempre populado pela corretora) e `tick_volume`
    (contagem de variacoes de preco, sempre presente). Prefere
    `real_volume` quando ele for genuinamente reportado (> 0); cai para
    `tick_volume` senao. `row.get("volume", 0.0)` sozinho zeraria em
    silencio para todo dado real vindo de `mt5_source.py`."""
    real = row.get("real_volume", 0.0)
    if real and real > 0:
        return float(real)
    return float(row.get("tick_volume", row.get("volume", 0.0)))


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


def run_intraday_backtest(
    bars: pd.DataFrame,
    strategy: IntradayStrategy,
    config: IntradayBacktestConfig,
    on_progress: Optional[Callable[[dict], None]] = None,
) -> IntradayBacktestResult:
    """`bars`: OHLCV M1 de UM simbolo, index = timestamp de fechamento da
    barra, pode abranger muitas sessoes. Agrupado por sessao (dia
    calendario) internamente."""
    strategy.initialize(bars)

    position: _Position | None = None
    pending: Enter | Exit | None = None
    trades: list[IntradayTrade] = []
    realized_pnl = 0.0
    equity_index: list[pd.Timestamp] = []
    equity_values: list[float] = []

    def _close_position(exit_ts: pd.Timestamp, exit_ref_price: float, reason: IntradayExitReason) -> float:
        nonlocal position, realized_pnl
        assert position is not None
        exec_px = apply_futures_slippage(exit_ref_price, _exit_side(position), config.costs)
        fees = fees_round_trip_brl(position.quantity, config.costs)
        trade = IntradayTrade(
            symbol=strategy.symbol,
            strategy_name=strategy.name,
            strategy_version=strategy.version,
            side=position.side,
            entry_ts=position.entry_ts,
            entry_price=position.entry_price,
            exit_ts=exit_ts,
            exit_price=exec_px,
            quantity=position.quantity,
            exit_reason=reason,
            point_value_brl=config.costs.point_value_brl,
            capital_base=config.initial_capital,
            fees_total=fees,
            slippage_total=abs(exec_px - exit_ref_price) * position.quantity * config.costs.point_value_brl,
        )
        trades.append(trade)
        pnl = trade.pnl_brl
        realized_pnl += pnl
        position = None
        return pnl

    for session_date, session_df in bars.groupby(bars.index.date):
        strategy.on_session_start(session_date)
        session_pnl = 0.0
        flattened = False

        for ts, row in session_df.iterrows():
            bar = Bar(ts=ts, open=float(row["open"]), high=float(row["high"]),
                      low=float(row["low"]), close=float(row["close"]), volume=_bar_volume(row))

            # (1) stop/target automatico tem prioridade sobre qualquer acao filada.
            if position is not None:
                hit = _resolve_stop_target_hit(position, bar, config.ambiguous_bar_resolution)
                if hit is not None:
                    ref_price = _exit_fill_price(position, bar, hit)
                    reason = IntradayExitReason.STOP if hit == "stop" else IntradayExitReason.TARGET
                    session_pnl += _close_position(ts, ref_price, reason)
                    pending = None  # decisao pendente do robo para este ticker fica obsoleta

            # (2) flatten forcado — primeira barra da sessao cujo horario >= corte,
            # ou a ultima barra da sessao. Nenhuma entrada nova depois disso.
            is_last_bar = ts == session_df.index[-1]
            if not flattened and (ts.time() >= config.session_end_time or is_last_bar):
                if position is not None:
                    session_pnl += _close_position(ts, bar.close, IntradayExitReason.FORCED_FLATTEN)
                pending = None
                flattened = True

            if not flattened:
                # (3) executa acao filada na ABERTURA desta barra.
                if isinstance(pending, Exit) and position is not None:
                    session_pnl += _close_position(ts, bar.open, IntradayExitReason.SIGNAL)
                    pending = None
                elif isinstance(pending, Enter) and position is None:
                    entry_side: Literal["buy", "sell"] = "buy" if pending.side == "long" else "sell"
                    entry_px = apply_futures_slippage(bar.open, entry_side, config.costs)
                    position = _Position(
                        side=pending.side,
                        entry_ts=ts,
                        entry_price=entry_px,
                        quantity=pending.quantity or config.default_quantity,
                        current_stop=pending.initial_stop,
                        current_target=pending.initial_target,
                        metadata=dict(pending.metadata or {}),
                    )
                    pending = None
                else:
                    pending = None  # Enter com posicao ja aberta (ou Exit sem posicao): descartado

            # (4) marca patrimonio (realizado + mark-to-market da posicao aberta).
            unrealized = 0.0
            if position is not None:
                points = (bar.close - position.entry_price) if position.side == "long" else (position.entry_price - bar.close)
                unrealized = points * config.costs.point_value_brl * position.quantity
            equity_index.append(ts)
            equity_values.append(config.initial_capital + realized_pnl + unrealized)

            # (5) decisao do robo para a PROXIMA barra — nao roda mais depois do flatten.
            if not flattened:
                actions = strategy.on_bar(ts, bar, _position_view(position) if position else None, session_pnl)
                for action in actions:
                    if isinstance(action, AdjustStop) and position is not None:
                        if position.current_stop is None:
                            position.current_stop = action.new_stop
                        elif position.side == "long" and action.new_stop >= position.current_stop:
                            position.current_stop = action.new_stop
                        elif position.side == "short" and action.new_stop <= position.current_stop:
                            position.current_stop = action.new_stop
                    elif isinstance(action, AdjustTarget) and position is not None:
                        position.current_target = action.new_target
                    elif isinstance(action, (Enter, Exit)):
                        pending = action

            if position is not None:
                position.bars_held += 1

        if on_progress is not None:
            on_progress({"session_date": session_date, "trades_so_far": len(trades), "session_pnl_brl": session_pnl})

    equity_curve = pd.Series(equity_values, index=pd.DatetimeIndex(equity_index), name="equity")
    pnl_pcts = [t.pnl_pct for t in trades]
    result_metrics = {
        "cagr": metrics.cagr(equity_curve),
        "max_drawdown": metrics.max_drawdown(equity_curve),
        "calmar": metrics.calmar(equity_curve),
        **metrics.trade_stats(pnl_pcts),
        "n_trades": len(trades),
    }
    return IntradayBacktestResult(trades=trades, equity_curve=equity_curve, metrics=result_metrics)
