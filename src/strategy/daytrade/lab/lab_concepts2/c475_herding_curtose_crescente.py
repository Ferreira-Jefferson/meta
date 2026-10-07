"""Item 76 do catalogo: monitora curtose CRESCENTE (manual) dos retornos
junto com volume CRESCENTE -- indice de herding estatistico.

Entra na direcao do movimento QUANDO ambos crescem juntos de forma anormal
(limiar empirico), esperando continuidade curta seguida de exaustao; sai
num horizonte curto fixo.
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


def _curtose(x: np.ndarray) -> float:
    n = len(x)
    if n < 4:
        return 0.0
    media = x.mean()
    desvio = x.std()
    if desvio <= 0:
        return 0.0
    return float(np.mean(((x - media) / desvio) ** 4) - 3.0)


@dataclass
class HerdingCurtoseCrescente(IntradayStrategy):
    """Curtose e volume crescentes juntos -- indice de herding, horizonte curto."""

    name: str = "c475_herding_curtose_crescente"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    crescimento_curtose_minimo: float = 1.0
    crescimento_volume_minimo: float = 0.2
    barras_saida: int = 5
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _retornos: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _volumes: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._retornos = deque(maxlen=2 * self.janela)
        self._volumes = deque(maxlen=2 * self.janela)
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if positions:
            pos = positions[0]
            if pos.bars_held >= self.barras_saida:
                return [Exit(reason="horizonte_curto_atingido")]
            return []

        self._volumes.append(bar.volume)
        if self._close_anterior is not None and self._close_anterior != 0:
            self._retornos.append((bar.close - self._close_anterior) / self._close_anterior)
        self._close_anterior = bar.close

        if len(self._retornos) < 2 * self.janela or len(self._volumes) < 2 * self.janela:
            return []
        ret = np.asarray(self._retornos, dtype=float)
        vol = np.asarray(self._volumes, dtype=float)
        curtose_antiga = _curtose(ret[:self.janela])
        curtose_recente = _curtose(ret[self.janela:])
        vol_antigo = float(vol[:self.janela].mean())
        vol_recente = float(vol[self.janela:].mean())
        if vol_antigo <= 0:
            return []
        crescimento_vol = vol_recente / vol_antigo - 1.0
        crescimento_curtose = curtose_recente - curtose_antiga

        if crescimento_curtose < self.crescimento_curtose_minimo:
            return []
        if crescimento_vol < self.crescimento_volume_minimo:
            return []
        movimento_recente = float(ret[self.janela:].sum())
        if movimento_recente > 0:
            return [self._ordem("long", bar.close, "herding_curtose_volume_crescentes_alta")]
        if movimento_recente < 0:
            return [self._ordem("short", bar.close, "herding_curtose_volume_crescentes_baixa")]
        return []

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
