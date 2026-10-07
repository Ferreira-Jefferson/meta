"""EntropiaAproximada (ApEn) -- Approximate Entropy da serie de retornos.

Implementacao manual classica de Pincus: mede quao previsivel/regular e'
a serie de retornos numa janela curta, comparando a frequencia de
padroes similares de comprimento `m` contra `m+1`. ApEn BAIXO (abaixo da
propria media historica rolante) indica regime mais regular/previsivel
-- entra em REVERSAO contra o retorno da ultima barra. Sai quando o ApEn
sobe de volta acima da media historica, ou pelo stop/alvo.
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


def _apen(serie: np.ndarray, m: int, r: float) -> float | None:
    n = len(serie)
    if n <= m + 1 or r <= 0:
        return None

    def _phi(comprimento: int) -> float:
        vetores = np.array([serie[i:i + comprimento] for i in range(n - comprimento + 1)])
        k = len(vetores)
        soma_log = 0.0
        for i in range(k):
            dist = np.max(np.abs(vetores - vetores[i]), axis=1)
            c_i = np.sum(dist <= r) / k
            soma_log += np.log(c_i) if c_i > 0 else 0.0
        return soma_log / k

    return float(_phi(m) - _phi(m + 1))


@dataclass
class EntropiaAproximadaApEn(IntradayStrategy):
    """Reversao quando a Approximate Entropy dos retornos cai abaixo do normal."""

    name: str = "c411_entropia_aproximada_apen"
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
    janela_historico_apen: int = 30
    limiar_desvios: float = 1.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)
    _historico_apen: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela)
        self._historico_apen = deque(maxlen=self.janela_historico_apen)

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

        apen = None
        if len(self._retornos) == self.janela:
            arr = np.array(self._retornos)
            std = arr.std(ddof=0)
            if std > 1e-12:
                apen = _apen(arr, self.m_padrao, self.r_fracao_std * std)
        if apen is not None:
            self._historico_apen.append(apen)

        media_hist = std_hist = None
        if len(self._historico_apen) >= 10:
            hist = np.array(self._historico_apen)
            media_hist = float(hist.mean())
            std_hist = float(hist.std(ddof=0))

        if positions:
            if apen is not None and media_hist is not None and apen >= media_hist:
                return [Exit(reason=f"{self.name}_apen_normalizou")]
            return []

        if apen is None or media_hist is None or std_hist is None or std_hist <= 1e-9:
            return []
        if apen > media_hist - self.limiar_desvios * std_hist:
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
