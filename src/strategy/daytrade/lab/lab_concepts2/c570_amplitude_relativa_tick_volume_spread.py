"""Catálogo regime/adaptação, item 71: AmplitudeRelativaTickVolumeSpread.

Précompute (em `initialize`) tick_volume e spread e suas médias móveis;
"qualidade de execução" = tick_volume relativo à média MENOS spread
relativo à média -- qualidade RUIM (spread alto + volume baixo) trava
qualquer entrada, independente do sinal de rompimento.
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
class AmplitudeRelativaTickVolumeSpread(IntradayStrategy):
    """Rompimento de range de N barras, travado quando a "qualidade de
    execução" précomputada (tick_volume relativo − spread relativo, ambos
    em razão à própria média móvel) está abaixo de `limiar_qualidade`."""

    name: str = "amplitude_relativa_tick_volume_spread"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_qualidade: int = 20
    limiar_qualidade: float = 0.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _qualidade_por_ts: dict = field(default_factory=dict, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        if "tick_volume" in bars.columns and "spread" in bars.columns:
            vol_ma = bars["tick_volume"].rolling(
                window=self.janela_qualidade, min_periods=self.janela_qualidade,
            ).mean()
            spread_ma = bars["spread"].rolling(
                window=self.janela_qualidade, min_periods=self.janela_qualidade,
            ).mean()
            vol_rel = (bars["tick_volume"] / vol_ma.replace(0.0, pd.NA)) - 1.0
            spread_rel = (bars["spread"] / spread_ma.replace(0.0, pd.NA)) - 1.0
            qualidade = (vol_rel - spread_rel).astype(float)
            self._qualidade_por_ts = {ts: float(v) for ts, v in qualidade.items() if pd.notna(v)}
        else:
            self._qualidade_por_ts = {}

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        qualidade = self._qualidade_por_ts.get(ts)
        execucao_boa = qualidade is None or qualidade >= self.limiar_qualidade

        if not positions and execucao_boa and len(self._highs) == self._highs.maxlen:
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
