"""Catálogo volume/microestrutura, item 64: VolumeAcumuladoAbaixoDoRitmoSazonal.

Espelho de `c362_volume_acumulado_acima_ritmo_sazonal.py`: volume acumulado
da sessão, no minuto de checagem, ABAIXO da média histórica -- trata o dia
como provável dia de range e faz fade nos extremos da sessão até agora.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class VolumeAcumuladoAbaixoDoRitmoSazonal(IntradayStrategy):
    """Volume acumulado abaixo da média histórica no minuto de checagem --
    trata como dia de range, fade no extremo mais próximo da sessão."""

    name: str = "volume_acumulado_abaixo_ritmo_sazonal"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    check_idx: int = 30
    fator_abaixo: float = 0.8
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _idx: int = field(default=0, init=False, repr=False)
    _cum_vol: float = field(default=0.0, init=False, repr=False)
    _sessao_high: float | None = field(default=None, init=False, repr=False)
    _sessao_low: float | None = field(default=None, init=False, repr=False)
    _n_dias: int = field(default=0, init=False, repr=False)
    _media_check: float = field(default=0.0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._idx = 0
        self._cum_vol = 0.0
        self._sessao_high = None
        self._sessao_low = None

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
        self._cum_vol += bar.volume
        self._sessao_high = bar.high if self._sessao_high is None else max(self._sessao_high, bar.high)
        self._sessao_low = bar.low if self._sessao_low is None else min(self._sessao_low, bar.low)

        if idx == self.check_idx:
            media_hist = self._media_check if self._n_dias > 0 else None
            if (not positions and media_hist is not None
                    and self._sessao_high is not None and self._sessao_low is not None):
                if self._cum_vol < self.fator_abaixo * media_hist:
                    dist_high = self._sessao_high - bar.close
                    dist_low = bar.close - self._sessao_low
                    if dist_low < dist_high:
                        acao = self._ordem("long", self._sessao_low)
                    else:
                        acao = self._ordem("short", self._sessao_high)
            self._n_dias += 1
            self._media_check += (self._cum_vol - self._media_check) / self._n_dias

        return acao
