"""Catálogo física, item 27: MeiaVidaMomentumRadioativo.

Analogia com decaimento radioativo N(t)=N0·e^(-λt): ao entrar por
rompimento de momentum, estima λ por regressão log-linear simples do
tamanho dos impulsos de momentum passados (janela de swings recentes,
mesma extração de amplitude de `BifurcacaoCascata`) contra o número de
barras desde o pico de cada um — sai (Exit) da posição quando as barras
decorridas (`bars_held`) excedem a "meia-vida" (ln2/λ) estimada do impulso
que gerou a entrada.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class MeiaVidaMomentumRadioativo(IntradayStrategy):
    """Estima λ de decaimento via regressão log-linear das amplitudes de
    swings passados; sai quando `bars_held` excede a meia-vida (ln2/λ) do
    impulso que gerou a entrada."""

    name: str = "meia_vida_momentum_radioativo"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_vol: int = 20
    k_volume: float = 1.5
    meia_vida_padrao_barras: int = 12
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 12
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _amplitudes_recentes: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)
    _meia_vida_da_entrada: int = field(default=12, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._vols = deque(maxlen=self.janela_vol)
        self._amplitudes_recentes = deque(maxlen=10)
        self._meia_vida_da_entrada = self.meia_vida_padrao_barras

    def _estimar_meia_vida(self) -> int:
        if len(self._amplitudes_recentes) < 3:
            return self.meia_vida_padrao_barras
        amplitudes = np.array(self._amplitudes_recentes, dtype=float)
        amplitudes = amplitudes[amplitudes > 1e-9]
        if len(amplitudes) < 3:
            return self.meia_vida_padrao_barras
        idx = np.arange(1, len(amplitudes) + 1, dtype=float)
        log_amp = np.log(amplitudes)
        inclinacao, _ = np.polyfit(idx, log_amp, 1)
        lam = -inclinacao
        if lam <= 1e-6:
            return self.meia_vida_padrao_barras
        meia_vida = np.log(2.0) / lam
        return int(np.clip(meia_vida, 2, 200))

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if positions:
            if positions[0].bars_held >= self._meia_vida_da_entrada:
                acao = [Exit(reason=self.name)]
        elif (len(self._highs) == self._highs.maxlen and len(self._vols) == self._vols.maxlen):
            range_high, range_low = max(self._highs), min(self._lows)
            vol_media = sum(self._vols) / len(self._vols)
            rompeu_alta = bar.close > range_high and bar.volume > self.k_volume * vol_media
            rompeu_baixa = bar.close < range_low and bar.volume > self.k_volume * vol_media
            if rompeu_alta or rompeu_baixa:
                self._amplitudes_recentes.append(range_high - range_low)
                self._meia_vida_da_entrada = self._estimar_meia_vida()
                if rompeu_alta:
                    limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                else:
                    limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        self._vols.append(bar.volume)
        return acao
