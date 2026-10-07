"""Catálogo regime/adaptação, item 44: AceleracaoAposSequenciaVitorias.

Rompimento de range de N barras; após K vitórias seguidas OCORRIDAS em
regime de tendência (Efficiency Ratio alto, proxy simples de ADX), aumenta
`quantity` além do tamanho normal.
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


def _efficiency_ratio(closes: list[float]) -> float:
    """Kaufman Efficiency Ratio simplificado: 1.0 = tendência pura, 0.0 =
    ruído puro. Proxy de regime de tendência sem precisar de ADX completo."""
    if len(closes) < 2:
        return 0.0
    numerador = abs(closes[-1] - closes[0])
    denominador = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    return numerador / denominador if denominador > 0 else 0.0


@dataclass
class AceleracaoAposSequenciaVitorias(IntradayStrategy):
    """Rompimento de range de N barras. Sizing: após `k_vitorias` vitórias
    seguidas com o regime de tendência (ER) ativo no fechamento do trade,
    soma `extra_contratos` ao tamanho normal (teto `teto_contratos`) —
    permite o que o robô normalmente não faria."""

    name: str = "aceleracao_apos_sequencia_vitorias"
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
    k_vitorias: int = 3
    extra_contratos: int = 2
    teto_contratos: int = 3

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes_regime: deque = field(default_factory=lambda: deque(maxlen=15), init=False, repr=False)
    _tinha_posicao: bool = field(default=False, init=False, repr=False)
    _pnl_abertura: float = field(default=0.0, init=False, repr=False)
    _win_streak: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._closes_regime = deque(maxlen=self.janela_regime + 1)
        self._tinha_posicao = False
        self._pnl_abertura = 0.0
        self._win_streak = 0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes_regime.append(bar.close)
        regime_tendencia = _efficiency_ratio(list(self._closes_regime)) >= self.limiar_tendencia

        if positions:
            if not self._tinha_posicao:
                self._pnl_abertura = session_pnl_brl
                self._tinha_posicao = True
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            return acao

        if self._tinha_posicao:
            venceu = (session_pnl_brl - self._pnl_abertura) > 0.0
            if venceu and regime_tendencia:
                self._win_streak += 1
            elif not venceu:
                self._win_streak = 0
            self._tinha_posicao = False

        if len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            quantidade = 1
            if self._win_streak >= self.k_vitorias and regime_tendencia:
                quantidade = min(1 + self.extra_contratos, self.teto_contratos)
            if bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=quantidade, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif bar.close < range_low:
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
