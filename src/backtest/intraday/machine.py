"""Maquina de estados de UMA sessao intradiaria — o corpo "por barra" que
antes vivia dentro do laco de `run_intraday_backtest`.

Existe por um motivo de OPERACAO, nao de estetica: a partir de 2026-08-21 a
mesma logica precisa rodar em dois lugares (backtest e operacao ao vivo, ver
`live/intraday_runtime.py`). Reescrever a maquina dentro de `live/`
garantiria divergencia silenciosa — o robo validado no backtest deixaria de
ser o robo que opera, e ninguem descobriria por um extrato. Extrair para uma
classe unica torna essa divergencia impossivel por construcao: quem executa
ao vivo alimenta `on_closed_bar` com a barra M1 que o MT5 acabou de fechar,
e o backtest alimenta com a barra do parquet — o resto e' identico.

O contrato e' deliberadamente "empurra barra fechada, recebe eventos":

    machine.begin_session(session_date)       # ou resume_session(...)
    for bar in barras_fechadas:
        for evento in machine.on_closed_bar(bar, is_last_bar=...):
            ...  # backtest: acumula trade; ao vivo: journaliza / manda ordem

`begin_session` chama `IntradayStrategy.on_session_start`; `resume_session`
NAO chama (ver `strategy/daytrade/base.py::warm_start_calibration` — o robo
ja foi calibrado por fora e chamar de novo apagaria a calibracao).

Prioridades (as MESMAS de antes, e as mesmas do motor diario):
  (1) stop/target automatico vence qualquer acao filada pelo robo;
  (2) flatten forcado no fim da sessao vence tudo — nenhuma estrategia pode
      escolher carregar posicao overnight;
  (3) acao filada executa na ABERTURA da barra seguinte a decisao, nunca na
      barra que a gerou (anti-look-ahead, regra 4 do AGENTS.md).

Este arquivo NAO conhece pandas.DataFrame, sessao nem broker: so barras. Quem
agrupa barras em sessoes e' o driver (`engine.py` no backtest,
`live/intraday_runtime.py` ao vivo). A unica excecao e' o CORTE DE FLATTEN,
que consulta o calendario (`core.b3_session`) quando
`session_end_policy="b3_equities"` — o fim do pregao a vista da B3 anda 1h com
o horario de verao dos EUA, e um numero fixo aqui faria o robo achatar 1h
antes do fechamento durante ~4 meses do ano.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import Literal, Optional, Union

import pandas as pd

from core import b3_session
from backtest.intraday.costs import (
    IntradayCostModel,
    apply_intraday_slippage,
    fees_round_trip_brl,
)
from core.models import IntradayExitReason
from strategy.daytrade.base import (
    AdjustStop,
    AdjustTarget,
    Bar,
    Enter,
    EnterLimit,
    Exit,
    IntradayOpenPosition,
    IntradayStrategy,
    Side,
)


@dataclass
class _Position:
    side: Side
    entry_ts: pd.Timestamp
    entry_price: float
    quantity: int
    current_stop: float | None
    current_target: float | None
    bars_held: int = 0
    metadata: dict = field(default_factory=dict)
    # Tamanho de cada fatia independente do FECHAMENTO por alvo, quando
    # `limit_fill_capped_by_volume` esta ligado -- ver `EnterLimit.
    # exit_split_unit`. `None` = alvo exige `quantity` inteira de uma vez
    # (comportamento antigo). Herdado da ordem que abriu/alimentou a
    # posicao, nao muda depois.
    exit_split_unit: int | None = None
    # Prazo (em barras) que cada fatia de saida REAL espera antes do motor
    # cancelar e fechar o resto a mercado -- so' usado quando `exit_split_unit`
    # e' declarado E a execucao e' REAL (ver `EnterLimit.exit_ttl_bars` e
    # `IntradaySessionMachine._resolve_live_split_exit`). Herdado da mesma
    # ordem que `exit_split_unit`, nao muda depois.
    exit_ttl_bars: int | None = None
    # Fatia de SAIDA vigiada agora PARA ESTA POSICAO (0 = nenhuma posicionada) --
    # 2026-08-24, migrado de campo unico da maquina (`_exit_resting_qty`) para
    # AQUI: com posicoes independentes (`IntradaySessionMachine.positions`,
    # ver a docstring da classe), cada posicao tem seu PROPRIO relogio de
    # saida, nao um relogio global compartilhado -- ver `_resolve_simulated_
    # split_exit`/`_resolve_live_split_exit`.
    exit_resting_qty: int = 0
    resting_exit_bars_waited: int = 0


@dataclass(frozen=True)
class IntradayBacktestConfig:
    costs: IntradayCostModel
    # SEM default -- ate 2026-08-22 valia R$20.000, que ninguem que montava a
    # config fora de `config_for()` sabia que estava ali: dimensiona lote via
    # `on_capital_update` E carimba `capital_base` de cada trade, entao um
    # caixa fantasma produz posicao/expectativa de retorno fantasma (medido
    # em PMAM3: CAGR de dezenas de milhares de % com o caixa real do dono,
    # R$100, contra numeros ilusoriamente "normais" com R$20k). Cada chamador
    # agora tem de decidir explicitamente -- `config_for()` computa o default
    # certo (`capital_minimo_brl` do preco atual) quando nao override.
    initial_capital: float
    default_quantity: int = 1
    # Corte de flatten forcado — dispara na PRIMEIRA barra cujo horario seja
    # >= este valor, ou na ultima barra da sessao, o que vier primeiro.
    # So vale com `session_end_policy="fixed"`.
    session_end_time: time = time(17, 50)
    # De onde sai o corte de flatten:
    #   "b3_equities" -> `core.b3_session.closing_bar_minute_utc(dia)`, que
    #                    anda 1h com o horario de verao dos EUA. E' o correto
    #                    para ACAO: o pregao a vista da B3 fecha 16:55 sob DST
    #                    americano e 17:55 fora dele (hora de Brasilia).
    #   "fixed"       -> `session_end_time`, igual todo dia. Para um
    #                    instrumento cujo fechamento NAO segue esse calendario
    #                    (futuro, medido sem deslocamento) e para relogio
    #                    sintetico de teste.
    # Um corte fixo numa acao acha 1h antes do fechamento durante ~4 meses do
    # ano — sem erro nenhum, so deixando de operar a ultima hora. Medido no
    # campeao: era isso que jogava fora +R$58 de P&L out-of-sample.
    session_end_policy: Literal["fixed", "b3_equities"] = "fixed"
    # Quando stop E target caem dentro da MESMA barra (o M1 nao tem
    # resolucao para saber qual tocou primeiro): "stop_first" e a hipotese
    # PESSIMISTA (mesmo espirito do default `stop_or_open` do motor diario);
    # "target_first" e a hipotese otimista, para comparar os dois bracos.
    ambiguous_bar_resolution: Literal["stop_first", "target_first"] = "stop_first"
    # `True`: a saida por TARGET (unica saida voluntaria/planejada — stop,
    # flatten forcado e Exit por sinal continuam pagando `slippage_ticks`
    # normalmente, pois sao saidas por URGENCIA/protecao, nao um "tirar
    # lucro com calma") e' modelada como ordem-limite (maker, sem
    # slippage) em vez de ordem a mercado. Reflete quem coloca a saida de
    # lucro como limite ja no nivel (a mesma logica de `EnterLimit` para
    # entradas) e usa stop a mercado so pra proteger — default `False`
    # preserva o comportamento antigo (todo fechamento paga slippage).
    target_fills_as_maker: bool = False
    # `True`: uma ordem PARADA (maker -- entrada `EnterLimit`, ou o alvo
    # quando `target_fills_as_maker=True`) so' preenche numa barra/tick cujo
    # `volume` seja >= a quantidade pedida (do FILHO, se a ordem veio
    # dividida por `EnterLimit.split_quantities` -- ver a docstring la).
    # Modela FOK (fill-or-kill): a ordem so' casa se existir contraparte
    # REAL suficiente naquele evento, nunca "meio preenche". Existe porque
    # o motor assumia preenchimento 100% garantido no toque, otimismo que
    # nao sobrevive a duas observacoes reais (2026-08-22, pedido do dono):
    # (1) uma ordem parada grande as vezes nao e' pega mesmo com o preco
    # tendo tocado o nivel; (2) na B3 o RLP (provedor de liquidez que
    # aumenta o volume disponivel num preco) so' interage com ordem A
    # MERCADO, nunca com ordem parada -- uma ordem maker estruturalmente
    # nao alcanca essa fatia de liquidez, e o motor antigo fingia que sim.
    # Ordem A MERCADO (`Enter`, `Exit`, stop, flatten, e o alvo quando
    # `target_fills_as_maker=False`) nunca tem este cap -- e' exatamente
    # essa a assimetria: quem paga o spread encontra contraparte sempre,
    # quem espera parado so' encontra o que realmente passou por ali.
    # Default `False` aqui preserva o comportamento antigo (preenchimento
    # garantido no toque) para quem monta a config na mao. PADRAO DE TESTE
    # a partir de 2026-08-23 (pedido do dono: "e' imprescindivel saber se
    # tinha ou nao volume pra comprar, senao o percentual de acerto se
    # afasta ainda mais da realidade") passa a ser `True` -- ver
    # `backtest.intraday.profiles.config_for`, o caminho que TODO backtest/
    # sombra real usa para montar a config.
    limit_fill_capped_by_volume: bool = False
    # `True`: no INICIO de cada sessao, `run_intraday_backtest` (`backtest.
    # intraday.engine`) recusa operar o dia inteiro se o caixa disponivel
    # (`initial_capital + realized_pnl`) nao cobrir `strategy.daytrade.base.
    # capital_minimo_brl` no preco de abertura -- MESMA regra que `live.
    # intraday_runtime.IntradayLiveRuntime._check_capital` ja aplica ao
    # vivo, so' que ate 2026-08-23 essa regra existia SO' la', nunca no
    # backtest (`IntradaySessionMachine`/`run_intraday_backtest` nao a
    # conheciam). Achado ao medir CLSC4 com capital de teste incompativel
    # com o preco dela: o backtest deixava a estrategia "comprar" um lote
    # que a conta simplesmente nao pagaria de verdade, produzindo MaxDD
    # abaixo de -100% (impossivel sem margem) -- o robo ao vivo NUNCA teria
    # essa chance, porque `_check_capital` recusaria o pregao antes de
    # comecar. Default `False` aqui preserva testes que usam capital
    # sintetico pequeno de proposito, so' para exercitar OUTRO
    # comportamento (fill, restart, etc); `config_for` liga `True` para
    # todo backtest/sombra real, fechando a divergencia.
    enforce_capital_minimo: bool = False
    # Teto de contratos SIMULTANEAMENTE abertos -- `None` (default) = sem
    # teto, o comportamento de sempre (acao a vista, onde quem limita e' o
    # caixa: `enforce_capital_minimo` + `initial_capital`).
    #
    # Existe para um ambiente onde o limitador NAO e' dinheiro: na Copa BTG
    # Trader o simulador declara "Simulacao de Margem Infinita" e nao ha'
    # saldo ficticio nenhum -- o unico limitador de tamanho e' quantos
    # contratos o competidor pode ter abertos ao mesmo tempo (WIN 15, WDO 5
    # em 2025). Modelar isso como caixa seria mentira em duas direcoes:
    # inventaria uma restricao que la' nao existe (margem) e deixaria de
    # aplicar a que existe de verdade.
    #
    # Recusa por INTEIRO, nunca trunca: uma ordem de 5 contratos com 12 de 15
    # ja abertos e' RECUSADA (0 contratos), nao reduzida a 3. Truncar
    # esconderia, dentro de um numero de P&L aparentemente saudavel, uma
    # estrategia que so' "funciona" porque o motor ficou apertando o tamanho
    # dela em silencio -- `IntradaySessionMachine.ordens_recusadas_por_teto`
    # torna isso visivel e mensuravel (portao G5 do plano da Copa: menos de
    # 5% das ordens).
    max_open_contracts: int | None = None


@dataclass
class IntradayTrade:
    symbol: str
    strategy_name: str
    strategy_version: str
    side: Side
    entry_ts: pd.Timestamp
    entry_price: float
    exit_ts: pd.Timestamp
    exit_price: float
    quantity: int
    exit_reason: IntradayExitReason
    point_value_brl: float
    capital_base: float
    fees_total: float = 0.0
    slippage_total: float = 0.0

    @property
    def pnl_brl(self) -> float:
        points = (self.exit_price - self.entry_price) if self.side == "long" else (self.entry_price - self.exit_price)
        gross = points * self.point_value_brl * self.quantity
        return gross - self.fees_total

    @property
    def pnl_pct(self) -> float:
        if self.capital_base == 0:
            return 0.0
        return self.pnl_brl / self.capital_base


# ---------- eventos devolvidos por `on_closed_bar` -------------------------

@dataclass(frozen=True)
class LimitPlaced:
    """Uma `EnterLimit` passou a ser a ordem-limite VIGIADA (substituindo
    qualquer anterior). No backtest e' so informacao; ao vivo e' o gatilho
    para registrar/enviar uma ordem pendente na corretora."""

    order: EnterLimit
    ts: pd.Timestamp
    replaced: Optional[EnterLimit] = None


@dataclass(frozen=True)
class LimitCancelled:
    """A ordem-limite vigiada deixou de valer sem ter preenchido.
    `reason`: "flatten" (fim da sessao), "ttl" (expirou por `ttl_bars`),
    "superseded" (o robo devolveu outra ordem / uma entrada a mercado
    venceu)."""

    order: EnterLimit
    ts: pd.Timestamp
    reason: str


@dataclass(frozen=True)
class PositionOpened:
    """Entrou posicao de verdade. `order_kind`: "market" (`Enter`, pagou
    slippage na abertura) ou "limit" (`EnterLimit`, preencheu no nivel
    exato). `bar` e' a barra em que o fill aconteceu — ao vivo, e' dela que
    sai a medicao de penetracao do nivel (ver
    `live/intraday_runtime.py`)."""

    ts: pd.Timestamp
    side: Side
    price: float
    quantity: int
    stop: float | None
    target: float | None
    order_kind: str
    reason: str
    bar: Bar


@dataclass(frozen=True)
class PositionClosed:
    """Fechou posicao. `trade` carrega tudo (precos, custos, motivo) — e' o
    MESMO objeto que o backtest acumula em `IntradayBacktestResult.trades`."""

    trade: IntradayTrade
    pnl_brl: float


@dataclass(frozen=True)
class OrderRejected:
    """Uma entrada foi RECUSADA por inteiro pelo motor, sem virar posicao --
    hoje so' por `IntradayBacktestConfig.max_open_contracts` (`reason=
    "max_open_contracts"`). `quantity` e' o que foi pedido e nao entrou;
    `open_contracts` e' quanto ja estava aberto no momento da recusa.

    E' um evento, e nao um `raise`, porque bater no teto e' comportamento
    ESPERADO de um ambiente com teto -- o que nao pode e' acontecer em
    silencio."""

    ts: pd.Timestamp
    side: Side
    quantity: int
    open_contracts: int
    cap: int
    order_kind: str
    reason: str


MachineEvent = Union[LimitPlaced, LimitCancelled, PositionOpened, PositionClosed, OrderRejected]


# ---------- helpers de preenchimento (portados de `engine.py` sem mudanca) --

def _position_view(pos: _Position) -> IntradayOpenPosition:
    return IntradayOpenPosition(
        side=pos.side,
        entry_ts=pos.entry_ts,
        entry_price=pos.entry_price,
        quantity=pos.quantity,
        current_stop=pos.current_stop,
        current_target=pos.current_target,
        bars_held=pos.bars_held,
        metadata=dict(pos.metadata),
    )


def _stop_target_touch(pos: _Position, bar: Bar) -> tuple[bool, bool]:
    """(`stop_hit`, `target_hit`) -- so' o toque de PRECO (`bar.high`/
    `bar.low` contra os niveis), sem nenhum cheque de volume. Extraido de
    `_resolve_stop_target_hit` para ser reusado por `on_closed_bar` no
    caminho de alvo dividido (`_Position.exit_split_unit`), que precisa da
    mesma deteccao de toque mas de uma resolucao de preenchimento
    diferente (parcial, nao tudo-ou-nada)."""
    stop_hit = pos.current_stop is not None and (
        bar.low <= pos.current_stop if pos.side == "long" else bar.high >= pos.current_stop
    )
    target_hit = pos.current_target is not None and (
        bar.high >= pos.current_target if pos.side == "long" else bar.low <= pos.current_target
    )
    return stop_hit, target_hit


def _resolve_stop_target_hit(
    pos: _Position, bar: Bar, ambiguous_bar_resolution: str,
    target_needs_volume: bool = False, orcamento: float | None = None,
) -> Optional[str]:
    """`"stop"`, `"target"` ou `None`. Quando os DOIS tocam na mesma barra,
    `ambiguous_bar_resolution` decide — nao ha como saber qual veio primeiro
    so com OHLC de 1 minuto.

    `target_needs_volume=True` (so quando `target_fills_as_maker` E
    `limit_fill_capped_by_volume` estao ligados): o alvo so' "toca" de
    verdade se `orcamento >= pos.quantity` -- a MESMA barra que nao tiver
    volume suficiente simplesmente nao resolve nada, e a posicao continua
    aberta para a PROXIMA barra reavaliar do zero (preco pode continuar no
    alvo com mais volume, ou ter ido embora). O stop NUNCA tem este cap:
    e' saida por protecao/urgencia, sempre a mercado. `orcamento` (2026-08-24,
    antes lia `bar.volume` direto): o CHAMADOR (`on_closed_bar`) mantem um
    orcamento de volume UNICO, compartilhado entre TODAS as posicoes
    avaliadas nesta barra -- com posicoes independentes, cada uma checando
    `bar.volume` por conta propria dobraria (ou N-plicaria) a liquidez real
    disponivel. `None` (default) so' e' seguro quando `target_needs_volume`
    e' `False` (o valor nunca e' lido nesse caso).

    So' vale para `pos.exit_split_unit is None` -- com fatia declarada,
    `on_closed_bar` usa `_stop_target_touch` + `_resolve_target_partial_fill`
    direto, para poder fechar SO' O QUANTO o volume cobrir em vez de tudo
    ou nada."""
    stop_hit, target_hit = _stop_target_touch(pos, bar)
    if target_hit and target_needs_volume and (orcamento or 0) < pos.quantity:
        target_hit = False
    if stop_hit and target_hit:
        return "stop" if ambiguous_bar_resolution == "stop_first" else "target"
    if stop_hit:
        return "stop"
    if target_hit:
        return "target"
    return None


def _resolve_target_partial_fill(pos: _Position, orcamento: float) -> int:
    """Quanto o alvo consegue fechar nesta barra, dado o tamanho de fatia
    `pos.exit_split_unit` (`None` = a posicao inteira e' UMA fatia so' --
    unifica os dois casos) -- mesma logica FOK por pedaco de
    `_resolve_limit_fills`, do lado da saida em vez da entrada, tudo-ou-nada
    por barra. `orcamento` (2026-08-24, antes `bar.volume` lido direto
    aqui dentro): o CHAMADOR (`on_closed_bar`) mantem um orcamento de
    volume UNICO da barra, compartilhado entre TODAS as posicoes avaliadas
    nela -- com posicoes independentes, cada uma consumindo `bar.volume`
    por conta propria dobraria (ou N-plicaria) a liquidez real disponivel.
    Processa fatias em ordem ate estourar o orcamento ou fechar a posicao
    inteira."""
    tamanho_fatia = pos.exit_split_unit or pos.quantity
    restante = pos.quantity
    fechado = 0
    while restante > 0:
        fatia = min(tamanho_fatia, restante)
        if orcamento < fatia:
            break
        fechado += fatia
        orcamento -= fatia
        restante -= fatia
    return fechado


def _exit_fill_price(pos: _Position, bar: Bar, kind: str) -> float:
    """Preco de referencia (ANTES de slippage) do fechamento por stop/target
    nesta barra. Se a barra abriu ja alem do nivel (gap), o fill e no
    `open` (pior para stop, melhor para target); senao, exatamente no
    nivel — mesmo espirito de `stop_or_open` do motor diario."""
    level = pos.current_stop if kind == "stop" else pos.current_target
    if pos.side == "long":
        # stop = venda no pior caso (min); target = venda no melhor caso (max)
        return min(bar.open, level) if kind == "stop" else max(bar.open, level)
    # short: stop = compra no pior caso (max); target = compra no melhor caso (min)
    return max(bar.open, level) if kind == "stop" else min(bar.open, level)


def _exit_side(pos: _Position) -> Literal["buy", "sell"]:
    """Lado da ORDEM de fechamento — inverso do lado da posicao."""
    return "sell" if pos.side == "long" else "buy"


def _limit_touched(order: EnterLimit, bar: Bar) -> bool:
    """`True` se esta barra tocou o preco da ordem-limite pendente (mesmo
    mecanismo de toque de `_resolve_stop_target_hit`, intrabar via
    high/low). Compra: `bar.low <= limit_price`; venda: `bar.high >=
    limit_price`."""
    return bar.low <= order.limit_price if order.side == "long" else bar.high >= order.limit_price


class IntradaySessionMachine:
    """Estado + transicoes de uma sessao intradiaria. Ver docstring do modulo.

    Nao guarda historico de trades nem curva de patrimonio — quem quer isso
    acumula os `PositionClosed` que `on_closed_bar` devolve. O que a maquina
    guarda e' so o que a PROXIMA barra precisa: posicao(oes) aberta(s), acao
    filada, ordem-limite vigiada, P&L da sessao (para o robo ver em `on_bar`)
    e P&L realizado acumulado (para marcar patrimonio).

    `self.positions: list[_Position]` (2026-08-24, antes um `_Position |
    None` unico) -- pedido do dono: "se eu tenho capital pra 2 lotes, mas o
    volume so' permite entrar aos poucos, tenho que abrir DUAS posicoes;
    abrindo duas eu ganho/perco igual (ou quase) ao abrir 1 sozinha, e cada
    uma tem que ter O SEU PROPRIO stop, nao um stop que fecha as duas
    juntas." Antes, uma entrada fatiada em N pedacos (`EnterLimit.
    split_quantities`) fundia cada preenchimento numa UNICA `_Position`
    agregada (preco medio ponderado, quantidade somada, um stop/alvo/TTL so'
    para o total) -- exatamente o oposto do pedido: mais capital (mais lotes
    agregados) podia se sair PIOR que 1 lote sozinho, porque o stop/TTL da
    posicao agregada dispara de um jeito diferente (mais barras expostas,
    mais lotes arrastados juntos num so' evento) do que o stop de uma
    posicao de 1 lote isolada.

    So' vale para o caminho SIMULADO (`self.execution is None` -- backtest E
    modo sombra, como o robo e' medido/selecionado hoje). Em EXECUCAO REAL
    (`self.execution` setado, conta NETTING na corretora) `self.positions`
    nunca passa de 1 elemento -- a corretora so' enxerga uma posicao
    agregada por simbolo, e o `exit_market`/o schema de `journal.live_store`
    (`upsert_position`/`delete_position`, indexados por `(account_id,
    ticker, kind)`) nao tem como representar duas posicoes independentes do
    mesmo ticker. Preenchimentos em execucao real continuam fundindo em UMA
    `_Position` so', como antes -- ver o laco de preenchimento em
    `on_closed_bar`.
    """

    def __init__(self, strategy: IntradayStrategy, config: IntradayBacktestConfig,
                 execution=None):
        self.strategy = strategy
        self.config = config
        # `None` (backtest, e tambem o modo sombra ao vivo) = os fills sao
        # SIMULADOS a partir do OHLC da barra: uma ordem-limite preenche se a
        # barra tocou o nivel, ao preco exato do nivel.
        #
        # Um objeto aqui (operacao REAL, `live/intraday_execution.py`) inverte
        # a fonte de verdade: a barra deixa de decidir se preencheu -- quem
        # decide e' a CORRETORA, e o preco que entra no trade e' o preco que
        # ela de fato executou. Isso existe porque a simulacao e' otimista por
        # construcao: ela assume que uma ordem parada no nivel X preenche
        # sempre que o preco TOCA X, ignorando fila de ofertas. Confiar nela
        # com dinheiro real faria o robo se achar posicionado (e comecar a
        # contar alvo e stop) enquanto a ordem ainda esta parada no book sem
        # ter executado nada.
        #
        # A logica de DECISAO nao muda entre os dois modos -- e' o mesmo
        # `on_closed_bar`, o mesmo robo, as mesmas prioridades. So a resposta
        # a "preencheu? a que preco?" troca de fonte.
        self.execution = execution
        self.positions: list[_Position] = []
        self.pending: Enter | Exit | None = None
        self.resting_limit: EnterLimit | None = None
        self.resting_limit_bars_waited = 0
        # Quantidades dos FILHOS de `resting_limit` ainda sem preencher (ver
        # `EnterLimit.split_quantities`) -- `[order.quantity]` quando a
        # ordem nao veio dividida, um lote so'. Caminho SIMULADO
        # (`execution is None`) preenche filho a filho, um por um, contra
        # `bar.volume`; caminho REAL (`execution` setado, ver
        # `live/intraday_execution.py`) manda um filho por elemento como
        # ordem de verdade na corretora e trata este total como um POOL
        # agregado, decrescido pelo que a corretora reportar como
        # crescimento da posicao a cada barra (ver `_resolve_limit_fills`).
        self._resting_children_qty: list[int] = []
        # Fatia de SAIDA (`_Position.exit_split_unit`) vigiada agora para
        # CADA posicao -- ordem-limite REAL na corretora quando `execution`
        # esta setado (`_resolve_live_split_exit`), ou simulada contra
        # `bar.volume` quando `exit_ttl_bars` esta declarado sem execucao
        # real (`_resolve_simulated_split_exit`). Sem `exit_ttl_bars`
        # declarado, backtest/sombra caem no caminho ANTIGO
        # (`_resolve_target_partial_fill`, sem prazo). 2026-08-24: migrado
        # para campos de `_Position` (`pos.exit_resting_qty`/`pos.
        # resting_exit_bars_waited`) -- cada posicao tem seu PROPRIO relogio,
        # nao um relogio global da maquina (ver a docstring da classe).
        # PERSISTIDO em `state()` (ver `restore()`) -- diferente de
        # `resting_limit`, que e' uma DECISAO do robo e por isso e' redecidida
        # do zero no warm start, esta fatia e' o rastro de uma ordem que JA
        # esta (ou nao) na corretora. Em modo simulado (`execution is None`)
        # restaurar os dois numeros e' o bastante -- nao ha' ordem real para
        # perder o rastro. Em execucao REAL, o ticket/estado de
        # `MT5IntradayExecution.pending_exit_order` vive so' em memoria (nunca
        # persistido -- a corretora e' a unica fonte de verdade sobre ele), e
        # um processo novo o perde: `restore()` falha alto nesse caso, em vez
        # de arriscar rearmar uma SEGUNDA ordem de saida por cima da que pode
        # ainda estar viva no book.
        self.flattened = False
        self.session_pnl = 0.0
        self.realized_pnl = 0.0
        self.session_date = None
        # Diagnostico de `config.max_open_contracts` -- CUMULATIVOS em todo o
        # backtest (nao zerados por `_reset_session`): a pergunta que eles
        # respondem ("esta estrategia so' funciona porque esbarra no teto?")
        # e' sobre a run inteira, nao sobre um pregao. Contam ENTRADAS
        # (`Enter` a mercado e cada filho de `EnterLimit` que preencheu ou
        # foi recusado), nunca saidas -- fechar posicao sempre cabe.
        self.ordens_aceitas = 0
        self.ordens_recusadas_por_teto = 0

    # ---------- ciclo de vida da sessao ----------------------------------

    def begin_session(self, session_date) -> None:
        """Comeca uma sessao NOVA: reseta o estado por-dia e avisa o robo
        (`on_session_start`)."""
        self.strategy.on_session_start(session_date)
        self._reset_session(session_date)

    def resume_session(self, session_date, seed_pending: Enter | EnterLimit | None = None) -> None:
        """Retoma uma sessao JA EM ANDAMENTO sem tocar no estado interno do
        robo — usar quando ele acabou de ser calibrado por fora
        (`warm_start_calibration`) e um `on_session_start` apagaria essa
        calibracao. `seed_pending` e' a ordem que o robo deixou em pe no fim
        do replay: passa a ser vigiada desde a PRIMEIRA barra, em vez de
        precisar de uma barra extra so para o robo redecidir o mesmo.
        `None` NAO limpa uma ordem que ja estivesse vigiada (reconectar no
        meio do pregao nao deve cancelar o que ja estava de pe).

        `seed_pending` e' IGNORADO se `self.positions` ja tiver algo (um
        `restore()` anterior repos posicao(oes) REAL, ver
        `live/intraday_runtime.py::_restore`, chamado ANTES desta funcao no
        despacho de reconexao): o replay do warm start nao sabe de posicao
        nenhuma (`warm_start_calibration` sempre chama o robo com
        `positions=[]`) e recalcula a ordem pendente do zero -- plantar
        essa ordem por cima de uma posicao ja aberta a deixaria orfa e
        desconectada assim que a posicao fechasse (o preco/nivel dela pode
        nem existir mais)."""
        self._reset_session(session_date, clear_resting=False)
        if self.positions:
            return
        if isinstance(seed_pending, Enter):
            self.pending = seed_pending
        elif isinstance(seed_pending, EnterLimit):
            self.resting_limit = seed_pending
            self.resting_limit_bars_waited = 0
            self._resting_children_qty = seed_pending.children(self.config.default_quantity)

    def _reset_session(self, session_date, clear_resting: bool = True) -> None:
        self.session_date = session_date
        self.session_pnl = 0.0
        self.flattened = False
        if clear_resting:
            self.resting_limit = None
            self.resting_limit_bars_waited = 0
            self._resting_children_qty = []

    # ---------- persistencia (so a operacao ao vivo usa) ------------------

    def state(self) -> dict:
        """Snapshot serializavel do que a maquina precisa para continuar
        DEPOIS de o processo reiniciar no meio do pregao.

        O backtest nunca chama isto (roda de ponta a ponta em memoria); ao
        vivo e' obrigatorio: sem persistir a posicao, um reinicio as 11h
        esqueceria que existe posicao aberta e o robo abriria outra. O estado
        interno da ESTRATEGIA nao entra aqui de proposito — ele e'
        reconstruido do dado real por `warm_start_calibration` (ver
        `strategy/daytrade/base.py`), que e' a unica forma de garantir que a
        calibracao ao voltar e' a mesma que teria sido sem a queda."""
        return {
            "session_date": self.session_date.isoformat() if self.session_date else None,
            "session_pnl": self.session_pnl,
            "realized_pnl": self.realized_pnl,
            "flattened": self.flattened,
            "positions": [
                {
                    "side": pos.side,
                    "entry_ts": pos.entry_ts.isoformat(),
                    "entry_price": pos.entry_price,
                    "quantity": pos.quantity,
                    "current_stop": pos.current_stop,
                    "current_target": pos.current_target,
                    "bars_held": pos.bars_held,
                    "metadata": dict(pos.metadata),
                    "exit_split_unit": pos.exit_split_unit,
                    "exit_ttl_bars": pos.exit_ttl_bars,
                    "exit_resting_qty": pos.exit_resting_qty,
                    "exit_resting_bars_waited": pos.resting_exit_bars_waited,
                }
                for pos in self.positions
            ],
        }

    def restore(self, state: dict) -> None:
        """Inverso de `state()`. Nao restaura a ordem-limite vigiada de
        proposito: `resting_limit` e' uma DECISAO do robo, e o robo acabou de
        ser recalibrado — a ordem certa vem do `seed_pending` do warm start,
        nao de um snapshot velho.

        A fatia de SAIDA (`exit_resting_qty`) e' diferente: nao e' uma decisao
        a redecidir, e' o rastro de uma ordem que pode estar (ou nao) viva na
        corretora agora mesmo. Em modo simulado (`self.execution is None`,
        backtest/sombra) restaurar os dois numeros basta -- a proxima barra
        volta a checar `bar.volume` normalmente, sem ordem real para perder o
        rastro. Em execucao REAL (`self.execution` setado) o ticket dessa
        ordem vive so' dentro de `MT5IntradayExecution.pending_exit_order`,
        NUNCA persistido -- um processo novo reconstroi a execucao do zero e
        nao tem como saber se aquela ordem-limite ainda esta no book.
        Silenciosamente assumir "nao esta" e continuar poderia rearmar uma
        SEGUNDA ordem de saida por cima da que sobrou: venda dobrada / posicao
        invertida numa conta NETTING. Falha alto em vez disso -- o supervisor
        (`scripts/run_live.py::cmd_loop`) ja loga e tenta de novo a cada
        barra, mesmo padrao de `BrokerExecutionError`; so' religa depois de um
        humano conferir o terminal e cancelar a ordem-limite de saida
        pendente, se ainda existir."""
        from datetime import date as _date

        if not state:
            return
        sd = state.get("session_date")
        self.session_date = _date.fromisoformat(sd) if sd else None
        self.session_pnl = float(state.get("session_pnl") or 0.0)
        self.realized_pnl = float(state.get("realized_pnl") or 0.0)
        self.flattened = bool(state.get("flattened"))
        blocos = state.get("positions")
        if blocos is None:
            bloco_legado = state.get("position")
            blocos = [bloco_legado] if bloco_legado else []
        self.positions = []
        for bloco in blocos:
            qtd_pendente = int(bloco.get("exit_resting_qty") or 0)
            if qtd_pendente > 0 and self.execution is not None:
                raise RuntimeError(
                    f"{self.strategy.symbol}: reinicio encontrou uma FATIA DE SAIDA "
                    f"posicionada ({qtd_pendente} acoes) em execucao REAL, mas o ticket "
                    "dessa ordem-limite vive so' em memoria e nao sobrevive a um "
                    "restart do processo -- a corretora e' a unica fonte de verdade "
                    "sobre ele. Resumir aqui sem saber se a ordem ainda esta no book "
                    "arriscaria mandar uma SEGUNDA ordem de saida por cima (venda "
                    "dobrada / posicao invertida numa conta NETTING). Confira o "
                    f"terminal MT5 manualmente: cancele a ordem-limite de saida "
                    f"pendente em {self.strategy.symbol} (se ainda existir) antes de "
                    "religar este slot."
                )
            self.positions.append(_Position(
                side=bloco["side"],
                entry_ts=pd.Timestamp(bloco["entry_ts"]),
                entry_price=float(bloco["entry_price"]),
                quantity=int(bloco["quantity"]),
                current_stop=bloco.get("current_stop"),
                current_target=bloco.get("current_target"),
                bars_held=int(bloco.get("bars_held") or 0),
                metadata=dict(bloco.get("metadata") or {}),
                exit_split_unit=bloco.get("exit_split_unit"),
                exit_ttl_bars=bloco.get("exit_ttl_bars"),
                exit_resting_qty=qtd_pendente,
                resting_exit_bars_waited=int(bloco.get("exit_resting_bars_waited") or 0),
            ))

    # ---------- marcacao de patrimonio -----------------------------------

    @property
    def open_contracts(self) -> int:
        """Contratos (ou acoes) SIMULTANEAMENTE abertos agora, somando todas
        as posicoes independentes -- a grandeza que
        `config.max_open_contracts` limita."""
        return sum(p.quantity for p in self.positions)

    @property
    def resting_children(self) -> tuple[int, ...]:
        """Quantidades dos FILHOS de `resting_limit` que ainda NAO preencheram
        -- tupla vazia quando nao ha ordem-limite de entrada em pe.

        Publico porque o PAINEL conta ordens posicionadas por aqui (ver
        `live/intraday_runtime.py::_espelho_da_ordem_em_pe`): `len()` e' quantas
        ordens estao no book (uma por filho, ver `EnterLimit.children` e a Fase
        2 em `live/intraday_execution.py`) e `sum()` e' quantas acoes elas
        somam. Copia, e nao a lista viva: quem le e' tela, nao decide nada, e
        nao pode conseguir mexer no estado da maquina por descuido."""
        return tuple(self._resting_children_qty)

    def _cabe_no_teto(self, quantity: int) -> bool:
        cap = self.config.max_open_contracts
        return cap is None or (self.open_contracts + quantity) <= cap

    def _recusa_por_teto(self, ts: pd.Timestamp, side: Side, quantity: int,
                         order_kind: str) -> "OrderRejected":
        """Registra e descreve UMA recusa por teto. Nao mexe em posicao nem
        em ordem parada -- quem chama decide o que fazer com a ordem
        recusada (hoje: descartada, ver `on_closed_bar`)."""
        self.ordens_recusadas_por_teto += 1
        return OrderRejected(
            ts=ts, side=side, quantity=quantity,
            open_contracts=self.open_contracts,
            cap=int(self.config.max_open_contracts or 0),
            order_kind=order_kind, reason="max_open_contracts",
        )

    def unrealized_brl(self, price: float) -> float:
        """Marcacao a mercado da SOMA de todas as posicoes abertas a `price`
        (0.0 sem posicao nenhuma)."""
        total = 0.0
        for pos in self.positions:
            points = (price - pos.entry_price) if pos.side == "long" else (pos.entry_price - price)
            total += points * self.config.costs.point_value_brl * pos.quantity
        return total

    def positions_view(self) -> list[IntradayOpenPosition]:
        return [_position_view(pos) for pos in self.positions]

    @property
    def position(self) -> _Position | None:
        """Atalho de compatibilidade para quem so' opera no caminho de NO
        MAXIMO 1 posicao -- hoje, so' `live/intraday_runtime.py` (execucao
        REAL, que continua fundindo tudo numa unica `_Position`, ver a
        docstring da classe). Levanta se `self.positions` tiver mais de 1
        elemento -- nao deveria acontecer nesse caminho; se acontecer, e'
        mais seguro falhar alto do que silenciosamente devolver so' a
        primeira e esconder as outras."""
        if len(self.positions) > 1:
            raise RuntimeError(
                f"{self.strategy.symbol}: `machine.position` (atalho de 1 posicao) "
                f"chamado com {len(self.positions)} posicoes abertas -- so' faz "
                "sentido em execucao REAL, que nunca deveria acumular mais de uma "
                "(ver a docstring de `IntradaySessionMachine`). Use `self.positions` "
                "diretamente."
            )
        return self.positions[0] if self.positions else None

    # ---------- o passo ---------------------------------------------------

    def session_end_time_for(self, ts: pd.Timestamp) -> time:
        """Corte de flatten forcado que vale no pregao da barra `ts`.

        Depende do DIA, e nao so da config, porque o pregao a vista da B3
        desloca 1h com o horario de verao dos EUA — ver `session_end_policy`
        em `IntradayBacktestConfig` e a medicao em `core.b3_session`."""
        if self.config.session_end_policy == "b3_equities":
            return b3_session.closing_bar_minute_utc(ts.date())
        return self.config.session_end_time

    def is_previous_session_bar(self, ts: pd.Timestamp) -> bool:
        """`ts` esta carimbado num pregao ANTERIOR ao que esta maquina abriu?

        Existe porque o corte de flatten (secao (2) de `on_closed_bar`)
        compara so' a HORA (`ts.time() >= session_end_time_for(ts)`) -- ele
        nao tem como saber sozinho de que DIA e' a barra. Ao vivo, o feed
        entrega tudo com `ts > last_bar_ts`, e essa marca atravessa a virada
        do pregao: uma barra atrasada de ONTEM, dentro da janela do corte,
        chegava como PRIMEIRA barra de hoje e achatava a sessao inteira antes
        da primeira decisao (achado 2026-08-25 na `dt-gremah-pmam3-shadow`:
        barra `2026-08-24 19:54`, corte da B3 `19:54` -> `flattened=True` as
        13:01, robo mudo nas 322 barras seguintes, zero ordem no dia).

        Barra de pregao FUTURO nao entra aqui de proposito: ao vivo ela nao
        existe (`_start_session` reabre a maquina no pregao de hoje antes de
        qualquer consumo), e inventar um comportamento para ela seria regra
        nova sem caso real.

        No backtest e' inerte: `run_intraday_backtest` agrupa por
        `bars.index.date` e abre a sessao com essa MESMA data, entao nenhuma
        barra do grupo e' anterior a ela."""
        return self.session_date is not None and ts.date() < self.session_date

    def on_closed_bar(self, bar: Bar, is_last_bar: bool = False) -> list[MachineEvent]:
        """Processa UMA barra ja FECHADA. `is_last_bar=True` forca o flatten
        nesta barra (ultima barra da sessao no dado); o corte por horario
        (`config.session_end_time`) e' avaliado de qualquer forma.

        Barra de pregao anterior (`is_previous_session_bar`) e' DESCARTADA
        sem nenhum efeito -- nem decisao, nem preenchimento, nem flatten."""
        cfg = self.config
        ts = bar.ts
        events: list[MachineEvent] = []

        if self.is_previous_session_bar(ts):
            return events

        # (1) stop/target automatico tem prioridade sobre qualquer acao filada.
        # Itera sobre uma COPIA (`list(...)`) porque fechar uma posicao
        # remove ela de `self.positions` durante o laco. `exit_orcamento`:
        # orcamento de volume da barra para preenchimento de SAIDA (maker),
        # UNICO e COMPARTILHADO entre todas as posicoes avaliadas aqui --
        # antes so' existia 1 posicao por vez (`bar.volume` bastava, lido
        # direto); com posicoes independentes (2026-08-24, ver a docstring
        # da classe), cada uma checando `bar.volume` por conta propria
        # dobraria (ou N-plicaria) a liquidez real disponivel para a saida.
        # So' relevante quando `target_needs_volume` (definido dentro do
        # laco, mesmo valor em toda a barra); despejo a MERCADO (stop, TTL
        # estourado) nunca disputa este orcamento -- e' urgencia, nao
        # preenchimento maker.
        exit_orcamento = bar.volume
        for pos in list(self.positions):
            target_needs_volume = cfg.target_fills_as_maker and cfg.limit_fill_capped_by_volume
            if self.execution is not None and pos.exit_split_unit is not None:
                # Execucao REAL com saida dividida: quem decide o fill e' a
                # corretora, via ordem-limite de verdade por fatia, com prazo
                # -- ver `_resolve_live_split_exit`. Execucao real nunca tem
                # mais de 1 elemento em `self.positions` (ver a docstring da
                # classe), entao este laco so' roda uma vez nesse caso. O
                # caminho simulado logo abaixo (guiado por `bar.volume`) e'
                # so' para backtest/sombra.
                events.extend(self._resolve_live_split_exit(ts, bar, pos))
            elif target_needs_volume and pos.exit_split_unit is not None and pos.exit_ttl_bars is not None:
                # Mesma divisao de alvo em fatias, mas com PRAZO -- espelha
                # `_resolve_live_split_exit` usando `bar.volume`/`bar.close`
                # no lugar da corretora, para o backtest conseguir prever o
                # que a execucao REAL vai fazer (mesmo motivo de a maquina
                # ser compartilhada). So' entra aqui quando `exit_ttl_bars`
                # esta declarado -- sem prazo, cai no `elif` de baixo
                # (comportamento ANTIGO, ilimitado). So' roda em modo
                # SIMULADO (execucao real cai no `if` de cima sempre que
                # `exit_split_unit` esta setado, com ou sem prazo).
                evs, exit_orcamento = self._resolve_simulated_split_exit(ts, bar, pos, exit_orcamento)
                events.extend(evs)
            elif target_needs_volume and pos.exit_split_unit is not None:
                # Alvo dividido em fatias (`EnterLimit.exit_split_unit`), SEM
                # prazo declarado, SIMULADO: o stop continua tudo-ou-nada
                # (protecao/urgencia, sempre a mercado), mas o alvo fecha
                # SO' O QUANTO o volume da barra cobrir -- pode levar varias
                # barras para zerar ESTA posicao, sem limite. Nao orfaniza
                # filhos irmaos ainda sem preencher (`self.
                # _resting_children_qty`) -- cada um vira sua PROPRIA posicao
                # independente quando preencher (ver a secao 3b), pedido do
                # dono 2026-08-24 (ver a docstring da classe).
                stop_hit, target_hit = _stop_target_touch(pos, bar)
                if stop_hit and target_hit:
                    hit = "stop" if cfg.ambiguous_bar_resolution == "stop_first" else "target"
                elif stop_hit:
                    hit = "stop"
                elif target_hit:
                    hit = "target"
                else:
                    hit = None
                if hit == "stop":
                    ref_price = _exit_fill_price(pos, bar, "stop")
                    events.append(self._close_position(pos, ts, ref_price, IntradayExitReason.STOP))
                    self._clear_stale_enter()
                elif hit == "target":
                    fechado = _resolve_target_partial_fill(pos, exit_orcamento)
                    if fechado > 0:
                        exit_orcamento -= fechado
                        ref_price = _exit_fill_price(pos, bar, "target")
                        events.append(self._close_position(
                            pos, ts, ref_price, IntradayExitReason.TARGET, quantity_override=fechado,
                        ))
                        if pos not in self.positions:  # fechou inteira agora
                            self._clear_stale_enter()
                        # senao: fechou uma fatia, esta posicao (menor)
                        # continua aberta -- proxima barra reavalia o resto
                        # do zero.
            else:
                hit = _resolve_stop_target_hit(pos, bar, cfg.ambiguous_bar_resolution,
                                               target_needs_volume=target_needs_volume,
                                               orcamento=exit_orcamento)
                if hit == "target" and target_needs_volume:
                    exit_orcamento -= pos.quantity
                if hit is not None:
                    ref_price = _exit_fill_price(pos, bar, hit)
                    reason = IntradayExitReason.STOP if hit == "stop" else IntradayExitReason.TARGET
                    events.append(self._close_position(pos, ts, ref_price, reason))
                    self._clear_stale_enter()
                    # a posicao fechou -- qualquer FILHO ainda sem preencher do
                    # MESMO grupo dividido (`EnterLimit.split_quantities`)
                    # ficou orfao, nao uma entrada nova para tentar de novo.
                    # So' se aplica quando esta posicao NAO veio de uma
                    # entrada dividida (`exit_split_unit is None` aqui, ver o
                    # `if/elif` acima) -- sem cap por volume isto quase nunca
                    # dispara de verdade.
                    orfa = self._cancelar_resting_orfa(ts)
                    if orfa is not None:
                        events.append(orfa)

        # (2) flatten forcado — primeira barra da sessao cujo horario >= corte,
        # ou a ultima barra da sessao. Nenhuma entrada nova depois disso.
        if not self.flattened and (ts.time() >= self.session_end_time_for(ts) or is_last_bar):
            if self.positions:
                if self.execution is not None and any(p.exit_resting_qty > 0 for p in self.positions):
                    # cancela a fatia de saida REAL em pe' antes de mandar o
                    # flatten -- senao as duas ordens (a limite parada e o
                    # flatten a mercado) ficariam vivas ao mesmo tempo na
                    # corretora, pela mesma posicao. Execucao real nunca tem
                    # mais de 1 posicao (ver a docstring da classe).
                    self.execution.cancel_exit_limit(ts, reason="flatten")
                for pos in list(self.positions):
                    pos.exit_resting_qty = 0
                    pos.resting_exit_bars_waited = 0
                    events.append(self._close_position(pos, ts, bar.close, IntradayExitReason.FORCED_FLATTEN))
            self.pending = None
            if self.resting_limit is not None:
                events.append(LimitCancelled(order=self.resting_limit, ts=ts, reason="flatten"))
                self.resting_limit = None
                self._resting_children_qty = []
            self.flattened = True

        if not self.flattened:
            # (3) executa acao filada na ABERTURA desta barra. `Exit` achata
            # TODAS as posicoes abertas de uma vez (ex.: stop agregado de
            # sessao, `IntradayExitReason.SIGNAL`) -- nao existe "Exit de uma
            # posicao so'" no contrato da estrategia.
            # Teto de contratos (`config.max_open_contracts`): uma entrada A
            # MERCADO que nao cabe e' recusada por INTEIRO aqui, antes de
            # qualquer execucao -- nunca truncada para o que sobra do teto
            # (ver o comentario do campo). So' vale quando o robo esta flat:
            # com posicao aberta, um `Enter` ja e' descartado mais abaixo por
            # outro motivo, e conta-lo como recusa de teto seria mentira.
            if (isinstance(self.pending, Enter) and not self.positions
                    and not self._cabe_no_teto(self.pending.quantity or cfg.default_quantity)):
                events.append(self._recusa_por_teto(
                    ts, self.pending.side,
                    self.pending.quantity or cfg.default_quantity, "market"))
                self.pending = None

            if isinstance(self.pending, Exit) and self.positions:
                for pos in list(self.positions):
                    events.append(self._close_position(pos, ts, bar.open, IntradayExitReason.SIGNAL))
                self.pending = None
                orfa = self._cancelar_resting_orfa(ts)
                if orfa is not None:
                    events.append(orfa)
            elif isinstance(self.pending, Enter) and not self.positions:
                pending = self.pending
                if self.execution is not None:
                    # Entrada A MERCADO ao vivo nao esta implementada de
                    # proposito: nenhum robo intradiario em operacao emite
                    # `Enter` (a familia `gremah` so' usa `EnterLimit`, que e'
                    # o proprio ponto do desenho -- ser maker). Falhar alto
                    # aqui e' melhor que simular o fill a mercado com o `open`
                    # da barra e mandar dinheiro real contra um preco
                    # inventado.
                    raise NotImplementedError(
                        "entrada a mercado (`Enter`) nao suportada em execucao real -- "
                        f"o robo {self.strategy.name!r} pediu uma. So `EnterLimit` "
                        "(ordem-limite pendente) tem caminho de execucao confirmado "
                        "pela corretora; ver `live/intraday_execution.py`."
                    )
                entry_side: Literal["buy", "sell"] = "buy" if pending.side == "long" else "sell"
                entry_px = apply_intraday_slippage(bar.open, entry_side, cfg.costs)
                nova_posicao = _Position(
                    side=pending.side,
                    entry_ts=ts,
                    entry_price=entry_px,
                    quantity=pending.quantity or cfg.default_quantity,
                    current_stop=pending.initial_stop,
                    current_target=pending.initial_target,
                    metadata=dict(pending.metadata or {}),
                )
                self.positions.append(nova_posicao)
                self.ordens_aceitas += 1
                self.pending = None
                events.append(PositionOpened(
                    ts=ts, side=nova_posicao.side, price=entry_px,
                    quantity=nova_posicao.quantity, stop=nova_posicao.current_stop,
                    target=nova_posicao.current_target, order_kind="market",
                    reason=pending.reason, bar=bar,
                ))
                # entrada a mercado supera qualquer ordem-limite ainda pendente
                if self.resting_limit is not None:
                    events.append(LimitCancelled(order=self.resting_limit, ts=ts, reason="superseded"))
                    self.resting_limit = None
                    self._resting_children_qty = []
            else:
                self.pending = None  # Enter com posicao ja aberta (ou Exit sem posicao): descartado

            # (3b) ordem-limite (maker) pendente: preenche no PRIMEIRO
            # toque de `bar.low`/`bar.high`, ao preco exato do nivel —
            # sem slippage, essa e' a diferenca de proposito frente a
            # `Enter` (que sempre paga `slippage_ticks` na abertura).
            # Persiste por varias barras (nao so a proxima), ate
            # tocar, expirar por `ttl_bars`, ou a sessao acabar.
            #
            # `self._resting_children_qty` (nao a existencia de posicao) e'
            # a guarda: uma ordem DIVIDIDA (`EnterLimit.split_quantities`)
            # continua tentando preencher os FILHOS restantes mesmo depois
            # de algum ja ter aberto posicao -- cada fill novo vira uma
            # posicao INDEPENDENTE em modo simulado (2026-08-24, pedido do
            # dono -- ver a docstring da classe), ou faz TOP-UP (soma
            # quantidade, recalcula preco medio ponderado) na UNICA posicao
            # agregada em execucao real, como antes.
            if self.resting_limit is not None and self._resting_children_qty:
                order = self.resting_limit
                fills, restantes = self._resolve_limit_fills(
                    order, self._resting_children_qty, bar,
                )
                if fills:
                    for fill_price, fill_qty in fills:
                        if not self._cabe_no_teto(fill_qty):
                            # Filho que nao cabe no teto e' recusado por
                            # INTEIRO e DESCARTADO (nao volta para
                            # `restantes`): deixa-lo parado o faria ser
                            # re-tentado e re-recusado a cada barra,
                            # inflando o contador com a MESMA ordem em vez
                            # de medir quantas ordens distintas o teto
                            # barrou.
                            events.append(self._recusa_por_teto(
                                ts, order.side, fill_qty, "limit"))
                            continue
                        self.ordens_aceitas += 1
                        if self.execution is not None and self.positions:
                            pos = self.positions[0]
                            nova_qty = pos.quantity + fill_qty
                            pos.entry_price = (
                                (pos.entry_price * pos.quantity + fill_price * fill_qty) / nova_qty
                            )
                            pos.quantity = nova_qty
                        else:
                            self.positions.append(_Position(
                                side=order.side,
                                entry_ts=ts,
                                entry_price=fill_price,
                                quantity=fill_qty,
                                current_stop=order.initial_stop,
                                current_target=order.initial_target,
                                metadata=dict(order.metadata or {}),
                                exit_split_unit=order.exit_split_unit,
                                exit_ttl_bars=order.exit_ttl_bars,
                            ))
                        events.append(PositionOpened(
                            ts=ts, side=order.side, price=fill_price,
                            quantity=fill_qty, stop=order.initial_stop,
                            target=order.initial_target, order_kind="limit",
                            reason=order.reason, bar=bar,
                        ))
                    self._resting_children_qty = restantes
                    if restantes:
                        # algum filho ainda espera -- ordem continua "fresca"
                        # (acabou de casar algo), nao acumula espera de TTL.
                        self.resting_limit_bars_waited = 0
                    else:
                        self.resting_limit = None
                        self.resting_limit_bars_waited = 0
                else:
                    self.resting_limit_bars_waited += 1
                    if order.ttl_bars is not None and self.resting_limit_bars_waited >= order.ttl_bars:
                        self.resting_limit = None
                        self._resting_children_qty = []
                        self.resting_limit_bars_waited = 0
                        events.append(LimitCancelled(order=order, ts=ts, reason="ttl"))

        # (5) decisao do robo para a PROXIMA barra — nao roda mais depois do flatten.
        if not self.flattened:
            self.strategy.on_capital_update(cfg.initial_capital + self.realized_pnl)
            actions = self.strategy.on_bar(ts, bar, self.positions_view(), self.session_pnl)
            for action in actions:
                if isinstance(action, AdjustStop):
                    # aplica a TODAS as posicoes abertas do lado -- nenhuma
                    # estrategia hoje tem mais de 1 posicao por vez, entao
                    # isto e' identico ao comportamento antigo para elas; uma
                    # futura estrategia multi-posicao decide 1 stop por
                    # posicao via `EnterLimit.initial_stop` na entrada, nao
                    # aqui.
                    for pos in self.positions:
                        if pos.current_stop is None:
                            pos.current_stop = action.new_stop
                        elif pos.side == "long" and action.new_stop >= pos.current_stop:
                            pos.current_stop = action.new_stop
                        elif pos.side == "short" and action.new_stop <= pos.current_stop:
                            pos.current_stop = action.new_stop
                elif isinstance(action, AdjustTarget):
                    for pos in self.positions:
                        pos.current_target = action.new_target
                elif isinstance(action, (Enter, Exit)):
                    self.pending = action
                    if self.resting_limit is not None:
                        # substitui qualquer ordem-limite pendente
                        events.append(LimitCancelled(order=self.resting_limit, ts=ts, reason="superseded"))
                    self.resting_limit = None
                    self._resting_children_qty = []
                    self.resting_limit_bars_waited = 0
                elif isinstance(action, EnterLimit) and not self.positions:
                    # substitui (nao acumula) qualquer ordem-limite ja pendente
                    events.append(LimitPlaced(order=action, ts=ts, replaced=self.resting_limit))
                    self.resting_limit = action
                    self.resting_limit_bars_waited = 0
                    self._resting_children_qty = action.children(cfg.default_quantity)

        for pos in self.positions:
            pos.bars_held += 1

        return events

    def discard_resting_limit(self) -> None:
        """Esquece a ordem-limite vigiada SEM emitir evento e SEM mandar
        cancelamento nenhum -- ela nunca chegou a existir no book.

        So' a operacao REAL usa, e para um caso so': a corretora RECUSOU o
        envio (`live/intraday_execution.py::BrokerExecutionError`, que so'
        sobe depois de cancelar as fatias ja enviadas -- nunca fica entrada
        pela metade). A maquina grava `resting_limit` ANTES do envio, entao
        uma recusa a deixava vigiando um fill impossivel: em 25/08/2026 o
        slot `dt-gremah_tick-pmam3-live` passou de 13:02 as 14:00 esperando
        uma ordem que o terminal tinha recusado (`AutoTrading disabled by
        client`), e so' voltou a mandar quando o proprio robo declarou a
        ordem obsoleta pelo relogio.

        `LimitCancelled` seria a ferramenta errada aqui: ele significa "uma
        ordem que ESTAVA no book saiu dele" e faz o chamador ao vivo mandar
        cancelamento para a corretora -- por uma ordem que ela recusou."""
        self.resting_limit = None
        self._resting_children_qty = []
        self.resting_limit_bars_waited = 0

    def force_flatten(self, ts: pd.Timestamp, price: float) -> list[MachineEvent]:
        """Achata a posicao (se houver) e cancela a ordem-limite vigiada, SEM
        consumir barra e sem consultar o robo.

        So a operacao ao vivo usa: quando o processo volta depois de um buraco
        grande de barras, reprocessar o buraco seria tomar decisoes velhas
        contra precos que ja passaram (regra 7 do AGENTS.md), e ignorar o
        buraco deixaria uma posicao real orfa. Achatar no preco mais recente
        e' a leitura honesta das duas coisas. No backtest nao existe buraco: a
        ultima barra da sessao ja dispara o flatten dentro de
        `on_closed_bar`."""
        eventos: list[MachineEvent] = []
        if self.positions:
            if self.execution is not None and any(p.exit_resting_qty > 0 for p in self.positions):
                self.execution.cancel_exit_limit(ts, reason="flatten")
            for pos in list(self.positions):
                pos.exit_resting_qty = 0
                pos.resting_exit_bars_waited = 0
                eventos.append(self._close_position(pos, ts, price, IntradayExitReason.FORCED_FLATTEN))
        if self.resting_limit is not None:
            eventos.append(LimitCancelled(order=self.resting_limit, ts=ts, reason="flatten"))
            self.resting_limit = None
        self._resting_children_qty = []
        self.resting_limit_bars_waited = 0
        self.pending = None
        self.flattened = True
        return eventos

    def _clear_stale_enter(self) -> None:
        """Invalida uma decisao `Enter` (mercado) filada quando UMA posicao
        acabou de fechar por stop/alvo -- decidida contra o mercado de ha'
        varias barras, executa-la so' porque uma posicao fechou agora seria
        descolado do presente (regra 7 do AGENTS.md). `Exit` NAO e' limpo
        aqui de proposito (2026-08-24): pode ter sido decidido para achatar
        VARIAS posicoes de uma vez (ex.: stop agregado de sessao,
        `gremah_tick.py`) -- so' e' consumido quando de fato executa
        (`on_closed_bar`, secao 3), nunca invalidado so' porque UMA posicao
        entre varias fechou seu proprio stop primeiro. Limpar aqui faria o
        robo nunca achatar as posicoes irmas quando ele mesmo ja parou de
        redecidir (sessao em `session_halted`, por exemplo)."""
        if isinstance(self.pending, Enter):
            self.pending = None

    def _cancelar_resting_orfa(self, ts: pd.Timestamp) -> Optional[LimitCancelled]:
        """Cancela o que sobrar de `resting_limit`/`_resting_children_qty`
        quando a posicao que os originou acabou de fechar (stop, alvo ou
        saida por sinal) -- so' pode existir aqui se a ordem veio DIVIDIDA
        (`EnterLimit.split_quantities`) e nem todos os filhos preencheram
        ainda: continuar tentando preencher os que sobraram abriria uma
        posicao NOVA e desconectada da que acabou de fechar, contra a
        intencao original do robo. Sem cap por volume isto nunca dispara --
        uma ordem nao dividida sempre preenche 100% de uma vez, entao
        `resting_limit` ja e' `None` no instante em que a posicao existe."""
        if self.resting_limit is None:
            return None
        order = self.resting_limit
        self.resting_limit = None
        self._resting_children_qty = []
        self.resting_limit_bars_waited = 0
        return LimitCancelled(order=order, ts=ts, reason="position_closed")

    # ---------- saida dividida em fatias, SIMULADA, com prazo (2026-08-23) --

    def _resolve_simulated_split_exit(
        self, ts: pd.Timestamp, bar: Bar, pos: _Position, orcamento: float,
    ) -> tuple[list[MachineEvent], float]:
        """Saida por ALVO dividida em fatias, SIMULADA (backtest/sombra), de
        UMA posicao (`pos`) -- espelha `_resolve_live_split_exit` (mesmo
        `exit_resting_qty`/`resting_exit_bars_waited`, agora campos de
        `_Position` em vez de globais da maquina desde 2026-08-24, mesma
        semantica de prazo), trocando a corretora por `bar.volume`/`bar.
        close`. Existe para o backtest poder PREVER o que a execucao real
        vai fazer com `EnterLimit.exit_ttl_bars` declarado, em vez de medir
        um cenario (espera ilimitada) que a execucao real nunca vai ter --
        mesmo motivo de toda esta maquina ser compartilhada entre os dois
        mundos. So' chamada quando `pos.exit_ttl_bars` esta declarado (ver
        `on_closed_bar`, item 1); sem prazo, `_resolve_target_partial_fill`
        (o caminho ANTIGO, ilimitado) continua servindo quem nao decidiu um
        prazo ainda. So' roda em modo SIMULADO (`self.execution is None`,
        ver `on_closed_bar`) -- nunca orfaniza `self._resting_children_qty`
        quando `pos` fecha: cada filho irmao ainda sem preencher vira sua
        PROPRIA posicao independente quando puder (pedido do dono
        2026-08-24, ver a docstring da classe), nunca uma tentativa
        "orfa" so' porque UMA posicao do grupo fechou.

        MESMA estrutura de `_resolve_live_split_exit`, de proposito -- checa
        primeiro a fatia JA posicionada (se houver), arma uma fatia NOVA so' no
        final. Isso da' ao arme o MESMO atraso estrutural de 1 barra que a
        execucao real tem (mandar a ordem e so' poder checar o fill dela na
        barra SEGUINTE): a fatia arma no primeiro toque do alvo mas nunca
        preenche na PROPRIA barra em que armou. Da'i em diante, preenche
        numa barra que TAMBEM toque o alvo E tenha volume suficiente para
        ela SOZINHA (FOK) -- nunca preenche pelo preco de uma barra que nem
        chegou perto do nivel. O prazo conta em TODA barra desde que armou,
        tocando ou nao (a ordem real ficaria no book esperando, nao so' nos
        instantes em que o preco volta a tocar). Estourado o prazo sem fill
        nenhum, fecha a MERCADO (`bar.close`) so' a FATIA que estava
        travada (`quantity_override`) -- se `pos` ja' nasceu com 1 lote so'
        (o caso comum desde o fatiamento de entrada de 2026-08-24), a fatia
        travada E' a posicao inteira, e este fechamento parcial vira, na
        pratica, um fechamento total dela. Se sobrar quantidade em `pos`
        (posicao maior que 1 lote), ela continua aberta e uma fatia NOVA
        arma do zero (prazo proprio) na proxima barra que tocar o alvo de
        novo -- mesma decisao do dono usada na execucao real ('prazo
        limitado, depois mercado'), agora aplicada por FATIA em vez de por
        posicao inteira. Stop e' sempre tudo-ou-nada e tem prioridade sobre
        o alvo numa barra ambigua, sem consultar `ambiguous_bar_resolution`
        -- mesma regra da execucao real, que tambem nao usa esse config.

        `orcamento`/retorno `(eventos, orcamento_restante)` (2026-08-24): o
        CHAMADOR (`on_closed_bar`) mantem um orcamento de volume UNICO da
        barra, compartilhado entre TODAS as posicoes avaliadas nela --
        antes so' existia 1 posicao por vez, entao ler `bar.volume` direto
        aqui dentro era seguro; com posicoes independentes, cada uma
        checando `bar.volume` por conta propria dobraria (ou N-plicaria) a
        liquidez real disponivel para preencher a saida."""
        assert pos.exit_split_unit is not None and pos.exit_ttl_bars is not None
        stop_hit, target_hit = _stop_target_touch(pos, bar)

        if stop_hit:
            pos.exit_resting_qty = 0
            pos.resting_exit_bars_waited = 0
            ref_price = _exit_fill_price(pos, bar, "stop")
            events: list[MachineEvent] = [self._close_position(pos, ts, ref_price, IntradayExitReason.STOP)]
            self._clear_stale_enter()
            return events, orcamento

        events = []
        if pos.exit_resting_qty > 0:
            if target_hit and orcamento >= pos.exit_resting_qty:
                fechado = pos.exit_resting_qty
                orcamento -= fechado
                ref_price = _exit_fill_price(pos, bar, "target")
                events.append(self._close_position(
                    pos, ts, ref_price, IntradayExitReason.TARGET, quantity_override=fechado,
                ))
                pos.exit_resting_qty = 0
                pos.resting_exit_bars_waited = 0
                if pos not in self.positions:  # fechou inteira agora
                    self._clear_stale_enter()
                # senao: fechou uma fatia, esta posicao (menor) continua
                # aberta -- a proxima fatia so' arma numa barra FUTURA que
                # tocar o alvo de novo (bloco abaixo, ja que `exit_resting_
                # qty == 0`).
            else:
                pos.resting_exit_bars_waited += 1
                if pos.resting_exit_bars_waited >= pos.exit_ttl_bars:
                    fechado = pos.exit_resting_qty
                    pos.exit_resting_qty = 0
                    pos.resting_exit_bars_waited = 0
                    events.append(self._close_position(
                        pos, ts, bar.close, IntradayExitReason.TARGET, quantity_override=fechado,
                    ))
                    if pos not in self.positions:  # essa fatia era o que sobrava
                        self._clear_stale_enter()
                    # senao: so' a fatia travada foi a mercado, esta posicao
                    # (menor) continua aberta -- a proxima fatia arma do
                    # zero (prazo proprio) na proxima barra que tocar o
                    # alvo de novo. Fechamento a MERCADO (estouro de prazo)
                    # nao disputa o orcamento de volume -- e' urgencia, nao
                    # preenchimento maker.
            return events, orcamento

        if target_hit:
            pos.exit_resting_qty = min(pos.exit_split_unit, pos.quantity)
            pos.resting_exit_bars_waited = 0

        return events, orcamento

    # ---------- saida dividida em execucao REAL (Fase 2, 2026-08-22) --------

    def _resolve_live_split_exit(self, ts: pd.Timestamp, bar: Bar, pos: _Position) -> list[MachineEvent]:
        """Saida por ALVO dividida em fatias, com EXECUCAO REAL -- reusa o
        mesmo padrao `ttl_bars`/`resting_limit_bars_waited` das ordens de
        entrada, do lado da saida (ver `EnterLimit.exit_ttl_bars`). So'
        chamada quando `self.execution is not None` e `pos.exit_split_unit
        is not None` (ver `on_closed_bar`, item 1) -- execucao real nunca
        tem mais de 1 elemento em `self.positions` (ver a docstring da
        classe), entao `pos` e' sempre a UNICA posicao aberta aqui.

        Stop continua tudo-ou-nada a MERCADO, sempre -- protecao/urgencia
        nao espera fatia nenhuma. O alvo arma UMA fatia por vez
        (`min(exit_split_unit, quantidade restante)`) como ordem-limite REAL
        na corretora; enquanto ela espera, cada barra pergunta a corretora
        (nao ao OHLC) se a posicao encolheu -- fill parcial ou total dessa
        fatia. Estourado `exit_ttl_bars` sem fill nenhum, cancela a fatia e
        fecha o QUE SOBRAR a MERCADO -- decisao do dono ('prazo limitado,
        depois mercado'): a posicao sempre fecha dentro de um tempo
        previsivel, nunca fica exposta indefinidamente esperando a fatia
        final."""
        assert pos.exit_split_unit is not None and self.execution is not None
        if pos.exit_ttl_bars is None:
            raise NotImplementedError(
                f"{self.strategy.symbol}: saida dividida (`exit_split_unit`) em "
                "execucao REAL exige `exit_ttl_bars` -- sem prazo a posicao ficaria "
                "exposta indefinidamente esperando a ultima fatia, contra a decisao "
                "do dono ('prazo limitado, depois mercado'). Declare "
                "`EnterLimit.exit_ttl_bars` na ordem que abriu a posicao."
            )
        events: list[MachineEvent] = []
        stop_hit, target_hit = _stop_target_touch(pos, bar)

        if stop_hit:
            if pos.exit_resting_qty > 0:
                self.execution.cancel_exit_limit(ts, reason="stop")
                pos.exit_resting_qty = 0
                pos.resting_exit_bars_waited = 0
            ref_price = _exit_fill_price(pos, bar, "stop")
            events.append(self._close_position(pos, ts, ref_price, IntradayExitReason.STOP))
            self.pending = None
            orfa = self._cancelar_resting_orfa(ts)
            if orfa is not None:
                events.append(orfa)
            return events

        if pos.exit_resting_qty > 0:
            fill = self.execution.exit_fill(pos.side, bar)
            if fill is not None:
                fechado = min(int(round(fill["quantity"])), pos.exit_resting_qty)
                events.append(self._close_position(
                    pos, ts, fill["price"], IntradayExitReason.TARGET,
                    quantity_override=fechado, already_filled_at=fill["price"],
                ))
                pos.exit_resting_qty -= fechado
                pos.resting_exit_bars_waited = 0
                if pos not in self.positions:  # ultima fatia (desta ou de outra rodada) fechou agora
                    self.pending = None
                    orfa = self._cancelar_resting_orfa(ts)
                    if orfa is not None:
                        events.append(orfa)
                # senao: fechou uma fatia, posicao (menor) continua aberta --
                # se `exit_resting_qty` ainda sobrar (fill parcial da propria
                # fatia), a MESMA ordem-limite continua vigiada; se zerou, a
                # proxima barra rearma outra fatia do zero (bloco `target_hit`
                # abaixo, ja que `exit_resting_qty == 0` de novo).
            else:
                pos.resting_exit_bars_waited += 1
                if pos.resting_exit_bars_waited >= pos.exit_ttl_bars:
                    self.execution.cancel_exit_limit(ts, reason="ttl")
                    pos.exit_resting_qty = 0
                    pos.resting_exit_bars_waited = 0
                    # fecha o RESTANTE a mercado -- ainda e' um exit de ALVO
                    # (a decisao continua sendo "sair no alvo"), so' que a
                    # ultima fatia nao esperou a vez dela na fila e saiu pelo
                    # caminho de urgencia.
                    events.append(self._close_position(pos, ts, bar.close, IntradayExitReason.TARGET))
                    self.pending = None
                    orfa = self._cancelar_resting_orfa(ts)
                    if orfa is not None:
                        events.append(orfa)
            return events

        if target_hit:
            fatia = min(pos.exit_split_unit, pos.quantity)
            self.execution.place_exit_limit(
                position_side=pos.side, quantity=fatia, limit_price=pos.current_target,
                current_position_qty=pos.quantity, ts=ts,
            )
            pos.exit_resting_qty = fatia
            pos.resting_exit_bars_waited = 0

        return events

    # ---------- preenchimento: simulado (backtest) ou real (corretora) ------

    def _resolve_limit_fills(
        self, order: EnterLimit, children_qty: list[int], bar: Bar,
    ) -> tuple[list[tuple[float, int]], list[int]]:
        """`(preenchimentos, filhos_restantes)` para a ordem-limite vigiada
        nesta barra. `preenchimentos`: uma entrada `(preco, quantidade)` por
        FILHO que preencheu -- pode ser mais de um na MESMA barra, se sobrar
        volume para varios. Ver `self.execution`.

        Backtest/sombra SEM cap (`limit_fill_capped_by_volume=False`):
        comportamento ANTIGO, inalterado -- toque preenche tudo de uma vez
        (a lista de filhos vira uma soma so', `split_quantities` fica sem
        efeito pratico: sem o cap nao ha' motivo nenhum para dividir).

        Backtest/sombra COM cap (`limit_fill_capped_by_volume=True`): cada
        filho so' preenche se sobrar volume REAL suficiente NESTA barra/tick
        para ele SOZINHO (FOK -- casa tudo ou nada, nunca parcial dentro de
        um filho). Processados na ORDEM declarada, o volume da barra e' um
        orcamento UNICO compartilhado entre eles: o primeiro filho que cabe
        consome esse orcamento antes do proximo ser testado -- e' por isso
        que pedacos MENORES tem mais chance de caber, mesmo quando o total
        pedido nao caberia inteiro.

        Real (2026-08-22, Fase 2 -- divisao de ordem de verdade na corretora):
        `self.execution.limit_fill` devolve o CRESCIMENTO da posicao desde a
        ultima checagem (delta, nao o total) -- porque `place_limit` da
        execucao ja manda um filho por elemento de `children_qty` como ordem
        REAL, e o motor nao precisa saber QUAL ticket preencheu, so' quanto
        cresceu (a corretora consolida tudo numa posicao so', ver
        `live/intraday_execution.py`). `children_qty` aqui e' tratado como
        UM POOL agregado (nao mais um filho por ordem real, ja que a
        corretora decide sozinha quais tickets casam e quando) -- o delta e'
        subtraido do total pendente e o restante volta como um unico item de
        lista, so' para o chamador continuar sabendo "ainda falta algo" (o
        `ttl_bars`/`resting_limit_bars_waited` do lado de fora nao muda).
        Uma falha em CONSULTAR a corretora nao vira "nao preencheu" (isso
        faria o robo re-armar sobre uma posicao que talvez ja exista) -- a
        excecao sobe de dentro de `limit_fill`."""
        if self.execution is not None:
            fill = self.execution.limit_fill(order, bar)
            if fill is None:
                return [], children_qty
            pendente_total = sum(children_qty)
            preenchido = min(int(round(fill["quantity"])), pendente_total)
            restante = pendente_total - preenchido
            return [(fill["price"], preenchido)], ([restante] if restante > 0 else [])

        if not _limit_touched(order, bar):
            return [], children_qty

        if not self.config.limit_fill_capped_by_volume:
            total = sum(children_qty)
            return ([(order.limit_price, total)] if total else []), []

        fills: list[tuple[float, int]] = []
        remaining: list[int] = []
        orcamento = bar.volume
        for qty in children_qty:
            if orcamento >= qty:
                fills.append((order.limit_price, qty))
                orcamento -= qty
            else:
                remaining.append(qty)
        return fills, remaining

    # ---------- fechamento -------------------------------------------------

    def _close_position(self, position: _Position, exit_ts: pd.Timestamp, exit_ref_price: float,
                        reason: IntradayExitReason,
                        quantity_override: int | None = None,
                        already_filled_at: float | None = None) -> PositionClosed:
        """Fecha (total ou parcialmente) `position` -- que precisa estar em
        `self.positions` (2026-08-24: cada posicao e' independente, entao o
        chamador diz QUAL fechar em vez de a maquina assumir "a" posicao).

        `quantity_override`: fecha so' uma FATIA da posicao (o resto
        continua aberto) -- existe para o alvo dividido (`EnterLimit.
        exit_split_unit`), onde o volume da barra (backtest/sombra) ou a
        fatia REAL (execucao ao vivo, ver `_resolve_live_split_exit`) pode
        cobrir menos do que a posicao inteira. `None` (todo o resto do
        motor) fecha tudo, comportamento antigo.

        `already_filled_at`: a fatia JA' preencheu na corretora (uma
        ordem-limite de saida que `_resolve_live_split_exit` estava
        vigiando) -- so' REGISTRA o trade nesse preco, sem mandar ordem
        nova nenhuma. `None` (todo o resto do motor, inclusive o alvo
        NAO dividido em execucao real) manda uma ordem de fechamento A
        MERCADO agora e usa o preco que a corretora de fato executou.

        Fechamento parcial (`quantity_override != position.quantity`) so'
        e' permitido em execucao REAL quando a posicao tem
        `exit_split_unit` declarado (o unico caminho com uma fatia REAL de
        verdade, ver `_resolve_live_split_exit`) -- qualquer outro
        fechamento parcial em execucao real seria mandar um tamanho que a
        corretora nunca confirmou, falha alto em vez disso."""
        cfg = self.config
        qty = position.quantity if quantity_override is None else quantity_override
        if self.execution is not None and qty != position.quantity and position.exit_split_unit is None:
            raise NotImplementedError(
                "fechamento parcial de posicao (EnterLimit.exit_split_unit) nao tem "
                "caminho de execucao real -- so' backtest/sombra, ver a docstring do campo."
            )
        is_maker_target = reason == IntradayExitReason.TARGET and cfg.target_fills_as_maker
        exec_px = (exit_ref_price if is_maker_target
                   else apply_intraday_slippage(exit_ref_price, _exit_side(position), cfg.costs))
        if already_filled_at is not None:
            exec_px = float(already_filled_at)
        elif self.execution is not None:
            # Execucao real: manda a ordem de fechamento AGORA e usa o preco
            # que a corretora executou, nao o estimado acima. Vem ANTES de
            # qualquer mutacao de estado de proposito -- se o envio falhar, a
            # excecao sobe com a posicao ainda aberta na maquina, coerente com
            # a posicao que continua aberta na corretora. Marcar como fechada
            # aqui e falhar depois deixaria as duas visoes divergentes, que e'
            # o pior estado possivel para um robo que decide sozinho.
            #
            # Sai a MERCADO inclusive no alvo (quando NAO ha' saida dividida
            # em andamento): `target_fills_as_maker` e' uma premissa de
            # MODELAGEM do backtest, e uma saida por alvo que dependesse de
            # nova ordem-limite poderia simplesmente nao preencher, deixando
            # a posicao aberta contra o proprio stop. O custo dessa diferenca
            # e' real e conhecido -- e' parte do que a corrida em sombra
            # existe para medir. `exit_market` fecha o RESTANTE da posicao
            # (`position.quantity`, ja' descontado de fatias anteriores que
            # tenham fechado por `already_filled_at`) -- coerente com `qty`
            # so' divergir de `position.quantity` quando `already_filled_at`
            # esta' setado (guarda acima).
            exec_px = float(self.execution.exit_market(position, exit_ts, reason)["price"])
        fees = fees_round_trip_brl(qty, position.entry_price, exec_px, cfg.costs)
        trade = IntradayTrade(
            symbol=self.strategy.symbol,
            strategy_name=self.strategy.name,
            strategy_version=self.strategy.version,
            side=position.side,
            entry_ts=position.entry_ts,
            entry_price=position.entry_price,
            exit_ts=exit_ts,
            exit_price=exec_px,
            quantity=qty,
            exit_reason=reason,
            point_value_brl=cfg.costs.point_value_brl,
            capital_base=cfg.initial_capital,
            fees_total=fees,
            slippage_total=abs(exec_px - exit_ref_price) * qty * cfg.costs.point_value_brl,
        )
        pnl = trade.pnl_brl
        self.session_pnl += pnl
        self.realized_pnl += pnl
        if qty >= position.quantity:
            self.positions.remove(position)
        else:
            position.quantity -= qty
        return PositionClosed(trade=trade, pnl_brl=pnl)
