"""Reversao apos excesso intrabar (Frente F6-win-volatilidade, 2026-08-26) --
regra CONDICIONAL sobre WIN@, gatilhada so' depois de um movimento medido,
nao um desenho de grid/bracket que fica sempre presente no book.

## Por que isto e' DIFERENTE do que ja foi refutado no projeto

1. Bracket OCO / straddle simples (familia `copa`, 0/560 celulas positivas):
   aquele desenho pendura DUAS ordens simetricas na ABERTURA de todo pregao
   (uma acima, uma abaixo) e segue quem tocar primeiro -- e' uma aposta
   incondicional de ROMPIMENTO a cada sessao. Esta estrategia nao pendura
   nada por padrao: so' entra depois de MEDIR um movimento de
   `threshold_ticks` em `k_bars` barras, e entao aposta o OPOSTO dele
   (reversao), nao o mesmo lado do rompimento -- direcao E gatilho sao os
   dois invertidos frente ao bracket.

2. Grid-maker estilo `gremah` (MORTO no WIN com certeza matematica -- 0/60
   celulas, alvo de 1 tick exige 83-98,5% de acerto mesmo sem pedagio de
   fila): aquele desenho pendura ordens-limite (maker) em VARIOS niveis
   fixos o pregao inteiro e vive de repiques de poucos ticks repetidos
   centenas de vezes -- e' um jogo de ACERTO ALTISSIMO com alvo minusculo.
   Esta estrategia entra a MERCADO (taker, paga o spread completo -- ver
   `IntradayStrategy.target_fills_as_maker = False`), UMA vez por sinal, com
   alvo/stop na casa de dezenas de ticks -- e' um jogo de RAZAO
   ganho/perda, nao de acerto quase perfeito. Perde MENOS por trade quando
   erra (paga so' `slippage_ticks` x2 + a tarifa fixa) mas tambem precisa de
   bem menos que 83% de acerto para empatar -- outra economia de aposta,
   nao uma variacao de parametro do grid.

3. Nao e' filtro de regime sobre o grid morto: o grid morreu por
   ARITMETICA (T=1/T=2 exigem acerto ACIMA de 100% com 1 tick de pedagio),
   nenhum filtro de regime destrava uma exigencia impossivel. Esta
   estrategia muda o DESENHO inteiro (taker, condicional, alvo largo), nao
   so' o portao de quando o grid antigo pode operar.

## O que o sinal mede

`burst_ticks = (close[t] - close[t-k_bars]) / tick_size` -- o deslocamento
LIQUIDO do fechamento em `k_bars` barras, no CAMPO das barras JA FECHADAS
(sem look-ahead: a barra `t` que gera a decisao ja fechou; a acao executa
na abertura de `t+1`, disciplina padrao de `IntradayStrategy`/
`IntradaySessionMachine`). Quando `|burst_ticks| >= threshold_ticks`:

- `mode="fade"` (a hipotese principal desta frente, mean-reversion apos
  excesso): entra no lado OPOSTO ao movimento -- comprou muito -> vende;
  caiu muito -> compra.
- `mode="continuation"` (contraste, nao a hipotese principal): entra no
  MESMO lado do movimento -- existe so' para comparar contra o fade com o
  MESMO gatilho/custo/tamanho de amostra. Se os dois perdem por
  aproximadamente o mesmo tanto (a diferenca sendo so' o custo, pago duas
  vezes de forma simetrica), o achado e' "sem tendencia direcional apos o
  excesso" -- consistente com MFE=MAE ja medido no WIN em todo horizonte
  incondicional; se um lado ganha e o outro perde por muito mais que o
  custo, e' evidencia de tendencia real (reversao OU continuacao).

`cooldown_bars`: depois que uma posicao fecha (por alvo, stop ou flatten),
a estrategia espera este numero de barras FLAT antes de voltar a avaliar
um novo gatilho -- sem isso, um movimento largo e sustentado (tendencia
real) dispara sinal em quase toda barra subsequente (a janela desliza 1
barra por vez), reamostrando o MESMO evento dezenas de vezes em vez de
tratar cada excesso como uma observacao independente.

`stop_ticks`/`target_ticks`: distancias FIXAS em ticks a partir do preco de
FECHAMENTO da barra de decisao (mesmo padrao de `OpeningRangeBreakout`:
`initial_stop`/`initial_target` absolutos, calculados no momento da
decisao -- o preenchimento real na abertura seguinte paga
`slippage_ticks`, entao o R:R efetivo desliza um pouco frente ao nominal,
igual a qualquer entrada a mercado deste motor).

## Limitacao conhecida para operacao AO VIVO (nao resolvida nesta rodada)

Esta estrategia usa `Enter` (entrada a MERCADO). `IntradaySessionMachine.
on_closed_bar` recusa `Enter` com `NotImplementedError` quando
`self.execution` esta setado (execucao real) -- ver `backtest/intraday/
machine.py`: nenhum robo em operacao hoje manda ordem a mercado, so'
`EnterLimit`. Isto e' so' BACKTEST/pesquisa; colocar isto para operar ao
vivo exigiria ou (a) implementar o caminho de execucao real de `Enter` em
`live/intraday_execution.py` (fora do escopo desta frente, e fora da
fronteira que `strategy/` pode tocar), ou (b) reformular a entrada como
`EnterLimit` com TTL curto perseguindo o preco -- mudanca de desenho, nao
testada aqui."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from strategy.daytrade.base import (
    Bar,
    Enter,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
)

Mode = Literal["fade", "continuation"]


@dataclass
class _SessionState:
    closes: deque = field(default_factory=deque)
    in_position: bool = False
    cooldown_left: int = 0


class WinExtremeReversalF6(IntradayStrategy):
    """Reversao (ou continuacao, `mode="continuation"`, so' para contraste)
    apos um movimento de `threshold_ticks` medido em `k_bars` barras.
    Entrada a MERCADO (taker); alvo/stop fixos em ticks a partir do
    fechamento da barra de decisao."""

    name = "win_extreme_reversal_f6"
    version = "0.1"
    # Taker nas duas pernas de proposito -- ver a secao 2 da docstring do
    # modulo (e' o que distingue este desenho do grid-maker morto no WIN).
    target_fills_as_maker = False

    def __init__(
        self,
        symbol: str = "WIN@",
        tick_size: float = 5.0,
        k_bars: int = 10,
        threshold_ticks: float = 40.0,
        stop_ticks: float = 15.0,
        target_ticks: float = 15.0,
        cooldown_bars: int = 20,
        mode: Mode = "fade",
        quantity: int | None = None,
        session_stop_brl: float | None = None,
    ):
        if k_bars < 1:
            raise ValueError("k_bars precisa ser >= 1")
        if threshold_ticks <= 0:
            raise ValueError("threshold_ticks precisa ser > 0")
        if stop_ticks <= 0 or target_ticks <= 0:
            raise ValueError("stop_ticks/target_ticks precisam ser > 0")
        self.symbol = symbol
        self.tick_size = tick_size
        self.k_bars = int(k_bars)
        self.threshold_ticks = float(threshold_ticks)
        self.stop_ticks = float(stop_ticks)
        self.target_ticks = float(target_ticks)
        self.cooldown_bars = int(cooldown_bars)
        self.mode = mode
        self.quantity = quantity
        # Default desligado -- mesma decisao de `WdoGridReloadMaker`: uma
        # perda de sessao grande em escala de FUTURO nao deve achatar o
        # robo sem pedido explicito (`session_stop_brl` de acao, 30.0, foi
        # calibrado para outro instrumento inteiramente).
        self.session_stop_brl = abs(session_stop_brl) if session_stop_brl is not None else None

        self._state = _SessionState()

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()

    def _maxlen(self) -> int:
        return self.k_bars + 1

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        state = self._state
        state.closes.append(bar.close)
        maxlen = self._maxlen()
        while len(state.closes) > maxlen:
            state.closes.popleft()

        if positions:
            state.in_position = True
            return []

        # Flat agora. Nao ha' `Exit` aqui de proposito: com posicao aberta o
        # stop/alvo por trade ja protege; o freio de sessao so' IMPEDE um
        # novo gatilho (nunca interrompe uma posicao ja em curso por um
        # limiar que e' de OUTRA escala -- mesma filosofia de
        # `WdoGridReloadMaker.session_stop_brl`).
        just_closed = state.in_position
        state.in_position = False
        if just_closed:
            state.cooldown_left = self.cooldown_bars
        elif state.cooldown_left > 0:
            state.cooldown_left -= 1

        if self.session_stop_brl is not None and session_pnl_brl <= -self.session_stop_brl:
            return []

        if state.cooldown_left > 0:
            return []

        if len(state.closes) < maxlen:
            return []  # ainda aquecendo o lookback de k_bars

        burst_price = state.closes[-1] - state.closes[0]
        burst_ticks = burst_price / self.tick_size
        if abs(burst_ticks) < self.threshold_ticks:
            return []

        moved_up = burst_price > 0
        if self.mode == "fade":
            side: Literal["long", "short"] = "short" if moved_up else "long"
        else:
            side = "long" if moved_up else "short"

        entry_ref = bar.close
        stop_dist = self.stop_ticks * self.tick_size
        target_dist = self.target_ticks * self.tick_size
        if side == "long":
            stop = entry_ref - stop_dist
            target = entry_ref + target_dist
        else:
            stop = entry_ref + stop_dist
            target = entry_ref - target_dist

        return [Enter(
            side=side,
            initial_stop=stop,
            initial_target=target,
            quantity=self.quantity,
            metadata={"burst_ticks": burst_ticks, "k_bars": self.k_bars},
            reason=f"extreme_{self.mode}_{side}",
        )]
