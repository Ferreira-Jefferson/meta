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

import html
import inspect
import re
from dataclasses import dataclass, field
from typing import Any, Callable

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
    # Tamanho do universo DECLARADO na classe (`universe_tickers`); 0 = o robô
    # não declara universo próprio e o engine usa a `WATCHLIST` default. Fica
    # aqui, resolvido no import, para uma grade de catálogo não precisar
    # instanciar todo robô só para escrever "63 ativos" num cartão.
    universe_size: int = 0
    watched_signals: tuple[str, ...] = ()
    entry_rules: tuple[str, ...] = ()
    exit_rules: tuple[str, ...] = ()
    sizing_rules: tuple[str, ...] = ()
    params: list[tuple[str, str, str]] = field(default_factory=list)


_INLINE_CODE = re.compile(r"`([^`\n]+)`")


def inline_html(texto: str) -> str:
    """Uma frase da ficha técnica virando HTML seguro.

    Escapa TUDO primeiro (o texto vem de docstring/atributo de classe, mas a
    página o injeta com `|safe` — escapar aqui é o que torna esse `|safe`
    defensável) e só depois traduz `crase` em `<code>`.
    """
    seguro = html.escape(texto, quote=False)
    return _INLINE_CODE.sub(r"<code>\1</code>", seguro)


def docstring_parts(cls: type) -> tuple[str, str]:
    """(descrição curta, HTML da descrição longa) a partir do docstring.

    A longa vira PARÁGRAFOS de verdade (linha em branco separa um do outro),
    não um bloco único emendado por `<br>`: o docstring de um robô desta base
    é prosa técnica de várias ideias, e emendar tudo numa linha era metade do
    motivo pela qual a página parecia despejo de texto.
    """
    doc = inspect.getdoc(cls) or ""
    if not doc:
        return (f"Robô {cls.__name__} (sem docstring).", "")
    linhas = [l.strip() for l in doc.strip().splitlines()]
    paragrafos: list[list[str]] = [[]]
    for linha in linhas:
        if linha:
            paragrafos[-1].append(linha)
        elif paragrafos[-1]:
            paragrafos.append([])
    long = "".join(
        f"<p>{inline_html(' '.join(p))}</p>" for p in paragrafos if p
    )
    # A curta é a primeira FRASE, não a primeira LINHA: um docstring quebrado
    # em 72 colunas cortava no meio da oração ("…; ancora rolante.") e virava
    # um resumo que não se entende sozinho, justamente onde ele aparece só —
    # no cartão do catálogo.
    primeiro = " ".join(paragrafos[0]) if paragrafos and paragrafos[0] else linhas[0]
    corte = primeiro.find(". ")
    short = (primeiro[:corte] if corte > 0 else primeiro).strip(" .") + "."
    return short, long


def _param_names(cls: type) -> list[str]:
    """Nomes dos parâmetros de `__init__` ao longo de TODO o MRO.

    Percorrer o MRO importa numa família por herança: `liqflop` declara dois
    parâmetros no `__init__` dele e herda oito (dip, histerese, universo,
    liquidez) — mostrar só os dois dava uma ficha que parecia incompleta
    porque estava.
    """
    nomes: list[str] = []
    for klass in reversed(cls.__mro__):
        init = klass.__dict__.get("__init__")
        if init is None:
            continue
        try:
            sig = inspect.signature(init)
        except (TypeError, ValueError):
            continue
        for pname, p in list(sig.parameters.items())[1:]:
            if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            if p.default is inspect.Parameter.empty:
                continue
            if pname not in nomes:
                nomes.append(pname)
    return nomes


def _param_docs(cls: type) -> dict[str, str]:
    """`param_docs` mesclado ao longo do MRO — a classe mais derivada ganha."""
    docs: dict[str, str] = {}
    for klass in reversed(cls.__mro__):
        docs.update(klass.__dict__.get("param_docs") or {})
    return docs


def _formata_valor(v: Any) -> str:
    if isinstance(v, bool) or v is None:
        return {True: "sim", False: "não", None: "—"}[v]
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, (list, tuple)):
        return f"{len(v)} itens"
    return str(v)


def declared_params(obj: Any) -> list[tuple[str, str, str]]:
    """(nome, valor EFETIVO, descrição) de uma INSTÂNCIA já construída.

    Lê o valor do objeto, não da assinatura, e é por isso que recebe instância
    em vez de classe: nesta família a folha reescreve o default da raiz por
    `kwargs.setdefault` (`DipTop1Portfolio` põe `dip_pct=0.02` sobre o 0.03 de
    `BuyTheDip`). Uma ficha lendo a assinatura anunciaria 3% para um robô que
    opera 2% — e um número errado na tela é pior que número nenhum.
    """
    cls = type(obj)
    docs = _param_docs(cls)
    linhas = []
    for nome in _param_names(cls):
        if not hasattr(obj, nome):
            continue  # parâmetro consumido no __init__ e não guardado
        linhas.append((nome, _formata_valor(getattr(obj, nome)), docs.get(nome, "")))
    return linhas


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
        short, long = docstring_parts(d.cls)
        reg[d.key] = StrategyInfo(
            key=d.key,
            name=d.key,
            version=getattr(d.cls, "version", "1.0"),
            description=short,
            long_description=long or f"<p>{inline_html(short)}</p>",
            universe_size=len(getattr(d.cls, "universe_tickers", None) or ()),
            # Ficha técnica declarada na classe (ver `Strategy.entry_rules` em
            # `strategy/base.py`) — herdada pela linhagem, então uma variante
            # que só troca um parâmetro já vem documentada.
            watched_signals=tuple(getattr(d.cls, "watched_signals", ()) or ()),
            entry_rules=tuple(getattr(d.cls, "entry_rules", ()) or ()),
            exit_rules=tuple(getattr(d.cls, "exit_rules", ()) or ()),
            sizing_rules=tuple(getattr(d.cls, "sizing_rules", ()) or ()),
            # `params` aqui fica pela ASSINATURA (barato, roda no import de
            # todo robô do catálogo). A ficha da página usa
            # `declared_params(instância)`, que é exata mas precisa construir
            # o objeto — ver a docstring de lá.
            params=[(n, "", "") for n in _param_names(d.cls)],
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
