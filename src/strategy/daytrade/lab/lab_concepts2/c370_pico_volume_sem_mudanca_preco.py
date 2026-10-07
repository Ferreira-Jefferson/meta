"""Catálogo volume/microestrutura, item 71: PicoDeVolumeSemMudancaDePreco.

Volume dispara acima da média mas o close termina praticamente igual ao
fechamento anterior -- arma o range da barra e entra na direção do
rompimento (retest) da barra seguinte que confirmar.
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
class PicoDeVolumeSemMudancaDePreco(IntradayStrategy):
    """Volume dispara sem o preço se mexer -- arma o range da barra do
    pico e entra na direção do rompimento das barras seguintes."""

    name: str = "pico_volume_sem_mudanca_preco"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_vol: int = 20
    k_volume: float = 2.0
    tolerancia_preco_ticks: int = 1
    armado_max_barras: int = 10
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)
    _armado: dict | None = field(default=None, init=False, repr=False)
    _armado_idade: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._vols = deque(maxlen=self.janela_vol)
        self._close_anterior = None
        self._armado = None
        self._armado_idade = 0

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

        if not positions and self._armado is not None:
            self._armado_idade += 1
            if bar.close > self._armado["high"]:
                acao = self._ordem("long", self._armado["high"])
                self._armado = None
            elif bar.close < self._armado["low"]:
                acao = self._ordem("short", self._armado["low"])
                self._armado = None
            elif self._armado_idade > self.armado_max_barras:
                self._armado = None

        if not positions and self._armado is None and len(self._vols) == self._vols.maxlen:
            vol_ma = sum(self._vols) / len(self._vols)
            if (self._close_anterior is not None and bar.volume > self.k_volume * vol_ma
                    and abs(bar.close - self._close_anterior) <= self.tolerancia_preco_ticks * self.tick_size):
                self._armado = {"high": bar.high, "low": bar.low}
                self._armado_idade = 0

        self._vols.append(bar.volume)
        self._close_anterior = bar.close
        return acao
