"""Catálogo física, item 21: VelocidadeTerminal.

Analogia com velocidade terminal (aceleração que se anula sob atrito):
entra num rompimento de momentum simples (breakout de N barras) e
acompanha a 2ª derivada do close (diferença de diferenças, "aceleração")
com posição aberta; quando a aceleração rolling achata perto de zero
(abaixo de um limiar relativo à sua própria história recente), sai (Exit) —
o movimento "atingiu velocidade terminal", parou de acelerar.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class VelocidadeTerminal(IntradayStrategy):
    """Entra no rompimento de N barras; sai quando a 2ª derivada do close
    ('aceleração') rolling achata perto de zero — o movimento parou de
    acelerar."""

    name: str = "velocidade_terminal"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_aceleracao: int = 5
    limiar_relativo: float = 0.15
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 20
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=3), init=False, repr=False)
    _aceleracoes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._closes = deque(maxlen=3)
        self._aceleracoes = deque(maxlen=max(self.janela_aceleracao * 4, 20))

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if len(self._closes) == 3:
            aceleracao = (self._closes[-1] - self._closes[-2]) - (self._closes[-2] - self._closes[-3])
            self._aceleracoes.append(aceleracao)

        if positions and len(self._aceleracoes) >= self.janela_aceleracao:
            recentes = list(self._aceleracoes)[-self.janela_aceleracao:]
            media_abs_recente = sum(abs(a) for a in recentes) / len(recentes)
            historico = list(self._aceleracoes)
            media_abs_historico = sum(abs(a) for a in historico) / len(historico)
            if media_abs_historico > 1e-9 and media_abs_recente <= self.limiar_relativo * media_abs_historico:
                acao = [Exit(reason=self.name)]
        elif not positions and len(self._highs) == self._highs.maxlen:
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
        self._closes.append(bar.close)
        return acao
