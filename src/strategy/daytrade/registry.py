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
from strategy.daytrade.lab.gremah_tick import GremahTick

# A ORDEM DESTE DICIONÁRIO É O PÓDIO DE DAY TRADE — o primeiro é o TOP-1.
#
# Diferente do ranking de swing (recalculado a cada 6h a partir do diário de
# backtests, ver `journal.reader.top_strategies_by_final_capital`), aqui a
# ordem é DECLARADA. Não é preguiça: dois robôs de day trade não são
# comparáveis por "capital final" de uma run — eles não rodam a mesma
# granularidade de dado, então não existe uma run em que os dois apareçam
# lado a lado. Um ranking automático teria de comparar números medidos em
# bases diferentes, que é a comparação desonesta que este projeto evita.
#
# 2026-08-22, decisão do dono: `gremah_tick` é o TOP-1 e `gremah` o TOP-2. O
# que sustenta a ordem, em uma linha cada:
#   - tick a tick não tem a ambiguidade "stop e alvo na mesma barra" que o M1
#     resolve por chute pessimista — um negócio tem um preço só;
#   - ao vivo, stop e alvo são avaliados no negócio, não no fim do minuto:
#     apaga a divergência de até 60s que `live/intraday_runtime.py` declara;
#   - uma ordem-limite só é dada como tocada quando alguém NEGOCIOU no nível,
#     em vez de bastar a faixa do minuto contê-lo.
# O que a ordem NÃO afirma, e precisa ser dito junto: a `gremah_tick` tem
# medição própria em UM ativo (PMAM3) contra os dez da `gremah` — é por isso
# que `GremahTick.calibrated_setups()` oferece um só.
_ROBOTS: dict[str, type[IntradayStrategy]] = {
    GremahTick.name: GremahTick,
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
    #: Posição no pódio declarado (1 = TOP-1). Sai da ordem de `_ROBOTS`, e
    #: existe como CAMPO para o painel poder rotular a escolha — antes a ordem
    #: só existia implícita na lista, e uma ordem que ninguém enxerga não é
    #: uma recomendação, é um acaso de iteração.
    rank: int = 1
    #: `"m1"` ou `"tick"` — a granularidade em que este robô foi medido (ver
    #: `IntradayStrategy.feed_kind`). No painel é o que distingue dois robôs
    #: do mesmo desenho.
    feed_kind: str = "m1"


def _description(cls: type) -> str:
    doc = inspect.getdoc(cls) or ""
    if not doc:
        return f"Robô {cls.__name__} (sem docstring)."
    primeira = doc.strip().splitlines()[0].strip(" .")
    return primeira + "."


def list_daytrade_robots() -> list[DaytradeRobotInfo]:
    """Um `DaytradeRobotInfo` por robô registrado, na ordem do PÓDIO (TOP-1
    primeiro) — ver o comentário sobre `_ROBOTS` no topo do módulo.

    Instancia com os defaults de cada classe só para ler `.symbol` — leitura
    pura, sem I/O (mesmo espírito de `strategy.registry.list_strategies`)."""
    infos = []
    for posicao, (key, cls) in enumerate(_ROBOTS.items(), start=1):
        robo = cls()
        infos.append(DaytradeRobotInfo(
            key=key, label=key, symbol=robo.symbol,
            version=getattr(robo, "version", "0.1"),
            description=_description(cls),
            rank=posicao,
            feed_kind=getattr(cls, "feed_kind", "m1"),
        ))
    return infos


def get_daytrade_robot(key: str, symbol: str | None = None) -> IntradayStrategy:
    """Resolve um robô de day trade por chave, com os PARÂMETROS DEFAULT da
    classe — quem precisa de parâmetros diferentes instancia direto.

    `symbol` escolhe o ativo. `None` usa o default da classe. Passar um ativo
    que o robô não aceita é erro DELE, não daqui: `Gremah.__init__` levanta
    `ValueError` para símbolo sem calibração própria, em vez de herdar a
    calibração de outro papel — é esse comportamento que impede o painel de
    ligar um robô num ativo nunca medido.

    Este parâmetro entrou em 2026-08-22, quando o painel passou a abrir N
    robôs de day trade (um por ativo): até então "o robô" e "o ativo" eram a
    mesma escolha, porque o registry só sabia instanciar com o default.

    `KeyError` (nunca um default silencioso) se a chave não existir: um id
    desconhecido chegando de form/CLI é catálogo desatualizado ou form
    adulterado, e escolher um robô por chute operaria dinheiro real com o
    robô errado."""
    if key not in _ROBOTS:
        raise KeyError(
            f"robô de day trade desconhecido: {key!r} — disponíveis: "
            f"{', '.join(sorted(_ROBOTS))}"
        )
    cls = _ROBOTS[key]
    return cls() if symbol is None else cls(symbol=symbol)


def symbols_for_robot(key: str) -> tuple[str, ...]:
    """Ativos que este robô aceita operar, na ordem em que ele os declara.

    Sai de `calibrated_setups()` na CLASSE quando ela oferece esse método (é o
    caso da `gremah`: cada ativo tem alvo/stop medidos separadamente, e a
    ordem é lucro OOS decrescente). Um robô de ativo único simplesmente não
    define o método, e aqui ele vira a tupla de um elemento com o símbolo
    default — o painel não precisa saber qual dos dois casos é.

    Ordenar por capital mínimo é do CHAMADOR, não daqui: depende do preço de
    hoje, e `strategy/` não busca preço (regra 1 do AGENTS.md).
    """
    if key not in _ROBOTS:
        raise KeyError(
            f"robô de day trade desconhecido: {key!r} — disponíveis: "
            f"{', '.join(sorted(_ROBOTS))}"
        )
    cls = _ROBOTS[key]
    setups = getattr(cls, "calibrated_setups", None)
    if callable(setups):
        return tuple(s.symbol for s in setups())
    return (cls().symbol,)
