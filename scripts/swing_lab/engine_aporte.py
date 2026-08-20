"""Motor com aporte mensal para `Strategy` simples — NAO existe no engine principal.

Por que este arquivo existe
----------------------------
`backtest/engine.py::run_backtest` (usado por toda hipotese desta busca de
swing) nao tem mecanismo de aporte mensal. Quem tem e
`backtest/engine_portfolio.py`, mas so para `PortfolioHysteresis` (a familia
do campeao de sleeves). Editar `engine.py` para adicionar o mecanismo esta fora
de cogitacao: uma sessao concorrente edita esse arquivo agora, e a regra deste
projeto e nunca tocar arquivo existente do motor.

Este arquivo e uma copia deliberada do loop de `run_backtest`, com a MESMA
contabilidade de cota que `engine_portfolio.py` ja usa e ja tem teste para
(ver o comentario em `engine_portfolio.py` linha ~316): cada aporte compra
cotas ao valor do patrimonio ANTES da execucao do dia, valorizado pelo ULTIMO
preco conhecido (nunca o preco de hoje — cotizar com preco que ainda nao
existia quando o dinheiro entrou seria look-ahead). Sem aporte, a curva de
cota e identica, byte a byte, a curva de patrimonio.

O que muda em relacao a `engine.run_backtest`
-----------------------------------------------
Uma insercao no loop diario, logo depois da remuneracao do caixa e antes de
qualquer execucao do dia: no primeiro pregao de cada mes civil (exceto o mes
do capital inicial), credita `config.monthly_contribution` em caixa e atualiza
`units`. O resto do loop — MFE/MAE, stop automatico, fila de Enter/Exit,
marcacao de equity, chamada a `strategy.on_bar` — e o MESMO de `engine.py`,
nao reimplementado por conveniencia: e literalmente o mesmo codigo, para que
divergir de `engine.py` no futuro no comportamento de trading seja um erro de
manutencao visivel, nao um bug silencioso escondido numa segunda implementacao.

Uso: so para medir "e se eu tivesse R$X e aportasse R$Y/mes" nas 5 candidatas
desta busca. Nao e chamado por nada em producao.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd

from backtest.costs import apply_slippage, cash_yield_series, fees_for_leg
from backtest.engine import BacktestResult, _enrich, _snapshot, _positions_view
from core.config import BENCHMARK, BacktestConfig
from core.models import ExitReason, MarketSnapshot, Trade
from strategy.base import AdjustStop, Enter, Exit, Strategy


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


def run_backtest_com_aporte(
    universe: dict[str, pd.DataFrame],
    strategy: Strategy,
    config: BacktestConfig,
    start: str,
    end: str,
) -> BacktestResult:
    ibov = universe[BENCHMARK]
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)

    raw_panels = {t: df for t, df in universe.items() if t != BENCHMARK}
    strategy.initialize(raw_panels, ibov)

    enriched: dict[str, pd.DataFrame] = {}
    for ticker, df_full in raw_panels.items():
        e = _enrich(df_full, ibov)
        mask = (e.index >= start_ts) & (e.index <= end_ts)
        enriched[ticker] = e.loc[mask]

    all_dates = pd.DatetimeIndex(sorted({d for df in enriched.values() for d in df.index}))
    ibov_slice = ibov.loc[(ibov.index >= start_ts) & (ibov.index <= end_ts)]

    cash = config.initial_capital
    positions: dict[str, _Position] = {}
    closed: list[Trade] = []
    equity_records: list[tuple[pd.Timestamp, float]] = []
    unit_records: list[tuple[pd.Timestamp, float]] = []
    last_price: dict[str, float] = {}
    pending: list = []
    default_stop = config.stop_loss_pct
    cash_yield = cash_yield_series(config.cash_yield_path, all_dates)

    # --- contabilidade de cota, formula idêntica a engine_portfolio.py ---
    units = 1.0
    mes_anterior: tuple[int, int] | None = None
    contributions: list[tuple[object, float]] = []

    for i, today in enumerate(all_dates):
        if cash_yield is not None and cash > 0.0:
            cash *= 1.0 + float(cash_yield.iat[i])

        mes = (today.year, today.month)
        if config.monthly_contribution > 0.0 and mes_anterior is not None and mes != mes_anterior:
            patrimonio_antes = cash + sum(
                last_price.get(t, 0.0) * pos.quantity for t, pos in positions.items()
            )
            aporte = float(config.monthly_contribution)
            if patrimonio_antes > 0 and units > 0:
                valor_cota = patrimonio_antes / units
                units += aporte / valor_cota
            else:
                units = 1.0
            cash += aporte
            contributions.append((today.date(), aporte))
        mes_anterior = mes

        for ticker, pos in positions.items():
            df = enriched.get(ticker)
            if df is not None and today in df.index:
                px = float(df.at[today, "close"])
                pos.max_price_seen = max(pos.max_price_seen, px)
                pos.min_price_seen = min(pos.min_price_seen, px)

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
                leg_fees = fees_for_leg(gross, config.costs)
                cash += gross - leg_fees
                snap = _snapshot(df.loc[today])
                closed.append(Trade(
                    ticker=ticker, strategy_name=strategy.name, strategy_version=strategy.version,
                    entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=pos.quantity,
                    capital_allocated=pos.capital_allocated, exit_date=today.date(), exit_price=exec_px,
                    exit_reason=ExitReason.STOP, fees_total=pos.fees_paid + leg_fees,
                    slippage_total=pos.slippage_paid + abs(exec_px - exec_ref) * pos.quantity,
                    max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                    max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                    entry_snapshot=pos.entry_snapshot, exit_snapshot=snap,
                ))
                del positions[ticker]

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
            exec_px = apply_slippage(open_px, "sell", config.costs)
            gross = exec_px * pos.quantity
            leg_fees = fees_for_leg(gross, config.costs)
            cash += gross - leg_fees
            snap = _snapshot(df.loc[today])
            closed.append(Trade(
                ticker=act.ticker, strategy_name=strategy.name, strategy_version=strategy.version,
                entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=pos.quantity,
                capital_allocated=pos.capital_allocated, exit_date=today.date(), exit_price=exec_px,
                exit_reason=act.reason, fees_total=pos.fees_paid + leg_fees,
                slippage_total=pos.slippage_paid + abs(exec_px - open_px) * pos.quantity,
                max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                entry_snapshot=pos.entry_snapshot, exit_snapshot=snap,
            ))

        for act in enters_pending:
            if act.ticker in positions:
                continue
            if len(positions) >= config.max_concurrent_positions:
                continue
            df = enriched.get(act.ticker)
            if df is None or today not in df.index:
                continue
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
                ticker=act.ticker, entry_date=today.date(), entry_price=exec_px, quantity=raw_qty,
                capital_allocated=cost, fees_paid=leg_fees,
                slippage_paid=abs(exec_px - open_px) * raw_qty, entry_snapshot=snap,
                max_price_seen=exec_px, min_price_seen=exec_px, current_stop=initial_stop,
                bars_held=0, metadata=dict(act.metadata) if act.metadata else {},
            )

        equity = cash
        for ticker, pos in positions.items():
            df = enriched.get(ticker)
            if df is not None and today in df.index:
                last_price[ticker] = float(df.at[today, "close"])
            px = last_price.get(ticker)
            if px is not None:
                equity += px * pos.quantity
        equity_records.append((today, float(equity)))
        unit_records.append((today, float(equity) / units if units > 0 else 0.0))

        actions = strategy.on_bar(today, _positions_view(positions), cash)
        for act in actions:
            if isinstance(act, AdjustStop):
                pos = positions.get(act.ticker)
                if pos is None:
                    continue
                if pos.current_stop is None or act.new_stop > pos.current_stop:
                    pos.current_stop = float(act.new_stop)
            elif isinstance(act, (Enter, Exit)):
                pending.append(act)

        for pos in positions.values():
            pos.bars_held += 1

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
        closed.append(Trade(
            ticker=ticker, strategy_name=strategy.name, strategy_version=strategy.version,
            entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=pos.quantity,
            capital_allocated=pos.capital_allocated, exit_date=last_day.date(), exit_price=exec_px,
            exit_reason=ExitReason.MANUAL, fees_total=pos.fees_paid + leg_fees,
            slippage_total=pos.slippage_paid + abs(exec_px - close_px) * pos.quantity,
            max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
            max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
            entry_snapshot=pos.entry_snapshot, exit_snapshot=snap,
        ))

    equity_series = pd.Series(dict(equity_records)).sort_index()
    unit_series = pd.Series(dict(unit_records)).sort_index()
    ibov_close = ibov_slice["close"]
    ibov_norm = ibov_close / ibov_close.iloc[0] * config.initial_capital if len(ibov_close) else ibov_close

    from backtest.metrics import cagr, calmar, max_drawdown, sharpe, sortino, trade_stats
    pnls = [t.pnl_pct for t in closed if not t.is_open]
    stats = trade_stats(pnls)
    metrics = {
        "final_capital": float(equity_series.iloc[-1]) if len(equity_series) else config.initial_capital,
        "cagr": cagr(equity_series), "cagr_unit": cagr(unit_series),
        "sharpe": sharpe(equity_series), "sortino": sortino(equity_series),
        "max_drawdown": max_drawdown(equity_series), "max_drawdown_unit": max_drawdown(unit_series),
        "calmar": calmar(equity_series), "win_rate": stats["win_rate"],
        "profit_factor": stats["profit_factor"], "trades_count": len(closed),
        "benchmark_cagr": cagr(ibov_norm) if len(ibov_norm) else 0.0,
        "contributed_total": float(sum(v for _, v in contributions)),
    }
    return BacktestResult(trades=closed, equity_curve=equity_series, benchmark_curve=ibov_norm,
                          metrics=metrics, unit_curve=unit_series, contributions=contributions)
