"""Utilitarios compartilhados pelos 40 conceitos de regime/adaptacao (c500-c539).

Nao e' estrategia -- mora aqui so' para nao repetir, em 40 arquivos, a mesma
mecanica de buffer/EnterLimit/piso-de-4-ticks. Cada arquivo de estrategia
continua sendo UM MECANISMO so' (o contrato do lote): o que se repete entre
eles e' a BARRA/EXECUCAO, nunca o sinal que decide a entrada.

Desenho de execucao FECHADO (CLAUDE.md, ordem do dono 2026-09-10): entrada
sempre `EnterLimit` parada no livro, alvo sempre ordem-limite real fatiada
SEM prazo, piso de 4 ticks no alvo, todo preco na grade do tick. `montar_
entrada` e' o unico lugar que constroi a acao de entrada -- os 40 arquivos
so' decidem SE e QUANDO chamar ela.
"""
from __future__ import annotations

from collections import deque

import numpy as np
import pandas as pd

from strategy.daytrade.base import Bar, EnterLimit, no_tick

#: prazo da fatia de saida por alvo: sem prazo, NUNCA `None` (o motor em
#: execucao real exige um numero finito) -- mesma constante de
#: `wdo_orb.EXIT_TTL_BARS_SEM_PRAZO`.
EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

#: piso de 4 ticks (2 pontos, tick_size=0,5) que NENHUM alvo dinamico pode
#: furar -- literal do catalogo ("piso de 4 ticks sempre respeitado").
PISO_ALVO_TICKS = 4


def alvo_com_piso(ticks: float, piso: int = PISO_ALVO_TICKS) -> int:
    """Arredonda `ticks` para inteiro e aplica o piso -- nunca abaixo de `piso`."""
    return max(piso, int(round(ticks)))


def clamp_quantity(qty: float, minimo: int = 1, teto: int = 5) -> int:
    """Tamanho de posicao nunca abaixo de `minimo` nem acima do `teto`."""
    return int(max(minimo, min(teto, round(qty))))


def montar_entrada(
    *,
    side: str,
    limit_price: float,
    stop_ticks: float,
    alvo_ticks: float,
    tick_size: float,
    quantity: int,
    ttl_bars: int,
    reason: str,
    exit_ttl_bars: int = EXIT_TTL_BARS_SEM_PRAZO,
) -> EnterLimit:
    """Constroi a `EnterLimit` no desenho de execucao FECHADO. `stop_ticks`/
    `alvo_ticks` sao distancias (sempre positivas) a partir de `limit_price`;
    o sinal (long soma, short subtrai) e' resolvido aqui, uma vez so'."""
    sinal = 1.0 if side == "long" else -1.0
    alvo_ticks = alvo_com_piso(alvo_ticks)
    stop_ticks = max(1, int(round(stop_ticks)))
    limit_price = no_tick(limit_price, tick_size)
    stop_price = no_tick(limit_price - sinal * stop_ticks * tick_size, tick_size)
    target_price = no_tick(limit_price + sinal * alvo_ticks * tick_size, tick_size)
    return EnterLimit(
        side=side,
        limit_price=limit_price,
        initial_stop=stop_price,
        initial_target=target_price,
        quantity=quantity,
        ttl_bars=ttl_bars,
        exit_split_unit=1,
        exit_ttl_bars=exit_ttl_bars,
        reason=reason,
    )


class BarBuffer:
    """Janela rolante de barras (M1 ou tick) para indicadores que precisam de
    SERIE -- `core.indicators` so' aceita `pd.Series` prontas, e `on_bar`
    recebe uma barra de cada vez, entao alguem tem que acumular. `maxlen`
    limita memoria/CPU (mais barra do que a maior janela usada nunca faz
    falta e so' custaria tempo de conversao)."""

    def __init__(self, maxlen: int):
        self.maxlen = int(maxlen)
        self._ts: deque = deque(maxlen=self.maxlen)
        self._open: deque = deque(maxlen=self.maxlen)
        self._high: deque = deque(maxlen=self.maxlen)
        self._low: deque = deque(maxlen=self.maxlen)
        self._close: deque = deque(maxlen=self.maxlen)
        self._volume: deque = deque(maxlen=self.maxlen)

    def push(self, bar: Bar) -> None:
        self._ts.append(bar.ts)
        self._open.append(bar.open)
        self._high.append(bar.high)
        self._low.append(bar.low)
        self._close.append(bar.close)
        self._volume.append(bar.volume)

    def __len__(self) -> int:
        return len(self._close)

    def close(self) -> pd.Series:
        return pd.Series(list(self._close))

    def high(self) -> pd.Series:
        return pd.Series(list(self._high))

    def low(self) -> pd.Series:
        return pd.Series(list(self._low))

    def open(self) -> pd.Series:
        return pd.Series(list(self._open))

    def volume(self) -> pd.Series:
        return pd.Series(list(self._volume))

    def ts_list(self) -> list:
        return list(self._ts)


def wilder_adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """ADX construido na mao (Wilder) a partir de +DM/-DM/TR -- devolve
    `(plus_di, minus_di, adx)` alinhadas com o indice de entrada. Sem lib
    alem de numpy/pandas (scipy/ta-lib banidos neste repo)."""
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low, (high - prev_close).abs(), (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr_w = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    plus_dm_s = pd.Series(plus_dm, index=high.index).ewm(
        alpha=1.0 / period, adjust=False, min_periods=period).mean()
    minus_dm_s = pd.Series(minus_dm, index=high.index).ewm(
        alpha=1.0 / period, adjust=False, min_periods=period).mean()

    plus_di = 100.0 * plus_dm_s / atr_w.replace(0.0, np.nan)
    minus_di = 100.0 * minus_dm_s / atr_w.replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx = dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    return plus_di, minus_di, adx


def percentile_rank(historico, valor: float) -> float:
    """Percentil (0-100) de `valor` dentro de `historico` (deque/lista de
    valores passados JA' encerrados -- quem chama decide se `valor` ja' esta'
    dentro ou nao, esta funcao nao empilha nada sozinha)."""
    if not historico:
        return 50.0
    arr = np.asarray(historico, dtype=float)
    return float((arr <= valor).sum()) / float(len(arr)) * 100.0


def resample_synthetic(buffer: BarBuffer, minutos: float) -> pd.DataFrame:
    """Agrega as barras do `buffer` (M1) em candles sinteticos de `minutos`
    minutos via `pandas.resample` -- usado pelos filtros multi-escala (M5/
    M15/M60 sinteticos) que nao tem feed proprio, so' agregam o M1 que ja
    chega. Devolve SO' os candles FECHADOS (o `.iloc[:-1]`) -- o candle mais
    recente ainda pode estar em formacao, e usa-lo inteiro seria olhar o
    futuro do proprio candle corrente."""
    ts = buffer.ts_list()
    if len(ts) < 2:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    df = pd.DataFrame({
        "open": list(buffer._open), "high": list(buffer._high),
        "low": list(buffer._low), "close": list(buffer._close),
    }, index=pd.DatetimeIndex(ts))
    agg = df.resample(f"{minutos}min", label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    if len(agg) < 2:
        return agg.iloc[0:0]
    return agg.iloc[:-1]
