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
from functools import lru_cache

from strategy import registry as swing_registry

SWING = "swing"
DAYTRADE = "daytrade"

_KIND_LABEL = {SWING: "Swing", DAYTRADE: "Day trade"}


def _formata_quantidade_em_lotes(nome: str, valor: str) -> str:
    """`quantity` (ações por ordem) em LOTES -- "1 lote (100 ações)" em vez
    do número cru de ações, que sozinho não diz se é 1 lote ou uma fração
    dele. Vazio (`quantity=None`) usa o mesmo padrão que todo perfil e o
    executor ao vivo já usam hoje (`LOTE_PADRAO_B3`) -- day trade nunca opera
    fracionário (custaria R$1,90 fixos por ordem na Rico)."""
    if nome != "quantity":
        return valor
    from strategy.daytrade.base import LOTE_PADRAO_B3

    acoes = LOTE_PADRAO_B3 if valor == "—" else int(valor)
    lotes = acoes / LOTE_PADRAO_B3
    lotes_str = f"{lotes:g}".replace(".", ",")
    return f"{lotes_str} lote{'' if lotes == 1 else 's'} ({acoes} ações)"


@dataclass(frozen=True)
class RobotAsset:
    """Um ativo operável do robô, com os números QUE MUDAM de um para outro.

    Existe por causa de um erro que a ficha do `gremah` cometia: ele aceita
    três ativos, cada um com alvo, stop e caixa mínimo próprios (a calibração
    não transfere entre símbolos — ver `strategy/daytrade/lab/gremah.py`), mas
    a página mostrava um só. A tabela de parâmetros, que exibe UMA instância,
    anunciava o alvo da PMAM3 como se fosse "o alvo do robô".

    `price`/`lot_cost`/`min_capital` são `None` quando não há dado de minuto
    salvo para o ativo: o caixa mínimo depende do preço de hoje, e a página
    mostra a falta em vez de inventar um número.

    `alvo_por_volatilidade`/`alvo_vol_mult`/`stop_vol_mult` (2026-08-23):
    quando ligado, `profit_pct`/`stop_multiplier` acima são só FALLBACK
    (usados quando a janela de volatilidade ainda não tem dado) — não o que
    decide o alvo no dia a dia. Mostrar o percentual como se fosse o número
    ativo seria a MESMA mentira que este dataclass foi criado para evitar
    (ver o histórico acima) — só que entre modos de dimensionar, não entre
    ativos. `robot_view` decide qual dos dois mostrar a partir destes
    campos, nunca inventa por conta própria."""

    symbol: str
    profit_pct: float
    stop_multiplier: float
    alvo_por_volatilidade: bool = False
    alvo_vol_mult: float | None = None
    stop_vol_mult: float | None = None
    price: float | None = None
    price_date: str = ""
    lot_cost: float | None = None
    min_capital: float | None = None
    # `True` para um robô de FUTURO (`IntradayStrategy.is_futuro`) -- muda a
    # LEITURA da ficha, não só o número: não há "lote" (é margem por
    # contrato) e alvo/stop são ticks, não % do preço. `profit_pct`/
    # `stop_multiplier` acima ficam 0.0 quando isto é `True` (ver `_asset`)
    # -- o template lê ESTE campo primeiro para nunca confundir "0.0%" com
    # um alvo real de 0%.
    is_futuro: bool = False
    profit_ticks: int | None = None
    stop_ticks: int | None = None


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
    # (nome, valor, nota, descrição) — ver `registry.declared_params`.
    params: list[tuple[str, str, str, str]] = field(default_factory=list)
    # Ativos com números PRÓPRIOS por ativo (ver `RobotAsset`). Vazio para os
    # robôs de swing: eles decidem sobre uma lista inteira e o que caracteriza
    # o universo deles já está em `facts`.
    assets: tuple[RobotAsset, ...] = ()
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


def _preco_key(symbol: str) -> tuple[str, float, int]:
    """Chave de cache do preço: identidade do ARQUIVO, não só o símbolo.

    Sem o `mtime` no meio, o cache serviria o preço da primeira renderização
    para sempre e o caixa mínimo da página envelheceria calado enquanto o
    download de minuto continuasse rodando.

    O CAMINHO tem de ser o MESMO que `market_data_intraday.storage.
    last_close` (chamado por `_ultimo_preco_cached` abaixo) de fato lê --
    daí o `_parquet_path` importado de lá em vez de reconstruído aqui.
    Symbol com `@`/`$` (futuro: `WDO@`) sem essa sanitização aponta para um
    arquivo que nunca existe (`WDO@.parquet` != `WDO_A_.parquet`),
    `caminho.stat()` sempre cai no `except`, e o cache fica TRAVADO na
    chave `(symbol, 0.0, 0)` para sempre -- exatamente o problema que este
    `mtime` existe para evitar, só que sem o sintoma aparecer, porque até
    2026-08-27 nenhum robô de futuro passava por aqui (achado ao promover a
    `wdo_grid_reload_maker` ao painel)."""
    from market_data_intraday.storage import _parquet_path

    caminho = _parquet_path(symbol)
    try:
        st = caminho.stat()
        return (symbol, st.st_mtime, st.st_size)
    except OSError:
        return (symbol, 0.0, 0)


