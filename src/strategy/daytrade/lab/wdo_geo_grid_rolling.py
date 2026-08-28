"""Grid maker ROLANTE para FUTURO (2026-08-26, Frente F4-wdo-geometria-sessao)
-- adapta a mecanica de REANCORAGEM da familia `gremah` (ver
`strategy.daytrade.lab.gremah.Gremah.on_bar`, fase rolante:
`anchor = bar.close`, rearma quando a ordem parada espera
`rolling_reanchor_after_bars` sem tocar) para o tick de PONTOS do futuro,
SEM a fase fixa-na-abertura nem o dimensionamento por caixa/lote (que sao
mecanismo de ACAO -- aqui e' 1 contrato por vez, capital nao dimensiona
nada, ver `strategy.daytrade.base.capital_minimo_brl`/`LOTE_PADRAO_B3`).

Por que este arquivo existe ALEM de `wdo_geo_grid_reload.py`: aquele
reproduz `GridReloadMaker` (nivel FIXO na abertura da sessao, nunca se
move); este reproduz o outro polo da familia gremah, o que o repo ja
mediu como SUPERIOR em acoes (`Âncora fixa da gremah REFUTADA`,
2026-08-26: sempre-rolante bate os 14:00 de producao em 8/9 simbolos). A
missao desta frente pede para "confirmar/quantificar por que T=1 venceu"
sobre a grade ja mapeada -- sem saber qual dos dois polos (fixo ou
rolante) produziu o numero-base de +R$37.606,53 citado na missao (o script
que gerou aquele numero nao esta neste repositorio -- procurado e nao
encontrado, ver o relatorio da rodada), medir os DOIS e' o jeito honesto
de nao estreitar a busca por engano (ver `feedback_sem_antolhos` na
memoria do dono: "se alguem ja alcancou, distancia grande = busca
estreita, nao teto do mercado").

Mecanica:
- `anchor = bar.close` no instante em que o robo arma UMA nova ordem
  (nunca a barra que a preencheu -- mesma disciplina anti-look-ahead).
- a ordem pendente e' REARMADA (nao so' esperada) quando ficar
  `rolling_reanchor_after_bars` barras sem preencher: o preco de ancora
  antigo fica velho, um novo `EnterLimit` no preco ATUAL substitui.
  `IntradaySessionMachine._reancoragem_no_mesmo_nivel` (diff nao
  commitado, ver AGENTS.md desta rodada) preserva a fila quando o novo
  nivel calcula EXATAMENTE o mesmo preco do antigo -- este arquivo nao
  precisa saber disso, e' transparente na camada do motor.
- alvo e' `initial_target` (maker, `target_fills_as_maker=True`); stop e'
  `initial_stop` (protecao a mercado, paga slippage).
- alterna o lado a cada novo armamento (mesmo anti-vies de tendencia do
  `GridReloadMaker`/`Gremah`).
- `session_stop_brl=None` por padrao -- mesma razao de
  `wdo_geo_grid_reload.py`: medir geometria pura, sem overlay de risco
  agregado confundindo o numero.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar,
    EnterLimit,
    Exit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
)


@dataclass
class _SessionState:
    session_halted: bool = False
    pending_side: str | None = None
    pending_bars_waited: int = 0
    open_side: str | None = None
    long_fills: int = 0
    short_fills: int = 0
    last_closed_side: str | None = None
    next_level_idx: dict = field(default_factory=lambda: {"long": 0, "short": 0})
    pending_level_idx: int | None = None


class WdoGeoGridRolling(IntradayStrategy):
    """Grid maker com ancora ROLANTE (`bar.close` no instante do armamento,
    rearmado apos `rolling_reanchor_after_bars` sem tocar) -- o polo
    "sempre-rolante" da familia gremah, adaptado a tick de pontos e 1
    contrato por vez.

    `n_levels` (2026-08-26, mesma ideia de `wdo_geo_grid_reload.
    WdoGeoGridReload`): distancias em RODIZIO por lado, a cada novo
    armamento (nao a cada `rolling_reanchor_after_bars` -- reanchor troca
    o PRECO de ancora, `n_levels` troca a DISTANCIA da ancora). `n_levels=1`
    (default) preserva o comportamento antigo, uma distancia so'. Mesma
    ressalva estrutural do irmao fixo-na-abertura: `IntradaySessionMachine`
    so' guarda UMA ordem-limite pendente por vez, entao isto e' rodizio de
    distancia, nao niveis simultaneos de verdade -- ver a nota no topo do
    modulo."""

    name = "wdo_geo_grid_rolling"
    version = "0.1"
    target_fills_as_maker = True

    def __init__(
        self,
        symbol: str = "WDO@",
        tick_size: float = 0.5,
        level_spacing_ticks: int = 16,
        profit_ticks: int = 1,
        stop_ticks: int | None = 16,
        rolling_reanchor_after_bars: int = 5,
        n_levels: int = 1,
        max_trades_per_side: int = 999,
        session_stop_brl: float | None = None,
        quantity: int | None = None,
    ):
        if n_levels < 1:
            raise ValueError("n_levels precisa ser >= 1")
        self.symbol = symbol
        self.tick_size = tick_size
        self.level_spacing_ticks = level_spacing_ticks
        self.profit_ticks = profit_ticks
        self.stop_ticks = stop_ticks
        self.rolling_reanchor_after_bars = rolling_reanchor_after_bars
        self.n_levels = n_levels
        self.max_trades_per_side = max_trades_per_side
        self.session_stop_brl = None if session_stop_brl is None else abs(session_stop_brl)
        self.quantity = quantity

        self._state = _SessionState()

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()

    def _build_entry(self, side: str, anchor: float, level_idx: int = 0) -> EnterLimit:
        spacing_off = (level_idx + 1) * self.level_spacing_ticks * self.tick_size
        level_price = anchor - spacing_off if side == "long" else anchor + spacing_off
        profit_off = self.profit_ticks * self.tick_size
        target_price = level_price + profit_off if side == "long" else level_price - profit_off
        stop_price = None
        if self.stop_ticks is not None:
            stop_off = self.stop_ticks * self.tick_size
            stop_price = level_price - stop_off if side == "long" else level_price + stop_off
        return EnterLimit(
            side=side,
            limit_price=level_price,
            initial_target=target_price,
            initial_stop=stop_price,
            quantity=self.quantity,
            reason="wdo_geo_grid_rolling_" + side,
        )

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
            if state.pending_side is not None:
                if state.pending_side == "long":
                    state.long_fills += 1
                else:
                    state.short_fills += 1
                state.open_side = state.pending_side
                state.pending_side = None
                state.pending_bars_waited = 0
                state.pending_level_idx = None
            return []

        if state.open_side is not None:
            state.last_closed_side = state.open_side
            state.open_side = None

        stale_order = (
            state.pending_side is not None
            and state.pending_bars_waited >= self.rolling_reanchor_after_bars
        )
        if state.pending_side is not None and not stale_order:
            state.pending_bars_waited += 1
            return actions

        next_side = state.pending_side if stale_order else self._next_side_to_arm()
        if next_side is None:
            return actions

        # Rearme por ESTAGNACAO (`stale_order`) mantem a MESMA distancia --
        # so' o preco de ancora atualiza para o `bar.close` atual. Uma
        # armacao NOVA (lado que acabou de ficar livre) e' que avanca o
        # rodizio para a proxima distancia -- reancorar nao e' "tentar de
        # novo do zero", e' "o preco de referencia envelheceu".
        level_idx = state.pending_level_idx if stale_order else state.next_level_idx[next_side]
        if not stale_order:
            state.next_level_idx[next_side] = (level_idx + 1) % self.n_levels

        state.pending_side = next_side
        state.pending_bars_waited = 0
        state.pending_level_idx = level_idx
        return [self._build_entry(next_side, bar.close, level_idx)]
