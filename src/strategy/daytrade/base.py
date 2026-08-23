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
from collections import deque
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


class RollingVolumeWindow:
    """Volume medio por minuto nos ultimos `janela_minutos` de tempo
    NEGOCIADO — cruza a virada de sessao quando a sessao corrente ainda
    nao acumulou a janela inteira sozinha, em vez de assumir minutos
    vazios (silenciosamente subestimaria o teto logo na abertura, quando o
    giro costuma ser mais alto, nao mais baixo).

    Substituiu (2026-08-22, pedido do dono) o teto de posicao anterior, que
    usava so' o volume do PRIMEIRO minuto/janela inicial do pregao,
    CONGELADO pelo resto do dia — um minuto so' e' amostra ruidosa demais, e
    congelar ignora o giro real do resto da sessao. Agora e' consultada a
    CADA sinal de entrada (`media_por_minuto`), nunca congelada.

    Resolution-agnostic por construcao (mesmo espirito de
    `IntradaySessionMachine`): recebe um EVENTO por vez (`registrar`), M1 ou
    tick — o que muda entre os dois e' so' quantos eventos chegam por
    minuto, nao a formula. `Bar.volume` ja' significa "acoes negociadas
    NESTE evento" nas duas granularidades (a barra M1 agrega o minuto; o
    tick degenerado e' o proprio negocio, ver
    `market_data_intraday/tick_bars.py`), entao a mesma soma-e-divide-por-
    tempo vale para as duas sem nenhum `if` de granularidade aqui dentro.
    """

    def __init__(self, janela_minutos: float):
        self.janela_minutos = float(janela_minutos)
        self._hoje: deque[tuple[pd.Timestamp, float]] = deque()
        self._cauda_ontem: list[tuple[pd.Timestamp, float]] = []
        self._abertura: pd.Timestamp | None = None

    def iniciar_sessao(self) -> None:
        """Chamar em `on_session_start` — zera a parte de HOJE, preserva a
        cauda do pregao anterior (definida a parte, ver
        `definir_cauda_anterior`: quem tem acesso ao historico e' o
        CHAMADOR, em `live/`/`backtest/`, nunca a propria estrategia —
        AGENTS.md, `strategy/` so importa `core`)."""
        self._hoje = deque()
        self._abertura = None

    def definir_cauda_anterior(self, bars: list[Bar]) -> None:
        """`bars`: qualquer trecho do FINAL do pregao anterior (o quanto
        sobrar dele) — so' os ultimos `janela_minutos` dela importam, o
        resto e' descartado aqui. Pode ser chamado antes OU depois de
        `iniciar_sessao`, sao independentes."""
        if not bars:
            self._cauda_ontem = []
            return
        fim = bars[-1].ts
        limite = fim - pd.Timedelta(minutes=self.janela_minutos)
        self._cauda_ontem = [(b.ts, b.volume) for b in bars if b.ts > limite]

    def registrar(self, ts: pd.Timestamp, volume: float) -> None:
        """Empilha o evento de HOJE — chamar em TODA barra/tick recebido,
        nao so' quando ha sinal de entrada: e' o dado bruto que
        `media_por_minuto` consulta depois."""
        if self._abertura is None:
            self._abertura = ts
        self._hoje.append((ts, volume))
        limite = ts - pd.Timedelta(minutes=self.janela_minutos)
        while self._hoje and self._hoje[0][0] <= limite:
            self._hoje.popleft()

    def media_por_minuto(self, ts: pd.Timestamp) -> float:
        """Volume medio por minuto nos ultimos `janela_minutos` ATE `ts`.
        Completa com a cauda do pregao anterior enquanto a sessao de hoje
        ainda nao acumulou a janela inteira sozinha — ver docstring da
        classe."""
        total = sum(v for _, v in self._hoje)
        decorrido_min = (
            (ts - self._abertura).total_seconds() / 60.0
            if self._abertura is not None else 0.0
        )
        if decorrido_min < self.janela_minutos and self._cauda_ontem:
            deficit_min = self.janela_minutos - decorrido_min
            fim_ontem = self._cauda_ontem[-1][0]
            limite = fim_ontem - pd.Timedelta(minutes=deficit_min)
            total += sum(v for t, v in self._cauda_ontem if t > limite)
        return total / self.janela_minutos

    def volumes_por_evento(self, ts: pd.Timestamp) -> list[float]:
        """Volume de CADA evento individual (tick ou barra) dentro da
        janela ATE `ts`, completando com a cauda igual `media_por_minuto` --
        nao a media, a lista crua. Existe para quem precisa do TAMANHO
        TIPICO de um evento so' (ex.: dividir uma ordem grande em pedacos do
        tamanho de um negocio real, `Gremah`/`GremahTick`
        `split_quantities`), que uma media por minuto nao responde: um
        minuto com 10 negocios de 100 acoes e um minuto com 1 negocio de
        1.000 tem a MESMA media, mas pedir 1.000 de uma vez so' preenche no
        segundo caso."""
        eventos = [v for _, v in self._hoje]
        decorrido_min = (
            (ts - self._abertura).total_seconds() / 60.0
            if self._abertura is not None else 0.0
        )
        if decorrido_min < self.janela_minutos and self._cauda_ontem:
            deficit_min = self.janela_minutos - decorrido_min
            fim_ontem = self._cauda_ontem[-1][0]
            limite = fim_ontem - pd.Timedelta(minutes=deficit_min)
            eventos = [v for t, v in self._cauda_ontem if t > limite] + eventos
        return eventos


