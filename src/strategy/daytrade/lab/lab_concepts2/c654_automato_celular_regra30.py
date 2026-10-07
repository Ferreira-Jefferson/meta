"""Catálogo autômatos/ML/jogos, item 55: AutomatoCelularRegra30.

Codifica a direção das últimas 8 barras como estado binário, aplica um
passo do autômato celular elementar Regra 30 (contorno circular) para
prever o próximo bit, e casa essa previsão contra uma tabela de contagem
histórica do mesmo padrão de 8 bits antes de decidir a direção.
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

# Regra 30 de Wolfram: (esquerda, centro, direita) -> novo centro.
_REGRA_30 = {
    (1, 1, 1): 0, (1, 1, 0): 1, (1, 0, 1): 1, (1, 0, 0): 1,
    (0, 1, 1): 1, (0, 1, 0): 1, (0, 0, 1): 1, (0, 0, 0): 0,
}


@dataclass
class AutomatoCelularRegra30(IntradayStrategy):
    """Um passo de Regra 30 sobre as últimas 8 direções prevê o próximo
    bit; entra na direção prevista só quando o mesmo padrão de 8 bits já
    foi visto antes e a maioria histórica concorda com a previsão."""

    name: str = "automato_celular_regra30"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    n_celulas: int = 8
    min_amostras: int = 3
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _direcoes: deque = field(default_factory=lambda: deque(maxlen=8), init=False, repr=False)
    _contagem: dict = field(default_factory=dict, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        if self._direcoes.maxlen != self.n_celulas:
            self._direcoes = deque(self._direcoes, maxlen=self.n_celulas)
        # `_contagem` sobrevive entre sessões de propósito: é uma tabela
        # de contagem histórica acumulada, não estado do dia.

    def _passo_regra30(self, estado: tuple[int, ...]) -> tuple[int, ...]:
        n = len(estado)
        return tuple(
            _REGRA_30[(estado[(i - 1) % n], estado[i], estado[(i + 1) % n])]
            for i in range(n)
        )

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        direcao_barra = 1 if bar.close >= bar.open else 0

        if len(self._direcoes) == self._direcoes.maxlen:
            padrao_anterior = tuple(self._direcoes)
            registro = self._contagem.setdefault(padrao_anterior, [0, 0])
            registro[direcao_barra] += 1

        self._direcoes.append(direcao_barra)

        if not positions and len(self._direcoes) == self._direcoes.maxlen:
            estado_atual = tuple(self._direcoes)
            bit_previsto = self._passo_regra30(estado_atual)[-1]
            registro = self._contagem.get(estado_atual)
            if registro is not None:
                total = registro[0] + registro[1]
                if total >= self.min_amostras:
                    maioria = 1 if registro[1] > registro[0] else 0
                    if maioria == bit_previsto:
                        side = "long" if bit_previsto == 1 else "short"
                        if side == "long":
                            limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                            stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                            alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                        else:
                            limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                            stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                            alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                        acao = [EnterLimit(
                            side=side, limit_price=limite, initial_stop=stop,
                            initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                        )]
        return acao
