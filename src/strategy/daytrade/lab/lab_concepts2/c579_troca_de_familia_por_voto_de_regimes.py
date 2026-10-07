"""Catálogo regime/adaptação, item 80: TrocaDeFamiliaPorVotoDeRegimes.

Dois detectores independentes rodam em paralelo: um de TENDÊNCIA
(proporção de barras na mesma direção nas últimas N barras) e um de
LATERALIDADE (Efficiency Ratio baixo). Concordância plena em tendência =
`quantity` cheio (teto); concordância plena em lateral = não opera;
qualquer outro caso = `quantity` reduzido pela metade.
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


def _efficiency_ratio(closes: list[float]) -> float:
    if len(closes) < 2:
        return 0.0
    numerador = abs(closes[-1] - closes[0])
    denominador = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    return numerador / denominador if denominador > 0 else 0.0


@dataclass
class TrocaDeFamiliaPorVotoDeRegimes(IntradayStrategy):
    """Rompimento de range de N barras. Detector de TENDÊNCIA (proporção
    de barras na mesma direção, enviesada o bastante) e detector de
    LATERALIDADE (ER baixo) votam juntos: concordância plena em tendência
    = `quantity` cheio (teto); concordância plena em lateral = não opera;
    caso misto = metade."""

    name: str = "troca_de_familia_por_voto_de_regimes"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_direcao: int = 10
    limiar_proporcao_direcao: float = 0.6
    janela_regime: int = 14
    limiar_lateral_er: float = 0.3
    teto_contratos: int = 4
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _direcoes: deque = field(default_factory=lambda: deque(maxlen=10), init=False, repr=False)
    _closes_regime: deque = field(default_factory=lambda: deque(maxlen=15), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._direcoes = deque(maxlen=self.janela_direcao)
        self._closes_regime = deque(maxlen=self.janela_regime + 1)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes_regime.append(bar.close)
        self._direcoes.append(bar.close > bar.open)

        if (not positions and len(self._highs) == self._highs.maxlen
                and len(self._direcoes) == self._direcoes.maxlen):
            range_high = max(self._highs)
            range_low = min(self._lows)
            prop_alta = sum(1 for d in self._direcoes if d) / len(self._direcoes)
            detector_tendencia = (
                prop_alta >= self.limiar_proporcao_direcao
                or prop_alta <= (1.0 - self.limiar_proporcao_direcao)
            )
            er = _efficiency_ratio(list(self._closes_regime))
            detector_lateral = er < self.limiar_lateral_er

            quantidade: "int | None"
            if detector_tendencia and not detector_lateral:
                quantidade = self.teto_contratos
            elif not detector_tendencia and detector_lateral:
                quantidade = None  # os dois indicam lateral -- nao opera
            else:
                quantidade = max(1, self.teto_contratos // 2)

            if quantidade is not None:
                if bar.close > range_high:
                    limite = no_tick(range_high - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=quantidade, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif bar.close < range_low:
                    limite = no_tick(range_low + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=quantidade, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return acao
