import sys; sys.path.insert(0, 'src')
import pandas as pd
from backtest.engine_portfolio import run_portfolio_backtest
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.portfolio_satellite import PortfolioHysteresis

TICKERS = ["WEGE3.SA","BRAP4.SA","RADL3.SA","CSMG3.SA","EMAE4.SA","KEPL3.SA","CXSE3.SA"]
ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
TODAY = ref.index[-1].strftime("%Y-%m-%d")

universe = load_universe(tickers=TICKERS, include_benchmark=True)
config = BacktestConfig(initial_capital=1000.0, lot_size=1, stop_loss_pct=0.15)
strategy = PortfolioHysteresis(confirm_months=2, redist_mode="pool")
r = run_portfolio_backtest(universe, strategy, config, start="2010-01-01", end=TODAY,
                            satellite_pct=0.05, satellite_stop_pct=0.20, redist_mode="pool")
m = r.metrics
eq = r.equity_curve
yearly = eq.resample("YE").agg(["first","last"])
yearly["ret"] = yearly["last"]/yearly["first"]-1
neg = int((yearly["ret"] < 0).sum())
print(f"REF: Final={m['final_capital']:.0f} CAGR={m['cagr']*100:.2f}% Sharpe={m['sharpe']:.2f} MaxDD={m['max_drawdown']*100:.2f}% NegYrs={neg}")
print(f"eq min={eq.min():.2f}, eq max={eq.max():.2f}, eq first={eq.iloc[0]:.2f}")
print(f"Sharpe check: {m['sharpe']:.4f}")
