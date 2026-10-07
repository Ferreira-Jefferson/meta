"""Catálogo volume/microestrutura, item 36: DoisEmpurroesComVolumeDecrescente.

Detecta pivôs (janela `janela_pivo`) de máxima e de mínima; dois toques
no MESMO nível (±tolerância) separados por pelo menos `n_barras_min`
barras, com o SEGUNDO toque tendo volume menor que o primeiro (empurrão
mais fraco) — entra em fade CONTRA o nível assim que o preço confirma a
reversão (fecha além do pivô intermediário oposto).
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
class DoisEmpurroesComVolumeDecrescente(IntradayStrategy):
    """Dois toques no mesmo nível separados por N barras, segundo toque
    com volume menor — entra fade contra o nível na confirmação da
    reversão."""

    name: str = "dois_empurroes_volume_decrescente"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_pivo: int = 2
    n_barras_min: int = 5
    lookback_barras: int = 40
    tolerancia_ticks: int = 3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _janela_high: deque = field(default_factory=lambda: deque(maxlen=5), init=False, repr=False)
    _janela_low: deque = field(default_factory=lambda: deque(maxlen=5), init=False, repr=False)
    _idx: int = field(default=0, init=False, repr=False)
    _pivos_alta: deque = field(default_factory=lambda: deque(maxlen=4), init=False, repr=False)
    _pivos_baixa: deque = field(default_factory=lambda: deque(maxlen=4), init=False, repr=False)
    _armado: dict | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        janela = 2 * self.janela_pivo + 1
        self._janela_high = deque(maxlen=janela)
        self._janela_low = deque(maxlen=janela)
        self._idx = 0
        self._pivos_alta = deque(maxlen=4)
        self._pivos_baixa = deque(maxlen=4)
        self._armado = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        idx = self._idx
        self._idx += 1
        self._janela_high.append((bar.high, bar.volume))
        self._janela_low.append((bar.low, bar.volume))
        tol = self.tolerancia_ticks * self.tick_size

        if len(self._janela_high) == self._janela_high.maxlen:
            centro_idx = idx - self.janela_pivo
            centro_high, centro_vol_h = self._janela_high[self.janela_pivo]
            centro_low, centro_vol_l = self._janela_low[self.janela_pivo]
            if centro_high == max(h for h, _ in self._janela_high):
                self._pivos_alta.append((centro_idx, centro_high, centro_vol_h))
            if centro_low == min(lo for lo, _ in self._janela_low):
                self._pivos_baixa.append((centro_idx, centro_low, centro_vol_l))

        limite_lookback = idx - self.lookback_barras

        if not positions:
            if self._armado is not None and bar.close is not None:
                nivel = self._armado["nivel"]
                if self._armado["lado"] == "short" and bar.close < self._armado["confirma"]:
                    limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                    self._armado = None
                elif self._armado["lado"] == "long" and bar.close > self._armado["confirma"]:
                    limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                    self._armado = None

            if self._armado is None:
                altas = [p for p in self._pivos_alta if p[0] >= limite_lookback]
                baixas = [p for p in self._pivos_baixa if p[0] >= limite_lookback]
                if len(altas) >= 2:
                    p1, p2 = altas[-2], altas[-1]
                    if (p2[0] - p1[0] >= self.n_barras_min and abs(p1[1] - p2[1]) <= tol
                            and p2[2] < p1[2]):
                        self._armado = {"lado": "short", "nivel": max(p1[1], p2[1]), "confirma": min(p1[1], p2[1]) - tol}
                if self._armado is None and len(baixas) >= 2:
                    p1, p2 = baixas[-2], baixas[-1]
                    if (p2[0] - p1[0] >= self.n_barras_min and abs(p1[1] - p2[1]) <= tol
                            and p2[2] < p1[2]):
                        self._armado = {"lado": "long", "nivel": min(p1[1], p2[1]), "confirma": max(p1[1], p2[1]) + tol}

        return acao
