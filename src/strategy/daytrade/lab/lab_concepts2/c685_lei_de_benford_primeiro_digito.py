"""Catálogo catástrofe/criticalidade, item 86: LeiDeBenfordPrimeiroDigito.

Verifica a distribuição do primeiro dígito significativo do volume numa
janela rolante contra a Lei de Benford (`log10(1+1/d)`); um desvio
significativo (soma de `|obs-esperado|`) é tratado como sinal de fluxo
anômalo (impressão artificial de volume), disparando fade.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

_BENFORD_ESPERADO = {d: math.log10(1 + 1 / d) for d in range(1, 10)}


def primeiro_digito(valor: float) -> int | None:
    """Primeiro dígito significativo de `valor` (>0), ou `None` se
    `valor<=0`."""
    if valor <= 0:
        return None
    while valor < 1:
        valor *= 10
    while valor >= 10:
        valor /= 10
    return int(valor)


@dataclass
class LeiDeBenfordPrimeiroDigito(IntradayStrategy):
    """Distribuição do primeiro dígito do volume numa janela rolante
    contra a Lei de Benford; desvio (`sum(|obs-esperado|)`) acima do
    limiar é tratado como fluxo anômalo -- entra em fade da direção da
    própria barra."""

    name: str = "lei_de_benford_primeiro_digito"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 60
    limiar_desvio: float = 0.35
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _digitos: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        if self._digitos.maxlen != self.janela:
            self._digitos = deque(self._digitos, maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        digito = primeiro_digito(bar.volume)

        if not positions and digito is not None and len(self._digitos) == self._digitos.maxlen:
            n = len(self._digitos)
            contagem = {d: 0 for d in range(1, 10)}
            for dg in self._digitos:
                contagem[dg] += 1
            desvio = sum(abs(contagem[d] / n - _BENFORD_ESPERADO[d]) for d in range(1, 10))

            if desvio > self.limiar_desvio:
                side = "short" if bar.close > bar.open else "long"
                if side == "long":
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                else:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side=side, limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        if digito is not None:
            self._digitos.append(digito)
        return acao
