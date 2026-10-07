"""Catálogo regime/adaptação, item 49: RegimeVolumeAltoBaixo.

Rompimento de range de N barras; classifica o volume da barra de ruptura
pelo percentil dele numa janela histórica de `janela_volume` barras.
Percentil ALTO confirma o rompimento (entra); percentil BAIXO é tratado
como armadilha (ignora o sinal).
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


def _percentil(valor: float, historico: list[float]) -> float:
    """Percentil (0..1) de `valor` dentro de `historico` -- fração de
    observações <= valor."""
    if not historico:
        return 0.5
    return sum(1 for v in historico if v <= valor) / len(historico)


@dataclass
class RegimeVolumeAltoBaixo(IntradayStrategy):
    """Rompimento de range de N barras, só aceito quando o volume da barra
    de ruptura está no percentil ALTO (`pct_confirma`) da janela histórica
    de volume; percentil BAIXO (`pct_armadilha`) descarta o sinal."""

    name: str = "regime_volume_alto_baixo"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_volume: int = 100
    pct_confirma: float = 0.7
    pct_armadilha: float = 0.3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _volumes: deque = field(default_factory=lambda: deque(maxlen=100), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._volumes = deque(maxlen=self.janela_volume)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if (not positions and len(self._highs) == self._highs.maxlen
                and len(self._volumes) == self._volumes.maxlen):
            range_high = max(self._highs)
            range_low = min(self._lows)
            pct = _percentil(bar.volume, list(self._volumes))
            rompeu_alta = bar.close > range_high
            rompeu_baixa = bar.close < range_low
            if (rompeu_alta or rompeu_baixa) and pct >= self.pct_confirma:
                if rompeu_alta:
                    limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                else:
                    limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
            # pct entre pct_armadilha e pct_confirma, ou <= pct_armadilha: sinal ignorado.

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        self._volumes.append(bar.volume)
        return acao