@lru_cache(maxsize=64)
def _ultimo_preco_cached(key: tuple[str, float, int]) -> tuple[float | None, str]:
    symbol, mtime, _ = key
    if not mtime:
        return (None, "")
    # A leitura em si mora em `market_data_intraday.storage.last_close` — o
    # processo de cada robô ao vivo precisa do MESMO número (ver a docstring
    # de lá). Aqui fica só o cache por mtime, que é do painel: a ficha é
    # repintada a cada poll e reler o parquet toda vez seria custo puro.
    # `last_close` já devolve `(None, "")` em parquet corrompido, então a
    # página nunca vira 500 por causa de um arquivo ilegível.
    from market_data_intraday.storage import last_close

    return last_close(symbol)


def _ultimo_preco(symbol: str) -> tuple[float | None, str]:
    """(último fechamento de minuto salvo, data) — `(None, "")` se não houver."""
    return _ultimo_preco_cached(_preco_key(symbol))


def capital_minimo_para(is_futuro: bool, symbol: str, preco: float | None) -> float | None:
    """Caixa mínimo para abrir 1 posição neste ativo, com ESTE robô.

    Ação: `capital_minimo_brl(preco)` -- depende do preço de hoje. Futuro
    (`is_futuro=True`): margem do PERFIL x `MARGIN_BUFFER_FUTUROS` -- não
    depende de preço nenhum (a margem já é o número que a corretora reserva
    por contrato). `None` quando falta o dado que a fórmula escolhida
    precisa (preço não salvo, ou perfil sem margem declarada).

    Existe para `app.py` (form de "novo robô" em `/operacao`) e `_asset`
    abaixo lerem a MESMA regra -- antes desta função, `app.py` chamava
    `capital_minimo_brl(preco)` direto para todo robô, o que daria um
    número por volta de R$1 milhão para 1 contrato de WDO@ (`preço x 100 x
    2`, a fórmula de LOTE DE AÇÃO aplicada a um preço de futuro).

    **Inclui `RESERVA_CAIXA_SEGURANCA` (2026-08-28.)** O portão de entrada
    liberava com `margem x 2` (R$300 no WDO@) enquanto o dimensionamento de
    ENTRADA REAL passou a usar `contracts_from_capital_com_reserva`, que
    empilha mais 1,25 por cima -- R$375. A diferença não era acadêmica: o
    robô SUBIA no painel, aparecia operando, e tinha toda ordem recusada por
    `capital_insuficiente` para sempre, em silêncio. Deadlock operacional
    criado pela própria correção do incidente. Um portão que libera o que a
    camada seguinte recusa é pior que portão nenhum -- ele mente."""
    from strategy.daytrade.base import (
        MARGIN_BUFFER_FUTUROS, RESERVA_CAIXA_SEGURANCA, capital_minimo_brl,
    )

    if is_futuro:
        from backtest.intraday.profiles import profile_for

        margem = profile_for(symbol).margin_per_contract_brl
        if margem is None:
            return None
        return margem * MARGIN_BUFFER_FUTUROS * RESERVA_CAIXA_SEGURANCA
    return capital_minimo_brl(preco) if preco is not None else None


