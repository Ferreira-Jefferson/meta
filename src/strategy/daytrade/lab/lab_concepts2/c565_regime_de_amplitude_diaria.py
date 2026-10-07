"""Catálogo regime/adaptação, item 66: RegimeDeAmplitudeDiaria.

Compara o range do pregão ATÉ O MOMENTO (máxima − mínima desde a abertura,
acumulado incrementalmente) contra a média histórica do range TOTAL do
mesmo dia da semana (précomputada em `initialize`, só com dias
ESTRITAMENTE anteriores -- sem look-ahead). Dia estreito = fade do
rompimento; dia largo = segue o rompimento (momentum).
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
class RegimeDeAmplitudeDiaria(IntradayStrategy):
    """Rompimento de range de N barras. Range do pregão até o momento vs
    média histórica do mesmo dia da semana: dia LARGO (já acima da média)
    segue o rompimento; dia ESTREITO (abaixo de `fracao_estreito` da
    média) faz FADE do rompimento."""

    name: str = "regime_de_amplitude_diaria"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    fracao_estreito: float = 0.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _media_range_por_dia: dict = field(default_factory=dict, init=False, repr=False)
    _media_range_hoje: "float | None" = field(default=None, init=False, repr=False)
    _alta_dia: "float | None" = field(default=None, init=False, repr=False)
    _baixa_dia: "float | None" = field(default=None, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        diario = bars.groupby(bars.index.date).agg(alta=("high", "max"), baixa=("low", "min"))
        diario = diario.sort_index()
        historico_por_dia_semana: dict[int, list[float]] = {}
        media_por_dia: dict = {}
        for data, row in diario.iterrows():
            dia_semana = pd.Timestamp(data).weekday()
            historico = historico_por_dia_semana.get(dia_semana, [])
            media_por_dia[data] = (sum(historico) / len(historico)) if historico else None
            historico_por_dia_semana.setdefault(dia_semana, []).append(row["alta"] - row["baixa"])
        self._media_range_por_dia = media_por_dia

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._media_range_hoje = self._media_range_por_dia.get(session_date)
        self._alta_dia = None
        self._baixa_dia = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._alta_dia = bar.high if self._alta_dia is None else max(self._alta_dia, bar.high)
        self._baixa_dia = bar.low if self._baixa_dia is None else min(self._baixa_dia, bar.low)
        range_hoje = self._alta_dia - self._baixa_dia

        if (not positions and len(self._highs) == self._highs.maxlen
                and self._media_range_hoje is not None and self._media_range_hoje > 0):
            range_high = max(self._highs)
            range_low = min(self._lows)
            dia_estreito = range_hoje < self.fracao_estreito * self._media_range_hoje
            rompeu_alta = bar.close > range_high
            rompeu_baixa = bar.close < range_low

            if rompeu_alta or rompeu_baixa:
                if dia_estreito:
                    lado = "short" if rompeu_alta else "long"
                    nivel_ancora = bar.close
                else:
                    lado = "long" if rompeu_alta else "short"
                    nivel_ancora = range_high if rompeu_alta else range_low

                if lado == "long":
                    limite = no_tick(nivel_ancora - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                else:
                    limite = no_tick(nivel_ancora + self.offset_ticks * self.tick_size, self.tick_size)
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
