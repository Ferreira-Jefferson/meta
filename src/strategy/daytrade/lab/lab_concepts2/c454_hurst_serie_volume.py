"""Item 55 do catalogo: expoente de Hurst (R/S manual, mesma familia do
expoente de Hurst sobre preco) aplicado a' serie de VOLUME.

Volume persistente (H>0,5) segue a ultima direcao de preco; volume
anti-persistente (H<0,5) opera reversao. Sai no cruzamento de 0,5.
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


def hurst_rs(serie: np.ndarray) -> float | None:
    """Expoente de Hurst por R/S manual, sobre `serie` (1D). `None` se a
    serie for curta ou constante demais para o calculo fazer sentido."""
    n = len(serie)
    if n < 20:
        return None
    tamanhos = [s for s in (10, 20, n // 2, n) if 4 <= s <= n]
    tamanhos = sorted(set(tamanhos))
    if len(tamanhos) < 2:
        return None
    log_rs, log_n = [], []
    for tamanho in tamanhos:
        n_blocos = n // tamanho
        if n_blocos < 1:
            continue
        rs_vals = []
        for i in range(n_blocos):
            bloco = serie[i * tamanho:(i + 1) * tamanho]
            media = bloco.mean()
            desviado = np.cumsum(bloco - media)
            amplitude = desviado.max() - desviado.min()
            desvio = bloco.std()
            if desvio > 0:
                rs_vals.append(amplitude / desvio)
        if rs_vals:
            log_rs.append(np.log(np.mean(rs_vals)))
            log_n.append(np.log(tamanho))
    if len(log_n) < 2:
        return None
    inclinacao, _ = np.polyfit(log_n, log_rs, 1)
    return float(inclinacao)


@dataclass
class HurstSerieVolume(IntradayStrategy):
    """Expoente de Hurst da serie de volume -- persistencia vs. reversao."""

    name: str = "c454_hurst_serie_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 60
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _volumes: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)
    _ultima_direcao: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._volumes = deque(maxlen=self.janela)
        self._close_anterior = None
        self._ultima_direcao = 0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._volumes.append(bar.volume)
        if self._close_anterior is not None:
            if bar.close > self._close_anterior:
                self._ultima_direcao = 1
            elif bar.close < self._close_anterior:
                self._ultima_direcao = -1
        self._close_anterior = bar.close

        h = hurst_rs(np.asarray(self._volumes, dtype=float)) if len(self._volumes) >= self.janela else None

        if positions:
            if h is not None:
                pos = positions[0]
                cruzou = (pos.side == "long" and h < 0.5) or (pos.side == "short" and h >= 0.5)
                # a entrada foi decidida com H de um lado de 0,5; sair quando
                # H cruza para o outro lado e' o "cruzamento de 0,5" do item.
                if cruzou:
                    return [Exit(reason="hurst_cruzou_0_5")]
            return []

        if h is None or self._ultima_direcao == 0:
            return []
        if h > 0.5:
            side = "long" if self._ultima_direcao > 0 else "short"
            return [self._ordem(side, bar.close, f"hurst_persistente_{h:.2f}")]
        side = "short" if self._ultima_direcao > 0 else "long"
        return [self._ordem(side, bar.close, f"hurst_antipersistente_{h:.2f}")]

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
