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

    # Ficha: o que muda em relacao a `BuyTheDip` e a HISTERESE (ver base.py).
    entry_rules = BuyTheDip.entry_rules + (
        "Uma posição por vez: só o rank-1 do momentum interessa.",
        f"Histerese de {int(HYSTERESIS * 100)}%: o novo rank-1 só substitui a posição "
        "atual se o score dele for essa margem melhor. Empate técnico não gera giro — "
        "cada troca custa corretagem, spread e IR.",
    )
    exit_rules = BuyTheDip.exit_rules + (
        "A saída por rotação também passa pela histerese: sem a margem, a posição "
        "FICA, mesmo tendo perdido o primeiro lugar.",
    )

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
        # Só para o `metadata` da entrada (registro, não decisão): de quem o
        # robô rotacionou e com que folga a histerese foi vencida.
        rotacionou_de: str | None = None
        folga_histerese: float | None = None

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
                rotacionou_de = held_ticker
                folga_histerese = rank1_score - threshold
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
                    # REGISTRO da entrada — ver `Enter` em `strategy/base.py`.
                    # A distinção rotação × entrada limpa importa no diário:
                    # uma compra que substituiu outra posição tem um "por quê"
                    # diferente de uma compra feita com o caixa parado.
                    actions.append(Enter(
                        ticker=tgt_ticker, size_hint=1.0,
                        reason=("dip_rank1_rotation" if rotacionou_de
                                else "dip_rank1"),
                        metadata={
                            "rank": 1,
                            "momentum_score": float(rank1_score),
                            "dist_from_high": float(dist),
                            "dip_threshold": -float(self.dip_pct),
                            "hysteresis": float(self._hysteresis),
                            "rotated_from": rotacionou_de,
                            "hysteresis_margin": folga_histerese,
                        },
                    ))

        return actions
