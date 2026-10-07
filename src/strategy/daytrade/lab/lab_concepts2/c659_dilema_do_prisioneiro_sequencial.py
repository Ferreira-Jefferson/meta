"""Catálogo autômatos/ML/jogos, item 60: DilemaDoPrisioneiroSequencial.

Cada barra "coopera" (mantém o sinal do retorno anterior) ou "trai"
(inverte); segue a continuação do último retorno, exceto quando duas
traições seguidas ocorrem — aí inverte a decisão.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class DilemaDoPrisioneiroSequencial(IntradayStrategy):
    """Rastreia "cooperação" (retorno mantém o sinal do anterior) vs
    "traição" (inverte); segue a continuação, invertendo quando duas
    traições seguidas ocorrem."""

    name: str = "dilema_do_prisioneiro_sequencial"
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

    _close_anterior: float | None = field(default=None, init=False, repr=False)
    _sinal_ret_anterior: int = field(default=0, init=False, repr=False)
    _streak_traicao: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._close_anterior = None
        self._sinal_ret_anterior = 0
        self._streak_traicao = 0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if self._close_anterior is not None:
            ret = bar.close - self._close_anterior
            sinal_ret = 1 if ret > 0 else (-1 if ret < 0 else 0)

            if sinal_ret != 0 and self._sinal_ret_anterior != 0:
                traiu = sinal_ret != self._sinal_ret_anterior
                self._streak_traicao = self._streak_traicao + 1 if traiu else 0

                if not positions:
                    direcao = sinal_ret if self._streak_traicao < 2 else -sinal_ret
                    side = "long" if direcao > 0 else "short"
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

            if sinal_ret != 0:
                self._sinal_ret_anterior = sinal_ret

        self._close_anterior = bar.close
        return acao
