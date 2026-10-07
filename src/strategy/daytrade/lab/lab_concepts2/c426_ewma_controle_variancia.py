"""EWMAControleVariancia -- gatilho de rompimento condicionado a vol EWMA elevada.

EWMA da VARIANCIA dos retornos (nao da media) detecta mudanca de regime
de volatilidade -- diferente de um controle de media (CUSUM), aqui o
alvo e' o segundo momento. Comparado a uma linha de base (mediana movel
da propria serie de vol EWMA), a estrategia "liga" um gatilho de
rompimento (maxima/minima recente) so' quando a vol EWMA sobe acima da
linha de base por um multiplicador; "desliga" (fica de fora) quando a
vol volta a normalizar. Sai pelo stop/alvo fixos.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class EWMAControleVariancia(IntradayStrategy):
    """Rompimento habilitado so' quando a vol EWMA supera a linha de base."""

    name: str = "c426_ewma_controle_variancia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    alpha_ewma: float = 0.06
    janela_baseline: int = 60
    multiplicador_gatilho: float = 1.4
    janela_rompimento: int = 10
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _var_ewma: float | None = field(default=None, init=False, repr=False)
    _historico_vol: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)
    _highs: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._var_ewma = None
        self._historico_vol = deque(maxlen=self.janela_baseline)
        self._highs = deque(maxlen=self.janela_rompimento)
        self._lows = deque(maxlen=self.janela_rompimento)

    def _entrada(self, side: str, limite: float, stop_dist: float, alvo_dist: float) -> list[IntradayAction]:
        tick = self.tick_size
        limite = no_tick(limite, tick)
        if side == "long":
            stop = no_tick(limite - stop_dist, tick)
            alvo = no_tick(limite + alvo_dist, tick)
        else:
            stop = no_tick(limite + stop_dist, tick)
            alvo = no_tick(limite - alvo_dist, tick)
        return [EnterLimit(
            side=side, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=1, ttl_bars=self.entrada_ttl_bars, exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
        )]

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._var_ewma = (
                r * r if self._var_ewma is None
                else self.alpha_ewma * r * r + (1 - self.alpha_ewma) * self._var_ewma
            )
            self._historico_vol.append(np.sqrt(self._var_ewma))

        if positions:
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            return []

        ligado = False
        if len(self._historico_vol) >= 15:
            vol_atual = self._historico_vol[-1]
            baseline = float(np.median(self._historico_vol))
            ligado = baseline > 1e-12 and vol_atual > baseline * self.multiplicador_gatilho

        acao: list[IntradayAction] = []
        if ligado and len(self._highs) == self.janela_rompimento:
            tick = self.tick_size
            if bar.high > max(self._highs):
                acao = self._entrada("long", bar.close - self.offset_ticks * tick,
                                      self.stop_ticks * tick, self.alvo_ticks * tick)
            elif bar.low < min(self._lows):
                acao = self._entrada("short", bar.close + self.offset_ticks * tick,
                                      self.stop_ticks * tick, self.alvo_ticks * tick)

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
