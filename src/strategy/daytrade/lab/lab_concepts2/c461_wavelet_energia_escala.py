"""Item 62 do catalogo: APROXIMACAO de analise wavelet -- nao usa `pywt`
(nao instalado). Proxy: diferencas de medias moveis em escalas diadicas
(MA(2)-MA(4), MA(4)-MA(8), MA(8)-MA(16)) como "energia por escala", medida
pela variancia rolling de cada diferenca.

Opera na direcao do sinal (momentum) da escala cuja energia relativa
domina na janela.
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
class WaveletEnergiaEscala(IntradayStrategy):
    """Proxy de energia wavelet por diferenca de medias moveis diadicas."""

    name: str = "c461_wavelet_energia_escala"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_energia: int = 30
    barras_saida: int = 10
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _closes: deque = field(default_factory=lambda: deque(maxlen=46), init=False, repr=False)
    _d1: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _d2: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _d3: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=16 + self.janela_energia)
        self._d1 = deque(maxlen=self.janela_energia)
        self._d2 = deque(maxlen=self.janela_energia)
        self._d3 = deque(maxlen=self.janela_energia)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if positions:
            pos = positions[0]
            if pos.bars_held >= self.barras_saida:
                return [Exit(reason="horizonte_fixo_atingido")]
            return []

        self._closes.append(bar.close)
        if len(self._closes) < 16:
            return []
        arr = np.asarray(self._closes, dtype=float)
        ma2 = arr[-2:].mean()
        ma4 = arr[-4:].mean()
        ma8 = arr[-8:].mean()
        ma16 = arr[-16:].mean()
        self._d1.append(ma2 - ma4)
        self._d2.append(ma4 - ma8)
        self._d3.append(ma8 - ma16)
        if len(self._d1) < self.janela_energia:
            return []

        energias = {
            1: float(np.var(self._d1)),
            2: float(np.var(self._d2)),
            3: float(np.var(self._d3)),
        }
        escala_dominante = max(energias, key=energias.get)
        valores = {1: self._d1, 2: self._d2, 3: self._d3}
        sinal_escala = valores[escala_dominante][-1]
        if sinal_escala > 0:
            return [self._ordem("long", bar.close, f"wavelet_escala{escala_dominante}_alta")]
        if sinal_escala < 0:
            return [self._ordem("short", bar.close, f"wavelet_escala{escala_dominante}_baixa")]
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
