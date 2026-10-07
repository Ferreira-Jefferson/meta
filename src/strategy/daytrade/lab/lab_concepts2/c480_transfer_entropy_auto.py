"""Item 81 do catalogo: APROXIMACAO de transfer entropy via informacao
mutua DISCRETIZADA (binning em tercis + formula manual de entropia,
numpy puro) entre o VOLUME passado (defasado k barras) e o RETORNO da
barra atual, da propria serie.

Entra na direcao implicita (a combinacao volume-bin -> sinal-de-retorno
mais forte historicamente) quando a informacao mutua supera um limiar
empirico; sai quando a medida cai a quase zero.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


def _informacao_mutua_binaria(x_bins: np.ndarray, y_bins: np.ndarray, n_bins: int) -> float:
    n = len(x_bins)
    if n == 0:
        return 0.0
    mi = 0.0
    for xb in range(n_bins):
        for yb in range(2):
            p_xy = float(np.mean((x_bins == xb) & (y_bins == yb)))
            p_x = float(np.mean(x_bins == xb))
            p_y = float(np.mean(y_bins == yb))
            if p_xy > 0 and p_x > 0 and p_y > 0:
                mi += p_xy * np.log2(p_xy / (p_x * p_y))
    return float(mi)


@dataclass
class TransferEntropyAuto(IntradayStrategy):
    """Informacao mutua discretizada entre volume defasado e retorno futuro."""

    name: str = "c480_transfer_entropy_auto"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    lag: int = 2
    janela: int = 60
    mi_entrada: float = 0.05
    mi_saida: float = 0.01
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _volumes: deque = field(default_factory=lambda: deque(), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._volumes = deque(maxlen=self.janela + self.lag)
        self._retornos = deque(maxlen=self.janela)
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._volumes.append(bar.volume)
        ret = None
        if self._close_anterior is not None and self._close_anterior != 0:
            ret = (bar.close - self._close_anterior) / self._close_anterior
            self._retornos.append(ret)
        self._close_anterior = bar.close

        mi, direcao = self._mi_e_direcao()
        if positions:
            if mi is not None and mi <= self.mi_saida:
                return [Exit(reason="informacao_mutua_dissipou")]
            return []

        if mi is None or mi < self.mi_entrada or direcao == 0:
            return []
        if direcao > 0:
            return [self._ordem("long", bar.close, f"transfer_entropy_mi{mi:.3f}")]
        return [self._ordem("short", bar.close, f"transfer_entropy_mi{mi:.3f}")]

    def _mi_e_direcao(self) -> tuple[float | None, int]:
        if len(self._retornos) < self.janela or len(self._volumes) < self.janela + self.lag:
            return None, 0
        vol = np.asarray(self._volumes, dtype=float)
        ret = np.asarray(self._retornos, dtype=float)
        vol_defasado = vol[-self.janela - self.lag: len(vol) - self.lag]
        if len(vol_defasado) != len(ret):
            return None, 0

        tercis = np.quantile(vol_defasado, [1 / 3, 2 / 3])
        x_bins = np.digitize(vol_defasado, tercis)
        y_bins = (ret > 0).astype(int)
        mi = _informacao_mutua_binaria(x_bins, y_bins, n_bins=3)

        # direcao implicita: o bin de volume ALTO (2) associa mais com
        # retorno positivo ou negativo?
        if not np.any(x_bins == 2):
            return mi, 0
        p_alta_dado_vol_alto = float(np.mean(y_bins[x_bins == 2]))
        direcao = 1 if p_alta_dado_vol_alto > 0.5 else -1
        return mi, direcao

    def _ordem(self, side: str, preco_ref: float, reason: str) -> EnterLimit:
        sinal = 1.0 if side == "long" else -1.0
        limite = no_tick(preco_ref, self.tick_size)
        stop = no_tick(limite - sinal * self.stop_ticks * self.tick_size, self.tick_size)
        alvo = no_tick(limite + sinal * self.alvo_ticks * self.tick_size, self.tick_size)
        return EnterLimit(
            side=side, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars,
            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=reason,
        )
