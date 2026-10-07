"""Catálogo volume/microestrutura, item 13: FechamentoNoFundoComVolume.

Espelho do item 12: close no decil INFERIOR do range da própria barra e
volume acima da média — entra vendido no reteste do fechamento
(continuação).
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
class FechamentoNoFundoComVolume(IntradayStrategy):
    """Close no decil inferior do range da barra, volume acima da média —
    entra vendido na continuação."""

    name: str = "fechamento_fundo_com_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_vol: int = 20
    k_volume: float = 1.2
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._vols = deque(maxlen=self.janela_vol)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        rng = bar.high - bar.low

        if not positions and rng > 0 and len(self._vols) == self._vols.maxlen:
            vol_ma = sum(self._vols) / len(self._vols)
            decil_inf = bar.high - 0.9 * rng
            if bar.close <= decil_inf and bar.volume > self.k_volume * vol_ma:
                nivel = bar.close
                limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._vols.append(bar.volume)
        return acao
