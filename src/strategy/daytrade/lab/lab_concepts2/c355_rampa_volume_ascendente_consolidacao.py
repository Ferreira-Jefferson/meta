"""Catálogo volume/microestrutura, item 56: RampaDeVolumeAscendenteEmConsolidacao.

Volume sobe quase linearmente (inclinação positiva + correlação alta com o
tempo, via `numpy.polyfit`/`numpy.corrcoef`) por `janela` barras enquanto o
range de preço encolhe (segunda metade da janela com range menor que a
primeira). Confirmado isso, entra no rompimento do range da janela (estilo
retest, como `c300_rompimento_volume_confirmado.py`).
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
class RampaDeVolumeAscendenteEmConsolidacao(IntradayStrategy):
    """Volume em rampa ascendente + range de preço encolhendo -- entra no
    rompimento do range formado (retest do nível rompido)."""

    name: str = "rampa_volume_ascendente_consolidacao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 10
    correlacao_min: float = 0.6
    fator_contracao: float = 0.7
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela)
        self._lows = deque(maxlen=self.janela)
        self._vols = deque(maxlen=self.janela)

    def _ordem(self, lado: str, nivel: float) -> list[IntradayAction]:
        if lado == "long":
            limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
            alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
        else:
            limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
            alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
        return [EnterLimit(
            side=lado, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=1, ttl_bars=self.entrada_ttl_bars, exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
        )]

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if (not positions and len(self._vols) == self._vols.maxlen
                and len(self._highs) == self._highs.maxlen):
            vols = np.array(self._vols, dtype=float)
            x = np.arange(len(vols), dtype=float)
            slope = float(np.polyfit(x, vols, 1)[0])
            corr = float(np.corrcoef(x, vols)[0, 1]) if vols.std() > 0 else 0.0
            highs = list(self._highs)
            lows = list(self._lows)
            meio = len(highs) // 2
            range1 = max(highs[:meio]) - min(lows[:meio])
            range2 = max(highs[meio:]) - min(lows[meio:])
            rampa_ok = slope > 0 and corr > self.correlacao_min
            contracao_ok = range1 > 0 and range2 < self.fator_contracao * range1

            if rampa_ok and contracao_ok:
                range_high = max(highs)
                range_low = min(lows)
                if bar.close > range_high:
                    acao = self._ordem("long", range_high)
                elif bar.close < range_low:
                    acao = self._ordem("short", range_low)

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        self._vols.append(bar.volume)
        return acao
