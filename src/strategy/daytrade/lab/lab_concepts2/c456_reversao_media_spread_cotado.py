"""Item 57 do catalogo: spread cotado esticado (precomputado em
`initialize`) como sinal de RETOMADA de liquidez esperada -- entra na
direcao do MOMENTUM recente (calibracao simples: sinal do retorno das
ultimas `janela_momentum` barras), apostando que a retomada acompanha a
continuacao do movimento que esticou o spread. Sai quando o spread volta a'
mediana movel.
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
class ReversaoMediaSpreadCotado(IntradayStrategy):
    """Spread esticado + momentum recente -- aposta em retomada de liquidez."""

    name: str = "c456_reversao_media_spread_cotado"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_mediana: int = 60
    janela_momentum: int = 3
    razao_esticado: float = 1.5
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _mediana_spread: pd.Series = field(default_factory=pd.Series, init=False, repr=False)
    _spread_serie: pd.Series = field(default_factory=pd.Series, init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        spread = bars["spread"].astype(float)
        self._spread_serie = spread
        self._mediana_spread = spread.rolling(
            window=self.janela_mediana, min_periods=self.janela_mediana
        ).median()

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela_momentum)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        spread, mediana = self._lookup(ts)
        self._closes.append(bar.close)

        if positions:
            if spread is not None and mediana is not None and mediana > 0 and spread <= mediana * 1.1:
                return [Exit(reason="spread_voltou_a_mediana")]
            return []

        if spread is None or mediana is None or mediana <= 0:
            return []
        esticado = spread >= mediana * self.razao_esticado
        if not esticado or len(self._closes) < self.janela_momentum:
            return []
        momentum = self._closes[-1] - self._closes[0]
        if momentum > 0:
            return [self._ordem("long", bar.close, "spread_esticado_momentum_alta")]
        if momentum < 0:
            return [self._ordem("short", bar.close, "spread_esticado_momentum_baixa")]
        return []

    def _lookup(self, ts: pd.Timestamp) -> tuple[float | None, float | None]:
        if self._spread_serie.empty or ts not in self._spread_serie.index:
            return None, None
        spread = self._spread_serie.loc[ts]
        mediana = self._mediana_spread.loc[ts]
        if pd.isna(spread) or pd.isna(mediana):
            return None, None
        return float(spread), float(mediana)

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
