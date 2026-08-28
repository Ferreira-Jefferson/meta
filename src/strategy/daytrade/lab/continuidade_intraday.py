"""Regra de trade da sub-hipotese 2 (CONTINUIDADE INTRADIARIA) da rodada
`continuidade_*`: converte o achado BRUTO medido em `continuidade_stats.py`
(retorno de barra reamostrada em `t` prediz o SINAL do retorno em `t+1`,
DENTRO da mesma sessao) numa regra de trade real.

Diferente de `continuidade_daily.ContinuidadeDiaria` (uma decisao por
pregao, sem timing nenhum), esta classe decide a CADA fronteira de barra
reamostrada -- ou seja, reintroduz exatamente o problema de TIMING que o
achado de cautela da linha Copa levantou (ML por barra acerta o lado 80,8%
mas so' 35% dos trades da' lucro). Por isso o estagio B desta sub-hipotese
(`scripts/daytrade/continuidade_intraday_rule.py`) testa isso
EXPLICITAMENTE com custo real, em vez de assumir que o achado bruto
sobrevive.

## Alinhamento com `continuidade_stats.intraday_return_groups`

O achado bruto vem de `closes.resample(rule, label="right",
closed="right").last().pct_change()` -- ou seja, o retorno da janela que
TERMINA na barra M1 cujo minuto e' multiplo de `bar_minutes` (resample com
origem em meia-noite: `label`/`closed="right"` fazem o intervalo
`(t-bar_minutes, t]` ser identificado pelo seu fim `t`). Esta classe
detecta a MESMA fronteira olhando `ts.minute % bar_minutes == 0` -- o
minuto de FECHAMENTO da barra M1 (index = fechamento, convencao do resto
do motor) cai exatamente nesses multiplos quando a sessao comeca em
qualquer minuto (a origem do resample e' meia-noite, que e' ela mesma
multiplo de `bar_minutes`).

## Por que EXIT-entao-ENTER, nunca Enter direto com posicao aberta

O motor DESCARTA em silencio um `Enter`/`EnterLimit` devolvido com posicao
ja' aberta (`backtest/intraday/machine.py`, "Enter com posicao ja aberta...
descartado") -- nao piramida. Uma troca de lado por isso precisa de DOIS
`on_bar` em sequencia: `Exit()` quando o lado desejado diverge do lado
aberto (fecha na abertura da barra seguinte), depois `Enter()` na chamada
seguinte, ja' com a posicao flat (fecha na abertura da barra depois
dessa) -- 2 barras M1 de atraso entre o sinal e a nova posicao, atraso
irrelevante frente a uma janela de `bar_minutes` inteira. Quando o lado
desejado NAO muda, a posicao so' CONTINUA (nenhuma acao) -- reabrir a
mesma posicao a cada fronteira so' pagaria custo de round-trip a toa, o
que nenhum robo de verdade faria.

`direction="reversal"`: aposta no lado OPOSTO ao retorno que acabou de
fechar (o sinal medido para WDO@/5min: corr lag-1 negativa).
`direction="continuation"`: aposta no MESMO lado. Retorno da janela
EXATAMENTE zero (raro com preco continuo) e' sinal indefinido -- fica
flat ate a proxima fronteira definir um lado."""
from __future__ import annotations

from typing import Literal

import pandas as pd

from strategy.daytrade.base import (
    Bar,
    Enter,
    Exit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
)

Direction = Literal["continuation", "reversal"]


def _flip(side: str) -> str:
    return "short" if side == "long" else "long"


class ContinuidadeIntraday(IntradayStrategy):
    """`bar_minutes`: tamanho da janela reamostrada testada em
    `continuidade_stats.py` (5/15/60) -- tem que bater com o horizonte cujo
    lag-1 foi promovido, nunca escolhido aqui de novo."""

    name = "continuidade_intraday"
    version = "0.1"

    def __init__(
        self,
        symbol: str,
        bar_minutes: int,
        direction: Direction = "continuation",
        quantity: int | None = None,
    ):
        if bar_minutes < 1:
            raise ValueError(f"bar_minutes tem que ser >= 1, recebeu {bar_minutes!r}")
        self.symbol = symbol
        self.bar_minutes = bar_minutes
        self.direction = direction
        self.quantity = quantity
        self._last_boundary_close: float | None = None
        self._desired_side: str | None = None

    def on_session_start(self, session_date) -> None:
        # nunca carrega fronteira/sinal de uma sessao para a seguinte -- o
        # retorno da ULTIMA janela de ontem nao pareia com a PRIMEIRA de
        # hoje em `continuidade_stats.lag_pairs` (nunca cruza sessao), a
        # regra de trade segue a MESMA fronteira.
        self._last_boundary_close = None
        self._desired_side = None

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if ts.minute % self.bar_minutes == 0:
            if self._last_boundary_close is not None:
                retorno = bar.close - self._last_boundary_close
                if retorno > 0:
                    lado_bruto = "long"
                elif retorno < 0:
                    lado_bruto = "short"
                else:
                    lado_bruto = None  # retorno exatamente zero -- sinal indefinido
                if lado_bruto is not None:
                    self._desired_side = (
                        lado_bruto if self.direction == "continuation" else _flip(lado_bruto)
                    )
                else:
                    self._desired_side = None
            self._last_boundary_close = bar.close

        if positions:
            lado_atual = positions[0].side
            if self._desired_side is None or self._desired_side != lado_atual:
                return [Exit(reason=f"continuidade_intraday:{self.direction}:flip")]
            return []
        if self._desired_side is not None:
            return [Enter(
                side=self._desired_side,  # type: ignore[arg-type]
                quantity=self.quantity,
                reason=f"continuidade_intraday:{self.direction}",
            )]
        return []
