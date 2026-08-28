from __future__ import annotations

import pandas as pd
import pytest

from backtest.intraday.continuidade_zigzag import (
    Pivot,
    continuation_series,
    zigzag_pivots,
)


def _series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2026-01-01", periods=len(values), freq="1min")
    return pd.Series(values, index=idx)


def test_zigzag_confirms_pivots_only_after_reversal_past_threshold():
    # 100(low) -> 103(high, confirmado ao cair 2.5) -> 100.5(low, confirmado
    # ao subir 4.5) -> 105(high, confirmado ao cair 3) -- ultimo movimento
    # (105->102) NAO confirma nada, fica pendente.
    prices = _series([100, 101, 99, 103, 100.5, 105, 102])
    pivots = zigzag_pivots(prices, threshold=2.0)
    assert [(p.price, p.kind) for p in pivots] == [
        (100.0, "low"),
        (103.0, "high"),
        (100.5, "low"),
        (105.0, "high"),
    ]
    # alterna low/high por construcao
    kinds = [p.kind for p in pivots]
    for a, b in zip(kinds, kinds[1:]):
        assert a != b


def test_zigzag_ignores_moves_below_threshold():
    # nenhum movimento chega a 5.0 de amplitude -> nenhum pivo confirmado
    prices = _series([100, 102, 99, 101, 103, 100])
    pivots = zigzag_pivots(prices, threshold=5.0)
    assert pivots == []


def test_zigzag_rejects_non_positive_threshold():
    prices = _series([100, 101])
    with pytest.raises(ValueError):
        zigzag_pivots(prices, threshold=0.0)
    with pytest.raises(ValueError):
        zigzag_pivots(prices, threshold=-1.0)


def test_zigzag_short_series_has_no_pivots():
    assert zigzag_pivots(_series([100.0]), threshold=1.0) == []
    assert zigzag_pivots(_series([]), threshold=1.0) == []


def _pivot(price: float, kind: str) -> Pivot:
    return Pivot(ts=pd.Timestamp("2026-01-01"), price=price, kind=kind)  # type: ignore[arg-type]


def test_continuation_series_flags_new_extreme_as_continuation():
    # topos: 103 -> 105 supera (1). fundos: 100 -> 100.5 NAO faz nova
    # minima, 100.5 > 100 (0).
    pivots = [
        _pivot(100.0, "low"),
        _pivot(103.0, "high"),
        _pivot(100.5, "low"),
        _pivot(105.0, "high"),
    ]
    out = continuation_series(pivots)
    assert out["high"] == [1]
    assert out["low"] == [0]


def test_continuation_series_needs_a_prior_pivot_of_the_same_kind():
    # so' 1 high e 1 low -- nenhum dos dois tem antecessor do mesmo tipo
    pivots = [_pivot(100.0, "low"), _pivot(103.0, "high")]
    out = continuation_series(pivots)
    assert out["high"] == []
    assert out["low"] == []


def test_continuation_series_uptrend_makes_higher_highs_but_not_lower_lows():
    # tendencia de alta pura: cada novo topo supera o anterior (high=1),
    # mas os fundos SOBEM (nao fazem nova minima) -> low=0 sempre.
    pivots = [
        _pivot(100.0, "low"),
        _pivot(103.0, "high"),
        _pivot(101.0, "low"),   # 101 > 100 -- NAO e' nova minima -> 0
        _pivot(106.0, "high"),  # supera o topo anterior 103 -> 1
        _pivot(102.0, "low"),   # 102 > 101 -- NAO e' nova minima -> 0
        _pivot(109.0, "high"),  # supera 106 -> 1
    ]
    out = continuation_series(pivots)
    assert out["high"] == [1, 1]
    assert out["low"] == [0, 0]


def test_continuation_series_downtrend_makes_lower_lows_but_not_higher_highs():
    pivots = [
        _pivot(110.0, "high"),
        _pivot(107.0, "low"),
        _pivot(109.0, "high"),  # 109 < 110 -- NAO supera -> 0
        _pivot(104.0, "low"),   # 104 < 107 -- nova minima -> 1
        _pivot(108.0, "high"),  # 108 < 109 -- NAO supera -> 0
        _pivot(101.0, "low"),   # 101 < 104 -- nova minima -> 1
    ]
    out = continuation_series(pivots)
    assert out["high"] == [0, 0]
    assert out["low"] == [1, 1]
