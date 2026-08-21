"""Interface `IntradayStrategy` — contrato para robos de day trade.

Distinto de `strategy.base.Strategy` (nao herda dela) porque a cadencia e
outra: o robo diario decide UMA vez por pregao; um robo de day trade decide
BARRA A BARRA dentro da sessao, podendo abrir e fechar varias posicoes no
mesmo dia — nenhuma delas carrega para o dia seguinte (day trade nunca
mantem posicao overnight). Forcar isso no `Strategy` existente exigiria um
`on_bar` que significasse duas coisas diferentes para quem le o codigo.

Mesma disciplina anti-look-ahead do lado diario, em granularidade de
minuto: `AdjustStop`/`AdjustTarget` aplicam imediato (custo zero);
`Enter`/`Exit` sao enfileiradas pelo motor (`backtest.intraday.engine`) e
executam na ABERTURA da PROXIMA barra, nunca no fechamento da barra que
gerou a decisao.

Por construcao deliberada, `IntradayStrategy` NAO herda de
`strategy.base.Strategy`: isso o deixa fora do scan de
`strategy.discovery.discover_strategies` por natureza (o filtro exige
`issubclass(obj, Strategy)`) — um robo de futuro intradiario nao pode
competir no mesmo podio que um robo diario de acoes, sao capital/risco/
instrumento incomparaveis.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, Union

import pandas as pd


Side = Literal["long", "short"]


@dataclass
class Bar:
    ts: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class IntradayOpenPosition:
    """Snapshot read-only da posicao vista pelo robo em `on_bar` — espelha
    `strategy.base.OpenPosition`, com `side` (long/short — o diario so
    opera comprado) e `current_target` (o diario nao tem alvo, so stop)."""

    side: Side
    entry_ts: pd.Timestamp
    entry_price: float
    quantity: int
    current_stop: float | None
    current_target: float | None
    bars_held: int
    metadata: dict = field(default_factory=dict)


@dataclass
class Enter:
    """Acao: abrir posicao. `quantity=None` -> motor usa
    `IntradayBacktestConfig.default_quantity`."""

    side: Side
    initial_stop: float | None = None
    initial_target: float | None = None
    quantity: int | None = None
    metadata: dict | None = None
    reason: str = ""


@dataclass
class Exit:
    """Acao: fechar posicao a mercado por decisao do robo (nao stop, nao
    target, nao flatten forcado — esses tres o motor decide por conta
    propria, ver `core.models.IntradayExitReason`)."""

    reason: str = ""


@dataclass
class AdjustStop:
    """Motor so aceita se o novo stop for MAIS PROTETOR que o atual (para
    long: `new_stop >= current_stop`; para short: `new_stop <= current_stop`)
    — mesma regra de `strategy.base.AdjustStop` (stop nunca "afrouxa")."""

    new_stop: float


@dataclass
class AdjustTarget:
    """Sem restricao de direcao — diferente de `AdjustStop`, um alvo pode
    legitimamente ser alargado OU estreitado pelo robo (ex.: reduzir o alvo
    perto do fim da sessao para garantir realizacao)."""

    new_target: float


IntradayAction = Union[Enter, Exit, AdjustStop, AdjustTarget]


class IntradayStrategy(ABC):
    """Interface que todo robo de day trade implementa."""

    name: str
    version: str
    # Serie continua MT5 que este robo negocia. Verificado empiricamente
    # (2026-08-20, terminal da Clear, `scripts/daytrade/
    # verify_continuous_symbol.py`) que `WIN@` e `WIN$` sao BYTE-IDENTICOS
    # em toda a profundidade disponivel (~9 meses, atravessando 4+
    # rolagens de contrato) — nenhuma das duas familias aplica ajuste
    # sintetico neste terminal. `WIN@` fica como default por convencao
    # (nao ha diferenca real a escolher aqui); revalidar com o script se o
    # terminal/corretora mudar.
    symbol: str = "WIN@"

    def initialize(self, bars: pd.DataFrame) -> None:
        """Pre-calcula indicadores sobre TODO o historico do backtest.
        Chamado uma vez antes do loop de sessoes. Default vazio — robos sem
        estado podem computar tudo em `on_bar`."""

    def on_session_start(self, session_date) -> None:
        """Reseta estado por-dia (ex.: contador de perda diaria, numero de
        entradas ja feitas hoje). Default no-op."""

    @abstractmethod
    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        position: IntradayOpenPosition | None,
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        """Decisao para esta barra. Devolve acoes declarativas ao motor."""
