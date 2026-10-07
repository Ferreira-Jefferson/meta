"""Catálogo volume/microestrutura, item 55: IlhaDeVolumeIsolada.

Três barras consecutivas A-B-C: B tem volume alto e fica isolada por gaps
de preço nos dois lados (A e C não se sobrepõem à faixa de B), enquanto A
e C têm volume baixo -- ilha de reversão, fade contra a direção de B.
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
class IlhaDeVolumeIsolada(IntradayStrategy):
    """Barra de volume alto isolada por gaps de preço entre duas barras de
    volume baixo -- fade contra a direção da ilha."""

    name: str = "ilha_volume_isolada"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_vol: int = 20
    k_volume_ilha: float = 2.0
    fator_volume_baixo: float = 0.7
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _hist3: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._hist3 = deque(maxlen=3)
        self._vols = deque(maxlen=self.janela_vol)

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
        self._hist3.append((bar.open, bar.high, bar.low, bar.close, bar.volume))

        if not positions and vol_ma and len(self._hist3) == 3:
            (oa, ha, la, ca, va), (ob, hb, lb, cb, vb), (oc, hc, lc, cc, vc) = self._hist3
            ilha_alta = (vb > self.k_volume_ilha * vol_ma
                         and va < self.fator_volume_baixo * vol_ma
                         and vc < self.fator_volume_baixo * vol_ma
                         and lb > ha and hc < lb)
            ilha_baixa = (vb > self.k_volume_ilha * vol_ma
                          and va < self.fator_volume_baixo * vol_ma
                          and vc < self.fator_volume_baixo * vol_ma
                          and hb < la and lc > hb)
            if ilha_alta:
                acao = self._ordem("short", bar.close)
            elif ilha_baixa:
                acao = self._ordem("long", bar.close)

        self._vols.append(bar.volume)
        return acao
