"""Engine com suporte a posições satélite (legacy).

Regras adicionais sobre o engine padrão:
- Rotação (ROTATION_OUT): vende 90% da posição principal, mantém 10% como satélite.
- Satélites são invisíveis ao robô (on_bar só vê a posição principal).
- Todo mês: satélite com valor < satellite_stop_pct × ref_value é fechado e o
  dinheiro volta ao caixa (usado na próxima entrada da posição principal).
- Defensive (IBOV_DEFENSIVE): fecha TUDO — principal + todos os satélites.
- Se o novo rank-1 já é um satélite: consolida o satélite de volta ao caixa
  antes de entrar na nova posição principal.

O engine original (engine.py) permanece intacto.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import pandas as pd

from backtest.costs import apply_slippage, fees_for_leg
from backtest.engine import BacktestResult, _Position, _enrich, _snapshot
from backtest.metrics import cagr, calmar, max_drawdown, sharpe, sortino, trade_stats
from core.config import BENCHMARK, BacktestConfig
from core.models import ExitReason, Trade
from strategy.base import AdjustStop, Enter, Exit, OpenPosition, Strategy


@dataclass
class _Satellite:
    """Posição residual mantida após rotação."""
    ticker: str
    entry_date: object          # date
    entry_price: float
    quantity: int
    ref_value: float            # valor total no momento em que virou satélite
    fees_paid: float
    slippage_paid: float
    max_price_seen: float
    min_price_seen: float


def _positions_view_main(positions: dict[str, _Position]) -> dict[str, OpenPosition]:
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


def run_satellite_backtest(
    universe: dict[str, pd.DataFrame],
    strategy: Strategy,
    config: BacktestConfig,
    start: str,
    end: str,
    satellite_pct: float = 0.10,
    satellite_stop_pct: float = 0.20,
    on_progress: Optional[Callable[[dict], None]] = None,
) -> BacktestResult:
    """Roda o backtest com mecânica de satélites.

    Args:
        satellite_pct: fração do capital principal que fica como satélite na rotação (0.10 = 10%).
        satellite_stop_pct: se valor do satélite cair abaixo desta fração do ref_value, fecha (0.20 = 20%).
    """
    ibov = universe[BENCHMARK]
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    raw_panels = {t: df for t, df in universe.items() if t != BENCHMARK}
    strategy.initialize(raw_panels, ibov)

    enriched: dict[str, pd.DataFrame] = {}
    for ticker, df_full in raw_panels.items():
        e = _enrich(df_full, ibov)
        mask = (e.index >= start_ts) & (e.index <= end_ts)
        enriched[ticker] = e.loc[mask]

    all_dates = sorted({d for df in enriched.values() for d in df.index})
    all_dates = pd.DatetimeIndex(all_dates)

    ibov_slice = ibov.loc[(ibov.index >= start_ts) & (ibov.index <= end_ts)]

    cash = config.initial_capital
    positions: dict[str, _Position] = {}       # posição principal (máx 1 no top_n=1)
    satellites: dict[str, _Satellite] = {}     # satélites residuais
    closed: list[Trade] = []
    equity_records: list[tuple[pd.Timestamp, float]] = []
    pending: list = []
    default_stop = config.stop_loss_pct
    # Último close conhecido por ticker — só para marcação de equity (ver
    # engine.py). Evita que um gap de 1 dia num único ticker faça a posição
    # sumir do equity e crie um drawdown fantasma.
    last_mark_price: dict[str, float] = {}

    # Meses já processados para o check de satélites (evita duplo check)
    last_sat_check_month: tuple[int, int] | None = None

    def _close_satellite(ticker: str, price: float, today, reason: ExitReason) -> None:
        nonlocal cash
        sat = satellites.pop(ticker)
        exec_px = apply_slippage(price, "sell", config.costs)
        gross = exec_px * sat.quantity
        leg_fees = fees_for_leg(gross, config.costs, sat.quantity)
        cash += gross - leg_fees
        df = enriched.get(ticker)
        snap = _snapshot(df.loc[today]) if (df is not None and today in df.index) else _snapshot(pd.Series(dtype=float))
        closed.append(Trade(
            ticker=ticker,
            strategy_name=strategy.name + "_sat",
            strategy_version=strategy.version,
            entry_date=sat.entry_date,
            entry_price=sat.entry_price,
            quantity=sat.quantity,
            capital_allocated=sat.ref_value,
            exit_date=today.date(),
            exit_price=exec_px,
            exit_reason=reason,
            fees_total=sat.fees_paid + leg_fees,
            slippage_total=sat.slippage_paid + abs(exec_px - price) * sat.quantity,
            max_favorable_excursion=(sat.max_price_seen - sat.entry_price) / sat.entry_price,
            max_adverse_excursion=(sat.min_price_seen - sat.entry_price) / sat.entry_price,
            entry_snapshot=None,
            exit_snapshot=snap,
        ))

    for i, today in enumerate(all_dates):
        # ── (1) MFE/MAE das posições abertas ─────────────────────────────────
        for ticker, pos in positions.items():
            df = enriched.get(ticker)
            if df is not None and today in df.index:
                px = float(df.at[today, "close"])
                pos.max_price_seen = max(pos.max_price_seen, px)
                pos.min_price_seen = min(pos.min_price_seen, px)

        for ticker, sat in satellites.items():
            df = enriched.get(ticker)
            if df is not None and today in df.index:
                px = float(df.at[today, "close"])
                sat.max_price_seen = max(sat.max_price_seen, px)
                sat.min_price_seen = min(sat.min_price_seen, px)

        # ── (2) Stop automático (posição principal) ───────────────────────────
        for ticker in list(positions.keys()):
            pos = positions[ticker]
            df = enriched.get(ticker)
            if df is None or today not in df.index or pos.current_stop is None:
                continue
            low_px = float(df.at[today, "low"])
            open_px = float(df.at[today, "open"])
            if low_px <= pos.current_stop:
                exec_ref = min(open_px, pos.current_stop)
                exec_px = apply_slippage(exec_ref, "sell", config.costs)
                gross = exec_px * pos.quantity
                leg_fees = fees_for_leg(gross, config.costs, pos.quantity)
                cash += gross - leg_fees
                snap = _snapshot(df.loc[today])
                closed.append(Trade(
                    ticker=ticker, strategy_name=strategy.name, strategy_version=strategy.version,
                    entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=pos.quantity,
                    capital_allocated=pos.capital_allocated, exit_date=today.date(), exit_price=exec_px,
                    exit_reason=ExitReason.STOP,
                    fees_total=pos.fees_paid + leg_fees,
                    slippage_total=pos.slippage_paid + abs(exec_px - exec_ref) * pos.quantity,
                    max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                    max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                    entry_snapshot=pos.entry_snapshot, exit_snapshot=snap,
                ))
                del positions[ticker]

        # ── (3) Check mensal de satélites ─────────────────────────────────────
        month_key = (today.year, today.month)
        if month_key != last_sat_check_month:
            last_sat_check_month = month_key
            for ticker in list(satellites.keys()):
                df = enriched.get(ticker)
                if df is None or today not in df.index:
                    continue
                price = float(df.at[today, "close"])
                curr_val = satellites[ticker].quantity * price
                if curr_val < satellite_stop_pct * satellites[ticker].ref_value:
                    _close_satellite(ticker, price, today, ExitReason.STOP)

        # ── (4) Executa ações filadas de D-1 no open[D] ──────────────────────
        exits_pending = [a for a in pending if isinstance(a, Exit)]
        enters_pending = [a for a in pending if isinstance(a, Enter)]
        pending = []

        for act in exits_pending:
            if act.ticker not in positions:
                continue
            df = enriched.get(act.ticker)
            if df is None or today not in df.index:
                pending.append(act)
                continue

            pos = positions.pop(act.ticker)
            open_px = float(df.at[today, "open"])

            if act.reason == ExitReason.ROTATION_OUT:
                # ── ROTAÇÃO: mantém satellite_pct como satélite ──────────────
                total_qty = pos.quantity
                sat_qty = max(0, int(total_qty * satellite_pct))
                sell_qty = total_qty - sat_qty

                if sell_qty > 0:
                    exec_px = apply_slippage(open_px, "sell", config.costs)
                    gross = exec_px * sell_qty
                    leg_fees = fees_for_leg(gross, config.costs, sell_qty)
                    cash += gross - leg_fees
                    closed.append(Trade(
                        ticker=act.ticker, strategy_name=strategy.name, strategy_version=strategy.version,
                        entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=sell_qty,
                        capital_allocated=pos.capital_allocated * (sell_qty / total_qty),
                        exit_date=today.date(), exit_price=exec_px, exit_reason=act.reason,
                        fees_total=pos.fees_paid * (sell_qty / total_qty) + leg_fees,
                        slippage_total=pos.slippage_paid * (sell_qty / total_qty) + abs(exec_px - open_px) * sell_qty,
                        max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                        max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                        entry_snapshot=pos.entry_snapshot, exit_snapshot=_snapshot(df.loc[today]),
                    ))

                if sat_qty > 0:
                    ref_val = sat_qty * open_px
                    if act.ticker in satellites:
                        # Consolida com satélite existente
                        old = satellites[act.ticker]
                        satellites[act.ticker] = _Satellite(
                            ticker=act.ticker,
                            entry_date=today.date(),
                            entry_price=open_px,
                            quantity=old.quantity + sat_qty,
                            ref_value=old.ref_value + ref_val,
                            fees_paid=0.0, slippage_paid=0.0,
                            max_price_seen=open_px, min_price_seen=open_px,
                        )
                    else:
                        satellites[act.ticker] = _Satellite(
                            ticker=act.ticker,
                            entry_date=today.date(),
                            entry_price=open_px,
                            quantity=sat_qty,
                            ref_value=ref_val,
                            fees_paid=0.0, slippage_paid=0.0,
                            max_price_seen=open_px, min_price_seen=open_px,
                        )

            else:
                # ── SAÍDA TOTAL (Selic defensive, manual) ────────────────────
                exec_px = apply_slippage(open_px, "sell", config.costs)
                gross = exec_px * pos.quantity
                leg_fees = fees_for_leg(gross, config.costs, pos.quantity)
                cash += gross - leg_fees
                closed.append(Trade(
                    ticker=act.ticker, strategy_name=strategy.name, strategy_version=strategy.version,
                    entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=pos.quantity,
                    capital_allocated=pos.capital_allocated, exit_date=today.date(), exit_price=exec_px,
                    exit_reason=act.reason,
                    fees_total=pos.fees_paid + leg_fees,
                    slippage_total=pos.slippage_paid + abs(exec_px - open_px) * pos.quantity,
                    max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                    max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                    entry_snapshot=pos.entry_snapshot, exit_snapshot=_snapshot(df.loc[today]),
                ))
                if act.reason == ExitReason.IBOV_DEFENSIVE:
                    # Fecha todos os satélites também
                    for sat_ticker in list(satellites.keys()):
                        sat_df = enriched.get(sat_ticker)
                        if sat_df is not None and today in sat_df.index:
                            sat_px = float(sat_df.at[today, "open"])
                        else:
                            sat_px = satellites[sat_ticker].entry_price
                        _close_satellite(sat_ticker, sat_px, today, ExitReason.IBOV_DEFENSIVE)

        for act in enters_pending:
            if act.ticker in positions:
                continue
            if len(positions) >= config.max_concurrent_positions:
                continue
            df = enriched.get(act.ticker)
            if df is None or today not in df.index:
                continue

            # Se este ticker tem satélite, consolida de volta ao caixa
            if act.ticker in satellites:
                sat = satellites[act.ticker]
                sat_df = enriched.get(act.ticker)
                if sat_df is not None and today in sat_df.index:
                    sat_px = float(sat_df.at[today, "open"])
                    exec_px_sat = apply_slippage(sat_px, "sell", config.costs)
                    gross_sat = exec_px_sat * sat.quantity
                    leg_fees_sat = fees_for_leg(gross_sat, config.costs, sat.quantity)
                    cash += gross_sat - leg_fees_sat
                del satellites[act.ticker]

            open_px = float(df.at[today, "open"])
            exec_px = apply_slippage(open_px, "buy", config.costs)

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
            leg_fees = fees_for_leg(gross, config.costs, raw_qty)
            cost = gross + leg_fees
            if cost > cash:
                continue
            cash -= cost

            snap = _snapshot(df.loc[today])
            initial_stop = act.initial_stop
            if initial_stop is None and default_stop > 0:
                initial_stop = exec_px * (1.0 - default_stop)

            positions[act.ticker] = _Position(
                ticker=act.ticker, entry_date=today.date(), entry_price=exec_px,
                quantity=raw_qty, capital_allocated=cost, fees_paid=leg_fees,
                slippage_paid=abs(exec_px - open_px) * raw_qty,
                entry_snapshot=snap, max_price_seen=exec_px, min_price_seen=exec_px,
                current_stop=initial_stop, bars_held=0,
                metadata=dict(act.metadata) if act.metadata else {},
            )

        # ── (5) Marca equity no close[D] (principal + satélites + caixa) ─────
        equity = cash
        for ticker, pos in positions.items():
            df = enriched.get(ticker)
            if df is not None and today in df.index:
                last_mark_price[ticker] = float(df.at[today, "close"])
            equity += last_mark_price.get(ticker, 0.0) * pos.quantity
        for ticker, sat in satellites.items():
            df = enriched.get(ticker)
            if df is not None and today in df.index:
                last_mark_price[ticker] = float(df.at[today, "close"])
            equity += last_mark_price.get(ticker, 0.0) * sat.quantity
        equity_records.append((today, float(equity)))

        # ── (6) Chama on_bar com APENAS a posição principal visível ──────────
        actions = strategy.on_bar(today, _positions_view_main(positions), cash)

        for act in actions:
            if isinstance(act, AdjustStop):
                pos = positions.get(act.ticker)
                if pos and (pos.current_stop is None or act.new_stop > pos.current_stop):
                    pos.current_stop = float(act.new_stop)
            elif isinstance(act, (Enter, Exit)):
                pending.append(act)

        for pos in positions.values():
            pos.bars_held += 1

        if on_progress and (i % 60 == 0 or i == len(all_dates) - 1):
            on_progress({"index": i, "total": len(all_dates), "date": today.strftime("%Y-%m-%d"),
                         "equity": float(equity), "open_positions": len(positions),
                         "satellites": len(satellites), "closed_trades": len(closed)})

    # ── Fecha tudo ao fim da janela ───────────────────────────────────────────
    for ticker in list(positions.keys()):
        pos = positions.pop(ticker)
        df = enriched.get(ticker)
        if df is None or len(df.index) == 0:
            continue
        last_day = df.index[-1]
        close_px = float(df.at[last_day, "close"])
        exec_px = apply_slippage(close_px, "sell", config.costs)
        gross = exec_px * pos.quantity
        leg_fees = fees_for_leg(gross, config.costs, pos.quantity)
        cash += gross - leg_fees
        closed.append(Trade(
            ticker=ticker, strategy_name=strategy.name, strategy_version=strategy.version,
            entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=pos.quantity,
            capital_allocated=pos.capital_allocated, exit_date=last_day.date(), exit_price=exec_px,
            exit_reason=ExitReason.MANUAL,
            fees_total=pos.fees_paid + leg_fees,
            slippage_total=pos.slippage_paid + abs(exec_px - close_px) * pos.quantity,
            max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
            max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
            entry_snapshot=pos.entry_snapshot, exit_snapshot=_snapshot(df.loc[last_day]),
        ))

    for ticker in list(satellites.keys()):
        sat = satellites[ticker]
        df = enriched.get(ticker)
        if df is None or len(df.index) == 0:
            continue
        last_day = df.index[-1]
        close_px = float(df.at[last_day, "close"])
        _close_satellite(ticker, close_px, last_day, ExitReason.MANUAL)

    equity_series = pd.Series(dict(equity_records)).sort_index()
    ibov_close = ibov_slice["close"]
    ibov_norm = ibov_close / ibov_close.iloc[0] * config.initial_capital if len(ibov_close) else ibov_close

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
