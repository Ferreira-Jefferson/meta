"""Engine event-driven de backtest — adaptativo.

Responsabilidades do engine:
- percorrer o calendário de datas
- entregar o snapshot atual ao robô (via `Strategy.on_bar`)
- executar as ações declarativas devolvidas: `Enter`, `Exit`, `AdjustStop`
- aplicar custos (corretagem + emolumentos + slippage) em toda execução
- disparar stops automáticos quando o `low` do dia rompe o `current_stop`
- gravar snapshots ricos no momento da decisão para o diário

Cada robô é dono da sua política de entrada, saída e ajuste de stop.
O engine só coordena. Anti-look-ahead: toda decisão tomada no close[D]
executa no open[D+1].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

import numpy as np
import pandas as pd

from backtest.costs import apply_slippage, fees_for_leg
from core.config import BENCHMARK, BacktestConfig
from core.indicators import (
    atr,
    cross_up,
    days_since_last_true,
    historical_volatility,
    ifr,
    rolling_correlation,
    rolling_high,
    rolling_low,
    sma,
)
from core.models import ExitReason, MarketSnapshot, Trade
from strategy.base import AdjustStop, Enter, Exit, OpenPosition, Strategy


@dataclass
class _Position:
    ticker: str
    entry_date: date
    entry_price: float
    quantity: int
    capital_allocated: float
    fees_paid: float
    slippage_paid: float
    entry_snapshot: MarketSnapshot
    max_price_seen: float
    min_price_seen: float
    current_stop: float | None
    bars_held: int
    metadata: dict = field(default_factory=dict)


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_curve: pd.Series
    benchmark_curve: pd.Series
    metrics: dict
    # Saques executados pelo overlay de gestao de capital (ver
    # `backtest/withdrawal.py`). Vazio quando o run nao usa politica de saque.
    withdrawals: list = field(default_factory=list)


def _enrich(df: pd.DataFrame, ibov: pd.DataFrame) -> pd.DataFrame:
    """Anexa colunas de indicadores usadas para preencher o `MarketSnapshot`."""
    close = df["close"]
    out = df.copy()
    out["mm20"] = sma(close, 20)
    out["mm50"] = sma(close, 50)
    out["mm200"] = sma(close, 200)
    out["mm50_over_mm200_pct"] = out["mm50"] / out["mm200"] - 1.0

    cross_events = cross_up(out["mm50"], out["mm200"])
    out["days_since_cross"] = days_since_last_true(cross_events)
    out["ifr14"] = ifr(close, 14)
    out["atr14"] = atr(df["high"], df["low"], close, 14)
    out["hvol30"] = historical_volatility(close, 30)
    out["high_52w"] = rolling_high(close, 252)
    out["low_52w"] = rolling_low(close, 252)
    out["dist_from_high"] = close / out["high_52w"] - 1.0
    out["dist_from_low"] = close / out["low_52w"] - 1.0
    out["volume_avg20"] = df["volume"].rolling(20, min_periods=20).mean()
    out["volume_vs_avg20"] = df["volume"] / out["volume_avg20"]

    ibov_close = ibov["close"].reindex(df.index).ffill()
    out["ibov_close"] = ibov_close
    out["ibov_mm200"] = sma(ibov_close, 200)
    out["ibov_above_mm200"] = ibov_close > out["ibov_mm200"]
    out["ibov_trend_strength"] = ibov_close / out["ibov_mm200"] - 1.0
    out["corr_ibov_60d"] = rolling_correlation(
        close.pct_change(), ibov_close.pct_change(), 60
    )
    return out


def _snapshot(row: pd.Series) -> MarketSnapshot:
    def f(k, default=0.0):
        v = row.get(k)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return default
        return float(v) if not isinstance(v, bool) else bool(v)

    return MarketSnapshot(
        close=f("close"),
        volume=f("volume"),
        volume_vs_avg20=f("volume_vs_avg20"),
        mm20=f("mm20"),
        mm50=f("mm50"),
        mm200=f("mm200"),
        mm50_over_mm200_pct=f("mm50_over_mm200_pct"),
        days_since_cross=int(row.get("days_since_cross") or 0),
        ifr14=f("ifr14"),
        atr14=f("atr14"),
        historical_vol_30d=f("hvol30"),
        distance_from_52w_high_pct=f("dist_from_high"),
        distance_from_52w_low_pct=f("dist_from_low"),
        ibov_close=f("ibov_close"),
        ibov_mm200=f("ibov_mm200"),
        ibov_above_mm200=bool(row.get("ibov_above_mm200") or False),
        ibov_trend_strength=f("ibov_trend_strength"),
        correlation_with_ibov_60d=f("corr_ibov_60d"),
    )


def _positions_view(positions: dict[str, _Position]) -> dict[str, OpenPosition]:
    """Espelha o estado interno como view read-only para o robô."""
    return {
        t: OpenPosition(
            ticker=p.ticker,
            entry_date=pd.Timestamp(p.entry_date),
            entry_price=p.entry_price,
            quantity=p.quantity,
            current_stop=p.current_stop,
            bars_held=p.bars_held,
            metadata=dict(p.metadata),
        )
        for t, p in positions.items()
    }


def run_backtest(
    universe: dict[str, pd.DataFrame],
    strategy: Strategy,
    config: BacktestConfig,
    start: str,
    end: str,
    on_progress: Optional[Callable[[dict], None]] = None,
) -> BacktestResult:
    ibov = universe[BENCHMARK]

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    # Passa OHLCV cru para o robô inicializar seus próprios indicadores.
    raw_panels: dict[str, pd.DataFrame] = {
        t: df for t, df in universe.items() if t != BENCHMARK
    }
    strategy.initialize(raw_panels, ibov)

    # Enriquece o histórico para snapshots do diário e recorta na janela.
    enriched: dict[str, pd.DataFrame] = {}
    for ticker, df_full in raw_panels.items():
        e = _enrich(df_full, ibov)
        mask = (e.index >= start_ts) & (e.index <= end_ts)
        enriched[ticker] = e.loc[mask]

    all_dates = sorted({d for df in enriched.values() for d in df.index})
    all_dates = pd.DatetimeIndex(all_dates)

    ibov_slice = ibov.loc[(ibov.index >= start_ts) & (ibov.index <= end_ts)]

    cash = config.initial_capital
    positions: dict[str, _Position] = {}
    closed: list[Trade] = []
    equity_records: list[tuple[pd.Timestamp, float]] = []
    # Último close conhecido por ticker — usado para marcar a posição a mercado
    # em dias onde o parquet do ativo tem um gap (bar faltando) mas outros
    # ativos do universo pregaram normalmente. Sem isso, um gap de 1 dia em
    # um único ticker faz a posição "sumir" do equity naquele dia (o valor
    # não é somado), criando um drawdown fantasma de quase -100%.
    last_price: dict[str, float] = {}

    # Ações filadas ao final de D para execução no open de D+1.
    # Só Enter/Exit vão para a fila; AdjustStop é aplicado imediatamente.
    pending: list = []

    default_stop = config.stop_loss_pct  # fallback quando Enter não trouxer stop

    for i, today in enumerate(all_dates):
        # (1) MFE/MAE usando close do dia
        for ticker, pos in positions.items():
            df = enriched.get(ticker)
            if df is not None and today in df.index:
                px = float(df.at[today, "close"])
                pos.max_price_seen = max(pos.max_price_seen, px)
                pos.min_price_seen = min(pos.min_price_seen, px)

        # (2) Stop automático: engine dispara Exit se low[D] <= current_stop.
        # Prioridade sobre ações filadas — protege a carteira antes de qualquer coisa.
        for ticker in list(positions.keys()):
            pos = positions[ticker]
            df = enriched.get(ticker)
            if df is None or today not in df.index or pos.current_stop is None:
                continue
            low_px = float(df.at[today, "low"])
            open_px = float(df.at[today, "open"])
            if low_px <= pos.current_stop:
                # gap down abaixo do stop → executa no open (pior); senão no stop
                exec_ref = min(open_px, pos.current_stop)
                exec_px = apply_slippage(exec_ref, "sell", config.costs)
                gross = exec_px * pos.quantity
                leg_fees = fees_for_leg(gross, config.costs)
                cash += gross - leg_fees
                snap = _snapshot(df.loc[today])
                closed.append(
                    Trade(
                        ticker=ticker,
                        strategy_name=strategy.name,
                        strategy_version=strategy.version,
                        entry_date=pos.entry_date,
                        entry_price=pos.entry_price,
                        quantity=pos.quantity,
                        capital_allocated=pos.capital_allocated,
                        exit_date=today.date(),
                        exit_price=exec_px,
                        exit_reason=ExitReason.STOP,
                        fees_total=pos.fees_paid + leg_fees,
                        slippage_total=pos.slippage_paid + abs(exec_px - exec_ref) * pos.quantity,
                        max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                        max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                        entry_snapshot=pos.entry_snapshot,
                        exit_snapshot=snap,
                    )
                )
                del positions[ticker]

        # (3) Executa ações filadas de D-1 no open[D]
        # Primeiro os Exits (liberam caixa), depois os Enters.
        exits_pending = [a for a in pending if isinstance(a, Exit)]
        enters_pending = [a for a in pending if isinstance(a, Enter)]
        pending = []

        for act in exits_pending:
            if act.ticker not in positions:
                continue
            df = enriched.get(act.ticker)
            if df is None or today not in df.index:
                # ativo não pregou hoje — reenfileira
                pending.append(act)
                continue
            pos = positions.pop(act.ticker)
            open_px = float(df.at[today, "open"])
            exec_px = apply_slippage(open_px, "sell", config.costs)
            gross = exec_px * pos.quantity
            leg_fees = fees_for_leg(gross, config.costs)
            cash += gross - leg_fees
            snap = _snapshot(df.loc[today])
            closed.append(
                Trade(
                    ticker=act.ticker,
                    strategy_name=strategy.name,
                    strategy_version=strategy.version,
                    entry_date=pos.entry_date,
                    entry_price=pos.entry_price,
                    quantity=pos.quantity,
                    capital_allocated=pos.capital_allocated,
                    exit_date=today.date(),
                    exit_price=exec_px,
                    exit_reason=act.reason,
                    fees_total=pos.fees_paid + leg_fees,
                    slippage_total=pos.slippage_paid + abs(exec_px - open_px) * pos.quantity,
                    max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                    max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                    entry_snapshot=pos.entry_snapshot,
                    exit_snapshot=snap,
                )
            )

        for act in enters_pending:
            if act.ticker in positions:
                continue
            if len(positions) >= config.max_concurrent_positions:
                continue
            df = enriched.get(act.ticker)
            if df is None or today not in df.index:
                # ativo não pregou hoje — descarta (regra de rebalance discreto)
                continue
            open_px = float(df.at[today, "open"])
            exec_px = apply_slippage(open_px, "buy", config.costs)

            # Sizing: prioriza size_hint do robô; senão default (cash / slots_livres)
            if act.size_hint is not None and act.size_hint > 0:
                slot_budget = cash * float(act.size_hint)
            else:
                slots_free = max(1, config.max_concurrent_positions - len(positions))
                slot_budget = cash / slots_free
            budget = slot_budget * (1.0 - config.costs.per_side_pct - 1e-4)
            raw_qty = int(budget // (exec_px * config.lot_size)) * config.lot_size
            if raw_qty <= 0:
                continue
            gross = exec_px * raw_qty
            leg_fees = fees_for_leg(gross, config.costs)
            cost = gross + leg_fees
            if cost > cash:
                continue
            cash -= cost

            snap = _snapshot(df.loc[today])
            initial_stop = act.initial_stop
            if initial_stop is None and default_stop > 0:
                initial_stop = exec_px * (1.0 - default_stop)

            positions[act.ticker] = _Position(
                ticker=act.ticker,
                entry_date=today.date(),
                entry_price=exec_px,
                quantity=raw_qty,
                capital_allocated=cost,
                fees_paid=leg_fees,
                slippage_paid=abs(exec_px - open_px) * raw_qty,
                entry_snapshot=snap,
                max_price_seen=exec_px,
                min_price_seen=exec_px,
                current_stop=initial_stop,
                bars_held=0,
                metadata=dict(act.metadata) if act.metadata else {},
            )

        # (4) Marca equity no close[D] — usa último close conhecido se o
        # ticker tiver um gap de dado hoje (ver `last_price` acima).
        equity = cash
        for ticker, pos in positions.items():
            df = enriched.get(ticker)
            if df is not None and today in df.index:
                last_price[ticker] = float(df.at[today, "close"])
            px = last_price.get(ticker)
            if px is not None:
                equity += px * pos.quantity
        equity_records.append((today, float(equity)))

        # (5) Chama on_bar do robô no close de D
        actions = strategy.on_bar(today, _positions_view(positions), cash)

        # (6) Aplica AdjustStop imediatamente; fila Enter/Exit para D+1
        for act in actions:
            if isinstance(act, AdjustStop):
                pos = positions.get(act.ticker)
                if pos is None:
                    continue
                if pos.current_stop is None or act.new_stop > pos.current_stop:
                    pos.current_stop = float(act.new_stop)
            elif isinstance(act, (Enter, Exit)):
                pending.append(act)

        # (7) Incrementa bars_held
        for pos in positions.values():
            pos.bars_held += 1

        if on_progress and (i % 60 == 0 or i == len(all_dates) - 1):
            on_progress(
                {
                    "index": i,
                    "total": len(all_dates),
                    "date": today.strftime("%Y-%m-%d"),
                    "equity": float(equity),
                    "open_positions": len(positions),
                    "closed_trades": len(closed),
                }
            )

    # Fecha posições abertas ao fim da janela ao último close disponível.
    for ticker in list(positions.keys()):
        pos = positions.pop(ticker)
        df = enriched.get(ticker)
        if df is None or len(df.index) == 0:
            continue
        last_day = df.index[-1]
        close_px = float(df.at[last_day, "close"])
        exec_px = apply_slippage(close_px, "sell", config.costs)
        gross = exec_px * pos.quantity
        leg_fees = fees_for_leg(gross, config.costs)
        cash += gross - leg_fees
        snap = _snapshot(df.loc[last_day])
        closed.append(
            Trade(
                ticker=ticker,
                strategy_name=strategy.name,
                strategy_version=strategy.version,
                entry_date=pos.entry_date,
                entry_price=pos.entry_price,
                quantity=pos.quantity,
                capital_allocated=pos.capital_allocated,
                exit_date=last_day.date(),
                exit_price=exec_px,
                exit_reason=ExitReason.MANUAL,
                fees_total=pos.fees_paid + leg_fees,
                slippage_total=pos.slippage_paid + abs(exec_px - close_px) * pos.quantity,
                max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                entry_snapshot=pos.entry_snapshot,
                exit_snapshot=snap,
            )
        )

    equity_series = pd.Series(dict(equity_records)).sort_index()

    ibov_close = ibov_slice["close"]
    ibov_norm = ibov_close / ibov_close.iloc[0] * config.initial_capital if len(ibov_close) else ibov_close

    from backtest.metrics import cagr, calmar, max_drawdown, sharpe, sortino, trade_stats

    pnls = [t.pnl_pct for t in closed if not t.is_open]
    stats = trade_stats(pnls)

    metrics = {
        "final_capital": float(equity_series.iloc[-1]) if len(equity_series) else config.initial_capital,
        "cagr": cagr(equity_series),
        "sharpe": sharpe(equity_series),
        "sortino": sortino(equity_series),
        "max_drawdown": max_drawdown(equity_series),
        "calmar": calmar(equity_series),
        "win_rate": stats["win_rate"],
        "profit_factor": stats["profit_factor"],
        "trades_count": len(closed),
        "benchmark_cagr": cagr(ibov_norm) if len(ibov_norm) else 0.0,
    }
    return BacktestResult(
        trades=closed,
        equity_curve=equity_series,
        benchmark_curve=ibov_norm,
        metrics=metrics,
    )
