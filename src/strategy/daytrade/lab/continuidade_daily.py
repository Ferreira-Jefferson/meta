"""Regra de trade da sub-hipotese 1 (CONTINUIDADE DIARIA) da rodada
`continuidade_*`: uma UNICA decisao por pregao, tomada na PRIMEIRA barra da
sessao, mantida ate o fechamento forcado do motor -- SEM timing
intradiario nenhum para acertar (nem stop, nem alvo, nem saida antecipada).

Por que este desenho, especificamente: o achado de cautela da linha Copa
(ML por BARRA acerta o LADO 80,8% das vezes mas so' 35% dos trades da'
lucro, porque o dificil e' A HORA de entrar/sair) NAO se aplica a uma regra
que decide uma vez so' por dia e deixa o motor flatten no fim da sessao --
esta classe existe para TESTAR essa hipotese de escape explicitamente
(`scripts/daytrade/continuidade_daily_rule.py`), nao para assumi-la.

`direction`: decidido de FORA (pelo sinal medido da autocorrelacao real,
`scripts/daytrade/continuidade_stats.py`), nunca escolhido tentando as duas
e ficando com a melhor -- isso seria exatamente o vies de "escolher o
melhor depois de olhar" que a rodada evita. `"continuation"` entra no MESMO
lado do dia anterior (fechou pra cima -> long hoje); `"reversal"` entra no
lado OPOSTO.

Usa o hook `seed_daily_volatility` (ja chamado pelo motor, ANTES de
`on_session_start`, so' com sessoes ANTERIORES -- `backtest/intraday/
engine.py`) para descobrir o retorno fechamento-a-fechamento do dia mais
recente JA CONCLUIDO -- nunca `initialize`/o `bars` completo, para a
decisao de CADA dia nunca depender de nada alem do que um robo ao vivo
teria disponivel naquela manha (mesma disciplina anti-look-ahead do resto
do motor, e o MESMO hook que `JanelaVolatilidadeDiaria` ja usa)."""
from __future__ import annotations

from typing import Literal

import pandas as pd

from strategy.daytrade.base import (
    Bar,
    Enter,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
)

Direction = Literal["continuation", "reversal"]


def _flip(side: str) -> str:
    return "short" if side == "long" else "long"


class ContinuidadeDiaria(IntradayStrategy):
    """`direction="continuation"`: aposta que o dia D+1 fecha no MESMO
    sinal do dia D. `direction="reversal"`: aposta no sinal OPOSTO. Um
    unico contrato por padrao (`quantity=None` -> `default_quantity` da
    config) -- escalonamento por capital e' outra frente de pesquisa, fora
    do escopo desta."""

    name = "continuidade_diaria"
    version = "0.1"

    def __init__(self, symbol: str, direction: Direction = "continuation", quantity: int | None = None):
        self.symbol = symbol
        self.direction = direction
        self.quantity = quantity
        self._pending_side: str | None = None
        self._today_side: str | None = None
        self._entered_today = False

    def seed_daily_volatility(self, previous_daily_bars: list[Bar]) -> None:
        """Chamado 1x por sessao, ANTES de `on_session_start`, com a barra
        DIARIA de cada sessao ANTERIOR ja concluida (mais antiga primeiro)
        -- ver docstring do modulo. Precisa de pelo menos 2 dias anteriores
        para existir um retorno fechamento-a-fechamento do dia mais
        recente; com menos que isso (inicio do historico), nao ha sinal e
        o robo fica de fora do pregao."""
        if len(previous_daily_bars) < 2:
            self._pending_side = None
            return
        retorno = previous_daily_bars[-1].close - previous_daily_bars[-2].close
        if retorno > 0:
            lado_bruto = "long"
        elif retorno < 0:
            lado_bruto = "short"
        else:
            self._pending_side = None  # retorno exatamente zero -- sinal indefinido
            return
        self._pending_side = lado_bruto if self.direction == "continuation" else _flip(lado_bruto)

    def on_session_start(self, session_date) -> None:
        self._today_side = self._pending_side
        self._entered_today = False

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._entered_today or self._today_side is None or positions:
            return []
        self._entered_today = True
        return [Enter(
            side=self._today_side,  # type: ignore[arg-type]
            quantity=self.quantity,
            reason=f"continuidade_diaria:{self.direction}",
        )]
