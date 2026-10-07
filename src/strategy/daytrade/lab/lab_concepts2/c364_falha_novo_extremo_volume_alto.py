"""Catálogo volume/microestrutura, item 65: FalhaDeNovoExtremoComVolumeAlto.

Preço fica `limiar_barras` barras sem fazer nova máxima/mínima (janela
rolante) apesar de volume persistentemente acima de uma referência mais
longa -- monta operação de range, fade nas bordas da faixa formada.
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
class FalhaDeNovoExtremoComVolumeAlto(IntradayStrategy):
    """N barras sem novo extremo apesar de volume alto -- monta range e
    faz fade na borda mais próxima do fechamento atual."""

    name: str = "falha_novo_extremo_volume_alto"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 30
    janela_vol_base: int = 60
    fator_volume_alto: float = 1.2
    limiar_barras_sem_extremo: int = 15
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _vols_base: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)
    _sem_extremo: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._vols_base = deque(maxlen=self.janela_vol_base)
        self._sem_extremo = 0

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
        if (len(self._highs) == self._highs.maxlen
                and len(self._vols_base) == self._vols_base.maxlen):
            range_high = max(self._highs)
            range_low = min(self._lows)
            vol_ma_base = sum(self._vols_base) / len(self._vols_base)
            fez_novo_extremo = bar.high > range_high or bar.low < range_low
            volume_alto = bar.volume > self.fator_volume_alto * vol_ma_base

            if fez_novo_extremo:
                self._sem_extremo = 0
            else:
                if volume_alto:
                    self._sem_extremo += 1

            if (not positions and self._sem_extremo >= self.limiar_barras_sem_extremo):
                dist_high = range_high - bar.close
                dist_low = bar.close - range_low
                if dist_high < dist_low:
                    acao = self._ordem("short", range_high)
                else:
                    acao = self._ordem("long", range_low)

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        self._vols_base.append(bar.volume)
        return acao
