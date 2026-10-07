"""Catálogo regime/adaptação, item 47: CooldownPosDerrota.

Rompimento de range de N barras; após um trade fechado com PREJUÍZO (proxy
de "foi parado no stop" — no desenho fechado do projeto o alvo maker só
fecha positivo, então uma perda vem do stop ou de um achatamento adverso),
bloqueia qualquer entrada nova por `cooldown_minutos` minutos, mesmo com
sinal técnico válido.
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
class CooldownPosDerrota(IntradayStrategy):
    """Rompimento de range de N barras. Após um trade fechado com prejuízo,
    nenhuma entrada nova é aceita nos `cooldown_minutos` minutos seguintes."""

    name: str = "cooldown_pos_derrota"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40
    cooldown_minutos: int = 15

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _tinha_posicao: bool = field(default=False, init=False, repr=False)
    _pnl_abertura: float = field(default=0.0, init=False, repr=False)
    _cooldown_ate: "pd.Timestamp | None" = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._tinha_posicao = False
        self._pnl_abertura = 0.0
        self._cooldown_ate = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if positions:
            if not self._tinha_posicao:
                self._pnl_abertura = session_pnl_brl
                self._tinha_posicao = True
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            return acao

        if self._tinha_posicao:
            venceu = (session_pnl_brl - self._pnl_abertura) > 0.0
            if not venceu:
                self._cooldown_ate = ts + pd.Timedelta(minutes=self.cooldown_minutos)
            self._tinha_posicao = False

        em_cooldown = self._cooldown_ate is not None and ts < self._cooldown_ate
        if not em_cooldown and len(self._highs) == self._highs.maxlen:
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
