"""Catálogo volume/microestrutura, item 77: ReteseFalhaComVolumeConfirmaContinuacao.

Rompimento de um nível (extremo de janela rolante) com volume alto é
seguido por um RETESTE do próprio nível com volume BAIXO -- confirma a
continuação: entra na mesma direção do rompimento original.
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
class ReteseFalhaComVolumeConfirmaContinuacao(IntradayStrategy):
    """Rompimento com volume + reteste subsequente com volume baixo --
    confirma continuação na direção original do rompimento."""

    name: str = "reteste_falha_volume_confirma_continuacao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    k_volume_rompimento: float = 1.5
    fator_volume_baixo_reteste: float = 0.8
    tolerancia_reteste_ticks: int = 3
    espera_max_barras: int = 15
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _rompimento: dict | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._vols = deque(maxlen=self.janela_range)
        self._rompimento = None

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
        vol_ma = sum(self._vols) / len(self._vols) if self._vols else None
        tol = self.tolerancia_reteste_ticks * self.tick_size

        if not positions and self._rompimento is not None:
            r = self._rompimento
            r["idade"] += 1
            perto_nivel = abs(bar.low - r["nivel"]) <= tol if r["lado"] == "long" else abs(bar.high - r["nivel"]) <= tol
            if perto_nivel and vol_ma is not None and bar.volume < self.fator_volume_baixo_reteste * vol_ma:
                acao = self._ordem(r["lado"], r["nivel"])
                self._rompimento = None
            elif r["idade"] > self.espera_max_barras:
                self._rompimento = None

        if (not positions and self._rompimento is None
                and len(self._highs) == self._highs.maxlen and vol_ma is not None):
            range_high = max(self._highs)
            range_low = min(self._lows)
            if bar.close > range_high and bar.volume > self.k_volume_rompimento * vol_ma:
                self._rompimento = {"lado": "long", "nivel": range_high, "idade": 0}
            elif bar.close < range_low and bar.volume > self.k_volume_rompimento * vol_ma:
                self._rompimento = {"lado": "short", "nivel": range_low, "idade": 0}

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        self._vols.append(bar.volume)
        return acao
