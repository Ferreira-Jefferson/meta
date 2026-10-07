"""Catálogo física, item 29: EfeitoDoppler.

Analogia com efeito Doppler: mede a "frequência" de trocas de sinal do
retorno barra-a-barra (quantas vezes o sinal do retorno inverte numa
janela rolling, dividido pelo tamanho da janela). Frequência crescente
(comparada com a frequência de uma janela mais longa) ao mesmo tempo em
que o preço se aproxima de um nível extremo recente prevê rompimento
iminente nessa direção — a "compressão de onda" que precede a passagem.
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


@dataclass
class EfeitoDoppler(IntradayStrategy):
    """Frequência de trocas de sinal do retorno (janela curta vs longa);
    frequência crescente perto de um extremo recente prevê rompimento na
    direção da aproximação."""

    name: str = "efeito_doppler"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_curta: int = 8
    janela_longa: int = 30
    janela_extremo: int = 30
    proximidade_ticks: float = 3.0
    fator_aumento_frequencia: float = 1.3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=31), init=False, repr=False)
    _sinais: deque = field(default_factory=lambda: deque(maxlen=30), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._closes = deque(maxlen=self.janela_longa + 1)
        self._sinais = deque(maxlen=self.janela_longa)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if self._closes:
            retorno = bar.close - self._closes[-1]
            sinal = 1 if retorno > 0 else (-1 if retorno < 0 else 0)
            self._sinais.append(sinal)

        if not positions and len(self._sinais) == self._sinais.maxlen and len(self._closes) == self._closes.maxlen:
            sinais = list(self._sinais)
            trocas_curtas = sum(
                1 for i in range(1, self.janela_curta)
                if sinais[-i] != 0 and sinais[-i - 1] != 0 and sinais[-i] != sinais[-i - 1]
            )
            trocas_longas = sum(
                1 for i in range(1, len(sinais))
                if sinais[-i] != 0 and sinais[-i - 1] != 0 and sinais[-i] != sinais[-i - 1]
            )
            freq_curta = trocas_curtas / max(self.janela_curta - 1, 1)
            freq_longa = trocas_longas / max(len(sinais) - 1, 1)

            if freq_longa > 1e-9 and freq_curta >= self.fator_aumento_frequencia * freq_longa:
                precos = list(self._closes)
                maximo = max(precos[-self.janela_extremo:])
                minimo = min(precos[-self.janela_extremo:])
                proximidade = self.proximidade_ticks * self.tick_size
                if abs(bar.close - maximo) <= proximidade:
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="long", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]
                elif abs(bar.close - minimo) <= proximidade:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                    acao = [EnterLimit(
                        side="short", limit_price=limite, initial_stop=stop,
                        initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                        exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                    )]

        self._closes.append(bar.close)
        return acao
