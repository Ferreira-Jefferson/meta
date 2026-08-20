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
    # Lista branca de `Strategy.state()`/`restore()` (ver `strategy/base.py`):
    # so `_pending_rebalance` precisa sobreviver a um restart. Declarada na
    # RAIZ da familia (nao na folha, `portfolio_dip2_hw40.py`) para ser
    # herdada automaticamente por `DipTop1Hysteresis` -> `PortfolioHysteresis`
    # -> `DipTop1Portfolio` (a campea), sem redeclarar em cada subclasse.
    _stateful_keys = ("_pending_rebalance",)

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

    def on_missed_bars(self, missed):
        """Pregão perdido que era fim de mês deixa a rotação DEVIDA.

        Este robô só rebalanceia quando `is_month_end` é verdade naquele dia
        (ver `on_bar`). Se o processo estava fora do ar exatamente naquele
        fecho, o mês inteiro passa sem rotação — a carteira fica com o que
        sobrou do mês anterior até a virada seguinte.

        Marca `_pending_rebalance`, que é o MESMO mecanismo já usado para o
        blackout de resultados: no próximo pregão o robô recalcula momentum,
        distância da máxima e gate de Selic COM O DADO DESSE PREGÃO e decide
        do zero. Não é a decisão velha sendo executada tarde (regra 7) — é
        uma decisão nova, que pode perfeitamente ser "não entra".

        Pregão perdido que não era fim de mês não deve nada: naquele dia o
        robô teria devolvido lista vazia de qualquer forma.
        """
        for d in missed:
            ts = pd.Timestamp(d)
            if ts in self._month_end.index and bool(self._month_end.loc[ts]):
                self._pending_rebalance = True
                return

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
        # Rank (1 = melhor momentum) e score por ticker, só para o `metadata`
        # da entrada — `tgt` abaixo continua sendo a decisão.
        rank_de = {t: i + 1 for i, (t, _) in enumerate(cands)}
        score_de = {t: v for (t, v) in cands}
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
            # `reason`/`metadata` são REGISTRO, não decisão: nada abaixo muda
            # o que já foi decidido nas linhas acima. Guardam a resposta para
            # "por que este papel neste dia?" — a regra que disparou mais os
            # números que a satisfizeram. Ver `Enter` em `strategy/base.py`.
            actions.append(Enter(
                ticker=t, size_hint=sh, reason="dip_rank",
                metadata={
                    "rank": rank_de.get(t),
                    "top_n": int(self.top_n),
                    "momentum_score": score_de.get(t),
                    "dist_from_high": float(dist),
                    "dip_threshold": -float(self.dip_pct),
                    "high_window": int(self.high_window),
                    "lookback": int(self.lookback),
                    "skip_recent": int(self.skip_recent),
                    "trigger": "month_end" if is_me else "pending_rebalance",
                },
            ))
        return actions
