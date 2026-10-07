"""Catálogo volume/microestrutura, item 45: RupturaDeLateralizacaoDeBaixoVolume.

Barras em range (janela curta) com volume médio baixo frente a uma
referência de volume mais longa, interrompidas pela primeira barra
direcional com volume alto -- entra na direção dessa barra.
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
class RupturaDeLateralizacaoDeBaixoVolume(IntradayStrategy):
    """Range de baixo volume (frente a uma referência mais longa) rompido
    por uma barra de volume alto -- entra na direção do rompimento."""

    name: str = "ruptura_lateralizacao_baixo_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_vol_base: int = 60
    fator_volume_baixo: float = 0.8
    k_volume_ruptura: float = 1.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols_base: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._vols = deque(maxlen=self.janela_range)
        self._vols_base = deque(maxlen=self.janela_vol_base)

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
        if (not positions and len(self._highs) == self._highs.maxlen
                and len(self._vols_base) == self._vols_base.maxlen):
            range_high = max(self._highs)
            range_low = min(self._lows)
            vol_ma_janela = sum(self._vols) / len(self._vols)
            vol_ma_base = sum(self._vols_base) / len(self._vols_base)
            baixo_volume = vol_ma_janela < self.fator_volume_baixo * vol_ma_base
            volume_forte = bar.volume > self.k_volume_ruptura * vol_ma_base
            if baixo_volume and volume_forte:
                if bar.close > range_high:
                    acao = self._ordem("long", range_high)
                elif bar.close < range_low:
                    acao = self._ordem("short", range_low)

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        self._vols.append(bar.volume)
        self._vols_base.append(bar.volume)
        return acao
