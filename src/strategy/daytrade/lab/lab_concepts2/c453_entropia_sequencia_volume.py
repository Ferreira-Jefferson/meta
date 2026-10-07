"""Item 54 do catalogo: entropia de Shannon (manual) sobre a serie BINARIA
de volume alto/baixo (nao a direcao do preco).

Entropia BAIXA = regime de volume persistente e previsivel; SIMPLIFICACAO
adotada (documentada aqui): opera no sentido do retorno liquido da propria
janela enquanto o regime de volume for persistente. Sai quando a entropia
sobe (regime deixou de ser previsivel).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class EntropiaSequenciaVolume(IntradayStrategy):
    """Entropia de Shannon da sequencia binaria volume alto/baixo."""

    name: str = "c453_entropia_sequencia_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    entropia_baixa: float = 0.5
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _volumes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _bits: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._volumes = deque(maxlen=self.janela)
        self._bits = deque(maxlen=self.janela)
        self._closes = deque(maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if len(self._volumes) >= 5:
            mediana = float(np.median(self._volumes))
            self._bits.append(1 if bar.volume > mediana else 0)
        self._volumes.append(bar.volume)
        self._closes.append(bar.close)

        entropia = self._entropia()
        if positions:
            if entropia is not None and entropia > self.entropia_baixa:
                return [Exit(reason="entropia_subiu")]
            return []

        if entropia is None or entropia > self.entropia_baixa or len(self._closes) < self.janela:
            return []
        retorno_liquido = self._closes[-1] - self._closes[0]
        if retorno_liquido > 0:
            return [self._ordem("long", bar.close, "regime_volume_persistente_alta")]
        if retorno_liquido < 0:
            return [self._ordem("short", bar.close, "regime_volume_persistente_baixa")]
        return []

    def _entropia(self) -> float | None:
        if len(self._bits) < self.janela:
            return None
        p = float(np.mean(self._bits))
        if p <= 0.0 or p >= 1.0:
            return 0.0
        return float(-p * np.log2(p) - (1 - p) * np.log2(1 - p))

    def _ordem(self, side: str, preco_ref: float, reason: str) -> EnterLimit:
        sinal = 1.0 if side == "long" else -1.0
        limite = no_tick(preco_ref, self.tick_size)
        stop = no_tick(limite - sinal * self.stop_ticks * self.tick_size, self.tick_size)
        alvo = no_tick(limite + sinal * self.alvo_ticks * self.tick_size, self.tick_size)
        return EnterLimit(
            side=side, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars,
            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=reason,
        )
