"""Catálogo volume/microestrutura, item 67: RetesteComVolumeDecrescenteRompeNivel.

Nível de suporte/resistência (extremo de uma janela rolante) retestado 3
vezes sem romper, cada reteste com volume sucessivamente menor -- entra no
rompimento subsequente do nível.
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
class RetesteComVolumeDecrescenteRompeNivel(IntradayStrategy):
    """3 retestes de um nível com volume decrescente -- entra no
    rompimento subsequente do nível (suporte ou resistência)."""

    name: str = "reteste_volume_decrescente_rompe"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_nivel: int = 30
    tolerancia_ticks: int = 3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _toques_res: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _toques_sup: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _pronto_res: bool = field(default=False, init=False, repr=False)
    _pronto_sup: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_nivel)
        self._lows = deque(maxlen=self.janela_nivel)
        self._toques_res = deque(maxlen=3)
        self._toques_sup = deque(maxlen=3)
        self._pronto_res = False
        self._pronto_sup = False

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
        tol = self.tolerancia_ticks * self.tick_size

        if len(self._highs) == self._highs.maxlen:
            nivel_res = max(self._highs)
            nivel_sup = min(self._lows)

            if not positions and self._pronto_res and bar.close > nivel_res:
                acao = self._ordem("long", nivel_res)
                self._toques_res.clear()
                self._pronto_res = False
            elif not positions and self._pronto_sup and bar.close < nivel_sup:
                acao = self._ordem("short", nivel_sup)
                self._toques_sup.clear()
                self._pronto_sup = False
            else:
                if bar.high >= nivel_res - tol and bar.close <= nivel_res + tol:
                    self._toques_res.append(bar.volume)
                    vs = list(self._toques_res)
                    self._pronto_res = len(vs) == 3 and vs[0] > vs[1] > vs[2]
                if bar.low <= nivel_sup + tol and bar.close >= nivel_sup - tol:
                    self._toques_sup.append(bar.volume)
                    vs = list(self._toques_sup)
                    self._pronto_sup = len(vs) == 3 and vs[0] > vs[1] > vs[2]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
