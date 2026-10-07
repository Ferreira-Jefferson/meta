"""Catálogo volume/microestrutura, item 39: QuedaDeVolumePreFechamento.

FILTRO + gatilho próprio (mesmo formato dos itens 22/23/37): gatilho é o
rompimento do range de `janela_range` barras; nos últimos
`janela_pre_fechamento_min` minutos antes de `hora_fechamento:
minuto_fechamento`, se o volume da barra cair abaixo do sazonal daquele
minuto (perfil précomputado em `initialize`), a estratégia ZERA posições
abertas e BLOQUEIA novas entradas pelo resto da sessão.
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


def _volume_normalizado(row) -> float:
    real = float(row.get("real_volume", 0.0) or 0.0)
    if real > 0:
        return real
    return float(row.get("tick_volume", 0.0) or 0.0)


@dataclass
class QuedaDeVolumePreFechamento(IntradayStrategy):
    """Rompimento de range de N barras, com achatamento forçado (zera
    posições e bloqueia novas entradas) quando o volume cai abaixo do
    sazonal nos minutos finais antes do fechamento."""

    name: str = "queda_volume_pre_fechamento"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    hora_fechamento: int = 17
    minuto_fechamento: int = 55
    janela_pre_fechamento_min: int = 20
    fator_volume_baixo: float = 0.7
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _perfil_sazonal: dict = field(default_factory=dict, init=False, repr=False)
    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _bloqueado_hoje: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        if bars.empty:
            self._perfil_sazonal = {}
            return
        volumes = bars.apply(_volume_normalizado, axis=1)
        chave_minuto = pd.Series(
            [(t.hour, t.minute) for t in bars.index], index=bars.index,
        )
        self._perfil_sazonal = volumes.groupby(chave_minuto).mean().to_dict()

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._bloqueado_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        minutos_ate_fechar = (
            (self.hora_fechamento * 60 + self.minuto_fechamento)
            - (ts.hour * 60 + ts.minute)
        )
        media_sazonal = self._perfil_sazonal.get((ts.hour, ts.minute))

        if not self._bloqueado_hoje and 0 <= minutos_ate_fechar <= self.janela_pre_fechamento_min:
            if media_sazonal is not None and media_sazonal > 0 and bar.volume < self.fator_volume_baixo * media_sazonal:
                self._bloqueado_hoje = True
                if positions:
                    return [Exit(reason=self.name)]
                return []

        if self._bloqueado_hoje:
            if positions:
                return [Exit(reason=self.name)]
            return []

        if not positions and len(self._highs) == self._highs.maxlen:
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
