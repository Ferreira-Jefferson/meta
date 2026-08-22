"""UM formato de robô para a interface — swing e day trade no mesmo molde.

Por que este arquivo existe
---------------------------
A home e a página de detalhe nasceram para UM tipo de robô (swing, ranqueado
por capital final em três horizontes). Quando o day trade entrou, ele entrou
por fora: um segundo cabeçalho de página no meio da home, cartões com outra
anatomia e um link que ia para `/operacao` porque não existia página de
detalhe para ele. A tela contava a história do encanamento — dois registries,
dois motores — em vez de contar a história do sistema, que é "estes são os
robôs".

Aqui o encanamento é traduzido UMA vez: `catalog()` devolve cartões idênticos
em forma para os dois tipos, e `detail()` devolve uma ficha idêntica em forma.
O que difere de verdade (day trade não compete no pódio FULL/5Y/1Y, não tem
simulação de carteira na tela, tem símbolo fixo) vira CAMPO — `kind`,
`can_simulate`, `symbol` — em vez de virar outro template.

Camada: `dashboard/` é orquestração (ver AGENTS.md), a única que pode compor
features — e é exatamente o que este arquivo faz, juntando
`strategy.registry` com `strategy.daytrade.registry`. Nenhuma regra de
decisão mora aqui: só metadata de exibição, lida por introspecção das mesmas
classes que o backtest e a operação real rodam.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from strategy import registry as swing_registry

SWING = "swing"
DAYTRADE = "daytrade"

_KIND_LABEL = {SWING: "Swing", DAYTRADE: "Day trade"}


@dataclass(frozen=True)
class RobotCard:
    """Um robô como ele aparece numa grade. Mesma anatomia para os dois tipos."""

    key: str
    kind: str
    kind_label: str
    version: str
    description: str
    href: str
    # Pares (rótulo, valor) da linha de metadata do cartão. Lista, e não campos
    # fixos, porque o que caracteriza um robô de day trade (símbolo) não é o
    # que caracteriza um de swing (tamanho do universo) — forçar os dois no
    # mesmo par de colunas foi o que produziu cartões meio vazios.
    facts: tuple[tuple[str, str], ...] = ()
    in_ranking: bool = False


@dataclass(frozen=True)
class RobotDoc:
    """Ficha completa de um robô — o que a página `/strategies/<key>` mostra.

    `description` e `summary`/`example` vêm dos campos escritos PARA HUMANO na
    classe (`Strategy.tagline`/`plain_summary`/`plain_example`), nunca do
    docstring: o docstring fala de hipótese a priori, refutação e nome de
    parâmetro, o que é o assunto de quem mexe no código e ruído para quem só
    quer saber o que o robô faz com o dinheiro. Robô sem esses campos escritos
    mostra a falta na tela, em vez de cair no texto técnico.
    """

    key: str
    kind: str
    kind_label: str
    version: str
    description: str
    summary: tuple[str, ...] = ()   # parágrafos de prosa
    example: tuple[str, ...] = ()   # um caso concreto, em passos
    facts: tuple[tuple[str, str], ...] = ()
    blocks: tuple[tuple[str, tuple[str, ...]], ...] = ()  # (título, itens)
    params: list[tuple[str, str, str]] = field(default_factory=list)
    can_simulate: bool = False
    in_ranking: bool = False
    symbol: str = ""


def _blocks(
    signals: tuple[str, ...],
    entrada: tuple[str, ...],
    saida: tuple[str, ...],
    sizing: tuple[str, ...],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Só os blocos que TÊM conteúdo.

    Era daqui que vinha a pior parte da tela antiga: `entry_rules`/`exit_rules`
    /`sizing_rules` nunca eram preenchidos por ninguém (`StrategyInfo` os
    criava vazios e nada os populava), então três caixas com título e nada
    dentro apareciam em toda página de robô. Bloco sem conteúdo não é
    renderizado — a página encurta em vez de mentir que tem seções.
    """
    candidatos = (
        ("O que ele olha", signals),
        ("Quando compra", entrada),
        ("Quando vende", saida),
        ("Quanto compra, e o que custa", sizing),
    )
    return tuple((titulo, itens) for titulo, itens in candidatos if itens)


def _universo_label(tamanho: int) -> str:
    """`universe_size == 0` significa "usa a WATCHLIST default do engine", não
    "universo vazio" — ver `StrategyInfo.universe_size`."""
    return f"{tamanho} ativos" if tamanho else "watchlist"


def _swing_card(info: swing_registry.StrategyInfo, in_ranking: bool) -> RobotCard:
    return RobotCard(
        key=info.key,
        kind=SWING,
        kind_label=_KIND_LABEL[SWING],
        version=info.version,
        # Frase humana quando o robô tem uma escrita; a do docstring só como
        # último recurso (ver `RobotDoc`).
        description=info.tagline or info.description,
        href=f"/strategies/{info.key}",
        # Sem instanciar o robô: a grade da home abriria todo robô do catálogo
        # só para escrever uma linha de metadata.
        facts=(("Universo", _universo_label(info.universe_size)), ("Cadência", "mensal")),
        in_ranking=in_ranking,
    )


