"""Catálogo Gann/Fibonacci, item 42: RetracaoFibonacciNaoObvia.

Razões de Fibonacci pouco usadas (0,236 / 0,786 / 1,272 / 1,414) sobre o
range da SESSÃO atual (não o swing). Entra no pullback em 0,786 do range;
alvo na extensão 1,272 além do extremo oposto (respeitando piso de 4
ticks entre entrada e alvo).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

_RETRACAO = 0.786
_EXTENSAO = 1.272
_RANGE_MINIMO_TICKS = 8


@dataclass
class RetracaoFibonacciNaoObvia(IntradayStrategy):
    """Sobre o range da sessão até agora, entra no pullback em 0,786 (a
    favor da direção do range) com alvo na extensão 1,272 além do extremo
    oposto."""

    name: str = "retracao_fibonacci_nao_obvia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    offset_ticks: int = 1
    stop_ticks: int = 16
    entrada_ttl_bars: int = 40

    _sessao_high: float | None = field(default=None, init=False, repr=False)
    _sessao_low: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._sessao_high = None
        self._sessao_low = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if self._sessao_high is None:
            self._sessao_high = bar.high
            self._sessao_low = bar.low
            return acao

        range_sessao = self._sessao_high - self._sessao_low
        if (not positions and range_sessao >= _RANGE_MINIMO_TICKS * self.tick_size):
            nivel_786_alta = no_tick(self._sessao_high - _RETRACAO * range_sessao, self.tick_size)
            nivel_786_baixa = no_tick(self._sessao_low + _RETRACAO * range_sessao, self.tick_size)

            if abs(bar.close - nivel_786_alta) <= self.offset_ticks * self.tick_size:
                limite = nivel_786_alta
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(self._sessao_low + _EXTENSAO * range_sessao, self.tick_size)
                if alvo - limite >= 4 * self.tick_size:
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
            elif abs(bar.close - nivel_786_baixa) <= self.offset_ticks * self.tick_size:
                limite = nivel_786_baixa
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(self._sessao_high - _EXTENSAO * range_sessao, self.tick_size)
                if limite - alvo >= 4 * self.tick_size:
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._sessao_high = max(self._sessao_high, bar.high)
        self._sessao_low = min(self._sessao_low, bar.low)
        return acao
