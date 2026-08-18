"""Hipóteses para superar portfolio_hysteresis (TOP-1).

REF: FULL R$134.403 / CAGR 34.33% / Sharpe 0.84 / MaxDD -32.99% / NegYrs 1
META: Final > R$150.000, MaxDD <= -32.99%, NegYrs <= 1

Hipóteses testadas:
  H1 - confirm_months=3 (satélite fecha após 3 meses negativos consecutivos)
  H2 - satellite_pct variável por lucro (5% se lucro, 0% se prejuízo)
  H3 - satellite_pct=8%, confirm_months=2
  H4 - hysteresis threshold=10% (mais rotações)
  H5 - hysteresis threshold=20% (menos rotações)
  H6 - score window 9-1 (189 dias skip 21)
  H7 - score window 6-1 (126 dias skip 21)
  H8 - dip_pct=0.005 (menos restritivo)
  H9 - dip_pct=0.015 (mais restritivo)
  H10 - best_sat + confirm2 (redistribuição para melhor satélite)
  H11 - manter satélites abertos durante modo defensivo (Selic gate só fecha principal)
  H12 - confirm3 + sat8pct (combinação)
  H13 - hyst10 + confirm2 (combinação)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from backtest.engine_portfolio import run_portfolio_backtest
from backtest.metrics import cagr, max_drawdown, sharpe
from core.config import BacktestConfig
from core.models import ExitReason
from market_data.loader import load_universe
from strategy.portfolio_satellite import PortfolioHysteresis
from strategy.base import Enter, Exit
from strategy.h3_hysteresis import DipTop1Hysteresis

TICKERS = ["WEGE3.SA","BRAP4.SA","RADL3.SA","CSMG3.SA","EMAE4.SA","KEPL3.SA","CXSE3.SA"]
INITIAL = 1000.0

ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY   = ref.index[-1].strftime("%Y-%m-%d")
THREE_Y = (pd.Timestamp(TODAY) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")

universe = load_universe(tickers=TICKERS, include_benchmark=True)
config   = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)

REF_FULL = 134_403.0
REF_3Y   = 2_264.0

# ---------------------------------------------------------------------------
# Helper: classe com histerese configurável
# ---------------------------------------------------------------------------
class PortfolioHysteresisCustom(PortfolioHysteresis):
    """Versão com histerese configurável (padrão 15%)."""
    name = "portfolio_hysteresis_custom"
    version = "1.0"

    def __init__(self, hysteresis=0.15, confirm_months=2, redist_mode="pool", **kwargs):
        super().__init__(confirm_months=confirm_months, redist_mode=redist_mode, **kwargs)
        self._hysteresis = hysteresis

# ---------------------------------------------------------------------------
# Classe com score window configurável (lookback e skip)
# ---------------------------------------------------------------------------
class PortfolioHysteresisScoreWindow(PortfolioHysteresisCustom):
    """Versão com lookback e skip configuráveis."""
    name = "portfolio_hysteresis_score_window"
    version = "1.0"

    def __init__(self, lookback=252, skip_recent=21, **kwargs):
        super().__init__(**kwargs)
        self._custom_lookback = lookback
        self._custom_skip = skip_recent

    def initialize(self, panels, ibov):
        super().initialize(panels, ibov)
        # Re-calcula scores com window customizada
        for t, df in panels.items():
            c = df["close"]
            self._scores[t] = (c.shift(self._custom_skip) / c.shift(self._custom_lookback)) - 1.0

# ---------------------------------------------------------------------------
# Classe com dip_pct configurável
# ---------------------------------------------------------------------------
class PortfolioHysteresisDip(PortfolioHysteresisCustom):
    """Versão com dip_pct configurável."""
    name = "portfolio_hysteresis_dip"
    version = "1.0"

    def __init__(self, dip_pct=0.01, **kwargs):
        super().__init__(**kwargs)
        self.dip_pct = dip_pct

# ---------------------------------------------------------------------------
# Engine extendida para H2 (only_if_profit) e H11 (keep_sats_defensive)
# ---------------------------------------------------------------------------
from backtest.engine_portfolio import _Sat, RedistMode
from backtest.costs import apply_slippage, fees_for_leg
from backtest.engine import BacktestResult, _Position, _enrich, _snapshot, _positions_view
from backtest.metrics import cagr, calmar, max_drawdown, sharpe, sortino, trade_stats
from core.config import BENCHMARK
from core.models import Trade
from strategy.base import AdjustStop, Enter, Exit

def run_portfolio_backtest_v2(
    universe, strategy, config, start, end,
    satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool",
    only_if_profit=False,
    keep_sats_defensive=False,
):
    """Engine portfolio estendida com flags adicionais:
    - only_if_profit: só cria satélite se posição está em lucro
    - keep_sats_defensive: em modo defensivo (Selic), mantém satélites abertos
    """
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
    positions: dict = {}
    satellites: dict = {}
    closed: list = []
    equity_records = []
    pending: list = []
    default_stop = config.stop_loss_pct
    last_sat_check_month = None

    def _price(ticker, date, col="close"):
        df = enriched.get(ticker)
        return float(df.at[date, col]) if (df is not None and date in df.index) else None

    def _sat_value(ticker, date):
        sat = satellites.get(ticker)
        if sat is None:
            return 0.0
        px = _price(ticker, date)
        return sat.quantity * px if px else 0.0

    def _close_satellite(ticker, price, today, reason) -> float:
        nonlocal cash
        sat = satellites.pop(ticker)
        exec_px = apply_slippage(price, "sell", config.costs)
        gross = exec_px * sat.quantity
        leg_fees = fees_for_leg(gross, config.costs)
        net = gross - leg_fees
        df = enriched.get(ticker)
        snap = _snapshot(df.loc[today]) if (df is not None and today in df.index) else _snapshot(pd.Series(dtype=float))
        closed.append(Trade(
            ticker=ticker, strategy_name=strategy.name + "_sat",
            strategy_version=strategy.version,
            entry_date=sat.entry_date, entry_price=sat.entry_price,
            quantity=sat.quantity, capital_allocated=sat.ref_value,
            exit_date=today.date(), exit_price=exec_px, exit_reason=reason,
            fees_total=sat.fees_paid + leg_fees,
            slippage_total=sat.slippage_paid + abs(exec_px - price) * sat.quantity,
            max_favorable_excursion=(sat.max_price_seen - sat.entry_price) / sat.entry_price,
            max_adverse_excursion=(sat.min_price_seen - sat.entry_price) / sat.entry_price,
            entry_snapshot=None, exit_snapshot=snap,
        ))
        return net

    def _redistribute(net: float, today, source_ticker: str):
        nonlocal cash
        if redist_mode == "pool" or not positions:
            cash += net
            return
        if redist_mode == "main":
            cash += net
            return
        if redist_mode == "best_sat":
            best = max(
                ((t, _sat_value(t, today)) for t in satellites if t != source_ticker),
                key=lambda x: x[1], default=None
            )
            if best is None or best[1] == 0:
                cash += net
                return
            best_ticker = best[0]
            px = _price(best_ticker, today, "close")
            if px is None or px <= 0:
                cash += net
                return
            extra_qty = int(net // px)
            if extra_qty > 0:
                exec_px = apply_slippage(px, "buy", config.costs)
                cost = exec_px * extra_qty + fees_for_leg(exec_px * extra_qty, config.costs)
                if cost <= net:
                    sat = satellites[best_ticker]
                    sat.quantity += extra_qty
                    sat.ref_value += cost
                    cash += net - cost
                else:
                    cash += net
            else:
                cash += net

    for i, today in enumerate(all_dates):
        for t, pos in positions.items():
            px = _price(t, today)
            if px:
                pos.max_price_seen = max(pos.max_price_seen, px)
                pos.min_price_seen = min(pos.min_price_seen, px)
        for t, sat in satellites.items():
            px = _price(t, today)
            if px:
                sat.max_price_seen = max(sat.max_price_seen, px)
                sat.min_price_seen = min(sat.min_price_seen, px)

        # Stop principal
        for ticker in list(positions.keys()):
            pos = positions[ticker]
            if pos.current_stop is None:
                continue
            low = _price(ticker, today, "low")
            opn = _price(ticker, today, "open")
            if low is None or low > pos.current_stop:
                continue
            exec_ref = min(opn, pos.current_stop)
            exec_px = apply_slippage(exec_ref, "sell", config.costs)
            gross = exec_px * pos.quantity
            leg_fees = fees_for_leg(gross, config.costs)
            cash += gross - leg_fees
            df = enriched.get(ticker)
            snap = _snapshot(df.loc[today]) if (df is not None and today in df.index) else _snapshot(pd.Series(dtype=float))
            closed.append(Trade(
                ticker=ticker, strategy_name=strategy.name, strategy_version=strategy.version,
                entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=pos.quantity,
                capital_allocated=pos.capital_allocated, exit_date=today.date(),
                exit_price=exec_px, exit_reason=ExitReason.STOP,
                fees_total=pos.fees_paid + leg_fees,
                slippage_total=pos.slippage_paid + abs(exec_px - exec_ref) * pos.quantity,
                max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                entry_snapshot=pos.entry_snapshot, exit_snapshot=snap,
            ))
            del positions[ticker]

        # Check mensal de satélites
        month_key = (today.year, today.month)
        if month_key != last_sat_check_month:
            last_sat_check_month = month_key
            for ticker in list(satellites.keys()):
                px = _price(ticker, today)
                if px is None:
                    continue
                sat = satellites[ticker]
                curr_val = sat.quantity * px
                neg_signal = strategy.satellite_exit_signal(ticker, today)
                stop_hit = curr_val < satellite_stop_pct * sat.ref_value
                if neg_signal or stop_hit:
                    reason = ExitReason.ROTATION_OUT if neg_signal else ExitReason.STOP
                    net = _close_satellite(ticker, px, today, reason)
                    _redistribute(net, today, ticker)

        # Executa ações
        exits_p = [a for a in pending if isinstance(a, Exit)]
        enters_p = [a for a in pending if isinstance(a, Enter)]
        pending = []

        for act in exits_p:
            if act.ticker not in positions:
                continue
            df = enriched.get(act.ticker)
            if df is None or today not in df.index:
                pending.append(act)
                continue

            pos = positions.pop(act.ticker)
            opn = float(df.at[today, "open"])

            if act.reason == ExitReason.ROTATION_OUT:
                total_qty = pos.quantity
                # H2: só cria satélite se em lucro
                in_profit = opn > pos.entry_price
                make_sat = (not only_if_profit) or in_profit
                sat_qty = max(0, int(total_qty * satellite_pct)) if make_sat else 0
                sell_qty = total_qty - sat_qty

                if sell_qty > 0:
                    exec_px = apply_slippage(opn, "sell", config.costs)
                    gross = exec_px * sell_qty
                    leg_fees = fees_for_leg(gross, config.costs)
                    cash += gross - leg_fees
                    closed.append(Trade(
                        ticker=act.ticker, strategy_name=strategy.name, strategy_version=strategy.version,
                        entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=sell_qty,
                        capital_allocated=pos.capital_allocated * (sell_qty / total_qty),
                        exit_date=today.date(), exit_price=exec_px, exit_reason=act.reason,
                        fees_total=pos.fees_paid * (sell_qty / total_qty) + leg_fees,
                        slippage_total=pos.slippage_paid * (sell_qty / total_qty) + abs(exec_px - opn) * sell_qty,
                        max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                        max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                        entry_snapshot=pos.entry_snapshot, exit_snapshot=_snapshot(df.loc[today]),
                    ))

                if sat_qty > 0:
                    ref_val = sat_qty * opn
                    if act.ticker in satellites:
                        old = satellites[act.ticker]
                        satellites[act.ticker] = _Sat(
                            ticker=act.ticker, entry_date=today.date(), entry_price=opn,
                            quantity=old.quantity + sat_qty, ref_value=old.ref_value + ref_val,
                            max_price_seen=opn, min_price_seen=opn,
                        )
                    else:
                        satellites[act.ticker] = _Sat(
                            ticker=act.ticker, entry_date=today.date(), entry_price=opn,
                            quantity=sat_qty, ref_value=ref_val,
                            max_price_seen=opn, min_price_seen=opn,
                        )
            else:
                # Saída total (Selic defensive etc)
                exec_px = apply_slippage(opn, "sell", config.costs)
                gross = exec_px * pos.quantity
                leg_fees = fees_for_leg(gross, config.costs)
                cash += gross - leg_fees
                closed.append(Trade(
                    ticker=act.ticker, strategy_name=strategy.name, strategy_version=strategy.version,
                    entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=pos.quantity,
                    capital_allocated=pos.capital_allocated, exit_date=today.date(),
                    exit_price=exec_px, exit_reason=act.reason,
                    fees_total=pos.fees_paid + leg_fees,
                    slippage_total=pos.slippage_paid + abs(exec_px - opn) * pos.quantity,
                    max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                    max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                    entry_snapshot=pos.entry_snapshot, exit_snapshot=_snapshot(df.loc[today]),
                ))
                if act.reason == ExitReason.IBOV_DEFENSIVE:
                    if not keep_sats_defensive:
                        for st in list(satellites.keys()):
                            sp = _price(st, today, "open") or satellites[st].entry_price
                            net = _close_satellite(st, sp, today, ExitReason.IBOV_DEFENSIVE)
                            cash += net  # modo defensivo → caixa
                    # Se keep_sats_defensive=True, deixa satélites abertos

        for act in enters_p:
            if act.ticker in positions:
                continue
            if len(positions) >= config.max_concurrent_positions:
                continue
            df = enriched.get(act.ticker)
            if df is None or today not in df.index:
                continue

            if act.ticker in satellites:
                sat = satellites[act.ticker]
                sp = _price(act.ticker, today, "open") or sat.entry_price
                exec_px_s = apply_slippage(sp, "sell", config.costs)
                gross_s = exec_px_s * sat.quantity
                leg_s = fees_for_leg(gross_s, config.costs)
                cash += gross_s - leg_s
                del satellites[act.ticker]

            opn = float(df.at[today, "open"])
            exec_px = apply_slippage(opn, "buy", config.costs)
            slot_budget = cash * float(act.size_hint) if (act.size_hint and act.size_hint > 0) else cash
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
                slippage_paid=abs(exec_px - opn) * raw_qty,
                entry_snapshot=snap, max_price_seen=exec_px, min_price_seen=exec_px,
                current_stop=initial_stop, bars_held=0, metadata={},
            )

        # Equity
        equity = cash
        for t, pos in positions.items():
            px = _price(t, today)
            if px:
                equity += px * pos.quantity
        for t, sat in satellites.items():
            px = _price(t, today)
            if px:
                equity += px * sat.quantity
        equity_records.append((today, float(equity)))

        actions = strategy.on_bar(today, _positions_view(positions), cash)
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
        if df is None or not len(df.index):
            continue
        last_day = df.index[-1]
        px = float(df.at[last_day, "close"])
        exec_px = apply_slippage(px, "sell", config.costs)
        gross = exec_px * pos.quantity
        leg_fees = fees_for_leg(gross, config.costs)
        cash += gross - leg_fees
        closed.append(Trade(
            ticker=ticker, strategy_name=strategy.name, strategy_version=strategy.version,
            entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=pos.quantity,
            capital_allocated=pos.capital_allocated, exit_date=last_day.date(),
            exit_price=exec_px, exit_reason=ExitReason.MANUAL,
            fees_total=pos.fees_paid + leg_fees,
            slippage_total=pos.slippage_paid + abs(exec_px - px) * pos.quantity,
            max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
            max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
            entry_snapshot=pos.entry_snapshot, exit_snapshot=_snapshot(df.loc[last_day]),
        ))

    for ticker in list(satellites.keys()):
        df = enriched.get(ticker)
        if df is None or not len(df.index):
            continue
        last_day = df.index[-1]
        px = float(df.at[last_day, "close"])
        net = _close_satellite(ticker, px, last_day, ExitReason.MANUAL)
        cash += net

    equity_series = pd.Series(dict(equity_records)).sort_index()
    ibov_close = ibov_slice["close"]
    ibov_norm = ibov_close / ibov_close.iloc[0] * config.initial_capital if len(ibov_close) else ibov_close
    pnls = [t.pnl_pct for t in closed if not t.is_open]
    stats = trade_stats(pnls)
    metrics = {
        "final_capital": float(equity_series.iloc[-1]) if len(equity_series) else config.initial_capital,
        "cagr": cagr(equity_series), "sharpe": sharpe(equity_series),
        "sortino": sortino(equity_series), "max_drawdown": max_drawdown(equity_series),
        "calmar": calmar(equity_series),
        "win_rate": stats["win_rate"], "profit_factor": stats["profit_factor"],
        "trades_count": len(closed),
        "benchmark_cagr": cagr(ibov_norm) if len(ibov_norm) else 0.0,
    }
    return BacktestResult(trades=closed, equity_curve=equity_series,
                          benchmark_curve=ibov_norm, metrics=metrics)


def neg_years(eq):
    yearly = eq.resample("YE").agg(["first","last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    return int((yearly["ret"] < 0).sum())


def report(label, r_full, r_3y):
    m = r_full.metrics
    eq = r_full.equity_curve
    m3 = r_3y.metrics
    neg = neg_years(eq)
    vs_full = r_full.metrics["final_capital"] - REF_FULL
    passed = (
        r_full.metrics["final_capital"] > 150_000
        and r_full.metrics["max_drawdown"] >= -0.3299
        and neg <= 1
    )
    status = "PASSOU" if passed else "FALHOU"
    print(f"\n{label}")
    print(f"  FULL: R${m['final_capital']:,.0f} / CAGR {m['cagr']*100:.2f}% / Sharpe {m['sharpe']:.2f} / MaxDD {m['max_drawdown']*100:.2f}% / NegYrs {neg}")
    print(f"  3Y:   R${m3['final_capital']:,.0f} / CAGR {m3['cagr']*100:.2f}%")
    print(f"  vs REF: {vs_full:+,.0f} ({vs_full/REF_FULL*100:+.1f}%) | {status} (meta: >150k, DD<=-33%, NegYrs<=1)")
    return {
        "label": label, "final": m["final_capital"], "cagr": m["cagr"],
        "sharpe": m["sharpe"], "maxdd": m["max_drawdown"], "neg": neg,
        "final_3y": m3["final_capital"], "cagr_3y": m3["cagr"],
        "passed": passed
    }


print("=" * 70)
print("TESTANDO HIPÓTESES — REF:", f"R${REF_FULL:,.0f}")
print("=" * 70)

results = []

# ===========================================================================
# H1 — confirm_months=3
# ===========================================================================
print("\n[H1] confirm_months=3 ...")
s = PortfolioHysteresis(confirm_months=3, redist_mode="pool")
r_full = run_portfolio_backtest(universe, s, config, "2010-01-01", TODAY,
                                satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
s3 = PortfolioHysteresis(confirm_months=3, redist_mode="pool")
r_3y = run_portfolio_backtest(universe, s3, config, THREE_Y, TODAY,
                               satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
results.append(report("H1 — confirm_months=3", r_full, r_3y))

# ===========================================================================
# H2 — satellite só se em lucro (only_if_profit)
# ===========================================================================
print("\n[H2] satellite só se em lucro ...")
s = PortfolioHysteresis(confirm_months=2, redist_mode="pool")
r_full = run_portfolio_backtest_v2(universe, s, config, "2010-01-01", TODAY,
                                   satellite_pct=0.05, satellite_stop_pct=0.20,
                                   redist_mode="pool", only_if_profit=True)
s3 = PortfolioHysteresis(confirm_months=2, redist_mode="pool")
r_3y = run_portfolio_backtest_v2(universe, s3, config, THREE_Y, TODAY,
                                  satellite_pct=0.05, satellite_stop_pct=0.20,
                                  redist_mode="pool", only_if_profit=True)
results.append(report("H2 — satellite só se lucro", r_full, r_3y))

# ===========================================================================
# H3 — satellite_pct=8%, confirm2
# ===========================================================================
print("\n[H3] satellite_pct=8%, confirm2 ...")
s = PortfolioHysteresis(confirm_months=2, redist_mode="pool")
r_full = run_portfolio_backtest(universe, s, config, "2010-01-01", TODAY,
                                satellite_pct=0.08, satellite_stop_pct=0.20, redist_mode="pool")
s3 = PortfolioHysteresis(confirm_months=2, redist_mode="pool")
r_3y = run_portfolio_backtest(universe, s3, config, THREE_Y, TODAY,
                               satellite_pct=0.08, satellite_stop_pct=0.20, redist_mode="pool")
results.append(report("H3 — satellite_pct=8%+confirm2", r_full, r_3y))

# ===========================================================================
# H4 — hysteresis=10% (mais rotações)
# ===========================================================================
print("\n[H4] hysteresis=10% ...")
s = PortfolioHysteresisCustom(hysteresis=0.10, confirm_months=2, redist_mode="pool")
r_full = run_portfolio_backtest(universe, s, config, "2010-01-01", TODAY,
                                satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
s3 = PortfolioHysteresisCustom(hysteresis=0.10, confirm_months=2, redist_mode="pool")
r_3y = run_portfolio_backtest(universe, s3, config, THREE_Y, TODAY,
                               satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
results.append(report("H4 — hysteresis=10%", r_full, r_3y))

# ===========================================================================
# H5 — hysteresis=20% (menos rotações)
# ===========================================================================
print("\n[H5] hysteresis=20% ...")
s = PortfolioHysteresisCustom(hysteresis=0.20, confirm_months=2, redist_mode="pool")
r_full = run_portfolio_backtest(universe, s, config, "2010-01-01", TODAY,
                                satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
s3 = PortfolioHysteresisCustom(hysteresis=0.20, confirm_months=2, redist_mode="pool")
r_3y = run_portfolio_backtest(universe, s3, config, THREE_Y, TODAY,
                               satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
results.append(report("H5 — hysteresis=20%", r_full, r_3y))

# ===========================================================================
# H6 — score window 9-1 (189 dias skip 21)
# ===========================================================================
print("\n[H6] score window 9-1 (189 dias) ...")
s = PortfolioHysteresisScoreWindow(lookback=189, skip_recent=21, hysteresis=0.15, confirm_months=2, redist_mode="pool")
r_full = run_portfolio_backtest(universe, s, config, "2010-01-01", TODAY,
                                satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
s3 = PortfolioHysteresisScoreWindow(lookback=189, skip_recent=21, hysteresis=0.15, confirm_months=2, redist_mode="pool")
r_3y = run_portfolio_backtest(universe, s3, config, THREE_Y, TODAY,
                               satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
results.append(report("H6 — score window 9-1 (189d)", r_full, r_3y))

# ===========================================================================
# H7 — score window 6-1 (126 dias skip 21)
# ===========================================================================
print("\n[H7] score window 6-1 (126 dias) ...")
s = PortfolioHysteresisScoreWindow(lookback=126, skip_recent=21, hysteresis=0.15, confirm_months=2, redist_mode="pool")
r_full = run_portfolio_backtest(universe, s, config, "2010-01-01", TODAY,
                                satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
s3 = PortfolioHysteresisScoreWindow(lookback=126, skip_recent=21, hysteresis=0.15, confirm_months=2, redist_mode="pool")
r_3y = run_portfolio_backtest(universe, s3, config, THREE_Y, TODAY,
                               satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
results.append(report("H7 — score window 6-1 (126d)", r_full, r_3y))

# ===========================================================================
# H8 — dip_pct=0.5% (menos restritivo)
# ===========================================================================
print("\n[H8] dip_pct=0.5% ...")
s = PortfolioHysteresisDip(dip_pct=0.005, hysteresis=0.15, confirm_months=2, redist_mode="pool")
r_full = run_portfolio_backtest(universe, s, config, "2010-01-01", TODAY,
                                satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
s3 = PortfolioHysteresisDip(dip_pct=0.005, hysteresis=0.15, confirm_months=2, redist_mode="pool")
r_3y = run_portfolio_backtest(universe, s3, config, THREE_Y, TODAY,
                               satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
results.append(report("H8 — dip_pct=0.5%", r_full, r_3y))

# ===========================================================================
# H9 — dip_pct=1.5% (mais restritivo)
# ===========================================================================
print("\n[H9] dip_pct=1.5% ...")
s = PortfolioHysteresisDip(dip_pct=0.015, hysteresis=0.15, confirm_months=2, redist_mode="pool")
r_full = run_portfolio_backtest(universe, s, config, "2010-01-01", TODAY,
                                satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
s3 = PortfolioHysteresisDip(dip_pct=0.015, hysteresis=0.15, confirm_months=2, redist_mode="pool")
r_3y = run_portfolio_backtest(universe, s3, config, THREE_Y, TODAY,
                               satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
results.append(report("H9 — dip_pct=1.5%", r_full, r_3y))

# ===========================================================================
# H10 — best_sat + confirm2
# ===========================================================================
print("\n[H10] best_sat + confirm2 ...")
s = PortfolioHysteresis(confirm_months=2, redist_mode="best_sat")
r_full = run_portfolio_backtest(universe, s, config, "2010-01-01", TODAY,
                                satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="best_sat")
s3 = PortfolioHysteresis(confirm_months=2, redist_mode="best_sat")
r_3y = run_portfolio_backtest(universe, s3, config, THREE_Y, TODAY,
                               satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="best_sat")
results.append(report("H10 — best_sat+confirm2", r_full, r_3y))

# ===========================================================================
# H11 — manter satélites durante modo defensivo
# ===========================================================================
print("\n[H11] keep_sats_defensive ...")
s = PortfolioHysteresis(confirm_months=2, redist_mode="pool")
r_full = run_portfolio_backtest_v2(universe, s, config, "2010-01-01", TODAY,
                                   satellite_pct=0.05, satellite_stop_pct=0.20,
                                   redist_mode="pool", keep_sats_defensive=True)
s3 = PortfolioHysteresis(confirm_months=2, redist_mode="pool")
r_3y = run_portfolio_backtest_v2(universe, s3, config, THREE_Y, TODAY,
                                  satellite_pct=0.05, satellite_stop_pct=0.20,
                                  redist_mode="pool", keep_sats_defensive=True)
results.append(report("H11 — keep_sats_defensive", r_full, r_3y))

# ===========================================================================
# H12 — confirm3 + sat8pct (combinação)
# ===========================================================================
print("\n[H12] confirm3 + sat8pct ...")
s = PortfolioHysteresis(confirm_months=3, redist_mode="pool")
r_full = run_portfolio_backtest(universe, s, config, "2010-01-01", TODAY,
                                satellite_pct=0.08, satellite_stop_pct=0.20, redist_mode="pool")
s3 = PortfolioHysteresis(confirm_months=3, redist_mode="pool")
r_3y = run_portfolio_backtest(universe, s3, config, THREE_Y, TODAY,
                               satellite_pct=0.08, satellite_stop_pct=0.20, redist_mode="pool")
results.append(report("H12 — confirm3+sat8pct", r_full, r_3y))

# ===========================================================================
# H13 — hysteresis=10% + confirm2 (mais rotações com confirmação)
# ===========================================================================
print("\n[H13] hysteresis=10% + confirm2 ...")
s = PortfolioHysteresisCustom(hysteresis=0.10, confirm_months=2, redist_mode="pool")
r_full = run_portfolio_backtest(universe, s, config, "2010-01-01", TODAY,
                                satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
s3 = PortfolioHysteresisCustom(hysteresis=0.10, confirm_months=2, redist_mode="pool")
r_3y = run_portfolio_backtest(universe, s3, config, THREE_Y, TODAY,
                               satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
# Note: H13 é idêntico a H4 (confirm_months é sempre 2 em H4)
results.append(report("H13 — hyst10%+confirm2 (=H4)", r_full, r_3y))

# ===========================================================================
# H14 — score window 9-1 + hysteresis 10%
# ===========================================================================
print("\n[H14] score 9-1 + hyst=10% ...")
s = PortfolioHysteresisScoreWindow(lookback=189, skip_recent=21, hysteresis=0.10, confirm_months=2, redist_mode="pool")
r_full = run_portfolio_backtest(universe, s, config, "2010-01-01", TODAY,
                                satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
s3 = PortfolioHysteresisScoreWindow(lookback=189, skip_recent=21, hysteresis=0.10, confirm_months=2, redist_mode="pool")
r_3y = run_portfolio_backtest(universe, s3, config, THREE_Y, TODAY,
                               satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
results.append(report("H14 — score9-1+hyst10%", r_full, r_3y))

# ===========================================================================
# RANKING FINAL
# ===========================================================================
print("\n" + "=" * 70)
print("RANKING FINAL (por capital final FULL)")
print("=" * 70)
print(f"  {'#':3}  {'Label':35}  {'Final':>10}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>7}  {'NegYrs':>7}  {'Status'}")
print(f"  {'-'*3}  {'-'*35}  {'-'*10}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*6}")

# REF line
print(f"  {'REF':3}  {'portfolio_hysteresis (REF)':35}  R${REF_FULL:>8,.0f}  {'34.33%':>7}  {'0.84':>7}  {'-32.99%':>7}  {'1':>7}  {'---'}")

sorted_r = sorted(results, key=lambda x: x["final"], reverse=True)
for i, r in enumerate(sorted_r, 1):
    label_short = r["label"][:35]
    status = "✓ PASSOU" if r["passed"] else "✗ FALHOU"
    print(f"  {i:3}  {label_short:35}  R${r['final']:>8,.0f}  {r['cagr']*100:>6.2f}%  {r['sharpe']:>7.2f}  {r['maxdd']*100:>6.2f}%  {r['neg']:>7}  {status}")

winners = [r for r in results if r["passed"]]
print(f"\n{'='*70}")
if winners:
    print(f"PASSOU A META: {len(winners)} hipótese(s)")
    for w in sorted(winners, key=lambda x: x["final"], reverse=True):
        print(f"  {w['label']}: R${w['final']:,.0f}")
else:
    print("NENHUMA hipótese passou a meta completa.")
    # Mostrar as mais promissoras
    top3 = sorted(results, key=lambda x: x["final"], reverse=True)[:3]
    print("Top-3 mais próximas:")
    for r in top3:
        gap = r["final"] - 150_000
        print(f"  {r['label']}: R${r['final']:,.0f} (gap={gap:+,.0f})")
print("=" * 70)
