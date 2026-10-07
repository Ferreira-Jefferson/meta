"""Catálogo regime/adaptação, item 68: DesvioVWAPBandas.

Bandas de desvio-padrão (janela móvel de `close - VWAP`) em torno do VWAP
da sessão. Em regime LATERAL (Efficiency Ratio baixo), toque na banda =
fade de volta ao VWAP; em regime de TENDÊNCIA, rompimento da banda =
segue (continuação).
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
PISO_TICKS_GARANTIDO = 4


def _efficiency_ratio(closes: list[float]) -> float:
    if len(closes) < 2:
        return 0.0
    numerador = abs(closes[-1] - closes[0])
    denominador = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    return numerador / denominador if denominador > 0 else 0.0


@dataclass
class DesvioVWAPBandas(IntradayStrategy):
    """VWAP incremental da sessão + bandas de `k_desvio` desvios-padrão
    (janela móvel de `close - VWAP`). Regime lateral (ER baixo): toque na
    banda faz FADE de volta ao VWAP (alvo nunca a menos do piso de 4
    ticks do nível de entrada). Regime de tendência (ER alto): rompimento
    da banda SEGUE (continuação)."""

    name: str = "desvio_vwap_bandas"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_bandas: int = 20
    janela_regime: int = 14
    limiar_tendencia: float = 0.3
    k_desvio: float = 2.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _soma_pv: float = field(default=0.0, init=False, repr=False)
    _soma_v: float = field(default=0.0, init=False, repr=False)
    _desvios: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes_regime: deque = field(default_factory=lambda: deque(maxlen=15), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._soma_pv = 0.0
        self._soma_v = 0.0
        self._desvios = deque(maxlen=self.janela_bandas)
        self._closes_regime = deque(maxlen=self.janela_regime + 1)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes_regime.append(bar.close)
        regime_tendencia = _efficiency_ratio(list(self._closes_regime)) >= self.limiar_tendencia
        piso_preco = self.tick_size * PISO_TICKS_GARANTIDO

        if not positions and self._soma_v > 0 and len(self._desvios) == self._desvios.maxlen:
            vwap = self._soma_pv / self._soma_v
            media_desvio = sum(self._desvios) / len(self._desvios)
            variancia = sum((d - media_desvio) ** 2 for d in self._desvios) / len(self._desvios)
            desvio_padrao = variancia ** 0.5
            banda_superior = vwap + self.k_desvio * desvio_padrao
            banda_inferior = vwap - self.k_desvio * desvio_padrao

            if regime_tendencia and bar.close > banda_superior:
                limite = no_tick(banda_superior + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif regime_tendencia and bar.close < banda_inferior:
                limite = no_tick(banda_inferior - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif not regime_tendencia and bar.high >= banda_superior:
                limite = no_tick(banda_superior - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(min(vwap, limite - piso_preco), self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif not regime_tendencia and bar.low <= banda_inferior:
                limite = no_tick(banda_inferior + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(max(vwap, limite + piso_preco), self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        vwap_atual = (self._soma_pv / self._soma_v) if self._soma_v > 0 else bar.close
        self._desvios.append(bar.close - vwap_atual)
        self._soma_pv += bar.close * bar.volume
        self._soma_v += bar.volume
        return acao
