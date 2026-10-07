"""Catálogo volume/microestrutura, item 46: CruzamentoDeMediasDeVolume.

Média móvel curta de volume cruza para cima da média móvel longa de volume
enquanto o preço também está em tendência (mesma direção) -- usa o
cruzamento como gatilho de entrada.
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
class CruzamentoDeMediasDeVolume(IntradayStrategy):
    """Cruzamento da média curta de volume acima/abaixo da longa, com
    preço em tendência na mesma direção, dispara a entrada."""

    name: str = "cruzamento_medias_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_curta: int = 5
    janela_longa: int = 20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _curta_acima_longa: bool | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._vols = deque(maxlen=self.janela_longa)
        self._closes = deque(maxlen=self.janela_longa)
        self._curta_acima_longa = None

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
        if len(self._vols) == self._vols.maxlen:
            vols = list(self._vols)
            curta = sum(vols[-self.janela_curta:]) / self.janela_curta
            longa = sum(vols) / len(vols)
            curta_acima = curta > longa
            if not positions and self._curta_acima_longa is not None:
                tendencia_alta = bar.close > self._closes[0]
                tendencia_baixa = bar.close < self._closes[0]
                if curta_acima and not self._curta_acima_longa and tendencia_alta:
                    acao = self._ordem("long", bar.close)
                elif not curta_acima and self._curta_acima_longa and tendencia_baixa:
                    acao = self._ordem("short", bar.close)
            self._curta_acima_longa = curta_acima

        self._vols.append(bar.volume)
        self._closes.append(bar.close)
        return acao
