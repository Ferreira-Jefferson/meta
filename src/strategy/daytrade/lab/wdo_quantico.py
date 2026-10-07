"""`wdo_quantico` -- fade nos niveis do oscilador harmonico QUANTICO, no WDO@.

## A traducao (e o que NAO se traduz)

Equacao de Schrodinger com potencial quadratico V(x) = 1/2 m w^2 x^2 (uma
"mola" que puxa o preco de volta ao centro -- reversao a media). Os
autoestados tem densidade de Born |psi_n|^2 e pontos de retorno classicos em
x_n = l * sqrt(2n+1), com l = sqrt(hbar / m w).

Calibrando pelo dado: o estado fundamental |psi_0|^2 e' uma gaussiana de
desvio l/sqrt(2). Igualando esse desvio ao sigma medido dos fechamentos da
janela, l = sqrt(2) * sigma, e os niveis viram

    nivel_n = centro +/- sigma * sqrt(2 * (2n + 1))
    n=0 -> 1,414 sigma   (entrada: borda da nuvem do estado fundamental)
    n=1 -> 2,449 sigma   (stop: o preco "saltou" para o estado excitado)

O multiplicador NAO e' parametro livre -- sai da equacao. O unico eixo livre
e' W (a escala de tempo do poco). `hbar` some dentro de sigma ao calibrar; o
papel dele no mercado e' do TICK (o quantum de preco): abaixo de
`DISTANCIA_MINIMA_TICKS` a discretizacao e o pedagio dominam e a formula
continua nao descreve nada, entao o robo nao opera.

Nulo: sob passeio aleatorio a chance de chegar ao alvo antes do stop e'
exatamente stop/(alvo+stop) -- o breakeven. Edge so' existe se o preco for de
fato "ligado" a um poco nessa escala de tempo.

Desenho de execucao FECHADO (CLAUDE.md): `EnterLimit` com prazo, alvo
limite fatiado sem prazo, so' o stop a mercado. Nenhum nivel atravessa o
pregao (emenda de rolagem do `WDO@`).
"""
from __future__ import annotations

import math
from collections import deque

import numpy as np
import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

#: Mesma formula de `wdo_retangulo.LARGURA_MINIMA_TICKS` (4 x pedagio de
#: 1,10 tick no WDO@), aplicada a distancia entrada->alvo.
DISTANCIA_MINIMA_TICKS = 4.4


def nivel_quantico(n: int) -> float:
    """Ponto de retorno do autoestado n, em unidades de sigma do fundamental."""
    return math.sqrt(2 * (2 * n + 1))


class WdoQuantico(IntradayStrategy):
    """Limite na borda da nuvem (n=0), alvo no centro, stop no nivel n=1."""

    name = "wdo_quantico"
    version = "0.1.0"
    symbol = "WDO@"
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(
        self,
        symbol: str | None = None,
        janela_barras: int = 60,
        k_entrada: float = nivel_quantico(0),
        k_stop: float = nivel_quantico(1),
        ttl_barras: int = 10,
        quantidade: int = 1,
    ) -> None:
        if janela_barras < 10:
            raise ValueError(f"janela_barras={janela_barras}: sigma sem amostra")
        if not 0 < k_entrada < k_stop:
            raise ValueError("exige 0 < k_entrada < k_stop")
        if ttl_barras is None or ttl_barras <= 0:
            raise ValueError("ttl_barras e' obrigatorio (fill 269,7 min depois do sinal)")
        if symbol is not None:
            self.symbol = symbol
        self.janela_barras = int(janela_barras)
        self.k_entrada = float(k_entrada)
        self.k_stop = float(k_stop)
        self.ttl_barras = int(ttl_barras)
        self.quantidade = int(quantidade)
        self.tick_size = economics_for(self.symbol).price_tick_size
        self._reset_sessao()

    def _reset_sessao(self) -> None:
        self._closes: deque[float] = deque(maxlen=self.janela_barras)
        self._barras_esperando: int | None = None

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._barras_esperando = None

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._barras_esperando = None

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._closes.append(bar.close)
        if len(self._closes) < self.janela_barras:
            return []
        if positions:
            self._barras_esperando = None
            return []
        if self._barras_esperando is not None:
            self._barras_esperando += 1
            if self._barras_esperando < self.ttl_barras:
                return []
            self._barras_esperando = None

        c = np.fromiter(self._closes, dtype=float)
        centro = float(c.mean())
        sigma = float(c.std(ddof=1))
        if self.k_entrada * sigma < DISTANCIA_MINIMA_TICKS * self.tick_size:
            return []

        # A limite descansa na borda do lado em que o preco ja' esta:
        # venda acima, compra abaixo -- nunca do lado errado do preco.
        if bar.close > centro:
            lado, sinal = "short", 1.0
        elif bar.close < centro:
            lado, sinal = "long", -1.0
        else:
            return []
        limite = no_tick(centro + sinal * self.k_entrada * sigma, self.tick_size)
        if (lado == "short" and limite <= bar.close) or (lado == "long" and limite >= bar.close):
            return []

        self._barras_esperando = 0
        return [EnterLimit(
            side=lado,
            limit_price=limite,
            initial_stop=no_tick(centro + sinal * self.k_stop * sigma, self.tick_size),
            initial_target=no_tick(centro, self.tick_size),
            quantity=self.quantidade,
            ttl_bars=self.ttl_barras,
            exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO,
            reason=f"quantico_W{self.janela_barras}_s{sigma:.2f}",
        )]
