"""Catálogo catástrofe/criticalidade, item 84: TransicaoDeFaseIsing.

Binariza cada barra como spin +1 (alta) / -1 (baixa); calcula a "energia
de alinhamento" tipo Ising (soma de produtos de spins vizinhos) numa
janela rolante; entra na direção do spin mais recente quando a energia
cruza o limiar associado à transição de fase (fase ordenada/
ferromagnética = tendência forte).
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
class TransicaoDeFaseIsing(IntradayStrategy):
    """`spin = sign(close-open)`; `energia = sum(spin_i * spin_{i+1})` na
    janela; entra na direção do último spin quando a energia (normalizada
    pelo tamanho da janela) cruza o limiar de "fase ordenada"."""

    name: str = "transicao_de_fase_ising"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 15
    limiar_energia_normalizada: float = 0.6
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _spins: deque = field(default_factory=lambda: deque(maxlen=15), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        if self._spins.maxlen != self.janela:
            self._spins = deque(maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        spin = 1 if bar.close >= bar.open else -1
        self._spins.append(spin)

        if not positions and len(self._spins) == self._spins.maxlen:
            spins = list(self._spins)
            energia = sum(a * b for a, b in zip(spins[:-1], spins[1:]))
            energia_normalizada = energia / (len(spins) - 1)

            if energia_normalizada > self.limiar_energia_normalizada:
                side = "long" if spin > 0 else "short"
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
        return acao
