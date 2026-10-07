"""Catálogo regime/adaptação, item 73: AlvoProporcionalAoRangeDoDia.

O alvo é uma fração do range do pregão acumulado até o momento (piso de
4 ticks garantido); conforme o range do dia se expande, o alvo é
AJUSTADO (`AdjustTarget`) para acompanhar -- sempre alargando, nunca
encolhendo abaixo do piso já garantido.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    AdjustTarget, Bar, EnterLimit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9
PISO_TICKS_GARANTIDO = 4


@dataclass
class AlvoProporcionalAoRangeDoDia(IntradayStrategy):
    """Rompimento de range de N barras. Alvo = `fracao_alvo` × range do
    pregão até o momento (piso de 4 ticks garantido); conforme o range do
    dia cresce, o alvo é alargado via `AdjustTarget` (nunca encolhe)."""

    name: str = "alvo_proporcional_ao_range_do_dia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    fracao_alvo: float = 0.3
    offset_ticks: int = 1
    stop_ticks: int = 16
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _alta_dia: "float | None" = field(default=None, init=False, repr=False)
    _baixa_dia: "float | None" = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._alta_dia = None
        self._baixa_dia = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._alta_dia = bar.high if self._alta_dia is None else max(self._alta_dia, bar.high)
        self._baixa_dia = bar.low if self._baixa_dia is None else min(self._baixa_dia, bar.low)
        range_dia = self._alta_dia - self._baixa_dia
        piso_preco = self.tick_size * PISO_TICKS_GARANTIDO

        if positions:
            pos = positions[0]
            distancia_candidata = max(piso_preco, self.fracao_alvo * range_dia)
            if pos.side == "long":
                novo_alvo = no_tick(pos.entry_price + distancia_candidata, self.tick_size)
                if pos.current_target is None or novo_alvo > pos.current_target:
                    acao.append(AdjustTarget(new_target=novo_alvo))
            else:
                novo_alvo = no_tick(pos.entry_price - distancia_candidata, self.tick_size)
                if pos.current_target is None or novo_alvo < pos.current_target:
                    acao.append(AdjustTarget(new_target=novo_alvo))
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            return acao

        if len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            distancia_inicial = max(piso_preco, self.fracao_alvo * range_dia)
            if bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + distancia_inicial, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif bar.close < range_low:
                limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - distancia_inicial, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
