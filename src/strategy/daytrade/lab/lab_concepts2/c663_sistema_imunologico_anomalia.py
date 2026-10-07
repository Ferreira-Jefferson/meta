"""Catálogo autômatos/ML/jogos, item 64: SistemaImunologicoAnomalia.

Mantém um perfil "normal" rolling do formato da vela (razão corpo/pavio);
uma vela cuja razão se distancia demais desse perfil (z-score simples) é
tratada como "antígeno" -- entra em fade da direção dela.
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
class SistemaImunologicoAnomalia(IntradayStrategy):
    """Perfil rolling de `corpo/(alta-baixa)`; vela com z-score da razão
    acima do limiar é "antígeno" -- entra em fade (contra) a direção
    dela."""

    name: str = "sistema_imunologico_anomalia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_perfil: int = 30
    limiar_z: float = 2.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _razoes: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        if self._razoes.maxlen != self.janela_perfil:
            self._razoes = deque(self._razoes, maxlen=self.janela_perfil)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        rng = bar.high - bar.low
        razao = abs(bar.close - bar.open) / rng if rng > 0 else 0.0

        if not positions and len(self._razoes) == self._razoes.maxlen:
            perfil = list(self._razoes)
            media = sum(perfil) / len(perfil)
            dp = (sum((p - media) ** 2 for p in perfil) / len(perfil)) ** 0.5
            z = (razao - media) / dp if dp > 0 else 0.0

            if z > self.limiar_z:
                # antigeno detectado -- fade da direcao da propria vela
                side = "short" if bar.close > bar.open else "long"
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

        self._razoes.append(razao)
        return acao
