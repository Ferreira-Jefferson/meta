"""Catálogo regime/adaptação, item 79: TamanhoDePosicaoPorRegimeCombinado.

Rompimento de range de N barras; `quantity` final é o produto de TRÊS
multiplicadores independentes -- regime de tendência (Efficiency Ratio),
regime de volatilidade (razão de range curto/longo) e taxa de acerto
recente -- cada um contribuindo um fator em {0,5x; 1,0x; 1,5x}, nunca uma
decisão binária. Teto `teto_contratos` contratos.
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
class TamanhoDePosicaoPorRegimeCombinado(IntradayStrategy):
    """Rompimento de range de N barras. `quantity` = produto de 3 fatores
    independentes (tendência via ER, volatilidade via razão de range
    curto/longo, taxa de acerto recente), cada um em {0,5; 1,0; 1,5}.
    Teto `teto_contratos` contratos."""

    name: str = "tamanho_de_posicao_por_regime_combinado"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_range: int = 20
    janela_regime: int = 14
    limiar_tendencia: float = 0.3
    janela_vol_curta: int = 5
    janela_vol_longa: int = 20
    janela_resultados: int = 20
    teto_contratos: int = 5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _highs: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _lows: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _closes_regime: deque = field(default_factory=lambda: deque(maxlen=15), init=False, repr=False)
    _ranges_longa: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _resultados: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _tinha_posicao: bool = field(default=False, init=False, repr=False)
    _pnl_abertura: float = field(default=0.0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._highs = deque(maxlen=self.janela_range)
        self._lows = deque(maxlen=self.janela_range)
        self._closes_regime = deque(maxlen=self.janela_regime + 1)
        self._ranges_longa = deque(maxlen=self.janela_vol_longa)
        self._resultados = deque(maxlen=self.janela_resultados)
        self._tinha_posicao = False
        self._pnl_abertura = 0.0

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        self._closes_regime.append(bar.close)
        self._ranges_longa.append(bar.high - bar.low)
        regime_tendencia = _efficiency_ratio(list(self._closes_regime)) >= self.limiar_tendencia

        if positions:
            if not self._tinha_posicao:
                self._pnl_abertura = session_pnl_brl
                self._tinha_posicao = True
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            return acao

        if self._tinha_posicao:
            venceu = (session_pnl_brl - self._pnl_abertura) > 0.0
            self._resultados.append(venceu)
            self._tinha_posicao = False

        if len(self._highs) == self._highs.maxlen:
            range_high = max(self._highs)
            range_low = min(self._lows)

            f_trend = 1.5 if regime_tendencia else 0.5

            f_vol = 1.0
            if len(self._ranges_longa) == self._ranges_longa.maxlen:
                curto = list(self._ranges_longa)[-self.janela_vol_curta:]
                media_curta = sum(curto) / len(curto)
                media_longa = sum(self._ranges_longa) / len(self._ranges_longa)
                if media_longa > 0:
                    razao = media_curta / media_longa
                    f_vol = 1.5 if razao >= 1.2 else (0.5 if razao <= 0.8 else 1.0)

            f_winrate = 1.0
            if self._resultados:
                winrate = sum(1 for r in self._resultados if r) / len(self._resultados)
                f_winrate = 1.5 if winrate >= 0.6 else (0.5 if winrate < 0.4 else 1.0)

            quantidade = max(1, min(self.teto_contratos, round(f_trend * f_vol * f_winrate)))

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
