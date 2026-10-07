"""Item 52 do catalogo: razao real_volume/tick_volume (tamanho medio do
negocio) precomputada em `initialize`, padronizada por z-score movel contra
o proprio historico.

Entra na direcao do preco CORRENTE quando essa razao esta anomalamente alta
(z extremo) -- negocio medio maior que o normal sugere fluxo informado; sai
no retorno a' faixa normal.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class DivergenciaTickVolumeRealVolume(IntradayStrategy):
    """Z-score do tamanho medio do negocio (real_volume/tick_volume)."""

    name: str = "c451_divergencia_tick_volume_real_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_zscore: int = 100
    z_entrada: float = 2.0
    z_saida: float = 0.5
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _z: pd.Series = field(default_factory=pd.Series, init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        tamanho_medio = bars["real_volume"] / bars["tick_volume"].replace(0.0, pd.NA)
        media = tamanho_medio.rolling(window=self.janela_zscore, min_periods=self.janela_zscore).mean()
        desvio = tamanho_medio.rolling(window=self.janela_zscore, min_periods=self.janela_zscore).std()
        self._z = (tamanho_medio - media) / desvio.replace(0.0, pd.NA)

    def on_session_start(self, session_date) -> None:
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        z = self._lookup(ts)
        direcao_preco = None
        if self._close_anterior is not None:
            if bar.close > self._close_anterior:
                direcao_preco = 1
            elif bar.close < self._close_anterior:
                direcao_preco = -1
        self._close_anterior = bar.close

        if positions:
            if z is None:
                return []
            if abs(z) <= self.z_saida:
                return [Exit(reason="tamanho_negocio_normalizou")]
            return []

        if z is None or direcao_preco is None or z < self.z_entrada:
            return []
        if direcao_preco > 0:
            return [self._ordem("long", bar.close, "negocio_medio_anomalo_alta")]
        return [self._ordem("short", bar.close, "negocio_medio_anomalo_baixa")]

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
