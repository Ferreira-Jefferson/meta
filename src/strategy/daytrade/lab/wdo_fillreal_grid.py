"""Grid maker WDO com TATICAS DE COLOCACAO DE ORDEM instrumentadas para medir
preenchimento passivo (2026-08-26, Frente F3-wdo-fill-realismo).

Mesma mecanica de base de `grid_reload_maker.py` (nivel fixo por lado a partir
da abertura, recarrega apos cada fechamento, stop largo de protecao por
posicao) -- NAO reescreve a ideia, adiciona DUAS taticas de execucao que um
operador real poderia usar, cada uma LIGAVEL por parametro, para comparar o
efeito isolado de cada uma sobre P&L e taxa de preenchimento simulada:

1. `retreat_ticks` (recuo do nivel): a ordem-limite nao fica no nivel "ideal"
   (`level_spacing_ticks` da abertura) — recua mais `retreat_ticks` ticks na
   direcao PIOR para quem entra (compra mais barato, vende mais caro do que
   o nivel ideal). Duas consequencias mecanicas, nenhuma delas otimismo: (a)
   filtra toques RASOS (a barra so encostou no nivel ideal por um tick e
   voltou) e so preenche quando o preco de fato ATRAVESSOU o nivel ideal por
   `retreat_ticks` ticks extras -- perto do que significa "nao estar na
   frente da fila, estar mais fundo nela"; (b) quando preenche, o preco de
   entrada e' `retreat_ticks` ticks MELHOR que o nivel ideal, e o alvo (T1)
   e' recalculado 1 tick a partir do preco de entrada REAL, entao a geometria
   T1/S16 nunca muda de definicao, so' desloca com o nivel.
   `retreat_ticks=0` reproduz o comportamento antigo (nivel = ideal).

2. `split_entry` / `split_exit` (fatiar o tamanho, so tem efeito com
   `quantity > 1`): em vez de um pedido MONOLITICO do lote inteiro (que so
   preenche, no modelo FOK do motor, se `bar.volume` cobrir o lote inteiro de
   uma vez -- ver `IntradayBacktestConfig.limit_fill_capped_by_volume`),
   fatia o pedido em N filhos de 1 contrato (`EnterLimit.split_quantities`
   na entrada, `EnterLimit.exit_split_unit=1` na saida por alvo) -- cada
   filho preenche (ou nao) de forma independente, e cada filho preenchido
   vira uma `_Position` PROPRIA com seu proprio stop/alvo (ver a docstring de
   `IntradaySessionMachine.positions`).

Contadores de preenchimento (`orders_armed`, `contracts_requested`,
`contracts_filled` -- atributos da INSTANCIA, cumulativos no backtest
inteiro, nao resetados por sessao) existem para o script que roda o backtest
medir `contracts_filled / contracts_requested` sem precisar instrumentar o
motor -- a estrategia sabe exatamente quantos contratos pediu (a cada
`EnterLimit` emitida) e quantos de fato apareceram como posicao aberta (o
motor SO abre `_Position` quando um filho realmente preencheu -- uma ordem
parada nunca aparece em `positions`), entao a diferenca entre os dois e'
puro preenchimento perdido, sem nenhuma suposicao adicional.

ACHADO sobre a MECANICA do motor (2026-08-26, medido rodando `Intraday
SessionMachine` diretamente, ver `tests/test_wdo_fillreal_grid.py`): quando
QUALQUER posicao de um grupo fatiado fecha (alvo ou stop), o motor CANCELA
(orfaniza) todos os filhos IRMAOS que ainda estivessem parados sem preencher
(`IntradaySessionMachine._cancelar_resting_orfa`, evento `LimitCancelled`
com `reason="position_closed"`) -- eles NAO continuam esperando. Com o alvo
em 1 tick (T1), o PRIMEIRO filho preenchido costuma bater o alvo antes dos
irmaos terem chance de preencher, entao um ciclo fatiado raramente fecha com
os `quantity` contratos inteiros -- ele fecha com o que preencheu ATE ali, e
o resto e' cancelado. Isto NAO e' um bug desta estrategia: e' o
comportamento real do motor compartilhado, e o motivo de este arquivo NAO
exigir `cycle_filled == cycle_requested` para recarregar (so' exige
`cycle_filled > 0` -- ver `on_bar`). Efeito pratico: `split_entry` melhora a
CHANCE de preencher ALGUMA coisa do pedido (em vez de nada, no caso
monolitico que precisa do lote inteiro de uma vez), mas nao garante
preencher o pedido INTEIRO quando o alvo e' apertado -- os dois efeitos
tem que ser medidos separados (fill rate por CICLO vs por CONTRATO), o que o
relatorio da Frente F3 faz.

LIMITACAO que NENHUMA das duas taticas acima resolve, e que este arquivo NAO
finge resolver: a serie M1 salva nao tem flag de agressor real, entao
"preencheu no backtest" so significa "o preco tocou (ou atravessou, com
recuo) o nivel e havia volume >= o tamanho do filho na barra inteira" --
nunca "havia realmente uma ordem SUA na fila naquele momento, na posicao
certa, e o fluxo que vier depois foi contra ela (nao a favor)". Selecao
adversa (a ordem parada so preenche de graca quando o fluxo vem CONTRA ela)
e' inteiramente invisivel aqui. As duas taticas so mudam O QUANTO o modelo
disponivel no repo consegue ser conservador; nenhuma delas prova
preenchimento passivo LUCRATIVO. Ver o relatorio da Frente F3 para a medicao
completa.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

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
    open_price: float | None = None
    session_halted: bool = False
    armed: bool = False              # ha' uma EnterLimit (ou algum filho dela) pendente/parcialmente preenchida
    armed_side: str | None = None
    cycle_requested: int = 0         # quantos contratos o ciclo armado pediu
    cycle_baseline: int = 0          # valor de `contracts_filled` (global) no instante em que o ciclo armou
    long_attempts: int = 0
    short_attempts: int = 0
    last_closed_side: str | None = None


class WdoFillRealismGrid(IntradayStrategy):
    """Grid maker de 1 nivel por lado, recarregavel, com recuo de nivel e
    fatiamento de ordem OPCIONAIS -- ver docstring do modulo para o que cada
    tatica faz e por que existe.

    Nao e' o candidato oficial "T1 S16 x1" da familia (esse arquivo nao foi
    encontrado neste estado do repo -- pode ter sido produzido por uma
    sessao anterior e nunca commitado). E' a MESMA mecanica de
    `grid_reload_maker.py` (que ja serve WDO/WIN, parametrizada por
    `symbol`/`tick_size`), com os parametros de geometria fixados em T=1
    tick / S=16 ticks pelo chamador, para reproduzir o espirito do
    candidato estabelecido o mais fielmente possivel dado o que esta'
    disponivel."""

    name = "wdo_fillreal_grid"
    version = "0.1"
    target_fills_as_maker = True

    def __init__(
        self,
        symbol: str = "WDO@",
        tick_size: float = 0.5,
        level_spacing_ticks: int = 3,
        profit_ticks: int = 1,
        stop_ticks: int | None = 16,
        retreat_ticks: int = 0,
        quantity: int = 1,
        split_entry: bool = False,
        split_exit: bool = False,
        max_trades_per_side: int = 60,
        session_stop_brl: float = 500.0,
    ):
        self.symbol = symbol
        self.tick_size = tick_size
        self.level_spacing_ticks = level_spacing_ticks
        self.profit_ticks = profit_ticks
        self.stop_ticks = stop_ticks
        self.retreat_ticks = retreat_ticks
        self.quantity = max(1, int(quantity))
        self.split_entry = split_entry
        self.split_exit = split_exit
        self.max_trades_per_side = max_trades_per_side
        self.session_stop_brl = abs(session_stop_brl)

        # Contadores CUMULATIVOS do backtest inteiro (nao resetam por sessao
        # -- ver docstring do modulo). `orders_armed` conta CICLOS (uma
        # EnterLimit emitida, monolitica ou fatiada), nao filhos.
        self.orders_armed = 0
        self.contracts_requested = 0
        self.contracts_filled = 0
        # Chave (side, entry_ts, entry_price, quantity) -> quantas `_Position`
        # com essa chave ja foram CONTADAS em `contracts_filled`. NUNCA
        # resetado por sessao (entry_ts inclui a data, chaves de dias
        # diferentes nunca colidem) -- ver `_registrar_preenchimentos`.
        self._fills_vistos: dict[tuple, int] = {}

        self._state = _SessionState()

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()

    # ---------- geometria ---------------------------------------------

    def _level_price(self, side: str) -> float:
        offset = self.level_spacing_ticks * self.tick_size
        base = self._state.open_price
        return round(base - offset, 2) if side == "long" else round(base + offset, 2)

    def _entry_price(self, level_price: float, side: str) -> float:
        """Preco de fato colocado na EnterLimit -- o nivel "ideal" recuado
        `retreat_ticks` ticks na direcao PIOR para quem entra (ver docstring
        do modulo, tatica 1)."""
        if not self.retreat_ticks:
            return level_price
        offset = self.retreat_ticks * self.tick_size
        return round(level_price - offset, 2) if side == "long" else round(level_price + offset, 2)

    def _target_price(self, entry_price: float, side: str) -> float:
        offset = self.profit_ticks * self.tick_size
        return round(entry_price + offset, 2) if side == "long" else round(entry_price - offset, 2)

    def _stop_price(self, entry_price: float, side: str) -> float | None:
        if self.stop_ticks is None:
            return None
        offset = self.stop_ticks * self.tick_size
        return round(entry_price - offset, 2) if side == "long" else round(entry_price + offset, 2)

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
        """Soma a `self.contracts_filled` os preenchimentos NOVOS desde a
        ultima chamada, contados por CHAVE `(side, entry_ts, entry_price,
        quantity)` -- nao por delta agregado de `sum(p.quantity)`.

        Por que nao delta agregado: dentro de UMA MESMA barra o motor
        primeiro fecha posicoes existentes (passo 1 de `on_closed_bar`, alvo/
        stop) e SO' DEPOIS resolve novos preenchimentos da ordem-limite
        pendente (passo 3b) -- com o alvo em 1 tick (T1), fechar-e-preencher
        na MESMA barra e' comum, nao excecao rara. Um delta agregado
        (`sum(qty_agora) - sum(qty_antes)`) mede o LIQUIDO da barra e
        SUBESTIMA preenchimento sempre que um fechamento e um preenchimento
        novo se cancelam parcialmente no total. Contar por chave individual
        evita isso: cada chave so' pode CRESCER (nunca decresce quando a
        posicao fecha e desaparece de `positions`), entao um fechamento
        nunca desconta um preenchimento ja' registrado."""
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
            state.open_price = bar.open

        if not state.session_halted and session_pnl_brl <= -self.session_stop_brl:
            state.session_halted = True
            if positions:
                actions.append(Exit(reason="stop_agregado_sessao"))
            return actions

        if state.session_halted:
            return actions

        self._registrar_preenchimentos(positions)

        if positions:
            # Alvo/stop de cada posicao ja' foram definidos no `initial_
            # target`/`initial_stop` da propria EnterLimit -- o motor fecha
            # sozinho, nada a decidir aqui.
            return []

        if state.armed:
            cycle_filled = self.contracts_filled - state.cycle_baseline
            if cycle_filled > 0:
                # Pelo menos 1 filho deste ciclo preencheu -- e como
                # `positions` esta vazia AGORA, ele (e qualquer irmao que
                # tenha preenchido junto) ja FECHOU. O motor cancela
                # (orfaniza) qualquer filho do MESMO grupo que ainda
                # estivesse parado no instante desse fechamento (ver
                # `IntradaySessionMachine._cancelar_resting_orfa`,
                # `reason="position_closed"` no evento `LimitCancelled`) --
                # entao "algo preencheu e fechou" implica CICLO ENCERRADO,
                # preenchido por completo ou nao. Nao esperamos
                # `cycle_filled == cycle_requested`: com o alvo em 1 tick, o
                # 1o filho costuma fechar ANTES dos irmaos preencherem, e a
                # fatia restante e' cancelada, nao preenchida -- ver a
                # docstring do modulo (achado sobre `split_entry` interagir
                # mal com alvo apertado).
                state.last_closed_side = state.armed_side
                state.armed = False
                state.armed_side = None
            else:
                # Nada deste ciclo preencheu ainda -- a ordem-limite (ou
                # todos os seus filhos) continua PARADA no motor, vigiada
                # sozinha; nao substituir por uma nova em cima dela.
                return actions

        next_side = self._next_side_to_arm()
        if next_side is None:
            return actions

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
            reason=f"wdo_fillreal_{next_side}_retreat{self.retreat_ticks}",
        )]

    # ---------- leitura pos-backtest -------------------------------------

    @property
    def fill_rate_pct(self) -> float | None:
        """`contracts_filled / contracts_requested`, em %. `None` se nenhuma
        ordem foi armada (backtest vazio)."""
        if self.contracts_requested <= 0:
            return None
        return 100.0 * self.contracts_filled / self.contracts_requested
