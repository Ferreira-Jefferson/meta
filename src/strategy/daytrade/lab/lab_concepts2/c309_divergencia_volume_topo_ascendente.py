"""Catálogo volume/microestrutura, item 10: DivergenciaDeVolumeEmTopoAscendente.

Detecta pivôs de máxima (janela `janela_pivo`) dentro do lookback; quando
um pivô de máxima é mais ALTO que o pivô de máxima anterior mas seu
volume-no-pivô é MENOR — divergência baixista — entra vendido no
rompimento do fundo entre os dois pivôs (swing low).
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
class DivergenciaDeVolumeEmTopoAscendente(IntradayStrategy):
    """Máxima mais alta com volume-no-pivô menor que o pivô anterior
    (divergência baixista) — entra vendido no rompimento do vale entre os
    dois pivôs."""

    name: str = "divergencia_volume_topo_ascendente"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_pivo: int = 2
    lookback_barras: int = 30
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _janela_high: deque = field(default_factory=lambda: deque(maxlen=5), init=False, repr=False)
    _historico: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _pivos_alta: deque = field(default_factory=lambda: deque(maxlen=4), init=False, repr=False)
    _idx: int = field(default=0, init=False, repr=False)
    _armado: dict | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        janela = 2 * self.janela_pivo + 1
        self._janela_high = deque(maxlen=janela)
        self._historico = deque(maxlen=self.lookback_barras)
        self._pivos_alta = deque(maxlen=4)
        self._idx = 0
        self._armado = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        idx = self._idx
        self._idx += 1
        self._historico.append((idx, bar.high, bar.low, bar.volume))
        self._janela_high.append((bar.high, bar.volume))

        if len(self._janela_high) == self._janela_high.maxlen:
            centro_idx = idx - self.janela_pivo
            centro_high, centro_vol = self._janela_high[self.janela_pivo]
            if centro_high == max(h for h, _ in self._janela_high):
                self._pivos_alta.append((centro_idx, centro_high, centro_vol))

        limite_lookback = idx - self.lookback_barras

        if not positions:
            if self._armado is not None and bar.close < self._armado["nivel"]:
                nivel = self._armado["nivel"]
                limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
                self._armado = None
            else:
                validos = [p for p in self._pivos_alta if p[0] >= limite_lookback]
                if len(validos) >= 2:
                    p1, p2 = validos[-2], validos[-1]
                    if p2[1] > p1[1] and p2[2] < p1[2]:
                        vale = min(
                            (lo for i, _, lo, _ in self._historico if p1[0] < i < p2[0]),
                            default=None,
                        )
                        if vale is not None:
                            self._armado = {"nivel": vale}

        return acao
