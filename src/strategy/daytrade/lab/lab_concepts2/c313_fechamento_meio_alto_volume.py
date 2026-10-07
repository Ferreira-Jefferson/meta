"""Catálogo volume/microestrutura, item 14: FechamentoNoMeioAltoVolume.

FILTRO de indecisão + gatilho próprio de rompimento (mesmo formato pedido
para os itens 22/23): gatilho é o rompimento do range de `janela_range`
barras; o filtro BLOQUEIA a entrada quando a própria barra de ruptura tem
volume acima da média mas fecha perto do MEIO do seu range (indecisão
apesar do volume) — mecanismo único: "alto volume sem direção definida não
é ruptura de verdade".
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
class FechamentoNoMeioAltoVolume(IntradayStrategy):
    """Rompimento de range de N barras, BLOQUEADO quando a barra de
    ruptura tem volume alto mas fecha perto do meio do próprio range
    (indecisão)."""

    name: str = "fechamento_meio_alto_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_vol: int = 20
    k_volume_indecisao: float = 1.2
    faixa_meio: float = 0.2
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._vols = deque(maxlen=self.janela_vol)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        rng = bar.high - bar.low

        if (not positions and len(self._highs) == self._highs.maxlen
                and len(self._vols) == self._vols.maxlen):
            range_high = max(self._highs)
            range_low = min(self._lows)
            vol_ma = sum(self._vols) / len(self._vols)

            meio_baixo = bar.low + (0.5 - self.faixa_meio) * rng if rng > 0 else bar.close
            meio_alto = bar.low + (0.5 + self.faixa_meio) * rng if rng > 0 else bar.close
            indecisao = (bar.volume > self.k_volume_indecisao * vol_ma
                         and meio_baixo <= bar.close <= meio_alto)

            if not indecisao:
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
        self._vols.append(bar.volume)
        return acao
