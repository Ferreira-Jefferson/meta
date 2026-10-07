"""Catalogo calendario/sazonalidade, item 1: AlmocoFadeContracao.

Conceito de CALENDARIO (janela de horario), nao de preco: 12:00-13:30 e' a
janela de almoco (baixa liquidez na B3), fixa no catalogo -- nao e' um
achado, e' o horario declarado. Fade de qualquer desvio > N ticks do
preco-referencia das 12:00 de volta a media movel da manha (media dos
closes de abertura ate meio-dia); saida por tempo as 13:30 (`Exit`
incondicional se ainda aberta).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
)
from strategy.daytrade.lab.lab_concepts2._common_calendario import (
    FIM_ALMOCO, INICIO_ALMOCO, montar_entrada,
)


@dataclass
class AlmocoFadeContracao(IntradayStrategy):
    name: str = "almoco_fade_contracao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    limiar_ticks: float = 6.0
    stop_ticks: int = 16
    entrada_ttl_bars: int = 30

    _manha_soma: float = field(default=0.0, init=False, repr=False)
    _manha_n: int = field(default=0, init=False, repr=False)
    _preco_ref: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._manha_soma = 0.0
        self._manha_n = 0
        self._preco_ref = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if ts.time() < INICIO_ALMOCO:
            self._manha_soma += bar.close
            self._manha_n += 1
            return []

        if ts.time() >= FIM_ALMOCO:
            if positions:
                return [Exit(reason=f"{self.name}_flatten_1330")]
            return []

        # dentro da janela 12:00-13:30
        if self._preco_ref is None:
            self._preco_ref = bar.close

        acao: list[IntradayAction] = []
        if not positions:
            desvio_ticks = (bar.close - self._preco_ref) / self.tick_size
            if abs(desvio_ticks) >= self.limiar_ticks:
                manha_ma = (self._manha_soma / self._manha_n) if self._manha_n else bar.close
                alvo_ticks = abs(bar.close - manha_ma) / self.tick_size
                side = "short" if desvio_ticks > 0 else "long"
                acao = [montar_entrada(
                    side=side, limit_price=bar.close, stop_ticks=self.stop_ticks,
                    alvo_ticks=alvo_ticks, tick_size=self.tick_size, quantity=1,
                    ttl_bars=self.entrada_ttl_bars, reason=self.name,
                )]
        return acao
