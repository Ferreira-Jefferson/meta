"""Buy-the-dip: entradas condicionadas a estar abaixo do 20d high.

Hipótese: comprar no fim do mês pega qualquer preço. Filtrar entradas para
tickers que estão pelo menos 3% abaixo do máximo dos últimos 20 pregões
melhora timing de entrada, reduz DD.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from core.indicators import rolling_high
from core.models import ExitReason
from strategy.base import Action, Enter, Exit, OpenPosition, Strategy


class BuyTheDip(Strategy):
    name = "buy_the_dip"
    version = "1.0"
    candidate = False  # classe-base da familia dip (usada por composicao), fora do ranking

    def __init__(
        self,
        lookback: int = 252,
        skip_recent: int = 21,
        top_n: int = 3,
        selic_window: int = 63,
        selic_threshold: float = 0.005,
        selic_path: str = "data/raw/selic.parquet",
        dip_pct: float = 0.03,
        high_window: int = 20,
    ):
        self.lookback = lookback
        self.skip_recent = skip_recent
        self.top_n = top_n
        self.selic_window = selic_window
        self.selic_threshold = selic_threshold
        self.selic_path = selic_path
        self.dip_pct = dip_pct
        self.high_window = high_window
        self._scores = {}
        self._dist_from_high = {}
        self._selic_tightening = pd.Series(dtype=bool)
        self._month_end = pd.Series(dtype=bool)
        self._blackout = pd.Series(dtype=bool)
        self._pending_rebalance = False

    def initialize(self, panels, ibov):
        from core.calendar import is_month_end
        from core.earnings_calendar import blackout_series
        p = Path(self.selic_path)
        if p.exists():
            selic = pd.read_parquet(p)["valor"].reindex(ibov.index).ffill()
            dch = selic - selic.shift(self.selic_window)
            self._selic_tightening = (dch > self.selic_threshold).fillna(False)
        else:
            self._selic_tightening = pd.Series(False, index=ibov.index)
        self._month_end = is_month_end(ibov.index)
        self._blackout = blackout_series(ibov.index)
        for t, df in panels.items():
            c = df["close"]
            self._scores[t] = (c.shift(self.skip_recent) / c.shift(self.lookback)) - 1.0
            hi = rolling_high(c, self.high_window)
            self._dist_from_high[t] = (c / hi) - 1.0  # negativo = abaixo do high

    def on_bar(self, date, open_positions, cash_available):
        is_me = date in self._month_end.index and bool(self._month_end.loc[date])
        should_rebalance = is_me or self._pending_rebalance
        if not should_rebalance:
            return []
        actions = []
        if date in self._selic_tightening.index and bool(self._selic_tightening.loc[date]):
            self._pending_rebalance = False
            for t in open_positions:
                actions.append(Exit(ticker=t, reason=ExitReason.IBOV_DEFENSIVE))
            return actions
        if date in self._blackout.index and bool(self._blackout.loc[date]):
            self._pending_rebalance = True
            return []
        self._pending_rebalance = False
        cands = []
        for t, s in self._scores.items():
            if date not in s.index: continue
            v = s.loc[date]
            if pd.isna(v): continue
            cands.append((t, float(v)))
        if not cands: return actions
        cands.sort(key=lambda x: x[1], reverse=True)
        tgt = {t for (t,_) in cands[:self.top_n]}
        # Exit por rotação
        for t in open_positions:
            if t not in tgt:
                actions.append(Exit(ticker=t, reason=ExitReason.ROTATION_OUT))
        # Entradas condicionais: só se dist_from_high <= -dip_pct
        sh = 1.0 / float(self.top_n)
        for t in tgt:
            if t in open_positions: continue
            dseries = self._dist_from_high.get(t)
            if dseries is None or date not in dseries.index: continue
            dist = dseries.loc[date]
            if pd.isna(dist) or float(dist) > -self.dip_pct:
                continue  # não entra sem o dip
            actions.append(Enter(ticker=t, size_hint=sh))
        return actions
