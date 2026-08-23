"""Qual feed alimenta ESTE robo de day trade — barra M1 ou negocio a negocio.

Um lugar so'. `IntradayLiveRuntime` recebe o feed pronto e nao sabe de qual
dos dois se trata (os dois tem a mesma interface: `closed_bars_since`,
`session_bars_until`, `offset_hours`, `name`); quem monta o ambiente
(`scripts/run_live.py`, `dashboard/live_service.py`) pergunta aqui.

Por que nao um `if robo.name == "gremah_tick"` em cada chamador: sao dois
chamadores hoje, e a familia de bug que isso cria ja' aconteceu neste
projeto uma vez — `target_fills_as_maker` era passado a mao por chamador, e o
robo que operava acabou com modelo de custo diferente do robo validado (ver
`IntradayStrategy.target_fills_as_maker`). A granularidade e' propriedade do
ROBO (`feed_kind`), declarada com ele; aqui so' se traduz a declaracao em
objeto.

Simbolo desconhecido em `feed_kind` FALHA ALTO, nunca cai no M1 por default:
rodar em minuto um robo cujos parametros de tempo foram medidos em tick e' um
robo diferente do validado, e o erro seria silencioso.
"""
from __future__ import annotations

from live.bar_feed import MT5BarFeed
from live.tick_feed import MT5TickFeed
from strategy.daytrade.base import IntradayStrategy


def feed_for(strategy: IntradayStrategy, on_error=None, **credentials):
    """`MT5BarFeed` ou `MT5TickFeed` para `strategy`, no simbolo dela.

    `credentials` sao os mesmos `login/password/server/path` que os dois feeds
    aceitam (ver `scripts/run_live.py::_mt5_credentials`); sem eles o feed so'
    anexa a um terminal ja' aberto e logado.
    """
    kind = getattr(strategy, "feed_kind", "m1")
    if kind == "m1":
        return MT5BarFeed(strategy.symbol, on_error=on_error, **credentials)
    if kind == "tick":
        return MT5TickFeed(strategy.symbol, on_error=on_error, **credentials)
    raise ValueError(
        f"robo {getattr(strategy, 'name', strategy)!r} declara feed_kind={kind!r}, "
        "que nao existe — use 'm1' (barra de 1 minuto) ou 'tick' (negocio a "
        "negocio). Nao ha default: um robo medido numa granularidade rodando na "
        "outra e' outro robo."
    )
