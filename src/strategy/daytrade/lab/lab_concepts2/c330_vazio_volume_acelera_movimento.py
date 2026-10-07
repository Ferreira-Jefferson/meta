"""Catálogo volume/microestrutura, item 31: VazioDeVolumeAceleraMovimento.

Mesmo perfil de volume simplificado (itens 28-30); identifica o bucket
com MENOR volume acumulado na janela (vazio/LVN — Low Volume Node). Se o
preço está entrando nesse bucket vindo de fora, entra na direção de
aproximação com alvo mais LARGO (o vazio tende a ser atravessado rápido,
sem suporte/resistência real).
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


def _lvn(janela: deque, bucket_size: float) -> float | None:
    if not janela or bucket_size <= 0:
        return None
    volumes: dict[int, float] = {}
    for b in janela:
        bucket = round(((b.high + b.low) / 2.0) / bucket_size)
        volumes[bucket] = volumes.get(bucket, 0.0) + b.volume
    if not volumes:
        return None
    pior = min(volumes, key=volumes.get)
    return pior * bucket_size


@dataclass
class VazioDeVolumeAceleraMovimento(IntradayStrategy):
    """Identifica o vazio de volume (LVN) do perfil simplificado; ao
    preço se aproximar dele, entra na direção de aproximação com alvo
    ampliado (o vazio costuma ser atravessado rápido)."""

    name: str = "vazio_volume_acelera_movimento"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_barras: int = 30
    bucket_ticks: int = 4
    proximidade_ticks: int = 4
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 16
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
        proximidade = self.proximidade_ticks * self.tick_size

        if not positions and len(self._janela) == self._janela.maxlen and self._close_anterior is not None:
            lvn = _lvn(self._janela, bucket_size)
            if lvn is not None and abs(bar.close - lvn) <= proximidade:
                aproximando_de_baixo = self._close_anterior < bar.close
                aproximando_de_cima = self._close_anterior > bar.close
                if aproximando_de_baixo:
                    nivel = bar.close
                    limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif aproximando_de_cima:
                    nivel = bar.close
                    limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
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
