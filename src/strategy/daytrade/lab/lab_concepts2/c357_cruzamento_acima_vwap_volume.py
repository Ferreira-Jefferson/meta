"""Catálogo volume/microestrutura, item 58: CruzamentoAcimaDoVWAPComVolume.

VWAP de sessão (preço típico `(H+L+C)/3` ponderado por volume, acumulado
desde a abertura, resetado a cada pregão). Fechamento cruza o VWAP de baixo
para cima com volume acima da média -- entrada comprada.
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
class CruzamentoAcimaDoVWAPComVolume(IntradayStrategy):
    """Fechamento cruza o VWAP de sessão de baixo para cima com volume
    acima da média -- entra comprado."""

    name: str = "cruzamento_acima_vwap_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_vol: int = 20
    k_volume: float = 1.2
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
            cruzou_acima = self._close_anterior <= self._vwap_anterior and bar.close > vwap_atual
            if cruzou_acima and bar.volume > self.k_volume * vol_ma:
                acao = self._ordem("long", bar.close)

        self._vwap_anterior = vwap_atual
        self._close_anterior = bar.close
        self._vols.append(bar.volume)
        return acao
