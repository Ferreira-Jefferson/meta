"""Grid maker WDO com TATICAS DE COLOCACAO DE ORDEM instrumentadas, RODADA 2
da Frente F3-wdo-fill-realismo (2026-08-27).

Por que este arquivo existe (nao editar `wdo_fillreal_grid.py`, criar outro):
o critico da rodada 1 apontou um problema de BASE -- `WdoFillRealismGrid`
usava `level_spacing_ticks=3` como o valor "headline" da varredura, mas o
candidato consolidado desta frente se CHAMA "T1 S16 x1"
(`level_spacing_ticks=1`, ver `wdo_grid_reload_maker.py` linha ~148 e
`scripts/daytrade/wdo_grid_reload_f1_lab.py::CANDIDATO_PARAMS`). Alem disso
`WdoFillRealismGrid` ancora o grid no preco de ABERTURA da sessao, fixo o
pregao inteiro (`state.open_price = bar.open`, nunca reatualizado) -- essa e'
exatamente a mecanica "fixed_session_open" que a Frente F1 ja MEDIU como
sendo a PIOR das duas leituras testadas (liquido mais negativo, ver
`WdoGridReloadMaker.ReanchorMode`). A leitura "rolling_last_price" (ancora
no FECHAMENTO da barra em que cada nova ordem arma) e' a leitura MENOS ruim
encontrada pela Frente F1 -- ainda assim NAO reproduz o ballpark conhecido
(+R$37.606,53), so' chega mais perto.

Este arquivo faz DUAS correcoes sobre `WdoFillRealismGrid`, mantendo as
MESMAS duas taticas instrumentadas (recuo de nivel, fatiamento) e os MESMOS
contadores de preenchimento:

1. `level_spacing_ticks` default passa de 3 para 1 -- a geometria REAL do
   candidato "T1 S16 x1".
2. Adiciona `reanchor_mode` (`"fixed_session_open"` | `"rolling_last_price"`,
   MESMO Literal de `wdo_grid_reload_maker.ReanchorMode`, reescrito aqui por
   proposito -- REGRA desta rodada: nenhuma frente importa arquivo de outra
   frente rodando em paralelo no mesmo diretorio de trabalho, mesmo
   justificativa que `wdo_grid_reload_maker.py` ja documenta para nao
   importar `GridReloadMaker` de acao). Default `"rolling_last_price"` --
   a leitura menos ruim encontrada pela Frente F1, NAO uma leitura
   validada como a mecanica original (ver o achado da checagem de
   sanidade REPETIDA nesta rodada, secao 1 do relatorio da Frente F3).
   Tambem passa a alinhar `open_price`/ancora a grade de tick via `no_tick`
   (`WdoFillRealismGrid` nao alinhava -- so' `round(..., 2)` nos niveis
   derivados, que NAO forca multiplo de `tick_size`; aqui, igual a
   `WdoGridReloadMaker`, a ancora e' alinhada uma vez e todo offset
   subsequente e' multiplo exato de `tick_size`, entao permanece alinhado
   sem precisar de `no_tick` de novo em cada nivel).

Resultado da checagem de sanidade desta rodada (rodando
`scripts/daytrade/wdo_grid_reload_f1_lab.py`, que ja' testava exatamente
esta geometria x1 nas duas ancoras, ANTES deste arquivo existir): NENHUMA
das tres leituras (rolling+capped, rolling+slippage0, fixed) chega perto do
ballpark com x1 -- desvios de -104%, -97% e -130%. Ou seja, o problema de
base da rodada 1 NAO era so' o spacing=3: com spacing=1 (x1 real) o
resultado continua muito longe do numero conhecido, em QUALQUER ancora. Ver
o relatorio da Frente F3 rodada 2 para a leitura completa; este arquivo
existe para medir o efeito das DUAS taticas de preenchimento SOBRE a leitura
MENOS ruim (x1, rolling, slippage nominal) em vez de sobre x3 -- ainda
assim uma medicao "efeito da tatica sobre uma base fraca", nao uma
validacao do candidato original.

Documentacao completa das duas taticas, dos contadores de preenchimento e
da limitacao de selecao adversa (serie sem flag de agressor real): ver a
docstring de `wdo_fillreal_grid.py` (identica aqui, nao repetida)."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from strategy.daytrade.base import (
    Bar,
    EnterLimit,
    Exit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
    no_tick,
)

#: Mesmo Literal de `wdo_grid_reload_maker.ReanchorMode` -- reescrito aqui
#: (nao importado) pela regra de nao-cruzar-frente desta rodada.
ReanchorMode = Literal["fixed_session_open", "rolling_last_price"]


@dataclass
class _SessionState:
    open_price: float | None = None
    anchor_price: float | None = None  # referencia ATUAL do nivel -- ver `ReanchorMode`
    session_halted: bool = False
    armed: bool = False
    armed_side: str | None = None
    cycle_requested: int = 0
    cycle_baseline: int = 0
    long_attempts: int = 0
    short_attempts: int = 0
    last_closed_side: str | None = None


class WdoFillRealismGridX1(IntradayStrategy):
    """`WdoFillRealismGrid` com geometria x1 (a real do candidato "T1 S16
    x1") e `reanchor_mode` explicito -- ver docstring do modulo para o
    porque deste arquivo separado."""

    name = "wdo_fillreal_grid_x1"
    version = "0.1"
    target_fills_as_maker = True

    def __init__(
        self,
        symbol: str = "WDO@",
        tick_size: float = 0.5,
        level_spacing_ticks: int = 1,   # "x1" -- geometria REAL do candidato (rodada 1 usava 3)
        profit_ticks: int = 1,          # "T1"
        stop_ticks: int | None = 16,    # "S16"
        reanchor_mode: ReanchorMode = "rolling_last_price",
        retreat_ticks: int = 0,
        quantity: int = 1,
        split_entry: bool = False,
        split_exit: bool = False,
        max_trades_per_side: int = 200,  # rolling reancora com muita frequencia, ver wdo_grid_reload_maker.py
        session_stop_brl: float | None = None,  # sem teto de sessao por default -- mesmo motivo do candidato F1
    ):
        self.symbol = symbol
        self.tick_size = tick_size
        self.level_spacing_ticks = level_spacing_ticks
        self.profit_ticks = profit_ticks
        self.stop_ticks = stop_ticks
        self.reanchor_mode = reanchor_mode
        self.retreat_ticks = retreat_ticks
        self.quantity = max(1, int(quantity))
        self.split_entry = split_entry
        self.split_exit = split_exit
        self.max_trades_per_side = max_trades_per_side
        self.session_stop_brl = None if session_stop_brl is None else abs(session_stop_brl)

        self.orders_armed = 0
        self.contracts_requested = 0
        self.contracts_filled = 0
        self._fills_vistos: dict[tuple, int] = {}

        self._state = _SessionState()

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()

    # ---------- geometria ---------------------------------------------

    def _level_price(self, side: str) -> float:
        offset = self.level_spacing_ticks * self.tick_size
        anchor = self._state.anchor_price
        return (anchor - offset) if side == "long" else (anchor + offset)

    def _entry_price(self, level_price: float, side: str) -> float:
        if not self.retreat_ticks:
            return level_price
        offset = self.retreat_ticks * self.tick_size
        return (level_price - offset) if side == "long" else (level_price + offset)

    def _target_price(self, entry_price: float, side: str) -> float:
        offset = self.profit_ticks * self.tick_size
        return entry_price + offset if side == "long" else entry_price - offset

    def _stop_price(self, entry_price: float, side: str) -> float | None:
        if self.stop_ticks is None:
            return None
        offset = self.stop_ticks * self.tick_size
        return entry_price - offset if side == "long" else entry_price + offset

    # ---------- cadencia de recarga -------------------------------------

    def _attempts_of(self, side: str) -> int:
        return self._state.long_attempts if side == "long" else self._state.short_attempts

    def _next_side_to_arm(self) -> str | None:
        candidates = ["long", "short"]
        if self._state.last_closed_side in candidates:
            candidates.remove(self._state.last_closed_side)
            candidates.append(self._state.last_closed_side)
        for side in candidates:
            if self._attempts_of(side) < self.max_trades_per_side:
                return side
        return None

    # ---------- contagem de preenchimento --------------------------------

    def _registrar_preenchimentos(self, positions: list[IntradayOpenPosition]) -> None:
        """Identica a `WdoFillRealismGrid._registrar_preenchimentos` -- conta
        por CHAVE `(side, entry_ts, entry_price, quantity)`, nunca por delta
        agregado (ver a docstring de `wdo_fillreal_grid.py` para o porque)."""
        contagem_agora = Counter(
            (p.side, p.entry_ts, round(p.entry_price, 4), p.quantity) for p in positions
        )
        novos_contratos = 0
        for chave, contagem in contagem_agora.items():
            visto = self._fills_vistos.get(chave, 0)
            if contagem > visto:
                novos_contratos += (contagem - visto) * chave[3]
                self._fills_vistos[chave] = contagem
        self.contracts_filled += novos_contratos

    # ---------- laco principal ------------------------------------------

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        state = self._state
        actions: list[IntradayAction] = []

        if state.open_price is None:
            state.open_price = no_tick(bar.open, self.tick_size)
            state.anchor_price = state.open_price

        if (self.session_stop_brl is not None and not state.session_halted
                and session_pnl_brl <= -self.session_stop_brl):
            state.session_halted = True
            if positions:
                actions.append(Exit(reason="stop_agregado_sessao"))
            return actions

        if state.session_halted:
            return actions

        self._registrar_preenchimentos(positions)

        if positions:
            return []

        if state.armed:
            cycle_filled = self.contracts_filled - state.cycle_baseline
            if cycle_filled > 0:
                state.last_closed_side = state.armed_side
                state.armed = False
                state.armed_side = None
            else:
                return actions

        next_side = self._next_side_to_arm()
        if next_side is None:
            return actions

        if self.reanchor_mode == "rolling_last_price":
            # Segue o preco -- ancora vira o FECHAMENTO da barra que acabou
            # de fechar, so' no instante de armar uma ordem NOVA (mesmo
            # ponto de `WdoGridReloadMaker.on_bar`, sem look-ahead: a ordem
            # so' executa em barra futura).
            state.anchor_price = no_tick(bar.close, self.tick_size)
        # "fixed_session_open": `state.anchor_price` ja' e' `state.open_price`
        # desde a primeira barra e nunca muda.

        level_price = self._level_price(next_side)
        entry_price = self._entry_price(level_price, next_side)
        target = self._target_price(entry_price, next_side)
        stop = self._stop_price(entry_price, next_side)

        quantity = self.quantity
        split_quantities = tuple([1] * quantity) if (self.split_entry and quantity > 1) else None
        exit_split_unit = 1 if (self.split_exit and quantity > 1) else None

        state.armed = True
        state.armed_side = next_side
        state.cycle_requested = quantity
        state.cycle_baseline = self.contracts_filled
        if next_side == "long":
            state.long_attempts += 1
        else:
            state.short_attempts += 1
        self.orders_armed += 1
        self.contracts_requested += quantity

        return [EnterLimit(
            side=next_side,
            limit_price=entry_price,
            initial_target=target,
            initial_stop=stop,
            quantity=quantity,
            split_quantities=split_quantities,
            exit_split_unit=exit_split_unit,
            reason=f"wdo_fillreal_x1_{next_side}_retreat{self.retreat_ticks}",
        )]

    # ---------- leitura pos-backtest -------------------------------------

    @property
    def fill_rate_pct(self) -> float | None:
        if self.contracts_requested <= 0:
            return None
        return 100.0 * self.contracts_filled / self.contracts_requested
