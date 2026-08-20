"""Registry de robôs — gerado automaticamente por `discovery.discover_strategies()`.

Antes desta versão, o TOP-3 era uma lista curada manualmente (3 entradas fixas
com métricas hardcoded no docstring). Isso quebrava o requisito de o sistema
identificar sozinho quem está no pódio: promover um robô era um passo manual
que alguém podia esquecer de fazer, e as métricas escritas aqui congelavam no
dia da promoção mesmo que os dados de mercado avançassem.

Agora TODO robô concreto em `strategy/` é candidato automaticamente (ver
`discovery.py`). Este módulo só monta a metadata de exibição (nome legível,
descrição, parâmetros) por introspecção da classe — o RANKING de quem é
TOP-3 é calculado a partir do diário por
`journal.reader.top_strategies_by_final_capital()`, alimentado por
`scheduler.refresh_champion_rankings()`.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Callable

from strategy.base import Strategy
from strategy.discovery import discover_strategies


@dataclass(frozen=True)
class StrategyInfo:
    key: str
    name: str
    version: str
    description: str
    factory: Callable[[], Strategy]
    long_description: str = ""
    entry_rules: list[str] = field(default_factory=list)
    exit_rules: list[str] = field(default_factory=list)
    sizing_rules: list[str] = field(default_factory=list)
    params: list[tuple[str, str, str]] = field(default_factory=list)


def _docstring_parts(cls: type) -> tuple[str, str]:
    """(descrição curta, descrição longa) a partir do docstring da classe."""
    doc = inspect.getdoc(cls) or ""
    if not doc:
        return (f"Robô {cls.__name__} (sem docstring).", "")
    lines = [l.strip() for l in doc.strip().splitlines()]
    short = lines[0].strip(" .") + "."
    long = "<br>".join(l for l in lines if l)
    return short, long


def _params_from_init(cls: type) -> list[tuple[str, str, str]]:
    """Extrai (nome, valor-default, "") assinando o `__init__` da classe.

    Só reflete os defaults declarados diretamente nesta classe — parâmetros
    absorvidos via `**kwargs` de uma classe-pai (ex.: `kwargs.setdefault(...)`)
    não aparecem aqui; ver `long_description` para a explicação em prosa.
    """
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return []
    out = []
    for pname, p in list(sig.parameters.items())[1:]:
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if p.default is inspect.Parameter.empty:
            continue
        out.append((pname, repr(p.default), ""))
    return out


def _build_registry() -> dict[str, StrategyInfo]:
    """Tudo que existe em `strategy/`, INCLUSIVE o que foi aposentado do pódio.

    A separação importa: `REGISTRY` serve para RESOLVER uma chave em objeto, e
    `list_strategies()` serve para dizer quem disputa o ranking. Se as duas
    fossem a mesma coisa, aposentar um robô (`candidate = False`) faria
    `get_strategy()` levantar `KeyError` para toda conta ao vivo que já opera
    esse robô — e uma decisão de curadoria de pódio derrubaria uma operação
    real. Ver `discovery.discover_strategies(include_retired=True)`.
    """
    reg: dict[str, StrategyInfo] = {}
    for d in discover_strategies(include_retired=True):
        short, long = _docstring_parts(d.cls)
        reg[d.key] = StrategyInfo(
            key=d.key,
            name=d.key,
            version=getattr(d.cls, "version", "1.0"),
            description=short,
            long_description=long or short,
            params=_params_from_init(d.cls),
            factory=d.factory,
        )
    return reg


REGISTRY: dict[str, StrategyInfo] = _build_registry()


def candidate_keys() -> frozenset[str]:
    """Chaves que disputam o ranking automático (`candidate = True`)."""
    return frozenset(d.key for d in discover_strategies())


def list_strategies() -> list[StrategyInfo]:
    """Só os candidatos — é isto que alimenta o pódio e o refresh do diário.

    Robô aposentado continua em `REGISTRY` (resolvível por chave), mas some
    daqui: não é rerrodado, não entra no ranking, não aparece como opção nova.
    """
    candidatos = candidate_keys()
    return [i for i in REGISTRY.values() if i.key in candidatos]


def list_all_strategies() -> list[StrategyInfo]:
    """Todos, aposentados inclusive — para telas de histórico e diagnóstico."""
    return list(REGISTRY.values())


def get_strategy(key: str) -> StrategyInfo:
    if key not in REGISTRY:
        raise KeyError(f"Estratégia desconhecida: {key}")
    return REGISTRY[key]