class JanelaVolatilidadeDiaria:
    """Mediana do range diario (`high - low`) das ultimas `janela_dias`
    sessoes ANTERIORES -- medida de volatilidade usada para dimensionar
    alvo/stop por fracao da volatilidade em vez de percentual do preco
    (`Gremah`/`GremahTick`, 2026-08-23: o percentual fixo satura no piso de
    1 tick em 9 dos 10 simbolos calibrados).

    Mediana, nao Wilder/EWM: robusta a um pregao anomalo, e o repo ja usa
    `median` nos dois robos. Range DIARIO, nao true range intrabar com
    gap: um ATR de barras de 1 minuto tem resolucao zero ou um tick (o
    tick da B3, R$0,01, e' maior que o movimento tipico de 1 minuto), e o
    gap overnight nao faz parte do risco deste robo, que nunca dorme com
    posicao aberta.

    Recebe barras DIARIAS ja prontas de fora (`registrar_dia`) -- quem tem
    acesso ao historico multi-dia e' o CHAMADOR (`backtest/intraday/
    engine.py`, `live/intraday_runtime.py`), nunca a propria estrategia
    (AGENTS.md, `strategy/` so importa `core`), mesmo padrao de
    `RollingVolumeWindow`."""

    def __init__(self, janela_dias: int):
        self.janela_dias = int(janela_dias)
        self._ranges: deque[float] = deque(maxlen=self.janela_dias)

    def registrar_dia(self, bar_diaria: Bar) -> None:
        """Chamar uma vez por sessao ANTERIOR concluida (nunca a sessao
        corrente, ainda incompleta -- olhar o proprio dia seria
        look-ahead)."""
        self._ranges.append(bar_diaria.high - bar_diaria.low)

    def range_mediano(self) -> float | None:
        """`None` enquanto nenhuma sessao foi registrada (primeiro pregao
        do historico, ou feed falhou) -- quem chama cai no fallback
        percentual, mesmo espirito de `seed_volume_window` vazio."""
        if not self._ranges:
            return None
        return float(pd.Series(self._ranges).median())


