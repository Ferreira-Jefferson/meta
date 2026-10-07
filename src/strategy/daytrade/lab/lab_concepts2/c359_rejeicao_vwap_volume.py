"""Catálogo volume/microestrutura, item 60: RejeicaoNoVWAPComVolume.

Preço se aproxima do VWAP de sessão (dentro de `tolerancia_ticks`), e a
barra seguinte, com volume alto, fecha se AFASTANDO dele (sem cruzar) --
entra na direção do afastamento.
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
class RejeicaoNoVWAPComVolume(IntradayStrategy):
    """Preço perto do VWAP de sessão, barra de volume alto fecha se
    afastando sem cruzar -- entra na direção do afastamento."""

    name: str = "rejeicao_vwap_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_vol: int = 20
    k_volume: float = 1.5
    tolerancia_ticks: int = 4
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _vwap_num: float = field(default=0.0, init=False, repr=False)
    _vwap_den: float = field(default=0.0, init=False, repr=False)
    _vwap_anterior: float | None = field(default=None, init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._vwap_num = 0.0
        self._vwap_den = 0.0
        self._vwap_anterior = None
        self._close_anterior = None
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
        tipico = (bar.high + bar.low + bar.close) / 3.0
        self._vwap_num += tipico * bar.volume
        self._vwap_den += bar.volume
        vwap_atual = self._vwap_num / self._vwap_den if self._vwap_den > 0 else None

        vol_ma = sum(self._vols) / len(self._vols) if self._vols else None
        if (not positions and vwap_atual is not None and self._vwap_anterior is not None
                and self._close_anterior is not None and vol_ma):
            perto_antes = abs(self._close_anterior - self._vwap_anterior) <= (
                self.tolerancia_ticks * self.tick_size
            )
            volume_alto = bar.volume > self.k_volume * vol_ma
            if perto_antes and volume_alto:
                sem_cruzar_acima = (
                    self._close_anterior >= self._vwap_anterior
                    and bar.close > self._close_anterior and bar.close > vwap_atual
                )
                sem_cruzar_abaixo = (
                    self._close_anterior <= self._vwap_anterior
                    and bar.close < self._close_anterior and bar.close < vwap_atual
                )
                if sem_cruzar_acima:
                    acao = self._ordem("long", bar.close)
                elif sem_cruzar_abaixo:
                    acao = self._ordem("short", bar.close)

        self._vwap_anterior = vwap_atual
        self._close_anterior = bar.close
        self._vols.append(bar.volume)
        return acao
