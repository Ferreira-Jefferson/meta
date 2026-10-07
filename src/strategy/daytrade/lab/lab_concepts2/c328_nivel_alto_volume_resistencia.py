"""Catálogo volume/microestrutura, item 29: NivelDeAltoVolumeComoResistencia.

Espelho do item 28: mesmo perfil de volume simplificado; quando o preço
estava ABAIXO do POC e retorna a ele sem romper para cima, entra vendido
(resistência).
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


def _poc(janela: deque, bucket_size: float) -> float | None:
    if not janela or bucket_size <= 0:
        return None
    volumes: dict[int, float] = {}
    for b in janela:
        bucket = round(((b.high + b.low) / 2.0) / bucket_size)
        volumes[bucket] = volumes.get(bucket, 0.0) + b.volume
    if not volumes:
        return None
    melhor = max(volumes, key=volumes.get)
    return melhor * bucket_size


@dataclass
class NivelDeAltoVolumeComoResistencia(IntradayStrategy):
    """Perfil de volume simplificado sobre janela rolante; entra vendido
    quando o preço retorna de baixo ao nível de maior volume acumulado
    (POC), tratado como resistência."""

    name: str = "nivel_alto_volume_resistencia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_barras: int = 30
    bucket_ticks: int = 4
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _janela: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._janela = deque(maxlen=self.janela_barras)
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        bucket_size = self.bucket_ticks * self.tick_size

        if not positions and len(self._janela) == self._janela.maxlen and self._close_anterior is not None:
            poc = _poc(self._janela, bucket_size)
            if poc is not None and self._close_anterior < poc and bar.close <= poc <= bar.high:
                limite = no_tick(poc + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._janela.append(bar)
        self._close_anterior = bar.close
        return acao
