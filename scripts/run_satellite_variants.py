"""H5/H6/H7: variantes conceituais da engine satelite.

H5 - so_if_profit: so faz satelite se posicao esta em lucro na rotacao
H6 - max_months: fecha satelite apos 12 meses independente do valor
H7 - take_profit: se satelite dobrar de valor, fecha e joga no principal
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dataclasses import dataclass, field
import pandas as pd
from backtest.engine import _enrich, _snapshot, _Position, BacktestResult
from backtest.engine_satellite import _Satellite, _positions_view_main
from backtest.costs import apply_slippage, fees_for_leg
from backtest.metrics import cagr, calmar, max_drawdown, sharpe, sortino, trade_stats
from core.config import BENCHMARK, BacktestConfig
from core.models import ExitReason, Trade
from strategy.base import AdjustStop, Enter, Exit, Strategy
from market_data.loader import load_universe
from strategy.h3_hysteresis import DipTop1Hysteresis

TICKERS = ["WEGE3.SA","BRAP4.SA","RADL3.SA","CSMG3.SA","EMAE4.SA","KEPL3.SA","CXSE3.SA"]
INITIAL = 1000.0

ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY   = ref.index[-1].strftime("%Y-%m-%d")
THREE_Y = (pd.Timestamp(TODAY) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")

SAT_PCT  = 0.10
STOP_PCT = 0.20


def run_variant(universe, strategy, config, start, end,
                satellite_pct=0.10, satellite_stop_pct=0.20,
                only_if_profit=False, max_months=None, take_profit_mult=None):
    """Engine satelite generalizada com flags de variante."""
    ibov = universe[BENCHMARK]
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    raw_panels = {t: df for t, df in universe.items() if t != BENCHMARK}
    strategy.initialize(raw_panels, ibov)

    enriched = {}
    for ticker, df_full in raw_panels.items():
        e = _enrich(df_full, ibov)
        mask = (e.index >= start_ts) & (e.index <= end_ts)
        enriched[ticker] = e.loc[mask]

    all_dates = pd.DatetimeIndex(sorted({d for df in enriched.values() for d in df.index}))
    ibov_slice = ibov.loc[(ibov.index >= start_ts) & (ibov.index <= end_ts)]

    cash = config.initial_capital
    positions: dict[str, _Position] = {}
    satellites: dict[str, _Satellite] = {}
    sat_entry_date: dict[str, pd.Timestamp] = {}
    closed: list[Trade] = []
    equity_records = []
    pending = []
    default_stop = config.stop_loss_pct
    last_sat_check_month = None

    def _price(ticker, date, col="open"):
        df = enriched.get(ticker)
        if df is not None and date in df.index:
            return float(df.at[date, col])
        return None

    def _close_sat(ticker, price, today, reason):
        nonlocal cash
        sat = satellites.pop(ticker, None)
        sat_entry_date.pop(ticker, None)
        if sat is None:
            return
        exec_px = apply_slippage(price, "sell", config.costs)
        gross = exec_px * sat.quantity
        leg_fees = fees_for_leg(gross, config.costs)
        cash += gross - leg_fees
        df = enriched.get(ticker)
        snap = _snapshot(df.loc[today]) if (df is not None and today in df.index) else _snapshot(pd.Series(dtype=float))
        closed.append(Trade(
            ticker=ticker, strategy_name=strategy.name+"_sat", strategy_version=strategy.version,
            entry_date=sat.entry_date, entry_price=sat.entry_price, quantity=sat.quantity,
            capital_allocated=sat.ref_value, exit_date=today.date(), exit_price=exec_px,
            exit_reason=reason,
            fees_total=sat.fees_paid + leg_fees,
            slippage_total=sat.slippage_paid + abs(exec_px - price) * sat.quantity,
            max_favorable_excursion=(sat.max_price_seen - sat.entry_price) / sat.entry_price,
            max_adverse_excursion=(sat.min_price_seen - sat.entry_price) / sat.entry_price,
            entry_snapshot=None, exit_snapshot=snap,
        ))

    for i, today in enumerate(all_dates):
        # MFE/MAE
        for t, pos in positions.items():
            px = _price(t, today, "close")
            if px:
                pos.max_price_seen = max(pos.max_price_seen, px)
                pos.min_price_seen = min(pos.min_price_seen, px)
        for t, sat in satellites.items():
            px = _price(t, today, "close")
            if px:
                sat.max_price_seen = max(sat.max_price_seen, px)
                sat.min_price_seen = min(sat.min_price_seen, px)

        # Stop principal
        for ticker in list(positions.keys()):
            pos = positions[ticker]
            if pos.current_stop is None:
                continue
            low_px = _price(ticker, today, "low")
            open_px = _price(ticker, today, "open")
            if low_px is None:
                continue
            if low_px <= pos.current_stop:
                exec_ref = min(open_px, pos.current_stop)
                exec_px = apply_slippage(exec_ref, "sell", config.costs)
                gross = exec_px * pos.quantity
                leg_fees = fees_for_leg(gross, config.costs)
                cash += gross - leg_fees
                df = enriched.get(ticker)
                snap = _snapshot(df.loc[today]) if (df is not None and today in df.index) else _snapshot(pd.Series(dtype=float))
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

        # Check mensal de satelites
        month_key = (today.year, today.month)
        if month_key != last_sat_check_month:
            last_sat_check_month = month_key
            for ticker in list(satellites.keys()):
                price = _price(ticker, today, "close")
                if price is None:
                    continue
                sat = satellites[ticker]
                curr_val = sat.quantity * price
                close_it = False

                # H5: nao aplicavel aqui (so_if_profit filtra na criacao)
                # H6: tempo maximo
                if max_months is not None:
                    entry_ts = sat_entry_date.get(ticker, today)
                    months_held = (today.year - entry_ts.year) * 12 + (today.month - entry_ts.month)
                    if months_held >= max_months:
                        close_it = True
                # Stop por valor
                if curr_val < satellite_stop_pct * sat.ref_value:
                    close_it = True
                # H7: take profit
                if take_profit_mult is not None and curr_val >= take_profit_mult * sat.ref_value:
                    cash_before = cash
                    _close_sat(ticker, price, today, ExitReason.MANUAL)
                    # O dinheiro vai para caixa — sera usado na proxima entrada
                    continue
                if close_it:
                    _close_sat(ticker, price, today, ExitReason.STOP)

        # Executa acoes filadas
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
                curr_px = open_px
                in_profit = curr_px > pos.entry_price

                # H5: so faz satelite se em lucro
                make_satellite = (not only_if_profit) or in_profit

                total_qty = pos.quantity
                sat_qty = max(0, int(total_qty * satellite_pct)) if make_satellite else 0
                sell_qty = total_qty - sat_qty

                if sell_qty > 0:
                    exec_px = apply_slippage(open_px, "sell", config.costs)
                    gross = exec_px * sell_qty
                    leg_fees = fees_for_leg(gross, config.costs)
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
                        old = satellites[act.ticker]
                        satellites[act.ticker] = _Satellite(
                            ticker=act.ticker, entry_date=today.date(), entry_price=open_px,
                            quantity=old.quantity + sat_qty, ref_value=old.ref_value + ref_val,
                            fees_paid=0.0, slippage_paid=0.0, max_price_seen=open_px, min_price_seen=open_px,
                        )
                    else:
                        satellites[act.ticker] = _Satellite(
                            ticker=act.ticker, entry_date=today.date(), entry_price=open_px,
                            quantity=sat_qty, ref_value=ref_val,
                            fees_paid=0.0, slippage_paid=0.0, max_price_seen=open_px, min_price_seen=open_px,
                        )
                    sat_entry_date[act.ticker] = today
            else:
                exec_px = apply_slippage(open_px, "sell", config.costs)
                gross = exec_px * pos.quantity
                leg_fees = fees_for_leg(gross, config.costs)
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
                    for st in list(satellites.keys()):
                        sp = _price(st, today, "open") or satellites[st].entry_price
                        _close_sat(st, sp, today, ExitReason.IBOV_DEFENSIVE)

        for act in enters_pending:
            if act.ticker in positions:
                continue
            if len(positions) >= config.max_concurrent_positions:
                continue
            df = enriched.get(act.ticker)
            if df is None or today not in df.index:
                continue
            if act.ticker in satellites:
                sp2 = _price(act.ticker, today, "open") or satellites[act.ticker].entry_price
                exec_px_s = apply_slippage(sp2, "sell", config.costs)
                gross_s = exec_px_s * satellites[act.ticker].quantity
                leg_fees_s = fees_for_leg(gross_s, config.costs)
                cash += gross_s - leg_fees_s
                del satellites[act.ticker]
                sat_entry_date.pop(act.ticker, None)

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
                ticker=act.ticker, entry_date=today.date(), entry_price=exec_px,
                quantity=raw_qty, capital_allocated=cost, fees_paid=leg_fees,
                slippage_paid=abs(exec_px - open_px) * raw_qty,
                entry_snapshot=snap, max_price_seen=exec_px, min_price_seen=exec_px,
                current_stop=initial_stop, bars_held=0, metadata={},
            )

        # Equity
        equity = cash
        for t, pos in positions.items():
            px = _price(t, today, "close")
            if px:
                equity += px * pos.quantity
        for t, sat in satellites.items():
            px = _price(t, today, "close")
            if px:
                equity += px * sat.quantity
        equity_records.append((today, float(equity)))

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

    # Fecha tudo no fim
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
        df = enriched.get(ticker)
        if df is None or len(df.index) == 0:
            continue
        last_day = df.index[-1]
        _close_sat(ticker, float(df.at[last_day, "close"]), last_day, ExitReason.MANUAL)

    equity_series = pd.Series(dict(equity_records)).sort_index()
    ibov_close = ibov_slice["close"]
    ibov_norm = ibov_close / ibov_close.iloc[0] * config.initial_capital if len(ibov_close) else ibov_close
    pnls = [t.pnl_pct for t in closed if not t.is_open]
    stats = trade_stats(pnls)
    metrics = {
        "final_capital": float(equity_series.iloc[-1]) if len(equity_series) else config.initial_capital,
        "cagr": cagr(equity_series), "sharpe": sharpe(equity_series),
        "max_drawdown": max_drawdown(equity_series),
        "trades_count": len(closed),
    }
    return BacktestResult(trades=closed, equity_curve=equity_series, benchmark_curve=ibov_norm, metrics=metrics)


def metrics_line(r):
    m = r.metrics
    eq = r.equity_curve
    yr = eq.resample("YE").agg(["first","last"])
    yr["ret"] = yr["last"]/yr["first"] - 1
    neg = int((yr["ret"] < 0).sum())
    return m["final_capital"], m["cagr"], m.get("sharpe",0), m["max_drawdown"], neg

universe = load_universe(tickers=TICKERS, include_benchmark=True)
config   = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)
REF_FULL = 155364.47

VARIANTS = [
    ("REF satelite 10/20",   dict(satellite_pct=0.10, satellite_stop_pct=0.20)),
    ("H5 so_lucro 10/20",    dict(satellite_pct=0.10, satellite_stop_pct=0.20, only_if_profit=True)),
    ("H6 max12m 10/20",      dict(satellite_pct=0.10, satellite_stop_pct=0.20, max_months=12)),
    ("H6 max6m 10/20",       dict(satellite_pct=0.10, satellite_stop_pct=0.20, max_months=6)),
    ("H7 tp2x 10/20",        dict(satellite_pct=0.10, satellite_stop_pct=0.20, take_profit_mult=2.0)),
    ("H7 tp1.5x 10/20",      dict(satellite_pct=0.10, satellite_stop_pct=0.20, take_profit_mult=1.5)),
    ("H5+H7 lucro+tp2x",     dict(satellite_pct=0.10, satellite_stop_pct=0.20, only_if_profit=True, take_profit_mult=2.0)),
]

print("\n=== VARIANTES CONCEITUAIS — FULL ===")
print(f"  {'Variante':25s}  {'Final':>10}  {'vs ref':>7}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>7}  {'NegYr':>6}")
print(f"  {'-'*25}  {'-'*10}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*6}")

for name, kwargs in VARIANTS:
    f, c, sh, dd, n = metrics_line(
        run_variant(universe, DipTop1Hysteresis(), config, "2010-01-01", TODAY, **kwargs))
    delta = (f / REF_FULL - 1) * 100
    print(f"  {name:25s}  R${f:8.2f}  {delta:+6.1f}%  {c*100:6.2f}%  {sh:7.2f}  {dd*100:6.2f}%  {n:>6}")

print("\n=== VARIANTES CONCEITUAIS — 3Y ===")
REF_3Y = 2267.62
print(f"  {'Variante':25s}  {'Final':>9}  {'vs ref':>7}  {'CAGR':>7}  {'NegYr':>6}")
print(f"  {'-'*25}  {'-'*9}  {'-'*7}  {'-'*7}  {'-'*6}")
for name, kwargs in VARIANTS:
    f3, c3, sh3, dd3, n3 = metrics_line(
        run_variant(universe, DipTop1Hysteresis(), config, THREE_Y, TODAY, **kwargs))
    d3 = (f3 / REF_3Y - 1) * 100
    print(f"  {name:25s}  R${f3:7.2f}  {d3:+6.1f}%  {c3*100:6.2f}%  {n3:>6}")
