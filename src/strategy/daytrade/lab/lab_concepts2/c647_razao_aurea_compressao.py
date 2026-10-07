"""Catálogo Gann/geometria sagrada, item 48: RazaoAureaCompressao.

Razão entre o range da barra atual e o range da barra anterior, comparada
a φ (1,618) e 1/φ (0,618). Cruzamento para cima de φ (expansão) dispara
entrada de rompimento no sentido da barra; cruzamento para baixo de 1/φ
(compressão extrema) dispara entrada de fade contra a barra.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

_PHI = 1.618
_INV_PHI = 0.618


@dataclass
class RazaoAureaCompressao(IntradayStrategy):
    """Razão range_atual/range_anterior comparada a φ e 1/φ: cruzar φ para
    cima dispara rompimento a favor da barra; cruzar 1/φ para baixo
    dispara fade contra a barra (compressão extrema)."""

    name: str = "razao_aurea_compressao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _range_anterior: float | None = field(default=None, init=False, repr=False)
    _razao_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._range_anterior = None
        self._razao_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        range_atual = bar.high - bar.low

        if self._range_anterior is not None and self._range_anterior > 0:
            razao = range_atual / self._range_anterior

            if not positions and self._razao_anterior is not None:
                cruzou_phi_cima = self._razao_anterior < _PHI <= razao
                cruzou_invphi_baixo = self._razao_anterior > _INV_PHI >= razao
                if cruzou_phi_cima:
                    lado = "long" if bar.close > bar.open else "short"
                    if lado == "long":
                        limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    else:
                        limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side=lado, limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif cruzou_invphi_baixo:
                    lado_fade = "short" if bar.close > bar.open else "long"
                    if lado_fade == "short":
                        limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    else:
                        limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                        stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                        alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side=lado_fade, limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

            self._razao_anterior = razao

        self._range_anterior = range_atual
        return acao
