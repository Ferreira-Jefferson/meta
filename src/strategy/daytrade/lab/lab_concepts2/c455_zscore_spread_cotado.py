"""Item 56 do catalogo: z-score movel do spread cotado, precomputado em
`initialize`.

Spread anormalmente alargado DESLIGA entradas novas (filtro), independente
da direcao. O gatilho proprio e' rompimento de N barras (maxima/minima
recente) -- so' dispara quando o filtro de spread permite.
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
class ZScoreSpreadCotado(IntradayStrategy):
    """Filtro de spread alargado (z-score) + rompimento de N barras."""

    name: str = "c455_zscore_spread_cotado"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_zscore: int = 100
    janela_rompimento: int = 20
    z_filtro: float = 2.0
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _z_spread: pd.Series = field(default_factory=pd.Series, init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        spread = bars["spread"].astype(float)
        media = spread.rolling(window=self.janela_zscore, min_periods=self.janela_zscore).mean()
        desvio = spread.rolling(window=self.janela_zscore, min_periods=self.janela_zscore).std()
        self._z_spread = (spread - media) / desvio.replace(0.0, pd.NA)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela_rompimento)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        z = self._lookup(ts)
        spread_largo = z is not None and z >= self.z_filtro

        if positions:
            self._closes.append(bar.close)
            if spread_largo:
                return [Exit(reason="spread_alargou_protecao")]
            return []

        janela_cheia = len(self._closes) >= self.janela_rompimento
        topo = float(max(self._closes)) if janela_cheia else None
        fundo = float(min(self._closes)) if janela_cheia else None
        self._closes.append(bar.close)

        if spread_largo or not janela_cheia:
            return []
        if bar.close > topo:
            return [self._ordem("long", bar.close, "rompimento_spread_normal")]
        if bar.close < fundo:
            return [self._ordem("short", bar.close, "rompimento_spread_normal")]
        return []

    def _lookup(self, ts: pd.Timestamp) -> float | None:
        if self._z_spread.empty or ts not in self._z_spread.index:
            return None
        valor = self._z_spread.loc[ts]
        if pd.isna(valor):
            return None
        return float(valor)

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
