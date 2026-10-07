"""Catálogo regime/adaptação, item 65: CruzamentoDeMediasComRegimeDeConfirmcao.

Cruzamento de MA curta × MA longa só é aceito quando o regime de
tendência (Efficiency Ratio, proxy simples de ADX) já está ativo; em
regime lateral o mesmo cruzamento é ignorado.
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
    """Kaufman Efficiency Ratio simplificado: 1.0 = tendência pura, 0.0 =
    ruído puro. Proxy de regime de tendência sem precisar de ADX completo."""
    if len(closes) < 2:
        return 0.0
    numerador = abs(closes[-1] - closes[0])
    denominador = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    return numerador / denominador if denominador > 0 else 0.0


@dataclass
class CruzamentoDeMediasComRegimeDeConfirmcao(IntradayStrategy):
    """Cruzamento de MA `janela_curta` × MA `janela_longa`, aceito só
    quando o regime de tendência (ER) está ativo -- em lateral, o mesmo
    cruzamento é ignorado."""

    name: str = "cruzamento_de_medias_com_regime_de_confirmcao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_curta: int = 5
    janela_longa: int = 20
    janela_regime: int = 14
    limiar_tendencia: float = 0.3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes_longa: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes_regime: deque = field(default_factory=lambda: deque(maxlen=15), init=False, repr=False)
    _ma_curta_ant: "float | None" = field(default=None, init=False, repr=False)
    _ma_longa_ant: "float | None" = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes_longa = deque(maxlen=self.janela_longa)
        self._closes_regime = deque(maxlen=self.janela_regime + 1)
        self._ma_curta_ant = None
        self._ma_longa_ant = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes_longa.append(bar.close)
        self._closes_regime.append(bar.close)
        regime_tendencia = _efficiency_ratio(list(self._closes_regime)) >= self.limiar_tendencia

        ma_curta = ma_longa = None
        if len(self._closes_longa) == self._closes_longa.maxlen:
            valores = list(self._closes_longa)
            ma_curta = sum(valores[-self.janela_curta:]) / self.janela_curta
            ma_longa = sum(valores) / len(valores)

        if (not positions and regime_tendencia and ma_curta is not None
                and self._ma_curta_ant is not None and self._ma_longa_ant is not None):
            cruzou_cima = self._ma_curta_ant <= self._ma_longa_ant and ma_curta > ma_longa
            cruzou_baixo = self._ma_curta_ant >= self._ma_longa_ant and ma_curta < ma_longa
            if cruzou_cima:
                limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif cruzou_baixo:
                limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        if ma_curta is not None:
            self._ma_curta_ant = ma_curta
            self._ma_longa_ant = ma_longa
        return acao
