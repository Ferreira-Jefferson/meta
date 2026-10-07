"""Catálogo Gann/geometria sagrada, item 40: LequeDeGann.

APROXIMAÇÃO: projeta linhas de leque de Gann (inclinações 1x1, 2x1, 1x2 em
ticks por barra) a partir do pivô de abertura do pregão, subindo e
descendo. Quando o preço toca uma linha e a barra fecha do lado da
tendência que a linha representa (rejeição), entra a favor dela.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

_INCLINACOES_TICKS_POR_BARRA = [1.0, 2.0, 0.5]


@dataclass
class LequeDeGann(IntradayStrategy):
    """Leque de Gann a partir do pivô de abertura, com linhas 1x1/2x1/1x2
    (em ticks/barra) subindo e descendo; entra na rejeição (toque + fecho a
    favor) de qualquer linha do leque."""

    name: str = "leque_de_gann"
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

    _pivo_preco: float | None = field(default=None, init=False, repr=False)
    _barras_desde_pivo: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._pivo_preco = None
        self._barras_desde_pivo = 0

    def _linhas(self) -> list[float]:
        assert self._pivo_preco is not None
        linhas = []
        for inclinacao in _INCLINACOES_TICKS_POR_BARRA:
            delta = inclinacao * self._barras_desde_pivo * self.tick_size
            linhas.append(self._pivo_preco + delta)
            linhas.append(self._pivo_preco - delta)
        return linhas

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if self._pivo_preco is None:
            self._pivo_preco = bar.open
            self._barras_desde_pivo = 0
            return acao

        if not positions:
            for linha in self._linhas():
                tocou = bar.low <= linha <= bar.high
                if not tocou:
                    continue
                rejeicao_suporte = bar.close > linha and linha >= self._pivo_preco - 1e-9
                rejeicao_resistencia = bar.close < linha and linha <= self._pivo_preco + 1e-9
                if rejeicao_suporte and bar.close > bar.open:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(linha - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                    break
                if rejeicao_resistencia and bar.close < bar.open:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(linha + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                    break

        self._barras_desde_pivo += 1
        return acao
