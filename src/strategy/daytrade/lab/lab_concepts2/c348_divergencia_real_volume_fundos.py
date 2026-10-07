"""Catálogo volume/microestrutura, item 49: DivergenciaDeRealVolumeEntreFundos.

Espelho de `c347_divergencia_real_volume_topos.py`: fundo de swing mais
baixo que o anterior, mas com real_volume menor -- divergência altista,
fade comprado.
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
class DivergenciaDeRealVolumeEntreFundos(IntradayStrategy):
    """Fundo de swing mais baixo que o anterior, mas com real_volume menor
    -- divergência altista, fade comprado."""

    name: str = "divergencia_real_volume_fundos"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_pivo: int = 2
    lookback_barras: int = 30
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _real_volume_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    _janela_low: deque = field(default_factory=lambda: deque(maxlen=5), init=False, repr=False)
    _idx: int = field(default=0, init=False, repr=False)
    _fundos: deque = field(default_factory=lambda: deque(maxlen=4), init=False, repr=False)
    _ts_por_idx: dict = field(default_factory=dict, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        self._real_volume_por_ts = bars["real_volume"].to_dict()

    def on_session_start(self, session_date) -> None:
        janela = 2 * self.janela_pivo + 1
        self._janela_low = deque(maxlen=janela)
        self._idx = 0
        self._fundos = deque(maxlen=4)
        self._ts_por_idx = {}

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
        idx = self._idx
        self._idx += 1
        self._ts_por_idx[idx] = ts
        self._janela_low.append(bar.low)

        if len(self._janela_low) == self._janela_low.maxlen:
            centro_idx = idx - self.janela_pivo
            centro_low = self._janela_low[self.janela_pivo]
            if centro_low == min(self._janela_low):
                centro_ts = self._ts_por_idx.get(centro_idx)
                rv = self._real_volume_por_ts.get(centro_ts, 0.0)
                self._fundos.append((centro_idx, centro_low, rv))

        limite_lookback = idx - self.lookback_barras
        candidatos = [p for p in self._fundos if p[0] >= limite_lookback]
        if not positions and len(candidatos) >= 2:
            p1, p2 = candidatos[-2], candidatos[-1]
            if p2[1] < p1[1] and p2[2] < p1[2] and bar.close > p2[1]:
                acao = self._ordem("long", bar.close)

        return acao
