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

    # Lista branca (class attribute) dos atributos privados que precisam
    # sobreviver a um restart do processo ao vivo — ver `state()`/`restore()`
    # abaixo. Vazia por default: a maioria dos robôs não tem nada que precise
    # sobreviver a um restart (indicadores são recalculados por
    # `initialize()`). Só entra aqui o que MUDA a decisão futura e não pode
    # ser recomputado do histórico — ex.: `BuyTheDip._pending_rebalance`, o
    # adiamento de rotação por blackout de resultados. Nunca usar
    # `vars(self)` cru em `state()`: a família dip guarda `_scores`/
    # `_dist_from_high` (`dict[str, pd.Series]`), não serializáveis em JSON
    # e recalculados a cada `initialize()` — não precisam e não podem
    # sobreviver a um restart.
    _stateful_keys: tuple[str, ...] = ()

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

    def state(self) -> dict:
        """Estado a persistir para sobreviver a um restart do processo ao vivo.

        Genérico sobre `_stateful_keys` (lista branca), de propósito: NUNCA
        `vars(self)` cru — ver o comentário em `_stateful_keys` para o
        motivo (indicadores não-serializáveis que não deveriam sobreviver a
        restart de qualquer forma, porque `initialize()` os recalcula).
        Mesma convenção de `backtest.withdrawal.WithdrawalPolicy.state()`.
        """
        return {k: getattr(self, k) for k in self._stateful_keys}

    def restore(self, state: dict) -> None:
        """Reidrata o estado devolvido por `state()`.

        Ignora silenciosamente qualquer chave fora de `_stateful_keys` —
        estado de uma versão diferente da estratégia (ou de outro robô, ver
        `live.runtime._restore_robot_state`) não pode contaminar esta
        instância. Normaliza lista→tupla (o caminho real de persistência
        passa por JSON, que não tem tipo tupla — mesmo cuidado de
        `CircuitBreaker.restore()`/`WithdrawalPolicy.restore()`) e COAGE o
        tipo pelo valor atual do atributo (bool/int/float): sem isso,
        `_pending_rebalance` persistido como a string `"false"` seria
        truthy em Python e dispararia rotação fora de hora.
        """
        for k, v in state.items():
            if k not in self._stateful_keys:
                continue
            if isinstance(v, list):
                v = tuple(v)
            default = getattr(self, k, None)
            if isinstance(default, bool):
                # `bool("false")` é `True` em Python (string não-vazia) — o
                # motivo exato do achado C2. Interpreta a string pelo seu
                # conteúdo; qualquer valor não-string cai no `bool()` normal.
                v = v.strip().lower() not in ("false", "0", "") if isinstance(v, str) else bool(v)
            elif isinstance(default, int):
                v = int(v)
            elif isinstance(default, float):
                v = float(v)
            setattr(self, k, v)
