"""Catálogo volume/microestrutura, item 44: QuebraDeSequenciaDeVolumeAltoNaTendencia.

Sequência de `janela_seq` barras na mesma cor (tendência), todas com volume
acima da média móvel de `janela_vol` barras, arma a entrada a favor da
tendência; uma barra com volume abaixo da média encerra a posição.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class QuebraDeSequenciaDeVolumeAltoNaTendencia(IntradayStrategy):
    """Entra a favor de uma sequência de barras direcionais com volume
    acima da média; sai assim que uma barra vier com volume abaixo dela."""

    name: str = "quebra_sequencia_volume_tendencia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_seq: int = 4
    janela_vol: int = 20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _cores: deque = field(default_factory=lambda: deque(maxlen=4), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._cores = deque(maxlen=self.janela_seq)
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

        if positions:
            if vol_ma is not None and bar.volume < vol_ma:
                acao = [Exit(reason=self.name)]
        elif len(self._cores) == self._cores.maxlen and vol_ma is not None:
            cores = list(self._cores)
            if len(set(cores)) == 1 and cores[0] != 0 and bar.volume > vol_ma:
                acao = self._ordem("long" if cores[0] > 0 else "short", bar.close)

        cor = 1 if bar.close > bar.open else (-1 if bar.close < bar.open else 0)
        self._cores.append(cor)
        self._vols.append(bar.volume)
        return acao
