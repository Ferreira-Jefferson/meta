"""Zigzag/pivo por LIMIAR para a hipotese de CONTINUIDADE DE PERNA (swing) --
funcao PURA sobre uma serie de precos (sem I/O; quem carrega o dado e' o
chamador em `scripts/`).

Limiar em TICKS (nao percentual do preco): o mesmo numero de ticks custa a
mesma coisa em qualquer nivel de indice, e o tick de WIN@ (5,0) e WDO@ (0,5)
ja' vem de `backtest.intraday.profiles.FUTURES_PROFILES` -- um limiar
percentual teria que ser recalibrado toda vez que o indice mudasse de
patamar; um limiar em ticks nao.

Algoritmo classico de zigzag por reversao de limiar: acompanha o extremo
(maximo ou minimo) desde o ultimo pivo CONFIRMADO; um pivo so' e' confirmado
quando o preco reverte pelo menos `threshold` a PARTIR desse extremo -- e'
o motivo de o pivo nunca usar informacao futura (so' confirma DEPOIS da
reversao acontecer de verdade, nunca antes, exatamente a mesma disciplina
anti-look-ahead do motor de backtest).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

Kind = Literal["high", "low"]


@dataclass(frozen=True)
class Pivot:
    ts: pd.Timestamp
    price: float
    kind: Kind


def zigzag_pivots(prices: pd.Series, threshold: float) -> list[Pivot]:
    """`threshold`: em UNIDADE DE PRECO (ja multiplicado por ticks x
    tick_size antes de chamar -- esta funcao nao sabe o que e' um tick,
    mesma separacao de responsabilidade de `strategy.daytrade.base.no_tick`).
    `threshold <= 0` levanta `ValueError` (limiar nao-positivo nao filtra
    nada -- e' erro de configuracao, nao "sem filtro").

    Devolve so' pivos CONFIRMADOS -- a ultima perna, do ultimo pivo ate o
    fim da serie, NUNCA e' confirmada (pode continuar), mesma disciplina de
    "sem look-ahead" do resto do motor. Por construcao a lista alterna
    'low','high','low','high',... comecando pelo tipo do primeiro
    movimento que rompeu o limiar a partir do primeiro preco da serie."""
    if threshold <= 0:
        raise ValueError(f"threshold tem que ser positivo, recebeu {threshold!r}")
    vals = prices.to_numpy(dtype=float)
    idxs = prices.index
    n = len(vals)
    if n < 2:
        return []

    pivots: list[Pivot] = []
    trend = 0  # 0 = direcao ainda desconhecida, 1 = buscando maximo, -1 = buscando minimo
    anchor_i = 0
    anchor_v = vals[0]
    ext_i = 0
    ext_v = vals[0]

    for i in range(1, n):
        v = vals[i]
        if trend == 0:
            if v - anchor_v >= threshold:
                pivots.append(Pivot(ts=idxs[anchor_i], price=float(anchor_v), kind="low"))
                trend, ext_i, ext_v = 1, i, v
            elif anchor_v - v >= threshold:
                pivots.append(Pivot(ts=idxs[anchor_i], price=float(anchor_v), kind="high"))
                trend, ext_i, ext_v = -1, i, v
        elif trend == 1:
            if v > ext_v:
                ext_i, ext_v = i, v
            elif ext_v - v >= threshold:
                pivots.append(Pivot(ts=idxs[ext_i], price=float(ext_v), kind="high"))
                trend, ext_i, ext_v = -1, i, v
        else:  # trend == -1
            if v < ext_v:
                ext_i, ext_v = i, v
            elif v - ext_v >= threshold:
                pivots.append(Pivot(ts=idxs[ext_i], price=float(ext_v), kind="low"))
                trend, ext_i, ext_v = 1, i, v
    return pivots


def continuation_series(pivots: list[Pivot]) -> dict[str, list[int]]:
    """DUAS series binarias de CONTINUACAO DE ESTRUTURA (Dow theory HH/LH e
    HL/LL), uma para topos e uma para fundos -- SEPARADAS de proposito (ver
    o motivo abaixo), cada uma em ordem cronologica dos pivos do seu tipo.

    `"high"`: `1` se este topo SUPERA o topo CONFIRMADO anterior (nova
    maxima, "higher high" -- a tendencia de alta que originou o topo
    anterior persiste), `0` se FALHA em superar ("lower high" -- sinal
    classico de topo/reversao). Mapeia DIRETO a pergunta do dono: "depois
    de uma perna de alta seguida de uma de queda, a proxima perna de alta
    supera a anterior?" = o proximo elemento desta serie.

    `"low"`: espelho para fundos -- `1` = nova minima ("lower low", a
    tendencia de baixa persiste), `0` = "higher low" (fundo nao confirma
    nova minima).

    Por que DUAS series, nao uma so intercalada: um topo e' sempre seguido
    de um fundo e vice-versa (alternancia estrutural do proprio zigzag,
    probabilidade 1 -- nunca um padrao com incerteza para testar). Juntar
    "topo supera topo anterior" (sinal de tendencia de ALTA) com "fundo
    supera -- ou seja, fica ABAIXO -- do fundo anterior" (sinal de
    tendencia de BAIXA) numa unica serie faria dois eventos de POLARIDADE
    OPOSTA (um bullish, um bearish) virarem "1" pelo mesmo criterio -- em
    uma tendencia de alta limpa (topos e fundos ambos subindo) a serie
    intercalada leria 0,1,0,1,... (o teste de fundo FALHA sempre, porque
    os fundos estao subindo, nao caindo) em vez de refletir que a
    tendencia esta, sim, persistindo. Manter as duas series separadas
    evita essa conflacao e responde exatamente a pergunta literal do
    dono para cada lado (topo depois de topo, fundo depois de fundo)."""
    high_out: list[int] = []
    low_out: list[int] = []
    last_high: float | None = None
    last_low: float | None = None
    for p in pivots:
        if p.kind == "high":
            if last_high is not None:
                high_out.append(1 if p.price > last_high else 0)
            last_high = p.price
        else:
            if last_low is not None:
                low_out.append(1 if p.price < last_low else 0)
            last_low = p.price
    return {"high": high_out, "low": low_out}