def _daytrade_assets(cls, robo) -> tuple[RobotAsset, ...]:
    """Os ativos do robô: os calibrados, se ele declarar; senão o único dele.

    Descoberto por `getattr` (ver `Gremah.calibrated_setups`) para esta função
    não precisar saber qual robô de day trade está sendo exibido.
    """
    is_futuro = getattr(cls, "is_futuro", False)
    setups = getattr(cls, "calibrated_setups", None)
    if setups is None:
        symbol = getattr(robo, "symbol", "")
        if not symbol:
            return ()
        preco, data = _ultimo_preco(symbol)
        return (_asset(symbol, getattr(robo, "profit_pct", 0.0),
                       getattr(robo, "stop_multiplier", 0.0),
                       getattr(robo, "alvo_por_volatilidade", False),
                       getattr(robo, "alvo_vol_mult", None),
                       getattr(robo, "stop_vol_mult", None),
                       preco, data, is_futuro,
                       getattr(robo, "profit_ticks", None),
                       getattr(robo, "stop_ticks", None)),)
    ativos = tuple(
        _asset(s.symbol, s.profit_pct, s.stop_multiplier,
               s.alvo_por_volatilidade, s.alvo_vol_mult, s.stop_vol_mult,
               *_ultimo_preco(s.symbol), is_futuro, None, None)
        for s in setups()
    )
    # Ordenado pelo CAIXA MÍNIMO, do mais barato ao mais caro. A ordem antiga
    # era a de medição (lucro OOS decrescente), que responde "qual mediu
    # melhor?" — mas a primeira pergunta de quem lê a tabela é "qual eu
    # consigo operar?", e essa é decidida pelo caixa: os ativos desta família
    # vão de ~R$28 a ~R$30.390, mais de mil vezes de diferença. Ativo sem
    # preço salvo (caixa `None`) vai para o fim: sem preço não há como
    # ordená-lo, e fingir que é o mais barato o colocaria em primeiro.
    return tuple(sorted(
        ativos, key=lambda a: (a.min_capital is None, a.min_capital or 0.0, a.symbol)))


def _asset(symbol, profit_pct, stop_multiplier, alvo_por_volatilidade,
           alvo_vol_mult, stop_vol_mult, preco, data, is_futuro=False,
           profit_ticks=None, stop_ticks=None) -> RobotAsset:
    # Futuro não tem "lote" (é 1 CONTRATO, margem por contrato) -- `lote =
    # preco x 100` e `capital_minimo_brl` (que embute o MESMO x100) são
    # fórmula de ação. Ver `capital_minimo_para` para o porquê de ramificar
    # aqui em vez de aplicar a fórmula de ação a um preço de futuro.
    lote = None if is_futuro else (preco * 100 if preco is not None else None)
    return RobotAsset(
        symbol=symbol,
        profit_pct=profit_pct,
        stop_multiplier=stop_multiplier,
        alvo_por_volatilidade=alvo_por_volatilidade,
        alvo_vol_mult=alvo_vol_mult,
        stop_vol_mult=stop_vol_mult,
        price=preco,
        price_date=data,
        lot_cost=lote,
        min_capital=capital_minimo_para(is_futuro, symbol, preco),
        is_futuro=is_futuro,
        profit_ticks=profit_ticks,
        stop_ticks=stop_ticks,
    )


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
        robo = get_daytrade_robot(info.key)
        cls = type(robo)
        curta = getattr(cls, "tagline", "") or swing_registry.docstring_parts(cls)[0]
        # Conta os ativos calibrados SEM buscar preço (o cartão não mostra
        # caixa mínimo, e a home renderiza todo robô do catálogo).
        setups = getattr(cls, "calibrated_setups", None)
        quantos = len(setups()) if setups is not None else 1
        fato_ativo = (("Ativos", f"{quantos} calibrados") if quantos > 1
                      else ("Ativo", info.symbol))
        cartoes.append(RobotCard(
            key=info.key,
            kind=DAYTRADE,
            kind_label=_KIND_LABEL[DAYTRADE],
            version=info.version,
            description=curta,
            href=f"/strategies/{info.key}",
            facts=(fato_ativo, ("Cadência", "negócio a negócio"
                                if info.feed_kind == "tick" else "barra de 1 min")),
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
    assets = _daytrade_assets(cls, robo)
    # "Ativo: PMAM3" era uma afirmação FALSA num robô de três ativos — a
    # instância default é PMAM3, mas o robô opera qualquer um dos calibrados
    # (um por conta). Com um ativo só, volta a nomear o ativo.
    fato_ativo = (
        ("Ativos", f"{len(assets)} calibrados") if len(assets) > 1
        else ("Ativo", assets[0].symbol if assets else "—")
    )
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
            fato_ativo,
            # "barra a barra" era verdade quando todo robô de day trade lia M1.
            # Desde a `gremah_tick` (2026-08-22) a família tem duas
            # granularidades, e é a única coisa que separa dois robôs do mesmo
            # desenho — dizer o mesmo dos dois apagaria a diferença na tela.
            ("Cadência", "negócio a negócio"
                if getattr(cls, "feed_kind", "m1") == "tick" else "barra de 1 min"),
            ("Overnight", "nunca"),
        ),
        assets=assets,
        blocks=_blocks(
            tuple(getattr(cls, "watched_signals", ()) or ()),
            tuple(getattr(cls, "entry_rules", ()) or ()),
            tuple(getattr(cls, "exit_rules", ()) or ()),
            tuple(getattr(cls, "sizing_rules", ()) or ()),
        ),
        params=[
            (nome, _formata_quantidade_em_lotes(nome, valor), nota, doc)
            for nome, valor, nota, doc in swing_registry.declared_params(robo)
        ],
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
