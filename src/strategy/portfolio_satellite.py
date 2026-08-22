"""PortfolioHysteresis — histerese com satelites acumulativos.

A cada rotacao, 5% fica como satelite no ativo anterior. Os satelites acumulam
ao longo do tempo. Saida de satelite: score 12-1 negativo (momentum perdido)
ou valor < 20% do ref (stop). O que acontece com o dinheiro ao sair e
controlado pelo engine (vide engine_portfolio.py).
"""
from __future__ import annotations
import pandas as pd
from strategy.h3_hysteresis import DipTop1Hysteresis


class PortfolioHysteresis(DipTop1Hysteresis):
    """Histerese 15% + satelites acumulativos com saida por momentum negativo."""
    name = "portfolio_hysteresis"
    version = "1.0"
    candidate = False  # classe-base da familia dip (usada por composicao), fora do ranking

    satellite_pct: float = 0.05
    satellite_stop_pct: float = 0.20
    signal_confirm_months: int = 1  # 1 = saida imediata, 2 = confirma 2 meses
    redist_mode: str = "pool"

    # Ficha (ver `Strategy` em `strategy/base.py`).
    param_docs = {
        "confirm_months": "Meses de momentum negativo para fechar um satélite.",
        "redist_mode": "Para onde vai o dinheiro de um satélite fechado.",
    }

    def __init__(self, confirm_months: int = 1, redist_mode: str = "pool", **kwargs):
        super().__init__(**kwargs)
        self.signal_confirm_months = confirm_months
        self.redist_mode = redist_mode
        self._neg_streak: dict[str, int] = {}  # ticker -> meses consecutivos negativos

    def satellite_exit_signal(self, ticker: str, date) -> bool:
        """True se o ticker deve ter o satelite fechado por momentum negativo."""
        score_series = self._scores.get(ticker)
        if score_series is None or date not in score_series.index:
            return False
        v = score_series.loc[date]
        if pd.isna(v):
            return False
        is_neg = float(v) < 0

        if self.signal_confirm_months <= 1:
            return is_neg

        # Confirma N meses consecutivos
        streak = self._neg_streak.get(ticker, 0)
        if is_neg:
            streak += 1
            self._neg_streak[ticker] = streak
        else:
            self._neg_streak[ticker] = 0
        return streak >= self.signal_confirm_months
