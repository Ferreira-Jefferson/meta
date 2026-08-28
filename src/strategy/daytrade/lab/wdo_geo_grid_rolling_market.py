"""Variante TAKER (entrada a MERCADO) do grid rolante `WdoGeoGridRolling`
(2026-08-27, Frente F4-wdo-geometria-sessao, RODADA 2, angulo alternativo
sugerido pelo critico da rodada 1 para o caso de o bloco A nao achar
sobrevivente a pedagio) -- mesma geometria de nivel/alvo/stop/reancoragem,
mas troca a ordem-limite (`EnterLimit`, maker, preenche SEM slippage no
toque exato do nivel) por uma entrada `Enter` a MERCADO (paga
`slippage_ticks` na abertura da PROXIMA barra, mesma disciplina
anti-look-ahead do resto do motor) no instante em que o nivel SERIA tocado.

## Por que este arquivo existe

Bloco (A) da rodada 2 mediu 1 tick de pedagio de fila na grade INTEIRA (nao
so' no top-15-por-pnl-bruto -- ver `scripts/daytrade/wdo_geo_pedagio_largo.
py`). Se nenhuma celula (nem espacamento largo, 8-32 ticks, que em teoria
depende menos de "ganhar a fila num unico tick") sobrevive, a pergunta que
sobra e' a do proprio critico: o "edge" medido em `WdoGeoGridRolling` e'
CAPTURA DE SPREAD/REBATE DE MAKER (a diferenca entre o toque do nivel e o
preenchimento exato -- que e' precisamente o que 1 tick de pedagio de fila
elimina) ou existe uma CONTINUIDADE DIRECIONAL real depois do toque (o
preco, apos tocar o nivel, tende para o lado do alvo mais do que o acaso)?
Um edge de continuidade sobreviveria a pagar o spread via entrada a
mercado -- so' fica mais caro, nao deixa de existir. Um edge que e' so'
spread/rebate MORRE nos dois testes (pedagio de fila E entrada a mercado)
pela MESMA razao.

## Mecanica (identica a `WdoGeoGridRolling` ate' o ponto do toque)

- mesma ancora ROLANTE (`bar.close` no armamento), mesma reancoragem por
  estagnacao (`rolling_reanchor_after_bars`) -- e com a MESMA cadencia
  "checa estagnacao ANTES de incrementar o contador" que `WdoGeoGridRolling`
  usa. A rodada 2, bloco B (`scripts/daytrade/wdo_geo_diff_reancoragem.py`)
  encontrou que essa cadencia espera 1 barra a MAIS do que o texto "reancora
  apos N barras paradas" sugere (confirmado lendo o motor E medido em 5
  pregoes reais: `WdoGridReloadReancoragem`, que le' o MESMO parametro
  nominal de forma mais literal, reancora por estagnacao 2,3x-3,4x mais
  vezes). Essa cadencia e' PRESERVADA aqui de proposito, SEM corrigir --
  o objetivo deste arquivo e' isolar SO' a variavel maker-vs-taker; trocar a
  cadencia ao mesmo tempo misturaria duas mudancas numa unica medicao.
- mesmo alvo/stop, calculados a partir do NIVEL (preco planejado da ordem,
  nao do preco de entrada real -- que so' se sabe DEPOIS do fill a
  mercado, e mudar o alvo/stop em funcao dele mudaria a geometria testada).
- DIFERENCA: em vez de devolver `EnterLimit` no instante do armamento (e
  deixar o motor decidir o preenchimento barra a barra, sem slippage,
  vigiando indefinidamente), este robo GUARDA o nivel internamente e so'
  devolve `Enter` (a mercado) na barra FECHADA em que `bar.low <= nivel`
  (compra) / `bar.high >= nivel` (venda) -- ou seja, exatamente o instante
  em que a ordem-limite equivalente TERIA sido tocada. O motor executa esse
  `Enter` na abertura da PROXIMA barra (`strategy.daytrade.base.Enter`),
  pagando `slippage_ticks` do modelo de custo padrao -- diferenca de
  proposito clara frente ao preenchimento maker.
- alvo continua ordem-limite (`target_fills_as_maker=True` na classe --
  builder de config externo decide o valor real usado, ver `scripts/
  daytrade/wdo_geo_sweep.py::_base_config`): so' a PERNA DE ENTRADA muda de
  maker para taker, a de SAIDA por alvo continua exatamente como antes --
  isola a variavel certa (entrada), nao mistura com uma segunda mudanca.
  O stop sempre foi a mercado nas duas variantes (protecao/urgencia).
- SEM `n_levels`/rodizio (a rodada 1, Achado 4, ja mostrou que rodizio so'
  dilui o mesmo edge -- nao vale repetir essa dimensao numa variante nova).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from strategy.daytrade.base import (
    Bar,
    Enter,
    Exit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
)


@dataclass
class _SessionState:
    session_halted: bool = False
    pending_side: str | None = None
    pending_level_price: float | None = None
    pending_target: float | None = None
    pending_stop: float | None = None
    pending_bars_waited: int = 0
    open_side: str | None = None
    long_fills: int = 0
    short_fills: int = 0
    last_closed_side: str | None = None


class WdoGeoGridRollingMarket(IntradayStrategy):
    """`WdoGeoGridRolling` com a perna de ENTRADA trocada de maker
    (`EnterLimit`, preenche sem slippage no toque exato) para taker
    (`Enter` a mercado, dispara quando o nivel SERIA tocado, paga
    slippage na abertura da barra seguinte). Ver a docstring do modulo."""

    name = "wdo_geo_grid_rolling_market"
    version = "0.1"
    target_fills_as_maker = True  # so' a SAIDA por alvo continua maker

    def __init__(
        self,
        symbol: str = "WDO@",
        tick_size: float = 0.5,
        level_spacing_ticks: int = 16,
        profit_ticks: int = 1,
        stop_ticks: int | None = 16,
        rolling_reanchor_after_bars: int = 5,
        max_trades_per_side: int = 999,
        session_stop_brl: float | None = None,
        quantity: int | None = None,
    ):
        self.symbol = symbol
        self.tick_size = tick_size
        self.level_spacing_ticks = level_spacing_ticks
        self.profit_ticks = profit_ticks
        self.stop_ticks = stop_ticks
        self.rolling_reanchor_after_bars = rolling_reanchor_after_bars
        self.max_trades_per_side = max_trades_per_side
        self.session_stop_brl = None if session_stop_brl is None else abs(session_stop_brl)
        self.quantity = quantity

        self._state = _SessionState()

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()

    def _levels(self, side: str, anchor: float) -> tuple[float, float, float | None]:
        spacing_off = self.level_spacing_ticks * self.tick_size
        level_price = anchor - spacing_off if side == "long" else anchor + spacing_off
        profit_off = self.profit_ticks * self.tick_size
        target_price = level_price + profit_off if side == "long" else level_price - profit_off
        stop_price = None
        if self.stop_ticks is not None:
            stop_off = self.stop_ticks * self.tick_size
            stop_price = level_price - stop_off if side == "long" else level_price + stop_off
        return level_price, target_price, stop_price

    def _fills_of(self, side: str) -> int:
        return self._state.long_fills if side == "long" else self._state.short_fills

    def _next_side_to_arm(self) -> str | None:
        candidates = ["long", "short"]
        if self._state.last_closed_side in candidates:
            candidates.remove(self._state.last_closed_side)
            candidates.append(self._state.last_closed_side)
        for side in candidates:
            if self._fills_of(side) < self.max_trades_per_side:
                return side
        return None

    def _tocou(self, side: str, bar: Bar) -> bool:
        nivel = self._state.pending_level_price
        if nivel is None:
            return False
        return bar.low <= nivel if side == "long" else bar.high >= nivel

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        state = self._state
        actions: list[IntradayAction] = []

        if (
            self.session_stop_brl is not None
            and not state.session_halted
            and session_pnl_brl <= -self.session_stop_brl
        ):
            state.session_halted = True
            if positions:
                actions.append(Exit(reason="stop_agregado_sessao"))
            return actions

        if state.session_halted:
            return actions

        if positions:
            # confirma o fill da `Enter` a mercado disparada quando o nivel
            # tocou (executada na abertura desta barra pelo motor).
            if state.pending_side is not None:
                if state.pending_side == "long":
                    state.long_fills += 1
                else:
                    state.short_fills += 1
                state.open_side = state.pending_side
                state.pending_side = None
                state.pending_level_price = None
                state.pending_bars_waited = 0
            return []

        if state.open_side is not None:
            state.last_closed_side = state.open_side
            state.open_side = None

        if state.pending_side is not None:
            if self._tocou(state.pending_side, bar):
                # toque NESTA barra fechada -- dispara entrada A MERCADO,
                # que o motor executa na abertura da PROXIMA barra (paga
                # slippage). Mesma disciplina anti-look-ahead das outras
                # estrategias: decide no fechamento, executa na abertura
                # seguinte -- nunca na propria barra que gerou o toque.
                return [Enter(
                    side=state.pending_side,
                    initial_target=state.pending_target,
                    initial_stop=state.pending_stop,
                    quantity=self.quantity,
                    reason="wdo_geo_grid_rolling_market_" + state.pending_side,
                )]
            stale = state.pending_bars_waited >= self.rolling_reanchor_after_bars
            if not stale:
                state.pending_bars_waited += 1
                return actions
            # reancora: MESMA distancia, novo preco de ancora (`bar.close`
            # atual) -- so' atualiza o nivel guardado, nao existe ordem no
            # motor para cancelar/substituir (a diferenca central desta
            # variante: o "nivel" e' so' contabilidade interna do robo ate'
            # o toque acontecer).
            level_price, target_price, stop_price = self._levels(state.pending_side, bar.close)
            state.pending_level_price = level_price
            state.pending_target = target_price
            state.pending_stop = stop_price
            state.pending_bars_waited = 0
            return actions

        next_side = self._next_side_to_arm()
        if next_side is None:
            return actions

        level_price, target_price, stop_price = self._levels(next_side, bar.close)
        state.pending_side = next_side
        state.pending_level_price = level_price
        state.pending_target = target_price
        state.pending_stop = stop_price
        state.pending_bars_waited = 0
        return actions