def _daytrade_cards() -> list[RobotCard]:
    """Cartões de day trade no MESMO formato dos de swing.

    A frase do cartão é a `tagline` humana do robô. Sem ela, cai no docstring
    via `registry.docstring_parts` (e não na descrição de
    `DaytradeRobotInfo`, que corta na primeira LINHA do docstring, quebra de
    72 colunas incluída — num catálogo lado a lado isso aparece como um cartão
    com frase truncada ao lado de um com frase inteira).
    """
    from strategy.daytrade.registry import get_daytrade_robot, list_daytrade_robots

    cartoes = []
    for info in list_daytrade_robots():
        cls = type(get_daytrade_robot(info.key))
        curta = getattr(cls, "tagline", "") or swing_registry.docstring_parts(cls)[0]
        cartoes.append(RobotCard(
            key=info.key,
            kind=DAYTRADE,
            kind_label=_KIND_LABEL[DAYTRADE],
            version=info.version,
            description=curta,
            href=f"/strategies/{info.key}",
            facts=(("Ativo", info.symbol), ("Cadência", "intradiária")),
            in_ranking=False,
        ))
    return cartoes


def catalog(ranking_keys: frozenset[str] | None = None) -> list[RobotCard]:
    """Todo robô operável do sistema, swing e day trade, no mesmo formato.

    Ordem: swing primeiro (é quem disputa o pódio logo acima na home), day
    trade depois. `ranking_keys` marca quem compete no ranking automático —
    passado de fora porque quem sabe disso é o diário, não o catálogo.
    """
    ranking = ranking_keys or frozenset()
    cartoes = [
        _swing_card(info, info.key in ranking)
        for info in swing_registry.list_strategies()
    ]
    cartoes += _daytrade_cards()
    return cartoes


def _swing_doc(key: str, in_ranking: bool) -> RobotDoc:
    info = swing_registry.get_strategy(key)
    # Instancia UM robô (o desta página) para a tabela de parâmetros mostrar o
    # valor EFETIVO e não o da assinatura — ver `registry.declared_params`.
    obj = info.factory()
    return RobotDoc(
        key=info.key,
        kind=SWING,
        kind_label=_KIND_LABEL[SWING],
        version=info.version,
        description=info.tagline or info.description,
        summary=info.plain_summary,
        example=info.plain_example,
        facts=(
            ("Cadência", "decide no fim do mês"),
            ("Posições", str(getattr(obj, "top_n", "—"))),
            ("Universo", _universo_label(info.universe_size)),
        ),
        blocks=_blocks(
            info.watched_signals, info.entry_rules, info.exit_rules, info.sizing_rules
        ),
        params=swing_registry.declared_params(obj),
        can_simulate=True,
        in_ranking=in_ranking,
    )


def _daytrade_doc(key: str) -> RobotDoc:
    from strategy.daytrade.registry import get_daytrade_robot

    robo = get_daytrade_robot(key)  # instância com os defaults da classe
    cls = type(robo)
    return RobotDoc(
        key=key,
        kind=DAYTRADE,
        kind_label=_KIND_LABEL[DAYTRADE],
        version=getattr(robo, "version", "0.1"),
        description=(getattr(cls, "tagline", "")
                     or swing_registry.docstring_parts(cls)[0]),
        summary=tuple(getattr(cls, "plain_summary", ()) or ()),
        example=tuple(getattr(cls, "plain_example", ()) or ()),
        facts=(
            ("Ativo", getattr(robo, "symbol", "—")),
            ("Cadência", "barra a barra"),
            ("Overnight", "nunca"),
        ),
        blocks=_blocks(
            tuple(getattr(cls, "watched_signals", ()) or ()),
            tuple(getattr(cls, "entry_rules", ()) or ()),
            tuple(getattr(cls, "exit_rules", ()) or ()),
            tuple(getattr(cls, "sizing_rules", ()) or ()),
        ),
        params=swing_registry.declared_params(robo),
        # Day trade não roda o motor de carteira do formulário de simulação
        # (`dashboard/simulate.py` monta backtest diário sobre a watchlist). A
        # página dele mostra a ficha e manda para `/operacao`, em vez de
        # oferecer um botão que rodaria o motor errado.
        can_simulate=False,
        in_ranking=False,
        symbol=getattr(robo, "symbol", ""),
    )


def detail(key: str, ranking_keys: frozenset[str] | None = None) -> RobotDoc | None:
    """Ficha do robô, seja ele de swing ou de day trade. `None` = não existe.

    Tenta o registry de swing primeiro e cai para o de day trade — os dois
    levantam `KeyError` em chave desconhecida (nunca default silencioso), então
    a ordem aqui é só preferência de busca, não fallback perigoso.
    """
    try:
        return _swing_doc(key, key in (ranking_keys or frozenset()))
    except KeyError:
        pass
    try:
        return _daytrade_doc(key)
    except KeyError:
        return None
