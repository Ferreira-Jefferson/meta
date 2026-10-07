"""Item 48 do catalogo: RSI de Wilder (`core.indicators.ifr`) padronizado
pelo seu PROPRIO z-score movel, em vez de niveis fixos 30/70.

Entra em reversao quando o z do RSI e' extremo; sai quando volta a faixa
central. RSI e z-score sao CAUSAIS (so' usam dados ate' o instante), entao
precomputa-los em `initialize` sobre o historico inteiro nao vaza futuro.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core.indicators import ifr
from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class IfrZScoreWilder(IntradayStrategy):
    """Z-score movel do RSI de Wilder -- reversao em extremos relativos."""

    name: str = "c447_ifr_zscore_wilder"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_rsi: int = 14
    janela_zscore: int = 100
    z_entrada: float = 2.0
    z_saida: float = 0.5
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _z: pd.Series = field(default_factory=pd.Series, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        rsi = ifr(bars["close"], window=self.janela_rsi)
        media = rsi.rolling(window=self.janela_zscore, min_periods=self.janela_zscore).mean()
        desvio = rsi.rolling(window=self.janela_zscore, min_periods=self.janela_zscore).std()
        self._z = (rsi - media) / desvio.replace(0.0, pd.NA)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        z = self._lookup(ts)
        if positions:
            if z is None:
                return []
            pos = positions[0]
            if pos.side == "long" and z >= -self.z_saida:
                return [Exit(reason="rsi_z_normalizou")]
            if pos.side == "short" and z <= self.z_saida:
                return [Exit(reason="rsi_z_normalizou")]
            return []

        if z is None:
            return []
        if z <= -self.z_entrada:
            return [self._ordem("long", bar.close, "rsi_z_extremo_baixo")]
        if z >= self.z_entrada:
            return [self._ordem("short", bar.close, "rsi_z_extremo_alto")]
        return []

    def _lookup(self, ts: pd.Timestamp) -> float | None:
        if self._z.empty or ts not in self._z.index:
            return None
        valor = self._z.loc[ts]
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
