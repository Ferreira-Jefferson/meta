"""Catálogo regime/adaptação, item 60: SaidaPorRegimeInvertido.

Rompimento de range de N barras, aceito só quando o regime de tendência
(Efficiency Ratio, proxy simples de ADX/ER reimplementado aqui) está ativo
na entrada. Sai (`Exit`) antecipadamente se o regime virar de tendência
para lateral no meio do trade, travando o lucro, desde que já esteja
acima do piso de 4 ticks.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9
PISO_TICKS_GARANTIDO = 4


def _efficiency_ratio(closes: list[float]) -> float:
    """Kaufman Efficiency Ratio simplificado: 1.0 = tendência pura, 0.0 =
    ruído puro. Proxy de regime de tendência sem precisar de ADX completo."""
    if len(closes) < 2:
        return 0.0
    numerador = abs(closes[-1] - closes[0])
    denominador = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    return numerador / denominador if denominador > 0 else 0.0


@dataclass
class SaidaPorRegimeInvertido(IntradayStrategy):
    """Rompimento de range de N barras, só aceito com regime de tendência
    ativo (ER >= `limiar_tendencia`). Sai (`Exit`) antecipadamente se o
    regime virar lateral no meio do trade, desde que o lucro já cubra o
    piso de 4 ticks."""

    name: str = "saida_por_regime_invertido"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_regime: int = 14
    limiar_tendencia: float = 0.3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes_regime: deque = field(default_factory=lambda: deque(maxlen=15), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._closes_regime = deque(maxlen=self.janela_regime + 1)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes_regime.append(bar.close)
        regime_tendencia = _efficiency_ratio(list(self._closes_regime)) >= self.limiar_tendencia

        if positions:
            pos = positions[0]
            piso_preco = self.tick_size * PISO_TICKS_GARANTIDO
            lucro = (bar.close - pos.entry_price) if pos.side == "long" else (pos.entry_price - bar.close)
            if not regime_tendencia and lucro >= piso_preco:
                self._highs.append(bar.high)
                self._lows.append(bar.low)
                return [Exit(reason=self.name)]
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            return acao

        if regime_tendencia and len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            if bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif bar.close < range_low:
                limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
