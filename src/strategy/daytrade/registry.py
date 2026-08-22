"""Registry de robôs de DAY TRADE.

Registry PRÓPRIO, não `strategy.registry` (ver docstring de
`strategy/daytrade/base.py`): `IntradayStrategy` não herda de `Strategy` de
propósito, então `discover_strategies()` nem varre o pacote `daytrade`, e um
robô de um símbolo só não pode competir no mesmo pódio que um robô diário de
carteira (capital/risco/instrumento incomparáveis). Por isso este catálogo é
uma lista EXPLÍCITA, não uma descoberta automática — cada entrada é uma
decisão deliberada de "este robô está pronto para aparecer no painel", não
"toda classe que existir em algum arquivo".

O SÍMBOLO é propriedade do ROBÔ, não do slot (`core.config.Slot` não declara
símbolo nenhum desde 2026-08-21): dois robôs registrados aqui podem operar
símbolos diferentes, e o slot só empresta o caixa/conta/processo — quem
decide o que negociar é a instância escolhida. Isto substitui três cópias do
mesmo mapa `{"gremah": Gremah}` que existiam soltas em `scripts/run_live.py`,
`dashboard/live_service.py` e `dashboard/live_control.py`: um catálogo
declarado em três lugares é um catálogo que diverge quando um robô novo
entra em só dois deles.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass

from strategy.daytrade.base import IntradayStrategy
from strategy.daytrade.lab.gremah import Gremah

_ROBOTS: dict[str, type[IntradayStrategy]] = {
    Gremah.name: Gremah,
}


@dataclass(frozen=True)
class DaytradeRobotInfo:
    """Metadata de exibição de um robô de day trade — para o select do
    painel, sem precisar do terminal MT5 nem de conta criada."""

    key: str
    label: str
    symbol: str
    version: str
    description: str


def _description(cls: type) -> str:
    doc = inspect.getdoc(cls) or ""
    if not doc:
        return f"Robô {cls.__name__} (sem docstring)."
    primeira = doc.strip().splitlines()[0].strip(" .")
    return primeira + "."


def list_daytrade_robots() -> list[DaytradeRobotInfo]:
    """Um `DaytradeRobotInfo` por robô registrado, na ordem do registry.

    Instancia com os defaults de cada classe só para ler `.symbol` — leitura
    pura, sem I/O (mesmo espírito de `strategy.registry.list_strategies`)."""
    infos = []
    for key, cls in _ROBOTS.items():
        robo = cls()
        infos.append(DaytradeRobotInfo(
            key=key, label=key, symbol=robo.symbol,
            version=getattr(robo, "version", "0.1"),
            description=_description(cls),
        ))
    return infos


def get_daytrade_robot(key: str) -> IntradayStrategy:
    """Resolve um robô de day trade por chave, com os PARÂMETROS DEFAULT da
    classe — quem precisa de parâmetros diferentes instancia direto.

    `KeyError` (nunca um default silencioso) se a chave não existir: um id
    desconhecido chegando de form/CLI é catálogo desatualizado ou form
    adulterado, e escolher um robô por chute operaria dinheiro real com o
    robô errado."""
    if key not in _ROBOTS:
        raise KeyError(
            f"robô de day trade desconhecido: {key!r} — disponíveis: "
            f"{', '.join(sorted(_ROBOTS))}"
        )
    return _ROBOTS[key]()
