"""Catálogo catástrofe/criticalidade, item 82: RessonanciaEstocasticaSinalFraco.

Um viés periódico fraco (fase lunar, mesma fórmula do item #67) só vira
sinal acionável quando o "ruído" (volatilidade rolante) está numa faixa
ÓTIMA -- nem calma demais (sinal não emerge do ruído) nem violenta
demais (sinal é engolido pelo ruído) -- imitando ressonância estocástica.
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

MES_SINODICO_DIAS = 29.530588
LUA_NOVA_REFERENCIA_ORDINAL = pd.Timestamp("2000-01-06").toordinal()


def _sinal_fraco_lunar(data: pd.Timestamp) -> float:
    dias = data.toordinal() - LUA_NOVA_REFERENCIA_ORDINAL
    fase = (dias % MES_SINODICO_DIAS) / MES_SINODICO_DIAS
    return math.sin(2 * math.pi * fase)


@dataclass
class RessonanciaEstocasticaSinalFraco(IntradayStrategy):
    """`initialize` mede a volatilidade histórica (desvio-padrão de
    retornos) e guarda a mediana como referência; ao vivo, o viés lunar
    fraco só é acionável (combinado a um gatilho de rompimento do range
    de abertura) quando a volatilidade rolante cai na faixa
    `[mediana*fator_min, mediana*fator_max]`."""

    name: str = "ressonancia_estocastica_sinal_fraco"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_volatilidade: int = 20
    fator_min: float = 0.7
    fator_max: float = 1.5
    limiar_sinal_fraco: float = 0.15
    barras_abertura: int = 15
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _vol_mediana_ref: float = field(default=0.0, init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)
    _bias: float = field(default=0.0, init=False, repr=False)
    _range_high: float | None = field(default=None, init=False, repr=False)
    _range_low: float | None = field(default=None, init=False, repr=False)
    _n_barras: int = field(default=0, init=False, repr=False)
    _armado: bool = field(default=True, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        closes = bars["close"].to_numpy(dtype=float)
        if len(closes) < self.janela_volatilidade * 2:
            self._vol_mediana_ref = 0.0
            return
        retornos = pd.Series(closes).pct_change().dropna()
        vol_rolante = retornos.rolling(self.janela_volatilidade).std().dropna()
        self._vol_mediana_ref = float(vol_rolante.median()) if len(vol_rolante) else 0.0

    def on_session_start(self, session_date) -> None:
        self._bias = _sinal_fraco_lunar(pd.Timestamp(session_date))
        if self._retornos.maxlen != self.janela_volatilidade:
            self._retornos = deque(maxlen=self.janela_volatilidade)
        self._close_anterior = None
        self._range_high = None
        self._range_low = None
        self._n_barras = 0
        self._armado = True

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if self._close_anterior is not None:
            self._retornos.append((bar.close - self._close_anterior) / self._close_anterior)
        self._close_anterior = bar.close
        self._n_barras += 1

        if self._n_barras <= self.barras_abertura:
            self._range_high = bar.high if self._range_high is None else max(self._range_high, bar.high)
            self._range_low = bar.low if self._range_low is None else min(self._range_low, bar.low)
            return acao

        if (not positions and self._armado and self._vol_mediana_ref > 0
                and len(self._retornos) == self._retornos.maxlen
                and self._range_high is not None and self._range_low is not None
                and abs(self._bias) > self.limiar_sinal_fraco):
            media = sum(self._retornos) / len(self._retornos)
            vol_atual = (sum((r - media) ** 2 for r in self._retornos) / len(self._retornos)) ** 0.5
            na_faixa_otima = (self.fator_min * self._vol_mediana_ref
                               <= vol_atual <= self.fator_max * self._vol_mediana_ref)
            if na_faixa_otima:
                bias_side = "long" if self._bias > 0 else "short"
                rompeu = ((bias_side == "long" and bar.close > self._range_high)
                          or (bias_side == "short" and bar.close < self._range_low))
                if rompeu:
                    side = bias_side
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
                    self._armado = False
        return acao
