"""Catálogo regime/adaptação, item 72: RegimeDeExaustaoPorNumeroDeBarras.

Conta há quantas barras a tendência (MA curta acima/abaixo da MA longa)
está ativa desde o último cruzamento; acima de `limite_barras`, reduz
`quantity` pela metade sem inverter o lado (tendência "exausta" pelo
tempo, não pelo preço).
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
class RegimeDeExaustaoPorNumeroDeBarras(IntradayStrategy):
    """Rompimento de range de N barras, filtrado pelo lado da MA curta vs
    MA longa. Conta barras desde o último cruzamento; acima de
    `limite_barras`, reduz `quantity` pela metade (nunca abaixo de 1) sem
    inverter o lado."""

    name: str = "regime_de_exaustao_por_numero_de_barras"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_curta: int = 5
    janela_longa: int = 20
    limite_barras: int = 60
    quantidade_base: int = 2
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes_longa: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lado_ma: "str | None" = field(default=None, init=False, repr=False)
    _barras_no_lado: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._closes_longa = deque(maxlen=self.janela_longa)
        self._lado_ma = None
        self._barras_no_lado = 0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes_longa.append(bar.close)

        if len(self._closes_longa) == self._closes_longa.maxlen:
            valores = list(self._closes_longa)
            ma_curta = sum(valores[-self.janela_curta:]) / self.janela_curta
            ma_longa = sum(valores) / len(valores)
            novo_lado = "alta" if ma_curta > ma_longa else "baixa"
            if novo_lado != self._lado_ma:
                self._lado_ma = novo_lado
                self._barras_no_lado = 0
            else:
                self._barras_no_lado += 1

        if (not positions and self._lado_ma is not None
                and len(self._highs) == self._highs.maxlen):
            range_high = max(self._highs)
            range_low = min(self._lows)
            quantidade = (
                self.quantidade_base if self._barras_no_lado <= self.limite_barras
                else max(1, self.quantidade_base // 2)
            )
            if self._lado_ma == "alta" and bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=quantidade, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif self._lado_ma == "baixa" and bar.close < range_low:
                limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=quantidade, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
