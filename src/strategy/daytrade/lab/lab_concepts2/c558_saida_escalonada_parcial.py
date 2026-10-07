"""Catálogo regime/adaptação, item 59: SaidaEscalonadaParcial.

O motor não permite fechar `Exit` parcial manual -- a saída fatiada NATIVA
(`EnterLimit(quantity=2, exit_split_unit=1)`) já entrega isso: o alvo
fecha em fatias de 1 lote quando o preço toca o nível, mantendo o restante
aberto. Este item adapta o alvo/stop do RESTANTE assim que a primeira
fatia sai (quantidade da posição cai): aproxima o alvo para o piso de 4
ticks (nunca menos) e liga um trailing stop simples para deixar o resto
correr.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    AdjustStop, AdjustTarget, Bar, EnterLimit, IntradayAction,
    IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9
PISO_TICKS_GARANTIDO = 4


@dataclass
class SaidaEscalonadaParcial(IntradayStrategy):
    """Rompimento de range de N barras, `quantity=2` e `exit_split_unit=1`
    (o motor já fatia a saída por alvo em lotes de 1). Assim que a primeira
    fatia sai (quantidade da posição cai), aproxima o alvo do restante ao
    piso de 4 ticks e passa a arrastar o stop pelas últimas
    `janela_trailing` mínimas/máximas."""

    name: str = "saida_escalonada_parcial"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_trailing: int = 10
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _highs_trailing: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)
    _lows_trailing: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)
    _quantidade_inicial: "int | None" = field(default=None, init=False, repr=False)
    _fatia_reduzida: bool = field(default=False, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._highs_trailing = deque(maxlen=self.janela_trailing)
        self._lows_trailing = deque(maxlen=self.janela_trailing)
        self._quantidade_inicial = None
        self._fatia_reduzida = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._highs_trailing.append(bar.high)
        self._lows_trailing.append(bar.low)

        if positions:
            pos = positions[0]
            piso_preco = self.tick_size * PISO_TICKS_GARANTIDO
            if self._quantidade_inicial is None:
                self._quantidade_inicial = pos.quantity
            elif not self._fatia_reduzida and pos.quantity < self._quantidade_inicial:
                self._fatia_reduzida = True
                if pos.side == "long":
                    novo_alvo = no_tick(pos.entry_price + piso_preco, self.tick_size)
                    if pos.current_target is None or novo_alvo < pos.current_target:
                        acao.append(AdjustTarget(new_target=novo_alvo))
                else:
                    novo_alvo = no_tick(pos.entry_price - piso_preco, self.tick_size)
                    if pos.current_target is None or novo_alvo > pos.current_target:
                        acao.append(AdjustTarget(new_target=novo_alvo))

            if self._fatia_reduzida and len(self._lows_trailing) == self._lows_trailing.maxlen:
                if pos.side == "long":
                    candidato = no_tick(min(self._lows_trailing), self.tick_size)
                    if pos.current_stop is None or candidato > pos.current_stop:
                        acao.append(AdjustStop(new_stop=candidato))
                else:
                    candidato = no_tick(max(self._highs_trailing), self.tick_size)
                    if pos.current_stop is None or candidato < pos.current_stop:
                        acao.append(AdjustStop(new_stop=candidato))

            self._highs.append(bar.high)
            self._lows.append(bar.low)
            return acao

        self._quantidade_inicial = None
        self._fatia_reduzida = False
        if len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)
            if bar.close > range_high:
                limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=2, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif bar.close < range_low:
                limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=2, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
