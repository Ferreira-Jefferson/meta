"""Precomputa em `initialize` o PERFIL medio historico de volume por
minuto-do-dia (media de todas as sessoes do historico carregado, por
HH:MM). Minuto muito abaixo do esperado para aquele horario = liquidez
baixa, desliga a entrada; minuto normal ou acima libera o rompimento de
range simples.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class RegimeVolumeIntradiario(IntradayStrategy):
    name: str = "c524_regime_volume_intradiario"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    fracao_minima_do_esperado: float = 0.4
    janela_range: int = 20
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(60), init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)
    _perfil_volume_minuto: dict = field(default_factory=dict, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        if bars.empty:
            self._perfil_volume_minuto = {}
            return
        if "real_volume" in bars.columns and "tick_volume" in bars.columns:
            volume = bars["real_volume"].where(bars["real_volume"] > 0, bars["tick_volume"])
        elif "real_volume" in bars.columns:
            volume = bars["real_volume"]
        else:
            volume = bars.get("tick_volume", pd.Series(0.0, index=bars.index))
        minuto_do_dia = bars.index.strftime("%H:%M")
        self._perfil_volume_minuto = (
            volume.groupby(minuto_do_dia).mean().to_dict()
        )

    def on_session_start(self, session_date) -> None:
        self._armou_hoje = False

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._buffer.push(bar)
        if positions or self._armou_hoje:
            return []
        if len(self._buffer) < self.janela_range + 1:
            return []

        esperado = self._perfil_volume_minuto.get(ts.strftime("%H:%M"))
        if esperado is not None and esperado > 0:
            if bar.volume < self.fracao_minima_do_esperado * esperado:
                return []  # liquidez abaixo do esperado para este minuto

        high, low = self._buffer.high(), self._buffer.low()
        faixa_hi = high.iloc[-self.janela_range - 1:-1].max()
        faixa_lo = low.iloc[-self.janela_range - 1:-1].min()
        off = self.offset_ticks * self.tick_size

        if bar.close > faixa_hi:
            self._armou_hoje = True
            return [self._ordem("long", bar.close - off, "volume_normal_rompe_cima")]
        if bar.close < faixa_lo:
            self._armou_hoje = True
            return [self._ordem("short", bar.close + off, "volume_normal_rompe_baixo")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
