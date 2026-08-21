from __future__ import annotations

import pytest

import strategy.daytrade.base  # garante que o modulo foi importado em processo
from strategy.daytrade.base import IntradayStrategy
from strategy.discovery import discover_strategies


def test_intraday_strategy_e_abstrata():
    with pytest.raises(TypeError):
        IntradayStrategy()


def test_discover_strategies_nunca_traz_nada_de_daytrade():
    found = discover_strategies()
    for d in found:
        assert not d.cls.__module__.startswith("strategy.daytrade")
