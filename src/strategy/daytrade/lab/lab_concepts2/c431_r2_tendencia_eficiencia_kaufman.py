"""R2TendenciaEficienciaKaufman -- Efficiency Ratio (Kaufman) como regime de tendencia/reversao.

`ER = deslocamento liquido / soma dos deslocamentos absolutos` numa
janela movel -- mede quanto do caminho percorrido foi "direto" (ER perto
de 1, tendencia) versus "picotado" (ER perto de 0, ruido lateral). ER
ALTO segue a direcao da janela (momentum); ER BAIXO opera reversao
dentro da faixa (contra a ultima barra). Sai quando o ER, recomputado a
cada barra, cai abaixo da metade do valor observado na entrada, ou pelo
stop/alvo.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


def _efficiency_ratio(closes: np.ndarray) -> float | None:
    n = len(closes)
    if n < 3:
        return None
    deslocamento = abs(closes[-1] - closes[0])
    soma_absoluta = np.sum(np.abs(np.diff(closes)))
    if soma_absoluta <= 1e-12:
        return None
    return float(deslocamento / soma_absoluta)


@dataclass
class R2TendenciaEficienciaKaufman(IntradayStrategy):
    """Momentum se ER alto, reversao se ER baixo -- Efficiency Ratio de Kaufman."""

    name: str = "c431_r2_tendencia_eficiencia_kaufman"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    limiar_er_alto: float = 0.5
    limiar_er_baixo: float = 0.2
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _er_entrada: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela)
        self._er_entrada = None

    def _entrada(self, side: str, limite: float, stop_dist: float, alvo_dist: float) -> list[IntradayAction]:
        tick = self.tick_size
        limite = no_tick(limite, tick)
        if side == "long":
            stop = no_tick(limite - stop_dist, tick)
            alvo = no_tick(limite + alvo_dist, tick)
        else:
            stop = no_tick(limite + stop_dist, tick)
            alvo = no_tick(limite - alvo_dist, tick)
        return [EnterLimit(
            side=side, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=1, ttl_bars=self.entrada_ttl_bars, exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
        )]

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        er = None
        if len(self._closes) == self.janela:
            er = _efficiency_ratio(np.array(self._closes))

        if positions:
            if er is not None and self._er_entrada is not None and er < 0.5 * self._er_entrada:
                return [Exit(reason=f"{self.name}_er_perdeu_forca")]
            return []

        if er is None:
            return []
        tick = self.tick_size
        janela_arr = np.array(self._closes)
        direcao = janela_arr[-1] - janela_arr[0]
        ultimo_retorno = janela_arr[-1] - janela_arr[-2]

        if er >= self.limiar_er_alto and direcao != 0:
            self._er_entrada = er
            if direcao > 0:
                return self._entrada("long", bar.close - self.offset_ticks * tick,
                                      self.stop_ticks * tick, self.alvo_ticks * tick)
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        if er <= self.limiar_er_baixo and ultimo_retorno != 0:
            self._er_entrada = er
            if ultimo_retorno > 0:
                return self._entrada("short", bar.close + self.offset_ticks * tick,
                                      self.stop_ticks * tick, self.alvo_ticks * tick)
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return []
