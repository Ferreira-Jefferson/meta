"""Catálogo física, item 23: GravidadeVWAPImplicito.

Analogia gravitacional: o VWAP intradiário (close×volume acumulado / volume
acumulado, calculado incrementalmente desde a abertura) age como "centro
gravitacional" da sessão. Entra em fade (volta ao centro) quando o preço se
estica além de N desvios-padrão (dos desvios close−VWAP acumulados) da
âncora.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class GravidadeVWAPImplicito(IntradayStrategy):
    """VWAP incremental da sessão como centro gravitacional; fade quando o
    preço se estica além de N desvios-padrão da âncora."""

    name: str = "gravidade_vwap_implicito"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    k_desvios: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    entrada_ttl_bars: int = 40

    _soma_pv: float = field(default=0.0, init=False, repr=False)
    _soma_v: float = field(default=0.0, init=False, repr=False)
    _desvios: deque = field(default_factory=lambda: deque(maxlen=200), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._soma_pv = 0.0
        self._soma_v = 0.0
        self._desvios = deque(maxlen=200)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        volume = max(bar.volume, 1e-6)
        self._soma_pv += bar.close * volume
        self._soma_v += volume
        vwap = self._soma_pv / self._soma_v

        if not positions and len(self._desvios) >= 20:
            import numpy as np
            desvio_padrao = float(np.std(self._desvios))
            if desvio_padrao > 1e-9:
                distancia = bar.close - vwap
                if distancia > self.k_desvios * desvio_padrao:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(vwap, self.tick_size)
                    if limite - alvo >= 4 * self.tick_size:
                        acao = [EnterLimit(
                            side="short", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                elif distancia < -self.k_desvios * desvio_padrao:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(vwap, self.tick_size)
                    if alvo - limite >= 4 * self.tick_size:
                        acao = [EnterLimit(
                            side="long", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]

        self._desvios.append(bar.close - vwap)
        return acao
