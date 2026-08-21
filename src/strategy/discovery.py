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


def _is_concrete_strategy(obj, include_retired: bool = False) -> bool:
    if not (inspect.isclass(obj) and issubclass(obj, Strategy) and obj is not Strategy):
        return False
    if inspect.isabstract(obj):
        return False
    if not include_retired and not getattr(obj, "candidate", True):
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


# `strategy/lab/` é o sandbox da busca de swing (ver `scripts/swing_lab/` e
# `scripts/run_vault_verdict.py`) e NAO e varrido por padrao — uma hipotese
# de busca so chega ao podio automatico se alguem promove-la aqui, de forma
# explicita e auditavel, depois do escrutinio que o veredito do cofre exige.
# Um `pkgutil.walk_packages` recursivo abriria a porta pra qualquer uma das
# hipoteses (inclusive as que reprovaram) por acidente; esta lista e o
# oposto disso: cada entrada e uma decisao, nao um efeito colateral de scan.
#
# HISTORICO — sintese_02_iliquidez_grupo_risco_orcado (promovida 2026-08-20)
# e liquid_focus (fee_capacity/hip_01, promovido 2026-08-21) passaram por
# este mecanismo e foram APOSENTADAS/DESPROMOVIDAS em 2026-08-21 (ver o
# proprio arquivo de cada uma) — nao por desempenho, mas porque o dono do
# capital decidiu reduzir o podio a UM robo so. liquid_dual10 (em
# `strategy/liquid_dual10.py`, fora desta lista) foi aposentado no mesmo
# dia pelo mesmo motivo.
#
# liqflop, ex-liquid_focus_loss_pause (fee_capacity/hip_03) — UNICO candidato desde
# 2026-08-21. Holdout de 48 janelas no regime R$100+taxa fixa real da Rico
# melhora `liquid_focus` em toda metrica (ver docstring da classe) — mesma
# ressalva declarada de regime (podio roda R$1.000 sem taxa fixa) segue
# valendo, aceita explicitamente pelo dono do capital.
_PROMOTED_LAB_MODULES: tuple[str, ...] = (
    "strategy.lab.fee_capacity.hip_03_pausa_apos_perdas",
)


def discover_strategies(include_retired: bool = False) -> list[DiscoveredStrategy]:
    """Importa todo módulo de `strategy/` e devolve as classes concretas achadas.

    Dedup por `name` (chave): se duas classes declararem o mesmo `name`,
    a primeira encontrada (ordem alfabética de módulo) vence — não deveria
    acontecer se cada robô mantiver `name` único, mas evita duplicar no pódio.

    `include_retired=True` traz também as classes com `candidate = False`. Isso
    existe para RESOLVER uma chave, nunca para ranquear: uma conta ao vivo que
    já opera um robô aposentado (`portfolio_dip2_hw40`, por exemplo) precisa
    continuar conseguindo instanciá-lo, senão aposentar um robô do pódio
    derrubaria uma operação real em produção. Quem monta pódio usa o default.

    Alem de `strategy/`, importa tambem `_PROMOTED_LAB_MODULES` — a lista
    explicita de hipoteses de `strategy/lab/` promovidas ao podio.
    """
    found: dict[str, DiscoveredStrategy] = {}
    pkg_path = _strategy_pkg.__path__
    modulos = [f"strategy.{m.name}" for m in sorted(pkgutil.iter_modules(pkg_path), key=lambda m: m.name)
               if m.name not in ("base", "registry", "discovery", "daytrade")]
    modulos += list(_PROMOTED_LAB_MODULES)
    for mod_name in modulos:
        module = importlib.import_module(mod_name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue  # só classes definidas neste módulo, não as importadas
            if not _is_concrete_strategy(obj, include_retired):
                continue
            key = obj.name
            if key not in found:
                found[key] = DiscoveredStrategy(key=key, cls=obj, factory=obj)
    return sorted(found.values(), key=lambda d: d.key)
