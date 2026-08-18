from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


TRADING_DAYS = 252


def cagr(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 0.0
    total_return = equity.iloc[-1] / equity.iloc[0]
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0 or total_return <= 0:
        return 0.0
    return total_return ** (1.0 / years) - 1.0


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def sharpe(equity: pd.Series, rf_annual: float = 0.10) -> float:
    ret = equity.pct_change().dropna()
    if ret.std() == 0 or len(ret) == 0:
        return 0.0
    daily_rf = (1.0 + rf_annual) ** (1.0 / TRADING_DAYS) - 1.0
    excess = ret - daily_rf
    return float(excess.mean() / excess.std() * math.sqrt(TRADING_DAYS))


def sortino(equity: pd.Series, rf_annual: float = 0.10) -> float:
    ret = equity.pct_change().dropna()
    if len(ret) == 0:
        return 0.0
    daily_rf = (1.0 + rf_annual) ** (1.0 / TRADING_DAYS) - 1.0
    excess = ret - daily_rf
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return 0.0
    return float(excess.mean() / downside.std() * math.sqrt(TRADING_DAYS))


def calmar(equity: pd.Series) -> float:
    c = cagr(equity)
    dd = abs(max_drawdown(equity))
    return c / dd if dd > 0 else 0.0


def negative_years(equity: pd.Series) -> int:
    """Conta anos-calendário com retorno negativo (primeiro vs último valor do ano).

    Critério usado nos experimentos de ranking (NegYrs) — ver scripts/run_confirm_final_winners.py.
    """
    if len(equity) < 2:
        return 0
    yearly = equity.resample("YE").agg(["first", "last"])
    ret = yearly["last"] / yearly["first"] - 1.0
    return int((ret < 0).sum())


def trade_stats(pnls: Iterable[float]) -> dict[str, float]:
    arr = np.array(list(pnls), dtype=float)
    if len(arr) == 0:
        return {"win_rate": 0.0, "profit_factor": 0.0, "expectancy": 0.0}
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    win_rate = len(wins) / len(arr)
    gross_win = float(wins.sum())
    gross_loss = float(-losses.sum())
    profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")
    expectancy = float(arr.mean())
    return {"win_rate": win_rate, "profit_factor": profit_factor, "expectancy": expectancy}
