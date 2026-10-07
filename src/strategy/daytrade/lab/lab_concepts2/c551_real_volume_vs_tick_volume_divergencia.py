"""Catálogo regime/adaptação, item 52: RealVolumeVsTickVolumeDivergencia.

Précompute (em `initialize`) a razão real_volume/tick_volume e sua média
móvel sobre TODO o histórico -- razão subindo (acima da própria média)
libera o gatilho de rompimento; razão abaixo da média bloqueia, mesmo com
rompimento técnico válido.
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
class RealVolumeVsTickVolumeDivergencia(IntradayStrategy):
    """Rompimento de range de N barras, liberado só quando a razão
    real_volume/tick_volume está ACIMA da própria média móvel de
    `janela_razao` barras (précomputada em `initialize`) -- proxy de
    participação institucional crescente por trás do rompimento."""

    name: str = "real_volume_vs_tick_volume_divergencia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_razao: int = 20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _liberado_por_ts: dict = field(default_factory=dict, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        if "tick_volume" in bars.columns and "real_volume" in bars.columns:
            tick_vol = bars["tick_volume"].replace(0.0, pd.NA)
            razao = (bars["real_volume"] / tick_vol).astype(float)
            razao_ma = razao.rolling(window=self.janela_razao, min_periods=self.janela_razao).mean()
            liberado = (razao > razao_ma).fillna(False)
            self._liberado_por_ts = {ts: bool(v) for ts, v in liberado.items()}
        else:
            self._liberado_por_ts = {}

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        liberado = self._liberado_por_ts.get(ts, False)

        if not positions and liberado and len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            if bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif bar.close < range_low:
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
        return acao
