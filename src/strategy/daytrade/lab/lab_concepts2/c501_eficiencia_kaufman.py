"""Efficiency Ratio de Kaufman: |close_N - close_0| / soma(|delta close|) numa
janela N. ER alto (perto de 1, deslocamento limpo) segue a direcao da janela;
ER baixo (perto de 0, so' ruido de ida-e-volta) faz reversao a media.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common import BarBuffer, montar_entrada


@dataclass
class EficienciaKaufman(IntradayStrategy):
    name: str = "c501_eficiencia_kaufman"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    er_alto: float = 0.5
    er_baixo: float = 0.2
    offset_ticks: int = 2
    stop_ticks: int = 20
    alvo_ticks: int = 30
    entrada_ttl_bars: int = 40
    quantity: int = 1

    _buffer: BarBuffer = field(default_factory=lambda: BarBuffer(80), init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)

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
        if len(self._buffer) < self.janela + 1:
            return []

        close = self._buffer.close()
        janela = close.iloc[-self.janela - 1:]
        deslocamento = abs(janela.iloc[-1] - janela.iloc[0])
        caminho = janela.diff().abs().sum()
        if caminho <= 0:
            return []
        er = deslocamento / caminho
        direcao = 1.0 if janela.iloc[-1] > janela.iloc[0] else -1.0
        off = self.offset_ticks * self.tick_size

        if er >= self.er_alto:
            # segue: a janela andou "limpa" nesta direcao
            side = "long" if direcao > 0 else "short"
            limite = bar.close - off if side == "long" else bar.close + off
            self._armou_hoje = True
            return [self._ordem(side, limite, "kaufman_er_alto_segue")]
        if er <= self.er_baixo:
            # reversao: caminho longo, deslocamento curto -- so' ruido,
            # fade contra o ultimo candle
            ultimo_delta = close.iloc[-1] - close.iloc[-2]
            if ultimo_delta == 0:
                return []
            side = "short" if ultimo_delta > 0 else "long"
            limite = bar.close + off if side == "short" else bar.close - off
            self._armou_hoje = True
            return [self._ordem(side, limite, "kaufman_er_baixo_reverte")]
        return []

    def _ordem(self, side: str, limite: float, reason: str) -> EnterLimit:
        return montar_entrada(
            side=side, limit_price=limite, stop_ticks=self.stop_ticks,
            alvo_ticks=self.alvo_ticks, tick_size=self.tick_size,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars, reason=reason,
        )
