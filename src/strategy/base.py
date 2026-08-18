"""Interface Strategy — event-driven, adaptativa.

Cada robô recebe o gatilho (o bar atual + estado da carteira) e devolve **ações
declarativas** que o engine executa: `Enter`, `Exit`, `AdjustStop`. Assim cada
estratégia é dona da sua própria política de entrada, saída e ajuste de stop
(fixo, trailing por ATR, canal Donchian, banda mediana etc.) — o engine só
coordena calendário, custos, sizing e diário.

Contrato:
- `initialize(panels, ibov)` é chamado uma vez com todo o histórico do universo.
  O robô pré-calcula os indicadores que quiser e guarda como estado.
- `on_bar(date, open_positions, cash_available)` é chamado a cada pregão.
  O robô devolve `list[Action]` — pode devolver lista vazia (rebalance mensal ignora
  os outros dias).
- As ações são **enfileiradas** pelo engine: `Enter`/`Exit` executam na abertura
  do próximo pregão (anti-look-ahead); `AdjustStop` é aplicado imediatamente
  (custo zero, só atualiza o stop registrado).
- Stops disparam intra-bar: se `low[D] <= current_stop`, o engine emite um
  `Exit(reason=STOP)` automático no próprio dia — sem esperar a decisão do robô.

Este contrato é portável a MQL5: `initialize()` vira `OnInit`, `on_bar()` vira
`OnTick` com timeframe D1.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Union

import pandas as pd

from core.models import ExitReason


@dataclass
class OpenPosition:
    """Snapshot da posição vista pelo robô no momento do `on_bar`."""

    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    quantity: int
    current_stop: float | None
    bars_held: int
    metadata: dict = field(default_factory=dict)


@dataclass
class Enter:
    """Ação: abrir posição comprada.

    - `initial_stop`: preço absoluto onde o robô quer parar caso o trade vire.
      Se `None`, o engine assume que não há stop e a posição só será fechada
      por `Exit` explícito.
    - `size_hint`: fração do caixa disponível a alocar (0..1). Se `None`,
      o engine aplica o default (caixa dividido pelos slots livres).
    - `metadata`: livre para o robô salvar contexto (ex.: banda no dia da
      entrada, ATR estimado). Fica preservado em `OpenPosition.metadata` para
      o robô consultar em `on_bar`.
    """

    ticker: str
    initial_stop: float | None = None
    size_hint: float | None = None
    metadata: dict | None = None


@dataclass
class Exit:
    """Ação: fechar posição. Deve levar um `ExitReason` para o diário."""

    ticker: str
    reason: ExitReason


@dataclass
class AdjustStop:
    """Ação: mover o stop registrado para `new_stop`.

    O engine só aceita se `new_stop >= current_stop` (stop nunca desce).
    Custo zero — é uma atualização de estado.
    """

    ticker: str
    new_stop: float


Action = Union[Enter, Exit, AdjustStop]


class Strategy(ABC):
    """Interface event-driven que todos os robôs implementam."""

    name: str
    version: str
    # Universo próprio do robô. Se None, engine usa WATCHLIST default.
    # Permite robôs experimentais escolherem seus tickers (setor bancário,
    # universo largo, etc.) sem mexer nos canonicals.
    universe_tickers: tuple[str, ...] | None = None

    def initialize(self, panels: dict[str, pd.DataFrame], ibov: pd.DataFrame) -> None:
        """Pré-calcula indicadores sobre o histórico completo.

        Chamado uma vez pelo engine antes do loop de datas. O robô deve
        guardar `panels`, `ibov` e quaisquer indicadores derivados como
        atributos de instância para consultar em `on_bar`.

        Implementação padrão vazia — robôs sem estado podem simplesmente
        computar tudo em `on_bar` (não recomendado por performance).
        """

    @abstractmethod
    def on_bar(
        self,
        date: pd.Timestamp,
        open_positions: dict[str, OpenPosition],
        cash_available: float,
    ) -> list[Action]:
        """Decisão do dia. Devolve ações declarativas ao engine."""
