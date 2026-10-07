"""Catálogo autômatos/ML/jogos, item 59: TeoriaDosJogosCompradorVendedor.

`p_buy = (close-low)/(high-low)` por barra, proxy de "participação do
agressor" comprador vs vendedor; quando um lado domina repetidamente
numa janela, segue o lado dominante.
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
class TeoriaDosJogosCompradorVendedor(IntradayStrategy):
    """Segue o lado (comprador/vendedor) que domina `p_buy` de forma
    consistente por `janela_dominancia` barras seguidas."""

    name: str = "teoria_dos_jogos_comprador_vendedor"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_dominancia: int = 6
    limiar_dominancia_compra: float = 0.65
    limiar_dominancia_venda: float = 0.35
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _p_buy: deque = field(default_factory=lambda: deque(maxlen=6), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._p_buy = deque(maxlen=self.janela_dominancia)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        rng = bar.high - bar.low
        p_buy = (bar.close - bar.low) / rng if rng > 0 else 0.5

        if not positions and len(self._p_buy) == self._p_buy.maxlen:
            side = None
            if all(p > self.limiar_dominancia_compra for p in self._p_buy):
                side = "long"
            elif all(p < self.limiar_dominancia_venda for p in self._p_buy):
                side = "short"

            if side is not None:
                if side == "long":
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                else:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side=side, limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._p_buy.append(p_buy)
        return acao
