from __future__ import annotations
import pandas as pd
from core.models import ExitReason
from strategy.base import Enter, Exit
from strategy.buy_the_dip import BuyTheDip

HYSTERESIS = 0.15

class DipTop1Hysteresis(BuyTheDip):
    """Só rotaciona se novo rank-1 tem score >= 15% melhor que o ticker em carteira."""
    name = "dip_top1_hysteresis"
    version = "1.0"
    candidate = False  # classe-base da familia dip (usada por composicao), fora do ranking

    def __init__(self, **kwargs):
        kwargs.setdefault("top_n", 1)
        kwargs.setdefault("dip_pct", 0.01)
        kwargs.setdefault("selic_threshold", 0.005)
        super().__init__(**kwargs)
        self._hysteresis = HYSTERESIS

    def on_bar(self, date, open_positions, cash_available):
        is_me = date in self._month_end.index and bool(self._month_end.loc[date])
        if not (is_me or self._pending_rebalance):
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
        if not cands:
            return actions
        cands.sort(key=lambda x: x[1], reverse=True)

        rank1_ticker, rank1_score = cands[0]

        # If already holding a ticker, check hysteresis before rotating
        held = list(open_positions.keys()) if open_positions else []
        if held:
            held_ticker = held[0]
            held_score_series = self._scores.get(held_ticker)
            held_score = 0.0
            if held_score_series is not None and date in held_score_series.index:
                v = held_score_series.loc[date]
                if not pd.isna(v):
                    held_score = float(v)

            if rank1_ticker != held_ticker:
                # Only rotate if new rank-1 is significantly better
                threshold = held_score * (1 + self._hysteresis) if held_score > 0 else held_score + abs(held_score) * self._hysteresis
                if rank1_score < threshold:
                    # Keep current position — hysteresis prevents rotation
                    # But still check if held ticker dip is ok (it's already in position, no dip check needed for holding)
                    return []
                # Rotation justified
                actions.append(Exit(ticker=held_ticker, reason=ExitReason.ROTATION_OUT))
        else:
            # No position — check if rank-1 has dip
            pass

        # Enter rank-1 if not already held (after potential exit above)
        tgt_ticker = rank1_ticker
        if tgt_ticker not in open_positions or (held and tgt_ticker != held[0]):
            dseries = self._dist_from_high.get(tgt_ticker)
            if dseries is not None and date in dseries.index:
                dist = dseries.loc[date]
                if not pd.isna(dist) and float(dist) <= -self.dip_pct:
                    actions.append(Enter(ticker=tgt_ticker, size_hint=1.0))

        return actions
