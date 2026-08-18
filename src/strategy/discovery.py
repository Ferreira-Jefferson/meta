"""Auto-descoberta de robôs.

Varre os módulos de `strategy/` e coleta toda classe concreta (instanciável
sem argumentos) que herda de `Strategy`. Isso é o que torna o ranking do
robôs disponíveis" automático:
o registry deixa de ser uma lista promovida manualmente e vira apenas
metadata de exibição sobre o que foi encontrado.

Cada robô concorre ao pódio automaticamente ao ser adicionado como um novo
arquivo em `strategy/` (uma classe por arquivo, por convenção do AGENTS.md).
Uma classe pode optar por ficar de fora do ranking automático (ex.: uma
classe-base usada só por composição) declarando `candidate = False`.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
from dataclasses import dataclass
from typing import Callable

import strategy as _strategy_pkg
from strategy.base import Strategy


@dataclass(frozen=True)
class DiscoveredStrategy:
    key: str          # Strategy.name — chave estável usada no diário e nas URLs
    cls: type
    factory: Callable[[], Strategy]


def _is_concrete_strategy(obj) -> bool:
    if not (inspect.isclass(obj) and issubclass(obj, Strategy) and obj is not Strategy):
        return False
    if inspect.isabstract(obj):
        return False
    if not getattr(obj, "candidate", True):
        return False
    # Precisa ser instanciável sem argumentos — todo robô do registry hoje
    # usa **kwargs com defaults, mas checamos para não quebrar em runtime.
    try:
        sig = inspect.signature(obj.__init__)
    except (TypeError, ValueError):
        return False
    for pname, p in list(sig.parameters.items())[1:]:  # pula 'self'
        if p.default is inspect.Parameter.empty and p.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            return False
    return True


def discover_strategies() -> list[DiscoveredStrategy]:
    """Importa todo módulo de `strategy/` e devolve as classes concretas achadas.

    Dedup por `name` (chave): se duas classes declararem o mesmo `name`,
    a primeira encontrada (ordem alfabética de módulo) vence — não deveria
    acontecer se cada robô mantiver `name` único, mas evita duplicar no pódio.
    """
    found: dict[str, DiscoveredStrategy] = {}
    pkg_path = _strategy_pkg.__path__
    for mod_info in sorted(pkgutil.iter_modules(pkg_path), key=lambda m: m.name):
        if mod_info.name in ("base", "registry", "discovery"):
            continue
        module = importlib.import_module(f"strategy.{mod_info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue  # só classes definidas neste módulo, não as importadas
            if not _is_concrete_strategy(obj):
                continue
            key = obj.name
            if key not in found:
                found[key] = DiscoveredStrategy(key=key, cls=obj, factory=obj)
    return sorted(found.values(), key=lambda d: d.key)
