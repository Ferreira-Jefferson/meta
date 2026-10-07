"""Catálogo regime/adaptação, item 51: VolumeCrescenteConfirmaTendencia.

Rompimento de range de N barras; observa as últimas `janela_confirmacao`
barras ANTES do rompimento: preço e volume ambos crescentes na mesma
direção = tendência saudável (aumenta `quantity`, teto `teto_contratos`);
preço subindo com volume decrescente = sinal de exaustão (não entra).
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


def _crescente(valores: list[float]) -> bool:
    return all(valores[i] < valores[i + 1] for i in range(len(valores) - 1))


def _decrescente(valores: list[float]) -> bool:
    return all(valores[i] > valores[i + 1] for i in range(len(valores) - 1))


@dataclass
class VolumeCrescenteConfirmaTendencia(IntradayStrategy):
    """Rompimento de range de N barras. Preço e volume crescentes juntos nas
    últimas `janela_confirmacao` barras (mesma direção do rompimento) =
    tendência saudável, aumenta `quantity` (teto `teto_contratos`); preço
    subindo com volume decrescente = exaustão, não entra."""

    name: str = "volume_crescente_confirma_tendencia"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_confirmacao: int = 5
    teto_contratos: int = 3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=5), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=5), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._closes = deque(maxlen=self.janela_confirmacao)
        self._vols = deque(maxlen=self.janela_confirmacao)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if (not positions and len(self._highs) == self._highs.maxlen
                and len(self._closes) == self._closes.maxlen):
            range_high = max(self._highs)
            range_low = min(self._lows)
            closes = list(self._closes)
            vols = list(self._vols)
            preco_subindo = _crescente(closes)
            preco_descendo = _decrescente(closes)
            volume_subindo = _crescente(vols)
            volume_descendo = _decrescente(vols)

            if bar.close > range_high:
                exaustao = preco_subindo and volume_descendo
                if not exaustao:
                    quantidade = self.teto_contratos if (preco_subindo and volume_subindo) else 1
                    limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=quantidade, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
            elif bar.close < range_low:
                exaustao = preco_descendo and volume_descendo
                if not exaustao:
                    quantidade = self.teto_contratos if (preco_descendo and volume_subindo) else 1
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
        self._closes.append(bar.close)
        self._vols.append(bar.volume)
        return acao
