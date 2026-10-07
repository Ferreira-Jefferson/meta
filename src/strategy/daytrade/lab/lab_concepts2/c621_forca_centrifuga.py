"""Catálogo física, item 22: ForcaCentrifuga.

Analogia com força centrífuga (F ∝ desvio² × curvatura): mede o desvio do
preço em relação a uma "órbita" (EMA) e a curvatura da própria EMA (2ª
derivada, diferença de diferenças); força = desvio² × |curvatura|. Força
crescente (acima de um limiar rolling) sinaliza rompimento iminente para
fora do range recente, na direção do desvio.
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
class ForcaCentrifuga(IntradayStrategy):
    """Força = desvio²×curvatura da EMA ('órbita'); excesso rolling
    sinaliza rompimento iminente na direção do desvio."""

    name: str = "forca_centrifuga"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    periodo_ema: int = 14
    janela_forca: int = 30
    percentil_limiar: float = 85.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _ema: float | None = field(default=None, init=False, repr=False)
    _emas: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _forcas: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._ema = None
        self._emas = deque(maxlen=3)
        self._forcas = deque(maxlen=self.janela_forca)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        alpha = 2.0 / (self.periodo_ema + 1)
        self._ema = bar.close if self._ema is None else alpha * bar.close + (1 - alpha) * self._ema
        self._emas.append(self._ema)

        if len(self._emas) == 3:
            curvatura = (self._emas[-1] - self._emas[-2]) - (self._emas[-2] - self._emas[-3])
            desvio = bar.close - self._ema
            forca = (desvio ** 2) * abs(curvatura)
            self._forcas.append(forca)

            if not positions and len(self._forcas) >= 10:
                import numpy as np
                limiar = float(np.percentile(self._forcas, self.percentil_limiar))
                if forca >= limiar and forca > 0:
                    if desvio > 0:
                        limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="long", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
                    elif desvio < 0:
                        limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side="short", limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
        return acao
