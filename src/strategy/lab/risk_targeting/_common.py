"""Base comum da familia `risk_targeting`.

Cada hipotese desta familia testa uma REGRA DE TAMANHO diferente — vol
targeting, risk parity, teto de risco por posicao — mantendo o MESMO sinal de
entrada/saida do campeao (`strategy.buy_the_dip.BuyTheDip`, os mesmos
parametros congelados que sustentam `liquid_champion`: momentum 12-1, dip 2%,
high_window 40, rebalance mensal, gate de Selic, blackout de resultados). Isso
isola o efeito do dimensionamento do efeito do sinal: se todas as 10 hipoteses
compartilhassem tambem o sinal e so o tamanho mudasse, a comparacao entre elas
mede exatamente o que a familia promete medir.

`RiskTargetingDip.on_bar` e uma copia deliberada da rotacao de
`BuyTheDip.on_bar` (nao um import/hook, porque a classe-mae nao expõe um ponto
de extensao para sizing) com UM ponto trocado: em vez de `sh = 1/top_n` fixo
para toda entrada, cada subclasse implementa `_weights_for(entering, date,
open_positions)` devolvendo a fracao do caixa ORIGINAL (antes de qualquer
entrada do dia) que cada ticker deveria receber. As fracoes NAO precisam somar
1 — uma hipotese de vol-targeting de carteira pode devolver soma < 1 de
proposito, deixando caixa parado quando o regime esta turbulento.

`sequential_size_hints` resolve a mecanica de execucao: o engine consome
`size_hint` como fracao do caixa RESTANTE no momento em que processa cada
`Enter`, nao do caixa original (ver `backtest/sizing.py` e o mesmo truque em
`strategy/liquid_sleeves5.py`, comentario sobre `1/(idle-k)`). Sem essa
conversao, pedir 20%/20%/20%/20%/20% do caixa original processado em
sequencia entregaria 20%, 16%, 12,8%... do caixa original ao ticket 2, 3, 4 —
nao a proporcao pretendida.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

from swing_lab.measure import wide_pool  # noqa: E402

from core.indicators import atr as atr_ind  # noqa: E402
from core.indicators import historical_volatility  # noqa: E402
from core.models import ExitReason  # noqa: E402
from strategy.base import Action, Enter, Exit  # noqa: E402
from strategy.buy_the_dip import BuyTheDip  # noqa: E402


def sequential_size_hints(weights: list[float]) -> list[float]:
    """`weights[k]` e a fracao do caixa ORIGINAL desejada para a k-esima
    entrada (na ordem em que o engine vai processa-las). Devolve a sequencia
    de `size_hint` (fracao do caixa RESTANTE) que reproduz essas fracoes
    depois do consumo sequencial do engine.
    """
    hints: list[float] = []
    consumed = 0.0
    for w in weights:
        remaining = 1.0 - consumed
        if remaining <= 1e-9 or w <= 0:
            hints.append(0.0)
        else:
            hints.append(min(1.0, w / remaining))
        consumed += max(0.0, w)
    return hints


class RiskTargetingDip(BuyTheDip):
    """Sinal congelado do campeao + ponto de extensao `_weights_for` para
    dimensionamento. Nao e instanciavel como robo de producao (`candidate =
    False`, e `_weights_for` explode se nao sobrescrito) — cada `hip_NN.py`
    e a peca concreta.
    """

    candidate = False
    universe_tickers = wide_pool()

    def __init__(
        self,
        vol_window: int = 20,
        atr_window: int = 14,
        **kwargs,
    ):
        # Sinal CONGELADO: os mesmos parametros que sustentam o campeao
        # (`portfolio_dip2_hw40`/`liquid_champion`). top_n=5 (nao 1) porque
        # dimensionamento so diz algo quando ha mais de uma posicao para
        # comparar tamanho entre si.
        kwargs.setdefault("top_n", 5)
        kwargs.setdefault("dip_pct", 0.02)
        kwargs.setdefault("high_window", 40)
        kwargs.setdefault("lookback", 252)
        kwargs.setdefault("skip_recent", 21)
        super().__init__(**kwargs)
        self.vol_window = vol_window
        self.atr_window = atr_window
        self._vol: dict[str, pd.Series] = {}
        self._atr_pct: dict[str, pd.Series] = {}
        self._worst_dd: dict[str, pd.Series] = {}
        self._returns: dict[str, pd.Series] = {}
        self._ibov_vol: pd.Series = pd.Series(dtype=float)

    def initialize(self, panels, ibov) -> None:
        super().initialize(panels, ibov)
        for t, df in panels.items():
            close = df["close"]
            self._vol[t] = historical_volatility(close, window=self.vol_window)
            a = atr_ind(df["high"], df["low"], close, window=self.atr_window)
            self._atr_pct[t] = a / close
            # Pior drawdown ja visto ATE aquele dia (expanding, sem look-ahead):
            # pico expandindo (`cummax`) e o proprio drawdown expandindo em
            # seguida (`cummin`) so usam dado passado.
            dd = close / close.cummax() - 1.0
            self._worst_dd[t] = dd.cummin()
            self._returns[t] = close.pct_change()
        self._ibov_vol = historical_volatility(ibov["close"], window=self.vol_window)

    # ------------------------------------------------------------ ponto de extensao
    def _weights_for(self, entering: list[str], date, open_positions) -> dict[str, float]:
        """Fracao do caixa ORIGINAL (pre-entradas do dia) para cada ticker em
        `entering`. Nao precisa somar 1. Sobrescrever em cada hipotese.
        """
        raise NotImplementedError

    # ------------------------------------------------------------ auxiliares
    def _safe(self, series_map: dict[str, pd.Series], ticker: str, date) -> float | None:
        s = series_map.get(ticker)
        if s is None or date not in s.index:
            return None
        v = s.loc[date]
        if pd.isna(v):
            return None
        return float(v)

    def _equal_weight_fallback(self, entering: list[str]) -> dict[str, float]:
        if not entering:
            return {}
        w = 1.0 / float(len(entering))
        return {t: w for t in entering}

    def _stop_price_for(self, ticker: str, date) -> float | None:
        """Preco ABSOLUTO de stop para a entrada, ou `None` (sem stop
        explicito — engine cai no `default_stop` percentual da config, igual
        para todo ticker). Aproximado a partir do close[D] (a entrada real
        executa no open[D+1], que o robo ainda nao ve): mesma aproximacao que
        toda comparacao de sinal neste arquivo ja faz com `close[D]`. Default
        `None` preserva o comportamento das hipoteses que nao usam stop
        explicito.
        """
        return None

    # ------------------------------------------------------------ on_bar (copia da rotacao)
    def on_bar(self, date, open_positions, cash_available):
        is_me = date in self._month_end.index and bool(self._month_end.loc[date])
        should_rebalance = is_me or self._pending_rebalance
        if not should_rebalance:
            return []
        actions: list[Action] = []
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
            if date not in s.index:
                continue
            v = s.loc[date]
            if pd.isna(v):
                continue
            cands.append((t, float(v)))
        if not cands:
            return actions
        cands.sort(key=lambda x: x[1], reverse=True)
        rank_de = {t: i + 1 for i, (t, _) in enumerate(cands)}
        score_de = {t: v for t, v in cands}
        tgt = {t for t, _ in cands[: self.top_n]}

        for t in open_positions:
            if t not in tgt:
                actions.append(Exit(ticker=t, reason=ExitReason.ROTATION_OUT))

        entering: list[str] = []
        for t in tgt:
            if t in open_positions:
                continue
            dseries = self._dist_from_high.get(t)
            if dseries is None or date not in dseries.index:
                continue
            dist = dseries.loc[date]
            if pd.isna(dist) or float(dist) > -self.dip_pct:
                continue
            entering.append(t)
        if not entering:
            return actions

        weights = self._weights_for(entering, date, open_positions)
        w_list = [max(0.0, float(weights.get(t, 0.0))) for t in entering]
        hints = sequential_size_hints(w_list)
        for t, h, w in zip(entering, hints, w_list):
            if h <= 0.0:
                continue
            dist = float(self._dist_from_high[t].loc[date])
            actions.append(
                Enter(
                    ticker=t,
                    size_hint=h,
                    initial_stop=self._stop_price_for(t, date),
                    reason="risk_targeting_entry",
                    metadata={
                        "rank": rank_de.get(t),
                        "momentum_score": score_de.get(t),
                        "dist_from_high": dist,
                        "weight_target": w,
                        "vol_20": self._safe(self._vol, t, date),
                        "atr_pct": self._safe(self._atr_pct, t, date),
                    },
                )
            )
        return actions
