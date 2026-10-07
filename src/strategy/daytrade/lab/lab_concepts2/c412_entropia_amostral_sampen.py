"""EntropiaAmostral (SampEn) -- Sample Entropy da serie de retornos.

Variante manual da ApEn que NAO conta auto-casamentos (exclui `i==j` na
contagem de padroes similares) -- estimador menos viesado para series
curtas. Mesmo uso de regime do item anterior: SampEn BAIXO (abaixo da
propria media historica rolante) indica regularidade -- entra em
REVERSAO contra o retorno da ultima barra; sai quando o SampEn volta a
subir acima da media historica, ou pelo stop/alvo.
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


def _sampen(serie: np.ndarray, m: int, r: float) -> float | None:
    n = len(serie)
    if n <= m + 1 or r <= 0:
        return None

    def _contagem(comprimento: int) -> int:
        vetores = np.array([serie[i:i + comprimento] for i in range(n - comprimento + 1)])
        k = len(vetores)
        total = 0
        for i in range(k):
            dist = np.max(np.abs(vetores - vetores[i]), axis=1)
            dist[i] = np.inf
            total += int(np.sum(dist <= r))
        return total

    b = _contagem(m)
    a = _contagem(m + 1)
    if b == 0 or a == 0:
        return None
    return float(-np.log(a / b))


@dataclass
class EntropiaAmostralSampEn(IntradayStrategy):
    """Reversao quando a Sample Entropy dos retornos cai abaixo do normal."""

    name: str = "c412_entropia_amostral_sampen"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 30
    m_padrao: int = 2
    r_fracao_std: float = 0.2
    janela_historico: int = 30
    limiar_desvios: float = 1.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _historico: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela)
        self._historico = deque(maxlen=self.janela_historico)

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
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)

        sampen = None
        if len(self._retornos) == self.janela:
            arr = np.array(self._retornos)
            std = arr.std(ddof=0)
            if std > 1e-12:
                sampen = _sampen(arr, self.m_padrao, self.r_fracao_std * std)
        if sampen is not None:
            self._historico.append(sampen)

        media_hist = std_hist = None
        if len(self._historico) >= 10:
            hist = np.array(self._historico)
            media_hist = float(hist.mean())
            std_hist = float(hist.std(ddof=0))

        if positions:
            if sampen is not None and media_hist is not None and sampen >= media_hist:
                return [Exit(reason=f"{self.name}_sampen_normalizou")]
            return []

        if sampen is None or media_hist is None or std_hist is None or std_hist <= 1e-9:
            return []
        if sampen > media_hist - self.limiar_desvios * std_hist:
            return []
        if not self._retornos:
            return []
        ultimo_retorno = self._retornos[-1]
        tick = self.tick_size
        if ultimo_retorno > 0:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        if ultimo_retorno < 0:
            return self._entrada("long", bar.close - self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return []
