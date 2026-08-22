"""Interface `IntradayStrategy` — contrato para robos de day trade.

Distinto de `strategy.base.Strategy` (nao herda dela) porque a cadencia e
outra: o robo diario decide UMA vez por pregao; um robo de day trade decide
BARRA A BARRA dentro da sessao, podendo abrir e fechar varias posicoes no
mesmo dia — nenhuma delas carrega para o dia seguinte (day trade nunca
mantem posicao overnight). Forcar isso no `Strategy` existente exigiria um
`on_bar` que significasse duas coisas diferentes para quem le o codigo.

Mesma disciplina anti-look-ahead do lado diario, em granularidade de
minuto: `AdjustStop`/`AdjustTarget` aplicam imediato (custo zero);
`Enter`/`Exit` sao enfileiradas pelo motor (`backtest.intraday.engine`) e
executam na ABERTURA da PROXIMA barra, nunca no fechamento da barra que
gerou a decisao.

Por construcao deliberada, `IntradayStrategy` NAO herda de
`strategy.base.Strategy`: isso o deixa fora do scan de
`strategy.discovery.discover_strategies` por natureza (o filtro exige
`issubclass(obj, Strategy)`) — um robo de futuro intradiario nao pode
competir no mesmo podio que um robo diario de acoes, sao capital/risco/
instrumento incomparaveis.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, Union

import pandas as pd


Side = Literal["long", "short"]


@dataclass
class Bar:
    ts: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class IntradayOpenPosition:
    """Snapshot read-only da posicao vista pelo robo em `on_bar` — espelha
    `strategy.base.OpenPosition`, com `side` (long/short — o diario so
    opera comprado) e `current_target` (o diario nao tem alvo, so stop)."""

    side: Side
    entry_ts: pd.Timestamp
    entry_price: float
    quantity: int
    current_stop: float | None
    current_target: float | None
    bars_held: int
    metadata: dict = field(default_factory=dict)


@dataclass
class Enter:
    """Acao: abrir posicao. `quantity=None` -> motor usa
    `IntradayBacktestConfig.default_quantity`."""

    side: Side
    initial_stop: float | None = None
    initial_target: float | None = None
    quantity: int | None = None
    metadata: dict | None = None
    reason: str = ""


@dataclass
class EnterLimit:
    """Acao: deixar uma ordem-limite PENDENTE (nao executa na proxima
    abertura como `Enter` — fica esperando, barra a barra, ate o preco
    tocar `limit_price` ou `ttl_bars` expirar). Existe para modelar quem
    FORNECE liquidez (maker) em vez de quem CONSOME (taker via `Enter`,
    que sempre paga `slippage_ticks` na abertura da barra seguinte):
    varias hipoteses (`grid_bidirecional_ticks`, reversao a media) definem
    o sinal como "o preco tocou o nivel X" — perseguir esse toque com uma
    ordem a mercado paga o spread; uma ordem-limite JA POSICIONADA em X
    captura o toque exatamente no nivel, sem o slippage adverso.

    Preenchida pelo motor no PRIMEIRO toque de `bar.low <= limit_price`
    (compra) ou `bar.high >= limit_price` (venda) em qualquer barra
    seguinte a esta decisao — nunca na propria barra que a gerou (mesma
    disciplina anti-look-ahead das outras acoes). Uma nova `EnterLimit`
    devolvida pelo robo enquanto uma ja esta pendente SUBSTITUI a
    anterior (mesmo espirito de `Enter`/`Exit` sobrescreverem `pending`).
    `ttl_bars=None` = espera indefinidamente (até o fim da sessao, que
    cancela qualquer ordem pendente no flatten forcado)."""

    side: Side
    limit_price: float
    initial_stop: float | None = None
    initial_target: float | None = None
    quantity: int | None = None
    ttl_bars: int | None = None
    metadata: dict | None = None
    reason: str = ""


@dataclass
class Exit:
    """Acao: fechar posicao a mercado por decisao do robo (nao stop, nao
    target, nao flatten forcado — esses tres o motor decide por conta
    propria, ver `core.models.IntradayExitReason`)."""

    reason: str = ""


@dataclass
class AdjustStop:
    """Motor so aceita se o novo stop for MAIS PROTETOR que o atual (para
    long: `new_stop >= current_stop`; para short: `new_stop <= current_stop`)
    — mesma regra de `strategy.base.AdjustStop` (stop nunca "afrouxa")."""

    new_stop: float


@dataclass
class AdjustTarget:
    """Sem restricao de direcao — diferente de `AdjustStop`, um alvo pode
    legitimamente ser alargado OU estreitado pelo robo (ex.: reduzir o alvo
    perto do fim da sessao para garantir realizacao)."""

    new_target: float


IntradayAction = Union[Enter, EnterLimit, Exit, AdjustStop, AdjustTarget]


class IntradayStrategy(ABC):
    """Interface que todo robo de day trade implementa."""

    name: str
    version: str
    # Simbolo MT5 que este robo negocia. SEM default, de proposito e no mesmo
    # espirito de `name`/`version`: um default herdado aqui e' um robo
    # operando o ativo errado em silencio, e o custo/tick/horario de cada
    # instrumento e' diferente (ver `backtest/intraday/profiles.py`). Quem
    # implementa um robo declara o que ele negocia.
    symbol: str

    # A saida por ALVO deste robo e' uma ordem-limite parada no nivel (maker,
    # sem slippage) ou uma ordem a mercado? E' decisao da ESTRATEGIA — ela
    # sabe se pendura a saida de lucro como limite —, e mora aqui porque era
    # passada a mao por cada chamador: `scripts/run_live.py` mandava `True` e o
    # CLI de backtest ficava no default `False`, ou seja, o robo ao vivo e o
    # robo validado tinham modelo de custo DIFERENTE. No campeao isso vale a
    # diferenca entre -R$288 e +R$621 no mesmo periodo. Ver
    # `IntradayBacktestConfig.target_fills_as_maker` para como o motor precifica.
    target_fills_as_maker: bool = False

    def initialize(self, bars: pd.DataFrame) -> None:
        """Pre-calcula indicadores sobre TODO o historico do backtest.
        Chamado uma vez antes do loop de sessoes. Default vazio — robos sem
        estado podem computar tudo em `on_bar`."""

    def on_session_start(self, session_date) -> None:
        """Reseta estado por-dia (ex.: contador de perda diaria, numero de
        entradas ja feitas hoje). Default no-op."""

    @abstractmethod
    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        position: IntradayOpenPosition | None,
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        """Decisao para esta barra. Devolve acoes declarativas ao motor."""


def warm_start_calibration(
    strategy: IntradayStrategy, session_date, seed_bars: list[Bar]
) -> Enter | EnterLimit | None:
    """Calibra `strategy` para um pregao JA EM ANDAMENTO, a partir de barras
    REAIS ja passadas (buscadas do historico, ex.: via MT5), sem depender
    de qual barra o robo recebeu primeiro ao vivo.

    Existe porque varios robos (ex.: `GridReloadMakerPct`) descobrem seu
    proprio `open_price`/nivel de calibracao na PRIMEIRA barra que virem
    (`on_bar`) — se o processo ao vivo so comecar a receber barra as 15h,
    ele calibraria com o preco das 15h em vez do preco de abertura real,
    deslocando o robo do nivel certo o dia todo. Chamar esta funcao 1x ao
    iniciar/reconectar em QUALQUER horario do pregao, alimentando as
    barras reais desde a abertura, ANTES de comecar a alimentar barras ao
    vivo (essas sim executam de verdade).

    `position=None` e `session_pnl_brl=0.0` em toda chamada porque nao
    houve execucao real ainda — esta funcao so calibra estado interno
    (ex.: `open_price`, espacamento do dia), nunca fabrica trade nem
    afeta P&L: com `position` sempre `None`, o robo nunca ve um fill de
    verdade, entao contas que dependeriam disso (ex.: `long_fills`)
    permanecem zeradas, corretamente — nenhum trade real aconteceu ainda
    hoje.

    Devolve a ULTIMA ordem ainda pendente/em pe (`Enter` ou `EnterLimit`)
    ao fim do replay — a decisao "como entrar" que o robo tomou com a
    calibracao certa, ainda valida (nada mudou desde). Passar para
    `run_intraday_backtest(..., resume_same_session=True, seed_pending=...)`
    para essa ordem comecar a ser vigiada de verdade a partir da PRIMEIRA
    barra ao vivo, em vez de descartada — descartar jogaria fora uma
    decisao genuina; `None` se o robo nao tem nenhuma ordem em pe no fim
    do replay (ou a ultima acao foi `Exit`, que so faz sentido com
    posicao real aberta, inexistente aqui)."""
    strategy.on_session_start(session_date)
    pending: Enter | EnterLimit | None = None
    for bar in seed_bars:
        for action in strategy.on_bar(bar.ts, bar, None, 0.0):
            if isinstance(action, (Enter, EnterLimit)):
                pending = action
            elif isinstance(action, Exit):
                pending = None
    return pending


#: Lote padrao de acao na B3 -- a menor quantidade negociavel SEM recorrer ao
#: mercado fracionario. Day trade nao usa fracionario: cada ordem la custa
#: R$1,90 fixos na corretora (confirmado pelo dono 2026-08-22), proibitivo num
#: robo de giro alto que faz centenas de round-trips por mes.
LOTE_PADRAO_B3 = 100

#: Quantas vezes o custo de 1 lote a conta precisa ter em caixa para o robo
#: poder operar aquele simbolo (regra do dono, 2026-08-22). O "dobro" nao e'
#: margem estetica: o robo alterna long/short (`Gremah` inverte de lado a cada
#: fechamento) e o preco se move entre montar e desmontar -- 1x o lote deixaria
#: a conta sem folga nenhuma para a proxima entrada, e qualquer oscilacao
#: normal ja impediria o robo de recarregar.
CAPITAL_MINIMO_EM_LOTES = 2.0


def capital_minimo_brl(preco_atual: float, shares_per_lot: int = LOTE_PADRAO_B3) -> float:
    """Caixa minimo para um robo de day trade poder operar este simbolo.

    `preco_atual x lote x 2` (ver `CAPITAL_MINIMO_EM_LOTES`). Ex.: PMAM3 a
    R$0,14 -> lote de R$14,00 -> minimo R$28,00.

    Depende do PRECO, logo muda todo dia: quem opera tem de reavaliar uma vez
    por pregao, no simbolo que vai operar, e nao operar se o caixa nao cobrir
    (`live/intraday_runtime.py::_check_capital` faz isso ao vivo; a ficha do
    robo mostra o numero de hoje via `dashboard/robot_view.py`). Um numero
    congelado ficaria errado sozinho -- CSAN3 saiu de R$7,62 para R$3,64 em
    11 meses, quase metade do minimo.

    Mora aqui, e nao em `live/`, por causa da regra 6 do AGENTS.md: `live/`
    aplica regra declarada, nunca inventa a propria. Substituiu (2026-08-22) a
    regra anterior de arredondar o custo do lote para cima ao proximo multiplo
    de R$50, que embutia a folga no arredondamento e por isso dava folga
    ridiculamente desigual conforme o preco (PMAM3 R$14 -> R$50, 3,6x; CSAN3
    R$364 -> R$400, 1,1x)."""
    return preco_atual * shares_per_lot * CAPITAL_MINIMO_EM_LOTES
