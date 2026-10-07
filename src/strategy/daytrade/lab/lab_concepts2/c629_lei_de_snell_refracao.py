"""Catálogo física, item 30: LeiDeSnellRefracao.

Analogia com refração (lei de Snell — o feixe se dobra ao mudar de meio):
ao tocar um nível de suporte/resistência (topo/fundo recente), compara o
"ângulo de aproximação" (inclinação do preço nas barras antes do toque, via
regressão linear simples) com o volume ANTES e DEPOIS do toque. Quando os
dois divergem muito (ângulo íngreme mas volume cai depois do toque, ou
vice-versa — o "feixe" não se comporta como o esperado no novo meio), entra
na direção do desvio dominante (o volume pós-toque).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class LeiDeSnellRefracao(IntradayStrategy):
    """Ângulo de aproximação (inclinação pré-toque) vs volume antes/depois
    do toque num nível; entra na direção do volume dominante quando os dois
    divergem além do limiar."""

    name: str = "lei_de_snell_refracao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_nivel: int = 30
    proximidade_ticks: float = 2.0
    janela_angulo: int = 5
    janela_volume_pos: int = 3
    fator_divergencia_volume: float = 1.4
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _closes: deque = field(default_factory=lambda: deque(maxlen=6), init=False, repr=False)
    _vols: deque = field(default_factory=lambda: deque(maxlen=6), init=False, repr=False)
    _tocou_nivel: str | None = field(default=None, init=False, repr=False)
    _barras_desde_toque: int = field(default=0, init=False, repr=False)
    _vol_pre_toque: float = field(default=0.0, init=False, repr=False)
    _angulo_pre_toque: float = field(default=0.0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_nivel)
        self._lows = deque(maxlen=self.janela_nivel)
        self._closes = deque(maxlen=self.janela_angulo + 1)
        self._vols = deque(maxlen=self.janela_angulo + 1)
        self._tocou_nivel = None
        self._barras_desde_toque = 0
        self._vol_pre_toque = 0.0
        self._angulo_pre_toque = 0.0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if self._tocou_nivel is not None and not positions:
            self._barras_desde_toque += 1
            if self._barras_desde_toque <= self.janela_volume_pos:
                pass
            if self._barras_desde_toque == self.janela_volume_pos:
                vol_pos = sum(list(self._vols)[-self.janela_volume_pos:]) / self.janela_volume_pos
                if self._vol_pre_toque > 1e-9:
                    razao_volume = vol_pos / self._vol_pre_toque
                    divergiu = (
                        razao_volume >= self.fator_divergencia_volume
                        or razao_volume <= 1.0 / self.fator_divergencia_volume
                    )
                    if divergiu:
                        volume_dominante_alta = razao_volume >= self.fator_divergencia_volume
                        if self._tocou_nivel == "topo" and volume_dominante_alta:
                            limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                            stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                            alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                            acao = [EnterLimit(
                                side="long", limit_price=limite, initial_stop=stop,
                                initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                                exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                            )]
                        elif self._tocou_nivel == "fundo" and not volume_dominante_alta:
                            limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                            stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                            alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                            acao = [EnterLimit(
                                side="short", limit_price=limite, initial_stop=stop,
                                initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                                exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                            )]
                self._tocou_nivel = None

        if not positions and not acao and len(self._highs) == self._highs.maxlen and len(self._closes) == self._closes.maxlen:
            nivel_topo, nivel_fundo = max(self._highs), min(self._lows)
            proximidade = self.proximidade_ticks * self.tick_size
            precos = np.array(self._closes)
            idx = np.arange(len(precos), dtype=float)
            inclinacao, _ = np.polyfit(idx, precos, 1)
            vol_pre = sum(list(self._vols)[:-1]) / max(len(self._vols) - 1, 1)

            if abs(bar.high - nivel_topo) <= proximidade and self._tocou_nivel is None:
                self._tocou_nivel = "topo"
                self._barras_desde_toque = 0
                self._vol_pre_toque = vol_pre
                self._angulo_pre_toque = inclinacao
            elif abs(bar.low - nivel_fundo) <= proximidade and self._tocou_nivel is None:
                self._tocou_nivel = "fundo"
                self._barras_desde_toque = 0
                self._vol_pre_toque = vol_pre
                self._angulo_pre_toque = inclinacao

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        self._closes.append(bar.close)
        self._vols.append(bar.volume)
        return acao
