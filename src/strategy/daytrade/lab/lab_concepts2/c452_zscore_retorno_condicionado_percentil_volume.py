"""Item 53 do catalogo: z-score do retorno CONDICIONADO ao percentil de
volume da barra -- medias/desvios separados para barras de volume alto vs
baixo (nao a distribuicao incondicional).

Entra em reversao SO' quando o retorno e' extremo E ocorreu em percentil de
volume alto; sai no retorno a' media INCONDICIONAL.
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


@dataclass
class ZScoreRetornoCondicionadoPercentilVolume(IntradayStrategy):
    """Z-score do retorno condicionado ao percentil de volume da barra."""

    name: str = "c452_zscore_retorno_condicionado_percentil_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_volume: int = 60
    janela_condicional: int = 40
    minimo_amostras: int = 20
    z_entrada: float = 2.0
    z_saida_incondicional: float = 0.5
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _volumes: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)
    _retornos_todos: deque = field(default_factory=lambda: deque(maxlen=200), init=False, repr=False)
    _retornos_vol_alto: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._volumes = deque(maxlen=self.janela_volume)
        self._retornos_todos = deque(maxlen=200)
        self._retornos_vol_alto = deque(maxlen=self.janela_condicional)
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        ret = None
        if self._close_anterior is not None and self._close_anterior != 0:
            ret = (bar.close - self._close_anterior) / self._close_anterior
        self._close_anterior = bar.close

        z_incond = self._z_incondicional(ret)

        if positions:
            if z_incond is not None and abs(z_incond) <= self.z_saida_incondicional:
                self._registrar(bar.volume, ret)
                return [Exit(reason="retorno_voltou_a_media_incondicional")]
            self._registrar(bar.volume, ret)
            return []

        z_cond, vol_alto = self._z_condicional(bar.volume, ret)
        self._registrar(bar.volume, ret)

        if z_cond is None or not vol_alto:
            return []
        if z_cond <= -self.z_entrada:
            return [self._ordem("long", bar.close, "retorno_extremo_vol_alto_baixo")]
        if z_cond >= self.z_entrada:
            return [self._ordem("short", bar.close, "retorno_extremo_vol_alto_alto")]
        return []

    def _registrar(self, volume: float, ret: float | None) -> None:
        if ret is None:
            self._volumes.append(volume)
            return
        vol_alto = len(self._volumes) >= 10 and volume > float(np.median(self._volumes))
        self._volumes.append(volume)
        self._retornos_todos.append(ret)
        if vol_alto:
            self._retornos_vol_alto.append(ret)

    def _z_incondicional(self, ret: float | None) -> float | None:
        if ret is None or len(self._retornos_todos) < self.minimo_amostras:
            return None
        arr = np.asarray(self._retornos_todos, dtype=float)
        desvio = float(arr.std())
        if desvio <= 0:
            return None
        return float((ret - arr.mean()) / desvio)

    def _z_condicional(self, volume: float, ret: float | None) -> tuple[float | None, bool]:
        if ret is None or len(self._volumes) < 10:
            return None, False
        vol_alto = volume > float(np.median(self._volumes))
        if not vol_alto or len(self._retornos_vol_alto) < self.minimo_amostras:
            return None, vol_alto
        arr = np.asarray(self._retornos_vol_alto, dtype=float)
        desvio = float(arr.std())
        if desvio <= 0:
            return None, vol_alto
        return float((ret - arr.mean()) / desvio), vol_alto

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
