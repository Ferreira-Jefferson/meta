"""Catálogo volume/microestrutura, item 73: ConcentracaoDeVolumeEmPoucasBarras.

Numa janela móvel, se as 2 barras de maior volume concentram uma fração
grande do volume total da janela, os extremos delas viram níveis-chave --
entra no rompimento (retest) desses níveis.
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
class ConcentracaoDeVolumeEmPoucasBarras(IntradayStrategy):
    """Duas barras concentram a maior parte do volume da janela -- seus
    extremos viram níveis-chave; entra no rompimento deles."""

    name: str = "concentracao_volume_poucas_barras"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    fracao_concentracao: float = 0.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _barras: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._barras = deque(maxlen=self.janela)

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
        if not positions and len(self._barras) == self._barras.maxlen:
            janela = list(self._barras)
            total_vol = sum(v for _, _, v in janela)
            top2 = sorted(janela, key=lambda item: item[2], reverse=True)[:2]
            soma_top2 = sum(v for _, _, v in top2)
            if total_vol > 0 and soma_top2 >= self.fracao_concentracao * total_vol:
                nivel_alto = max(h for h, _, _ in top2)
                nivel_baixo = min(l for _, l, _ in top2)
                if bar.close > nivel_alto:
                    acao = self._ordem("long", nivel_alto)
                elif bar.close < nivel_baixo:
                    acao = self._ordem("short", nivel_baixo)

        self._barras.append((bar.high, bar.low, bar.volume))
        return acao
