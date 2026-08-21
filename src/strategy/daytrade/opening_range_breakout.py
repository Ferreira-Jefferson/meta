"""Opening Range Breakout (ORB) — hipotese CLASSICA de day trade: o
intervalo de preco dos primeiros `range_minutes` da sessao define um
"range de abertura"; romper para cima entra comprado, romper para baixo
entra vendido. Stop no lado OPOSTO do range (a invalidacao natural do
rompimento); alvo como multiplo do tamanho do range
(`target_r_multiple`). Uma entrada por sessao — convencao usual do ORB,
nao regra do motor.

Generica de proposito: nao tenta imitar o robo comercial (T2G) que
descreve "contexto/ciclo/pressao/contagem de pernas" — price-action vago
demais pra operacionalizar objetivamente e comparar de forma justa. Este
e o ponto de partida "amplo e generico" decidido em conversa antes de
escrever qualquer sinal, nao uma tentativa de replicar aquele produto.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from strategy.daytrade.base import Bar, Enter, IntradayAction, IntradayOpenPosition, IntradayStrategy


@dataclass
class _SessionState:
    range_high: float | None = None
    range_low: float | None = None
    traded_today: bool = False


class OpeningRangeBreakout(IntradayStrategy):
    """Generica sobre instrumento — `symbol` e OBRIGATORIO no construtor. A
    logica de sinal (range + rompimento) nao depende do instrumento; o que
    muda por instrumento e' custo/tamanho/horario, tratados fora da
    estrategia (`IntradayCostModel`, `IntradayBacktestConfig`), nao aqui —
    mesma separacao de responsabilidade que `strategy.base.Strategy` ja tem
    do lado diario."""

    name = "orb"
    version = "0.1"

    def __init__(
        self,
        symbol: str,
        range_minutes: int = 30,
        target_r_multiple: float = 1.5,
        min_range_price: float = 0.0,
    ):
        """`min_range_price`: ignora a sessao inteira se o range de abertura
        for menor que este valor (em unidade de preco, nao ticks — quem
        instancia converte ticks->preco pro simbolo em questao). Existe
        porque um papel de tick grande RELATIVO ao preco (ex.: PMAM3, tick
        de R$0,01 sobre preco de R$0,14 = 7% do preco) gera range de
        abertura de 1-2 ticks em boa parte dos pregoes — qualquer
        "rompimento" desse range e ruido de quantizacao, nao sinal. Default
        0.0 preserva o comportamento antigo (so exige range > 0)."""
        self.range_minutes = range_minutes
        self.target_r_multiple = target_r_multiple
        self.symbol = symbol
        self.min_range_price = min_range_price
        self._session_start: pd.Timestamp | None = None
        self._state = _SessionState()

    def on_session_start(self, session_date) -> None:
        self._session_start = None
        self._state = _SessionState()

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        position: IntradayOpenPosition | None,
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._session_start is None:
            self._session_start = ts

        formando_range = (ts - self._session_start) < pd.Timedelta(minutes=self.range_minutes)
        if formando_range:
            self._state.range_high = bar.high if self._state.range_high is None else max(self._state.range_high, bar.high)
            self._state.range_low = bar.low if self._state.range_low is None else min(self._state.range_low, bar.low)
            return []

        if self._state.range_high is None or self._state.range_low is None:
            return []  # sessao sem barra suficiente pra formar range (pregao encurtado, etc.)

        if position is not None or self._state.traded_today:
            return []

        range_size = self._state.range_high - self._state.range_low
        if range_size <= 0 or range_size < self.min_range_price:
            return []

        if bar.close > self._state.range_high:
            self._state.traded_today = True
            target = bar.close + self.target_r_multiple * range_size
            return [Enter(
                side="long",
                initial_stop=self._state.range_low,
                initial_target=target,
                reason="orb_breakout_alta",
            )]
        if bar.close < self._state.range_low:
            self._state.traded_today = True
            target = bar.close - self.target_r_multiple * range_size
            return [Enter(
                side="short",
                initial_stop=self._state.range_high,
                initial_target=target,
                reason="orb_breakout_baixa",
            )]
        return []
