"""TesteNormalidadeJarqueBeraRegime -- score tipo Jarque-Bera contra limiar empirico.

SUBSTITUICAO DECLARADA (catalogo pede para pular o p-valor qui-quadrado
formal): calcula assimetria e curtose (formulas manuais, sem
`scipy.stats`) numa janela movel dos retornos e combina as duas na
propria formula do Jarque-Bera, `JB = n/6*(skew^2 + kurt^2/4)`, mas
compara o resultado a um LIMIAR EMPIRICO -- o percentil 90 da propria
historia rolante do score, nao uma tabela qui-quadrado. Score ALTO
(distribuicao anormalmente longe da normal) liga um modo de REVERSAO
EXTREMA: entra contra a ultima barra. Sai pelo stop/alvo fixos.
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


def _skew_kurt(arr: np.ndarray) -> tuple[float, float] | None:
    n = len(arr)
    std = arr.std(ddof=0)
    if std <= 1e-12:
        return None
    desvio = arr - arr.mean()
    skew = float(np.mean(desvio ** 3) / std ** 3)
    kurt_excesso = float(np.mean(desvio ** 4) / std ** 4 - 3.0)
    return skew, kurt_excesso


@dataclass
class TesteNormalidadeJarqueBeraRegime(IntradayStrategy):
    """Score tipo Jarque-Bera (assimetria+curtose) vs limiar empirico rolante."""

    name: str = "c436_teste_normalidade_jarque_bera_regime"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    janela_historico_score: int = 30
    percentil_gatilho: float = 90.0
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=2), init=False, repr=False)
    _retornos: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _historico_score: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=2)
        self._retornos = deque(maxlen=self.janela)
        self._historico_score = deque(maxlen=self.janela_historico_score)

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
        score = None
        if len(self._closes) == 2:
            r = float(np.log(self._closes[-1] / self._closes[-2]))
            self._retornos.append(r)
            if len(self._retornos) == self.janela:
                sk_kt = _skew_kurt(np.array(self._retornos))
                if sk_kt is not None:
                    skew, kurt = sk_kt
                    n = len(self._retornos)
                    score = (n / 6.0) * (skew ** 2 + (kurt ** 2) / 4.0)
                    self._historico_score.append(score)

        if positions:
            return []

        if score is None or len(self._historico_score) < 10 or not self._retornos:
            return []
        limiar = np.percentile(np.array(self._historico_score), self.percentil_gatilho)
        if score < limiar:
            return []

        ultimo = self._retornos[-1]
        if ultimo == 0:
            return []
        tick = self.tick_size
        if ultimo > 0:
            return self._entrada("short", bar.close + self.offset_ticks * tick,
                                  self.stop_ticks * tick, self.alvo_ticks * tick)
        return self._entrada("long", bar.close - self.offset_ticks * tick,
                              self.stop_ticks * tick, self.alvo_ticks * tick)
