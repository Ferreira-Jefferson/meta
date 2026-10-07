"""Catálogo regime/adaptação, item 45: TamanhoPorTaxaAcertoMovel.

Rompimento de range de N barras; a cada `recalc_a_cada` trades fechados,
recalcula a taxa de acerto da janela móvel e ajusta `quantity` por uma
fórmula de Kelly fracionário simplificada: f = edge/odds, odds FIXAS.
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
class TamanhoPorTaxaAcertoMovel(IntradayStrategy):
    """Rompimento de range de N barras. `quantity` é recalculada a cada
    `recalc_a_cada` trades fechados: `edge = 2*winrate - 1`,
    `f = edge/odds_fixas`, `quantity = clamp(round(1 + max(f,0)*4), 1, teto)`."""

    name: str = "tamanho_por_taxa_acerto_movel"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_resultados: int = 20
    recalc_a_cada: int = 5
    odds_fixas: float = 1.5
    teto_contratos: int = 5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _resultados: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _tinha_posicao: bool = field(default=False, init=False, repr=False)
    _pnl_abertura: float = field(default=0.0, init=False, repr=False)
    _trades_desde_recalc: int = field(default=0, init=False, repr=False)
    _quantidade_atual: int = field(default=1, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._resultados = deque(maxlen=self.janela_resultados)
        self._tinha_posicao = False
        self._pnl_abertura = 0.0
        self._trades_desde_recalc = 0
        self._quantidade_atual = 1

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
            self._resultados.append(venceu)
            self._trades_desde_recalc += 1
            self._tinha_posicao = False
            if self._trades_desde_recalc >= self.recalc_a_cada and self._resultados:
                winrate = sum(1 for r in self._resultados if r) / len(self._resultados)
                edge = 2.0 * winrate - 1.0
                f = edge / self.odds_fixas if self.odds_fixas > 0 else 0.0
                nova = round(1 + max(f, 0.0) * 4)
                self._quantidade_atual = max(1, min(int(nova), self.teto_contratos))
                self._trades_desde_recalc = 0

        if len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            if bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=self._quantidade_atual,
                    ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif bar.close < range_low:
                limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=self._quantidade_atual,
                    ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
