"""Registro da ULTIMA falha de LEITURA de um feed MT5 — o instrumento que
faltava em 2026-09-08 para "nada novo" e "nao consegui ler" pararem de ser a
mesma coisa aos olhos de quem consome o feed.

O que aconteceu (item 5.17 do `LICOES_DE_PRODUCAO.md`)
------------------------------------------------------
O terminal parou de entregar tick NOVO de WDO@ por 44,8 minutos sem levantar
erro nenhum: `MT5TickFeed.closed_bars_since` devolveu lista VAZIA em 538
passos seguidos do supervisor (5 em 5 segundos), com a marca d'agua congelada
em 2026-09-08 14:14:20.804, e no passo seguinte devolveu 13.644 barras de uma
vez. O robo tratou o despejo como tempo real e mandou 45 ordens-limite REAIS
contra precos de ate' 45 minutos atras (-R$116 no dia). A CAUSA do congelamento
segue desconhecida; o que este modulo ataca e' a INVISIBILIDADE dela.

Duas camadas engoliam o sintoma, e as duas foram corrigidas juntas:

  1. `market_data_intraday.mt5_ticks_source.fetch_ticks_range` devolvia
     DataFrame vazio sem chamar `on_error` mesmo quando o pacote `MetaTrader5`
     sinalizava falha (`copy_ticks_range` -> `None`, ou array vazio com
     `last_error()` negativo) — ver `_falha_de_leitura` la';
  2. o `on_error` do feed nunca era ligado a nada: `scripts/run_live.py` chama
     `live.intraday_feed.feed_for(...)` SEM callback, entao mesmo o erro que
     ja' era reportado (falha de conexao ao terminal) morria no caminho.

Por que um objeto em vez de uma excecao
---------------------------------------
O contrato dos dois feeds e' "lista vazia, NUNCA excecao" (`MT5BarFeed` e
`MT5TickFeed`), e ele nao pode mudar: um passo do supervisor que levanta
derruba o robo em vez de deixa-lo esperar o terminal voltar. Entao a falha
precisa viajar POR FORA do valor de retorno — o feed anota aqui, e quem sabe o
que fazer com isso (`IntradayLiveRuntime`) le depois de cada leitura.

Por que fica em `live/` e nao em `core/`
----------------------------------------
E' politica de orquestracao (o que fazer quando o terminal cala), nao um tipo
de dominio. `bar_feed.py` e `tick_feed.py` sao ambos de `live/`, entao os dois
importarem daqui nao cruza fronteira nenhuma (AGENTS.md, tabela de camadas).
"""
from __future__ import annotations

from typing import Callable, Optional


class RegistroDeLeitura:
    """Anota a ultima falha de leitura do terminal e a repassa adiante.

    Uso: o feed cria um por instancia, chama `reset()` no comeco de cada
    leitura publica, entrega `registro.callback` como `on_error` da funcao de
    busca, e expoe `registro.falha` para quem consome.

    `on_error` externo continua sendo chamado — este registro NAO substitui o
    callback de quem construiu o feed, so' garante que a falha fique legivel
    mesmo quando ninguem passou callback nenhum (que era o caso de todos os
    slots de day trade ao vivo ate' 2026-09-08).
    """

    def __init__(self, on_error: Optional[Callable[[str, Exception], None]] = None) -> None:
        self._on_error = on_error
        self._falha: Optional[str] = None

    def reset(self) -> None:
        """Zera a anotacao. Tem de ser chamado no comeco de CADA leitura: sem
        isso uma falha de 5 minutos atras continuaria sendo reportada como se
        fosse de agora, e um alarme que nao apaga sozinho vira ruido."""
        self._falha = None

    def callback(self, key: str, exc: Exception) -> None:
        self._falha = f"{key}: {exc}"
        if self._on_error is not None:
            self._on_error(key, exc)

    @property
    def falha(self) -> Optional[str]:
        """Texto da ultima falha desta leitura, ou `None` se a leitura foi bem
        sucedida — inclusive quando ela devolveu ZERO barra, que e' o caso
        normal de papel parado e nao pode virar alarme."""
        return self._falha