def barra_diaria(bars: list[Bar]) -> Bar | None:
    """Agrega barras M1 (ou ticks degenerados) de UMA sessao numa barra
    diaria -- mora aqui para backtest e ao vivo agregarem pelo MESMO
    caminho (mesmo argumento de `profiles.py:1-10`: um numero computado em
    dois lugares e' um numero que vai divergir). `None` se `bars` vier
    vazio."""
    if not bars:
        return None
    return Bar(
        ts=bars[-1].ts,
        open=bars[0].open,
        high=max(b.high for b in bars),
        low=min(b.low for b in bars),
        close=bars[-1].close,
        volume=sum(b.volume for b in bars),
    )


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
    cancela qualquer ordem pendente no flatten forcado).

    `split_quantities` (2026-08-22, pedido do dono): a MESMA ordem (lado,
    preco, stop, alvo) fatiada em varios filhos independentes em vez de um
    lote so' -- existe porque uma ordem parada grande demais pode nao ser
    CASADA de verdade mesmo com o preco tendo tocado o nivel (ver
    `IntradayBacktestConfig.limit_fill_capped_by_volume`: cada filho so'
    preenche se o evento que tocou o nivel teve volume real >= o tamanho
    DELE, nao do total). `None` (default) = comportamento antigo, um lote
    so' do tamanho de `quantity`. Quando presente, `sum(split_quantities)`
    tem que bater com `quantity` -- o motor NAO redistribui sozinho.

    `exit_split_unit` (2026-08-22, pedido do dono): o MESMO problema do
    `split_quantities` acima, mas do lado da SAIDA -- o alvo, quando
    `IntradayBacktestConfig.limit_fill_capped_by_volume` esta ligado, so'
    "toca" de verdade se `bar.volume` cobrir a posicao INTEIRA de uma vez
    (ver `IntradayBacktestConfig.limit_fill_capped_by_volume`), o mesmo
    otimismo que a entrada tinha antes de ser dividida. `exit_split_unit`
    declara o tamanho de cada pedaco independente do FECHAMENTO (ex.:
    `LOTE_PADRAO_B3` = fecha em fatias de 1 lote); o motor preenche quantos
    pedacos o volume da barra cobrir, gera um `IntradayTrade` PARCIAL para
    cada fatia que fechar (cada uma com seu proprio `exit_price`, ja que
    podem fechar em barras/precos diferentes) e mantem a posicao aberta
    (com a quantidade restante) ate a ultima fatia sair -- por stop, por
    alvo ou por flatten. `None` (default) = comportamento antigo, exige o
    total de uma vez.

    `exit_ttl_bars` (2026-08-22, pedido do dono -- execucao REAL): so' vale
    com `exit_split_unit` E execucao ao vivo (`IntradaySessionMachine.
    execution` setado). Em execucao real uma saida por alvo dividida vira
    uma ordem-limite REAL na corretora, por fatia -- e' a PRIMEIRA vez que
    uma saida ao vivo pode simplesmente NAO preencher (toda saida real, ate
    aqui, sempre foi a mercado). `exit_ttl_bars` e' o prazo (em barras) que
    cada fatia espera parada antes do motor CANCELAR essa ordem-limite e
    fechar o QUE SOBRAR da posicao a MERCADO (mesmo caminho de
    `IntradayExitReason.FORCED_FLATTEN`/`STOP`) -- decisao do dono: "prazo
    limitado, depois mercado", para a posicao sempre fechar dentro de um
    tempo previsivel, nunca ficar exposta indefinidamente esperando a
    fatia final. `None` (default) preserva o comportamento de backtest/
    sombra (`_resolve_target_partial_fill`, guiado por `bar.volume`, sem
    prazo) -- so' precisa ser declarado por quem for operar `exit_split_unit`
    com dinheiro real."""

    side: Side
    limit_price: float
    initial_stop: float | None = None
    initial_target: float | None = None
    quantity: int | None = None
    ttl_bars: int | None = None
    metadata: dict | None = None
    reason: str = ""
    split_quantities: tuple[int, ...] | None = None
    exit_split_unit: int | None = None
    exit_ttl_bars: int | None = None

    def children(self, default_quantity: int) -> list[int]:
        """Quantidades dos FILHOS independentes desta ordem -- `split_quantities`
        se declarado, senao um filho so' do tamanho de `quantity` (comportamento
        antigo, um lote so'). Usado tanto pelo preenchimento simulado
        (`backtest.intraday.machine`) quanto pelo envio de ordens REAIS
        (`live.intraday_execution.MT5IntradayExecution.place_limit`) -- as duas
        pontas tem de concordar em quantos pedacos existem."""
        if self.split_quantities:
            return list(self.split_quantities)
        return [self.quantity or default_quantity]


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

    # Granularidade em que este robo foi MEDIDO, e portanto a unica em que ele
    # pode operar: `"m1"` (barra de 1 minuto) ou `"tick"` (negocio a negocio).
    # Mora aqui pelo mesmo motivo de `target_fills_as_maker`: e' propriedade do
    # ROBO, e deixa-la a cargo de cada chamador ja' produziu, uma vez, um robo
    # ao vivo com modelo de custo diferente do robo validado. Quem monta o
    # ambiente le este campo (`live/intraday_feed.py::feed_for`) em vez de
    # decidir por nome de classe -- um `if robo == "gremah_tick"` espalhado
    # pelos chamadores e' a mesma divergencia esperando para acontecer.
    #
    # Nao e' uma preferencia: um robo calibrado em M1 rodando em tick veria
    # dezenas de vezes mais eventos por sessao, e todo parametro contado em
    # BARRAS (espera de ordem parada, janela de volume) passaria a significar
    # outra coisa. Foi por isso que a `gremah_tick` recontou os dois dela em
    # tempo de parede em vez de herdar os numeros da `gremah`.
    feed_kind: Literal["m1", "tick"] = "m1"

    def initialize(self, bars: pd.DataFrame) -> None:
        """Pre-calcula indicadores sobre TODO o historico do backtest.
        Chamado uma vez antes do loop de sessoes. Default vazio — robos sem
        estado podem computar tudo em `on_bar`."""

    def on_session_start(self, session_date) -> None:
        """Reseta estado por-dia (ex.: contador de perda diaria, numero de
        entradas ja feitas hoje). Default no-op."""

    def on_capital_update(self, cash_brl: float) -> None:
        """Avisa o robo do caixa acumulado (capital inicial + PnL realizado
        ate agora, contas anteriores incluidas) ANTES de decidir a barra.
        Chamado pelo motor (`backtest.intraday.machine.IntradaySessionMachine`)
        logo antes de `on_bar`, com o MESMO numero em backtest e ao vivo
        (`config.initial_capital + machine.realized_pnl` — o segundo termo ja
        e' persistido entre reinicios, ver `IntradaySessionMachine.state`).
        Default no-op: so' um robo que dimensiona posicao pelo caixa (ex.:
        `Gremah`, reload 2026-08-22) precisa disso; a maioria decide so' com
        o que ja recebe em `on_bar`."""

    def seed_volume_window(self, previous_session_tail: list[Bar]) -> None:
        """Alimenta o robo com o FINAL do pregao ANTERIOR, antes da
        primeira barra/tick de hoje — para um teto de posicao baseado em
        volume rolante (`RollingVolumeWindow`) ter o que precisa quando a
        sessao de hoje ainda nao acumulou a janela inteira sozinha (ex.:
        logo na abertura). Chamado por quem tem acesso ao historico
        (`backtest/intraday/engine.py`, `live/intraday_runtime.py`) — nunca
        pela propria estrategia, que so' importa `core` (AGENTS.md).

        `previous_session_tail` pode vir vazio (primeiro pregao do
        historico carregado, ou sem dado do dia anterior disponivel) —
        nesse caso o robo so' tem o que acumular a partir de agora, mesmo
        comportamento de quando este metodo nunca e' chamado. Default
        no-op: so' um robo com teto de volume rolante (ex.:
        `Gremah`/`GremahTick`, 2026-08-22) precisa disso."""

    def seed_daily_volatility(self, previous_daily_bars: list[Bar]) -> None:
        """Alimenta o robo com a barra DIARIA (`base.barra_diaria`) de cada
        uma das `vol_janela_dias` sessoes ANTERIORES a hoje, mais antiga
        primeiro -- para um alvo/stop dimensionado por volatilidade
        (`JanelaVolatilidadeDiaria`) ja ter o que precisa na primeira
        decisao do pregao, em vez de esperar `vol_janela_dias` sessoes
        vivendo do zero. Chamado por quem tem acesso ao historico
        (`backtest/intraday/engine.py`, `live/intraday_runtime.py`) —
        nunca pela propria estrategia (AGENTS.md, `strategy/` so importa
        `core`).

        `previous_daily_bars` pode vir com menos de `vol_janela_dias`
        barras (comeco do historico) ou vazio (feed falhou) -- o robo usa
        o que tiver; `JanelaVolatilidadeDiaria.range_mediano()` devolve
        `None` se nada foi registrado, e quem le isso cai no fallback
        percentual. Default no-op: so' um robo com alvo por volatilidade
        (ex.: `Gremah`/`GremahTick`, 2026-08-23) precisa disso."""

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
