import numpy as np
import pandas as pd

from core.indicators import atr, bollinger_bands, cross_down, cross_up, days_since_last_true, ifr, sma


def test_sma_matches_manual():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    result = sma(s, 3)
    expected = pd.Series([np.nan, np.nan, 2.0, 3.0, 4.0])
    pd.testing.assert_series_equal(result.reset_index(drop=True), expected)


def test_cross_up_detects_only_crossing_bar():
    fast = pd.Series([1, 2, 3, 4, 5], dtype=float)
    slow = pd.Series([3, 3, 3, 3, 3], dtype=float)
    result = cross_up(fast, slow).tolist()
    # Only bar where fast becomes > slow after being <= is index 3 (4 > 3)
    assert result == [False, False, False, True, False]


def test_cross_down_detects_only_crossing_bar():
    fast = pd.Series([5, 4, 3, 2, 1], dtype=float)
    slow = pd.Series([3, 3, 3, 3, 3], dtype=float)
    result = cross_down(fast, slow).tolist()
    assert result == [False, False, False, True, False]


def test_ifr_bounded_between_0_and_100():
    rng = np.random.default_rng(42)
    close = pd.Series(100 + rng.standard_normal(200).cumsum())
    result = ifr(close, 14).dropna()
    assert (result >= 0).all() and (result <= 100).all()


def test_atr_positive():
    rng = np.random.default_rng(0)
    close = pd.Series(100 + rng.standard_normal(60).cumsum())
    high = close + 1.0
    low = close - 1.0
    result = atr(high, low, close, 14).dropna()
    assert (result > 0).all()


def test_days_since_last_true():
    s = pd.Series([False, False, True, False, False, True, False], dtype=bool)
    result = days_since_last_true(s).tolist()
    # Antes do primeiro True → -1; nas barras seguintes conta desde o último True.
    assert result == [-1, -1, 0, 1, 2, 0, 1]


def test_bollinger_bands_midline_matches_sma_and_bands_symmetric():
    rng = np.random.default_rng(7)
    close = pd.Series(100 + rng.standard_normal(60).cumsum())
    upper, mid, lower = bollinger_bands(close, window=20, k=2.0)

    # A mediana é a SMA(20)
    pd.testing.assert_series_equal(
        mid.dropna(), sma(close, 20).dropna(), check_names=False
    )
    # Bandas simétricas em torno da mediana
    spread_upper = (upper - mid).dropna()
    spread_lower = (mid - lower).dropna()
    pd.testing.assert_series_equal(spread_upper, spread_lower, check_names=False)
    # k=2 → banda distante 2 desvios; nunca colapsa em série com variação
    assert (spread_upper > 0).all()


def test_bollinger_bands_known_values():
    # série determinística: primeiros 20 valores 1..20 → SMA(20) = 10.5
    close = pd.Series(list(range(1, 25)), dtype=float)
    upper, mid, lower = bollinger_bands(close, window=20, k=2.0)
    # SMA na barra índice 19 (20a barra) = (1+2+...+20)/20 = 10.5
    assert np.isclose(mid.iloc[19], 10.5)
    # std populacional de 1..20 ≈ 5.766
    expected_std = float(np.std(np.arange(1, 21), ddof=0))
    assert np.isclose(upper.iloc[19], 10.5 + 2 * expected_std)
    assert np.isclose(lower.iloc[19], 10.5 - 2 * expected_std)
