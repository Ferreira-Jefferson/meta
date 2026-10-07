"""Catálogo volume/microestrutura, item 33: ValueAreaRejeicaoComVolumeDecrescente.

Mesmo cálculo de value area do item 32; rompimento de um dos limites com
volume DECRESCENTE (barra atual < barra anterior, ao contrário do item
32) é lido como falta de convicção — fade de volta para DENTRO da faixa.
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


def _value_area(janela: deque, bucket_size: float, fracao: float) -> tuple[float, float] | None:
    if not janela or bucket_size <= 0:
        return None
    volumes: dict[int, float] = {}
    for b in janela:
        bucket = round(((b.high + b.low) / 2.0) / bucket_size)
        volumes[bucket] = volumes.get(bucket, 0.0) + b.volume
    if not volumes:
        return None
    total = sum(volumes.values())
    if total <= 0:
        return None
    ordenados = sorted(volumes.items(), key=lambda kv: kv[1], reverse=True)
    acumulado = 0.0
    escolhidos: list[int] = []
    for bucket, vol in ordenados:
        escolhidos.append(bucket)
        acumulado += vol
        if acumulado >= fracao * total:
            break
    return min(escolhidos) * bucket_size, max(escolhidos) * bucket_size


@dataclass
class ValueAreaRejeicaoComVolumeDecrescente(IntradayStrategy):
    """Rompimento de um dos limites da value area com volume decrescente
    (falta de convicção) — fade de volta para dentro da faixa."""

    name: str = "value_area_rejeicao_volume_decrescente"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_barras: int = 30
    bucket_ticks: int = 4
    fracao_value_area: float = 0.7
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _janela: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _volume_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._janela = deque(maxlen=self.janela_barras)
        self._volume_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        bucket_size = self.bucket_ticks * self.tick_size

        if (not positions and len(self._janela) == self._janela.maxlen
                and self._volume_anterior is not None and bar.volume < self._volume_anterior):
            va = _value_area(self._janela, bucket_size, self.fracao_value_area)
            if va is not None:
                va_low, va_high = va
                if bar.close > va_high:
                    limite = no_tick(va_high + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif bar.close < va_low:
                    limite = no_tick(va_low - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._janela.append(bar)
        self._volume_anterior = bar.volume
        return acao
