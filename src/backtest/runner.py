"""Dispatcher universal de engine.

Ordem de verificacao (mais especifico primeiro):
  PortfolioHysteresis -> engine_portfolio (satelites acumulativos + momentum exit)
  demais              -> engine padrao
"""
from __future__ import annotations
from typing import Callable, Optional

import pandas as pd

from core.config import BacktestConfig
from strategy.base import Strategy
from backtest.engine import BacktestResult, run_backtest


def run(
    universe: dict[str, pd.DataFrame],
    strategy: Strategy,
    config: BacktestConfig,
    start: str,
    end: str,
    on_progress: Optional[Callable] = None,
    withdrawal_policy=None,
) -> BacktestResult:
    """Roteia para o engine correto conforme o tipo de estrategia.

    `withdrawal_policy` (opcional): overlay de saque periodico — ver
    `backtest/withdrawal.py`. Implementado so no engine de portfolio por
    enquanto; passar para outra familia de estrategia levanta erro em vez de
    silenciosamente ignorar o saque.
    """
    from strategy.portfolio_satellite import PortfolioHysteresis
    if isinstance(strategy, PortfolioHysteresis):
        from backtest.engine_portfolio import run_portfolio_backtest
        return run_portfolio_backtest(
            universe, strategy, config, start=start, end=end,
            satellite_pct=strategy.satellite_pct,
            satellite_stop_pct=strategy.satellite_stop_pct,
            redist_mode=strategy.redist_mode,
            on_progress=on_progress,
            withdrawal_policy=withdrawal_policy,
        )
    if withdrawal_policy is not None:
        raise NotImplementedError(
            f"withdrawal_policy nao suportado no engine padrao (estrategia {strategy.name!r}) — "
            "implementado apenas em backtest/engine_portfolio.py"
        )
    return run_backtest(universe, strategy, config, start=start, end=end,
                        on_progress=on_progress)
