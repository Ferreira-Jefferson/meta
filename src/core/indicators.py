"""Indicadores técnicos como funções puras.

Sem estado, sem I/O, sem dependência de outras features — todas essas
funções devem ser portáveis diretamente para MQL5 na Fase 2.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ifr(close: pd.Series, window: int = 14) -> pd.Series:
    """Índice de Força Relativa (RSI) — método Wilder."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()


def historical_volatility(close: pd.Series, window: int = 30) -> pd.Series:
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window=window, min_periods=window).std() * np.sqrt(252.0)


def cross_up(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """True nas barras em que `fast` cruza para cima de `slow`."""
    return (fast > slow) & (fast.shift(1) <= slow.shift(1))


def cross_down(fast: pd.Series, slow: pd.Series) -> pd.Series:
    return (fast < slow) & (fast.shift(1) >= slow.shift(1))


def days_since_last_true(series: pd.Series) -> pd.Series:
    """Para cada índice, quantas barras se passaram desde o último True."""
    idx = np.arange(len(series))
    last_true = np.where(series.fillna(False).to_numpy(), idx, -1)
    running = np.maximum.accumulate(last_true)
    result = np.where(running >= 0, idx - running, -1)
    return pd.Series(result, index=series.index)


def rolling_high(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=1).max()


def rolling_low(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=1).min()


def rolling_correlation(a: pd.Series, b: pd.Series, window: int = 60) -> pd.Series:
    return a.rolling(window=window, min_periods=window).corr(b)


def bollinger_bands(
    close: pd.Series, window: int = 20, k: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands: (upper, mid, lower).

    `mid` é a média móvel simples de `window` barras; `upper`/`lower` são
    `mid ± k * std(window)` usando desvio populacional (ddof=0) para bater
    com a convenção clássica de John Bollinger.
    """
    mid = close.rolling(window=window, min_periods=window).mean()
    std = close.rolling(window=window, min_periods=window).std(ddof=0)
    upper = mid + k * std
    lower = mid - k * std
    return upper, mid, lower
