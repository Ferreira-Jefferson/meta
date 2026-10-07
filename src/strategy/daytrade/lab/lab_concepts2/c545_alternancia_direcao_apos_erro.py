"""Catálogo regime/adaptação, item 46: AlternanciaDirecaoAposErro.

Rompimento de range de N barras; após uma derrota num lado, só aceita o
PRÓXIMO sinal se for do lado OPOSTO — mesmo que o rompimento aponte de
novo para o mesmo lado que acabou de perder.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    Side, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class AlternanciaDirecaoAposErro(IntradayStrategy):
    """Rompimento de range de N barras. Após uma derrota no lado X, bloqueia
    o PRÓXIMO sinal nesse mesmo lado (só aceita o oposto) — o bloqueio é
    consumido pela entrada seguinte aceita, seja qual for o resultado dela."""

    name: str = "alternancia_direcao_apos_erro"
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

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _tinha_posicao: bool = field(default=False, init=False, repr=False)
    _pnl_abertura: float = field(default=0.0, init=False, repr=False)
    _lado_ultimo: "Side | None" = field(default=None, init=False, repr=False)
    _lado_bloqueado: "Side | None" = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._tinha_posicao = False
        self._pnl_abertura = 0.0
        self._lado_ultimo = None
        self._lado_bloqueado = None

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
                self._lado_bloqueado = self._lado_ultimo
            self._tinha_posicao = False

        if len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            sinal_lado: "Side | None" = None
            if bar.close > range_high:
                sinal_lado = "long"
            elif bar.close < range_low:
                sinal_lado = "short"

            if sinal_lado is not None and sinal_lado != self._lado_bloqueado:
                self._lado_bloqueado = None
                self._lado_ultimo = sinal_lado
                if sinal_lado == "long":
                    limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                else:
                    limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side=sinal_lado, limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
