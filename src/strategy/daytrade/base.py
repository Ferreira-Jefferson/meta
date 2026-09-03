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

import math
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


def mediana_negocio_diario(bars: list[Bar]) -> float | None:
    """Mediana do volume de CADA evento (barra M1 ou tick degenerado) de
    UMA sessao inteira -- a mesma estatistica que `RollingVolumeWindow.
    volumes_por_evento` da' intradia, so' que fechada no fim do dia, pra
    servir de ANCORA ESTAVEL (ver `JanelaNegocioTipicoDiaria`).

    Existe porque a mediana intradia (janela rolante de poucos minutos)
    oscila o dia inteiro -- um teto de CAPACIDADE calculado em cima dela
    vaza: caixa acima do teto ainda produz posicao maior nos minutos em
    que a mediana rolante estiver alta. A mediana de uma sessao INTEIRA ja'
    fechada nao oscila mais (2026-08-24, achado medindo a PMAM3: com R$50
    mil e R$200 mil dando o MESMO lucro so' depois de trocar a ancora
    rolante por esta). `None` se `bars` vier vazio."""
    if not bars:
        return None
    return float(pd.Series([b.volume for b in bars]).median())


class JanelaNegocioTipicoDiaria:
    """Mediana de `mediana_negocio_diario` das ultimas `janela_dias` sessoes
    ANTERIORES -- a ANCORA ESTAVEL de tamanho de negocio usada por um teto
    de CAPACIDADE de caixa (`Gremah`/`GremahTick`, 2026-08-24: acima da
    capacidade, caixa extra vira inerte -- nao aumenta posicao nem lucro,
    so' fica parado, o que o dono pode entao sacar sem perder nada).

    Mesma familia de `JanelaVolatilidadeDiaria` (mediana de dias FECHADOS,
    nunca o dia corrente -- olhar o proprio dia seria look-ahead) e mesma
    razao de ser DIARIA em vez de intrabar: a mediana de POUCOS eventos
    numa janela curta (a PMAM3 tem so' ~2 negocios/minuto) e' refem de um
    unico negocio de bloco, do mesmo jeito que a MEDIA por minuto era --
    so' que uma sessao inteira tem centenas de eventos, amostra grande o
    bastante pra nao balancar com um bloco isolado.

    Default `janela_dias=1` (so' ontem) e' o que foi MEDIDO: um numero que
    se ajusta de um pregao pro outro (acompanha o mercado mudando de
    patamar de liquidez, como pedido) mas fica ESTAVEL dentro do dia
    (nao vaza o teto). `janela_dias` maior suaviza mais, ao custo de reagir
    mais devagar a uma mudanca real de patamar -- nao medido ainda."""

    def __init__(self, janela_dias: int = 1):
        self.janela_dias = max(1, int(janela_dias))
        self._medianas: deque[float] = deque(maxlen=self.janela_dias)

    def registrar_dia(self, bar_diaria: Bar | None, mediana_do_dia: float | None) -> None:
        """Chamar uma vez por sessao ANTERIOR concluida. `bar_diaria` so'
        existe na assinatura pra simetria com `JanelaVolatilidadeDiaria` (o
        chamador ja tem as duas prontas do mesmo loop); quem importa aqui e'
        `mediana_do_dia`. `None` (sessao vazia) e' ignorado, nao empilha
        zero -- um dia sem negocio nao e' evidencia de negocio pequeno."""
        if mediana_do_dia is not None:
            self._medianas.append(mediana_do_dia)

    def tipico_mediano(self) -> float | None:
        """`None` enquanto nenhuma sessao foi registrada (primeiro pregao
        do historico, ou feed falhou) -- quem chama cai no fallback sem
        teto de capacidade, mesmo espirito de `range_mediano` vazio."""
        if not self._medianas:
            return None
        return float(pd.Series(self._medianas).median())


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

    # `True` só para um robô de FUTURO (WIN@/WDO@) -- o painel usa isto para
    # decidir se "quanto opera, e o que custa" é lote de ação (preço x 100,
    # `capital_minimo_brl`) ou margem por contrato (`profile_for(symbol).
    # margin_per_contract_brl x MARGIN_BUFFER_FUTUROS`), e se o alvo/stop se
    # mostram em % do preço ou em ticks (ver `dashboard/robot_view.py::
    # _asset`). Campo explícito em vez de inferir do símbolo terminar em "@"
    # -- mesmo argumento já usado para `SymbolProfile.is_futures`
    # (`backtest/intraday/profiles.py`): duas finalidades diferentes não
    # devem compartilhar um jeito só de serem lidas.
    is_futuro: bool = False

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

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        """Avisa o robo que a ULTIMA ordem que ele emitiu (`Enter` a
        mercado, ou o ULTIMO filho de uma `EnterLimit` que ainda restava
        esperando) morreu sem abrir posicao nenhuma -- recusada pelo motor
        (`backtest.intraday.machine.IntradaySessionMachine._recusa_por_teto`,
        hoje so' por teto de capital ou `max_open_contracts`), nunca por
        preco nao ter tocado. Chamado SO' quando a ordem esta definitivamente
        morta (nenhum filho restando mais) E nenhuma posicao resultou dela --
        uma `EnterLimit` fatiada (`split_quantities`) com PELO MENOS um filho
        aceito nao dispara isto, porque `positions` deixa de estar vazio e o
        proprio `on_bar` ja' teria como saber.

        Default no-op (2026-08-29, achado no incidente WDO F1 de
        2026-08-28): um robo que guarda estado proprio de "ordem pendente"
        (`pending_side`/equivalente, fora de `positions`) TEM que zerar esse
        estado aqui, senao ele acha para sempre que uma ordem ainda esta
        viva quando na verdade o motor ja' a descartou -- travando o robo
        pelo resto da sessao (confirmado 20/20 amostras em
        `WdoGridReloadMaker` antes deste hook existir). Um robo sem estado
        de pendencia proprio (decide so' a partir de `positions` a cada
        chamada) nao precisa sobrescrever isto."""

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

    def seed_typical_trade_size(self, previous_daily_medians: list[float]) -> None:
        """Alimenta o robo com `base.mediana_negocio_diario` de cada uma
        das sessoes ANTERIORES cobertas pela janela de um teto de
        CAPACIDADE (`JanelaNegocioTipicoDiaria`), mais antiga primeiro --
        para o teto ja' ter o que precisa na primeira decisao do pregao.
        Chamado por quem tem acesso ao historico (`backtest/intraday/
        engine.py`, `live/intraday_runtime.py`) — nunca pela propria
        estrategia (AGENTS.md, `strategy/` so importa `core`).

        `previous_daily_medians` ja' vem SEM os dias vazios (sessao sem
        negocio nenhum nao e' evidencia de negocio pequeno, ver
        `mediana_negocio_diario`) -- pode vir com menos itens que a janela
        pede (comeco do historico) ou vazio (feed falhou); `Janela
        NegocioTipicoDiaria.tipico_mediano()` devolve `None` se nada foi
        registrado, e quem le isso cai no fallback sem teto de capacidade.
        Default no-op: so' um robo com teto de capacidade de caixa (ex.:
        `GremahTick`, 2026-08-24) precisa disso."""

    @abstractmethod
    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        """Decisao para esta barra. Devolve acoes declarativas ao motor.

        `positions` (2026-08-24, antes `position: IntradayOpenPosition |
        None` unico) -- `IntradaySessionMachine` pode manter mais de uma
        posicao aberta ao mesmo tempo quando uma entrada e' fatiada em
        varios lotes (`EnterLimit.split_quantities`) e cada fatia vira uma
        posicao independente, com seu proprio stop/alvo/prazo (ver
        `backtest/intraday/machine.py`). Lista vazia = flat. Uma estrategia
        que nunca pede mais de 1 lote nunca ve mais de 1 item aqui -- o
        contrato antigo (`if position is not None`) vira `if positions:`
        sem mudanca de comportamento."""


def warm_start_calibration(
    strategy: IntradayStrategy, session_date, seed_bars: list[Bar],
    cash_brl: float | None = None,
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

    `positions=[]` e `session_pnl_brl=0.0` em toda chamada porque nao
    houve execucao real ainda — esta funcao so calibra estado interno
    (ex.: `open_price`, espacamento do dia), nunca fabrica trade nem
    afeta P&L: com `positions` sempre vazia, o robo nunca ve um fill de
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
    posicao real aberta, inexistente aqui).

    `cash_brl` (2026-09-03, achado de auditoria adversarial --
    `LICOES_DE_PRODUCAO.md` item 3.14): o caixa corrente da conta
    (`initial_capital + realized_pnl`), quando o CHAMADOR ja o conhece.
    Passado, chama `strategy.on_capital_update(cash_brl)` antes de CADA
    barra do replay -- a MESMA sequencia que
    `IntradaySessionMachine.step()` roda a cada barra real
    (`backtest/intraday/machine.py`, `on_capital_update` sempre
    imediatamente antes de `on_bar`). Sem isto, um robo que dimensiona
    posicao pelo caixa via `on_capital_update` (`Gremah`, `GremahTick`,
    `CopaWin`, `WdoGridReloadMaker`) recalibra num restart no meio do
    pregao com `_cash_atual_brl` ainda no default `0.0` -- o teto por
    risco/margem colapsa em SILENCIO pro piso deliberado de 1 contrato
    (`max(1, teto)`) ate a proxima atualizacao normal de capital, sem
    nenhum log ou erro no caminho. Esta funcao continua PURA mesmo assim
    (AGENTS.md, regra 2): nao busca caixa nenhum sozinha, so' repassa um
    numero que o chamador ja calculou -- `live/` (ou o motor de backtest)
    e' quem tem I/O pra saber o caixa real, nunca `strategy/`. `None`
    (default) preserva o comportamento antigo -- nenhuma chamada a
    `on_capital_update` durante o replay -- para quem ainda nao tem esse
    numero disponivel."""
    strategy.on_session_start(session_date)
    pending: Enter | EnterLimit | None = None
    for bar in seed_bars:
        if cash_brl is not None:
            strategy.on_capital_update(cash_brl)
        for action in strategy.on_bar(bar.ts, bar, [], 0.0):
            if isinstance(action, (Enter, EnterLimit)):
                pending = action
            elif isinstance(action, Exit):
                pending = None
    return pending


def no_tick(preco: float, tick_size: float) -> float:
    """Ajusta um preco a GRADE de negociacao do instrumento.

    Mora aqui (e nao dentro de uma estrategia) porque vale para qualquer robo
    que calcule nivel: um stop/alvo/ordem-limite fora da grade nao existe no
    book, a corretora recusa, e o backtest que o preenche esta medindo um
    trade impossivel.

    Vira obrigatorio em FUTURO por uma armadilha medida (2026-08-25): a serie
    continua do MT5 reporta o tick errado (`WIN@` diz 1,0 quando o `WINV26`
    negocia de 5 em 5; `WDO@` diz 0,001 contra 0,5 do `WDOV26`). O valor certo
    entra pelo construtor do robo, vindo de `SymbolProfile.price_tick_size`.

    `tick_size <= 0` devolve o preco intacto -- e' o caso "nao sei o tick",
    onde arredondar seria pior que nao arredondar."""
    if tick_size <= 0:
        return preco
    return round(preco / tick_size) * tick_size


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


# ---------- escalonamento por CAPITAL em FUTURO (2026-08-26) ---------------
# Equivalente de `capital_minimo_brl`/`CAPITAL_MINIMO_EM_LOTES` para um robo
# de FUTURO (WIN@/WDO@): o limitador de tamanho deixa de ser caixa-por-lote
# (acao) e passa a ser MARGEM-por-contrato (a corretora reserva margem, nao
# o preco cheio do contrato). Objetivo novo do dono (2026-08-26): comecar
# operando 1 contrato (o que ele consegue hoje) e o robo escalar SOZINHO
# para mais contratos conforme o caixa/margem disponivel permitir -- mesma
# ideia de `IntradaySessionMachine.positions` (posicoes independentes, cada
# uma com seu proprio stop/alvo), so' que aqui calculamos o TETO quantos
# contratos cabem, nao o agrupamento em si (isso a maquina ja faz).

#: Multiplicador de seguranca sobre a margem exigida por contrato -- o
#: EQUIVALENTE, em futuro, do `CAPITAL_MINIMO_EM_LOTES` de acao (2x o custo
#: de 1 lote). NAO e' o mesmo numero por acidente: escolhido para reusar o
#: mesmo fator do precedente ja validado pelo dono, nao porque a logica por
#: tras seja identica -- ela E' diferente, e vale registrar o porque:
#:
#: * Em ACAO, `CAPITAL_MINIMO_EM_LOTES=2.0` cobre o preco CHEIO de 1 lote
#:   (nao ha alavancagem: caixa parado = 1x o lote, e o dobro da folga para
#:   o robo trocar de lado sem faltar caixa). A margem de futuro JA e' uma
#:   FRACAO alavancada do valor do contrato -- ela mesma e' o "compromisso"
#:   que a corretora exige, nao o valor cheio. Isso puxaria o fator para
#:   BAIXO (a margem em si ja embute uma folga de risco calculada pela
#:   bolsa para cobrir a oscilacao esperada de 1 dia).
#: * Mas ao vivo o robo pode ter VARIAS posicoes independentes abertas ao
#:   mesmo tempo (o proprio objetivo desta funcao -- escalar sozinho), e uma
#:   corretora pode cobrar CHAMADA DE MARGEM intraday se o caixa livre cair
#:   abaixo do exigido enquanto uma posicao esta perdendo -- isso puxaria o
#:   fator para CIMA (menos alavancagem de fato usada do que a margem
#:   minima permitiria, para nao ficar exposto a uma chamada de margem no
#:   meio do pregao, que forcaria liquidacao exatamente no pior momento).
#:
#: Sem numero real de margem/chamada de margem medido no MT5 ainda (ver
#: `contracts_from_capital`), as duas pressões nao tem como ser pesadas uma
#: contra a outra com dado -- inventar um fator novo sem medicao seria tao
#: arbitrario quanto manter o antigo. Decisao: MANTER 2.0, o mesmo fator ja
#: aprovado pelo dono para acao, tratado como o PONTO DE PARTIDA seguro (nao
#: como se a derivacao fosse a mesma) ate existir dado real de margem via
#: MT5 (`order_calc_margin`/`symbol_info_margin`, hoje NAO consultado neste
#: repo -- grep confirmado em `market_data_intraday/` e `live/broker_mt5.py`,
#: 2026-08-26) para calibrar o fator certo por simbolo. Quem calibrar um
#: robo especifico com dado real de chamada de margem pode passar `buffer=`
#: diferente para `contracts_from_capital` -- este e' so' o default.
MARGIN_BUFFER_FUTUROS = 2.0


def contracts_from_capital(
    cash_brl: float,
    margin_per_contract_brl: float,
    buffer: float = MARGIN_BUFFER_FUTUROS,
    hard_cap: int | None = None,
) -> int:
    """Quantos CONTRATOS independentes (1 contrato cada, ver
    `IntradaySessionMachine.positions`) o caixa atual sustenta, em FUTURO.

    Formula: `floor(cash_brl / (margin_per_contract_brl * buffer))`,
    truncado (nunca contrato fracionario) e nunca negativo. `buffer` existe
    pelo MESMO motivo de `CAPITAL_MINIMO_EM_LOTES` em `capital_minimo_brl`
    -- ver a nota longa em `MARGIN_BUFFER_FUTUROS` para o porque do fator
    escolhido nao ser uma copia cega do caso de acao.

    Funcao PURA e' de proposito: nao consulta MT5, nao sabe o simbolo, nao
    sabe quantos contratos ja estao abertos (isso e' papel de
    `IntradayBacktestConfig.max_open_contracts` + `IntradaySessionMachine`,
    ja implementados -- esta funcao so calcula o TETO, nunca o
    agrupamento). `margin_per_contract_brl` e' parametro OBRIGATORIO --
    nunca uma constante interna: a fonte real de margem por simbolo
    (equivalente a `order_calc_margin`/`symbol_info_margin` do MT5) e'
    TRABALHO FUTURO, ainda nao coberto neste repo (confirmado por grep,
    2026-08-26); ate la, quem chama tem de ler o numero de algum lugar
    (terminal, planilha, o que for) e passar explicito -- mesmo padrao que
    `trade_tick_value`/`trade_tick_size` ja usam em `config_for`, nunca
    inventados aqui dentro.

    `hard_cap`: teto adicional, aplicado DEPOIS do calculo por capital (ex.:
    o teto OFICIAL de um instrumento/regulamento, ou um limite de risco do
    dono) -- o resultado e' sempre o MENOR dos dois, nunca so' um ou so' o
    outro. `None` (default) = sem teto adicional, so' o capital limita.

    Casos de borda: `cash_brl` que nao cobre nem 1 contrato (com o buffer)
    devolve `0` (nao um erro -- e' o robo esperando ter caixa, exatamente
    como `enforce_capital_minimo` recusa o pregao em vez de operar
    parcialmente). `margin_per_contract_brl<=0` ou `buffer<=0` levanta
    `ValueError` -- um numero nao-positivo ali e' erro de quem chamou (dado
    de margem invalido), nunca "sem teto"."""
    if margin_per_contract_brl <= 0:
        raise ValueError(
            f"margin_per_contract_brl tem que ser positivo, recebeu {margin_per_contract_brl!r}"
        )
    if buffer <= 0:
        raise ValueError(f"buffer tem que ser positivo, recebeu {buffer!r}")
    if cash_brl <= 0:
        contratos = 0
    else:
        custo_por_contrato = margin_per_contract_brl * buffer
        # `+1e-9`: tolerancia de ponto flutuante -- `cash_brl` exatamente
        # igual a N x custo_por_contrato nao pode truncar para N-1 so' por
        # erro de representacao binaria (ex.: 1000.0 / 500.0 == 1.9999999999998).
        contratos = int(math.floor(cash_brl / custo_por_contrato + 1e-9))
        contratos = max(0, contratos)
    if hard_cap is not None:
        contratos = min(contratos, max(0, int(hard_cap)))
    return contratos


# ---------- reserva de seguranca sobre CAPITAL (2026-08-28, incidente REAL) -
# `wdo_grid_reload_maker` (WDO@, capital real R$300) operou pela primeira vez
# ao vivo em 2026-08-28 e ZEROU a conta: saldo final -R$298,60, equity
# NEGATIVA. Forense confirmado no terminal MT5: dois deals de ABERTURA
# (`475209192` as 11:58:59 e `475209197` as 11:59:04, mesmo magic, volume 1
# cada) -- DUAS entradas INDEPENDENTES do grid, consolidadas pela conta
# NETTING numa unica posicao de -2 contratos. Com 2 contratos a margem
# exigida DOBROU, a margem livre da conta ficou NEGATIVA, e a corretora
# passou a recusar toda ordem nova -- inclusive as de FECHAMENTO (erro
# `[MG51] Para abrir novas posicoes`) -- prendendo a conta numa posicao
# perdedora sem conseguir sair.
#
# `contracts_from_capital(300, 150, buffer=2.0)` da' EXATAMENTE 1 contrato
# (300 = 150 x 2.0 x 1) -- matematicamente correto, mas SEM NENHUMA folga: o
# calculo "cabe exatamente 1" e o calculo "cabe exatamente 2" ficam separados
# por UM UNICO evento (uma segunda entrada independente que nao deveria ter
# passado pelo teto agregado, ver `backtest.intraday.machine.
# IntradaySessionMachine._cap_capital_atual`). O dono foi explicito sobre o
# que quer daqui pra frente: "operou com todos os contratos, ao inves de
# fazer uma estrategia segura mantendo sempre um caixa de seguranca".
#
# `RESERVA_CAIXA_SEGURANCA` e' a resposta a isso -- um SEGUNDO fator de
# seguranca, empilhado por CIMA de `MARGIN_BUFFER_FUTUROS` (que ja dobra a
# margem exigida por contrato, mas por um motivo DIFERENTE: cobrir 1 troca de
# lado, ver a nota longa em `MARGIN_BUFFER_FUTUROS`). Multiplicador em vez de
# fracao subtraida do caixa por ser a mesma forma matematica que o repo ja usa
# em `buffer` -- os dois compoem por multiplicacao no MESMO denominador
# (`margin_per_contract_brl x buffer x RESERVA_CAIXA_SEGURANCA`), nunca dois
# mecanismos concorrentes. `1.25` equivale a reservar 20% do caixa fora do
# calculo (`1 - 1/1.25 = 0.20`) -- NAO E' MEDICAO, e' DECISAO, mesmo espirito
# de `MARGIN_BUFFER_FUTUROS`: nao existe (ainda) estatistica de chamada de
# margem/slippage de fechamento neste repo para calibrar o numero certo.
# Ponto de apoio parcial (nao prova): a escada de capital medida por Monte
# Carlo de rejeicao de fila (`scripts/daytrade/capital_ladder_wdof1_
# oos_2026_08_27.py`, achado independente e ANTERIOR a este incidente) ja
# tinha encontrado que N=1 contrato de WDO F1 precisa de ~R$360 no OOS para
# nunca zerar em 30 sementes (20% acima do piso ingenuo de R$300) -- mesma
# ORDEM DE GRANDEZA da reserva aqui escolhida, por um caminho totalmente
# diferente (rejeicao de ordem, nao exposicao agregada).
#
# Efeito HONESTO e deliberado: para uma conta EXATAMENTE no piso de
# `MARGIN_BUFFER_FUTUROS` (como o WDO@ a R$300 do incidente), esta reserva
# reduz a capacidade calculada para MENOS de 1 contrato inteiro -- ou seja,
# sob esta regra, R$300 deixa de ser "capital minimo real" suficiente para
# abrir nenhum contrato COM folga. Isto e' proposital, nao um efeito colateral
# a esconder: o proprio incidente mostra que operar exatamente no limite, sem
# nenhuma folga, e' o que quebrou a conta. Quem quiser o numero CRU (sem
# reserva) continua podendo chamar `contracts_from_capital` direto -- esta
# funcao NUNCA o substitui, so' e' o caminho que qualquer sizing de ENTRADA
# REAL (motor ou estrategia) deve preferir.
RESERVA_CAIXA_SEGURANCA = 1.25


def contracts_from_capital_com_reserva(
    cash_brl: float,
    margin_per_contract_brl: float,
    buffer: float = MARGIN_BUFFER_FUTUROS,
    reserva: float = RESERVA_CAIXA_SEGURANCA,
    hard_cap: int | None = None,
) -> int:
    """`contracts_from_capital` (ver la' a mecanica pura, casos de borda e
    tolerancia de ponto flutuante -- tudo herdado sem mudanca) com a reserva
    de seguranca de `RESERVA_CAIXA_SEGURANCA` ja aplicada ao `buffer`.

    E' o UNICO caminho que o motor (`backtest.intraday.machine.
    IntradaySessionMachine`) e as estrategias com dimensionamento dinamico
    por capital (`WdoGridReloadMaker`, `CopaWin`) devem usar para transformar
    caixa corrente em "quantos contratos e' seguro ABRIR/MANTER agora" -- ter
    UM lugar so' fazendo essa conta e' o que garante que o motor e a
    estrategia nunca divergem sobre o numero (AGENTS.md: "um numero declarado
    em dois lugares e' um numero que vai divergir"). `contracts_from_capital`
    pura continua existindo e nao e' substituida -- serve para quem
    deliberadamente quer o numero CRU (ex.: `config_for(cash_brl=...,
    margin_per_contract_brl=...)`, um snapshot explicito e documentado, ou
    scripts de pesquisa que exploram a sensibilidade ao buffer)."""
    return contracts_from_capital(
        cash_brl, margin_per_contract_brl, buffer=buffer * reserva, hard_cap=hard_cap,
    )


# ---------- teto por RISCO por trade (2026-08-29, item 3.9) ----------------
# `contracts_from_capital_com_reserva` (acima) limita ALAVANCAGEM/margem --
# quantos contratos a CORRETORA deixa abrir sem chamada de margem. Medido no
# `CopaWin` (WIN@, R$3.000 real, 182 pregoes salvos): isso NAO limita RISCO.
# O caixa cresceu 43% num dia bom (R$3.000 -> R$4.290), o teto por margem
# escalou a proxima entrada de 12 para 15 contratos, e o MESMO `stop_vol` de
# sempre -- agora sobre 15 contratos em vez de 12 -- perdeu R$3.457,50 num
# unico trade: a conta foi de R$3.000,00 a R$68,50 (-97,7%) sem nunca ficar
# negativa, quase zerando com margem/reserva funcionando exatamente como
# desenhadas. Os dois tetos so' coincidem por acidente no tamanho em que
# foram medidos -- margem protege a CORRETORA (chamada de margem), nao o
# DONO (ruina por sequencia de stops). Ver `LICOES_DE_PRODUCAO.md` item 3.9.
#
# Uma ideia INTERMEDIARIA foi testada e REFUTADA antes desta (2026-08-29,
# `copawin_ratchet_skim_teste_2026_08_29.py`, memoria `copawin-ratchet-skim-
# refutado-risco-pct-validado`): "separar" uma fatia do caixa a cada marco de
# crescimento e parar de conta-la como caixa operacional. Nao funciona porque
# a fatia separada e' so' contabil (nunca sai da MESMA posicao/MESMA conta) e
# fica CONGELADA em reais -- quando o caixa recupera de uma perda, ela vira
# uma fracao cada vez MENOR do caixa atual, e o tamanho da entrada reinfla
# sem nenhum novo gatilho. Em alguns parametros testados isso deixou a conta
# em EQUITY NEGATIVA, pior que nao fazer nada.
def contracts_from_risk(
    cash_brl: float,
    risco_pct: float,
    stop_reais_por_unidade: float,
    hard_cap: int | None = None,
) -> int:
    """Quantos CONTRATOS (ou LOTES, a formula e' a mesma -- "unidade" e' o
    que quem chama dimensiona: 1 contrato de futuro ou 1 lote de acao) o
    caixa atual sustenta se o pior caso aceitavel (o STOP sendo tocado) nao
    puder consumir mais que `risco_pct` do caixa.

    Formula: `floor(cash_brl x risco_pct / stop_reais_por_unidade)`, truncado
    e nunca negativo -- mesma forma/mesmos casos de borda de `contracts_from_
    capital` (ver la' a nota sobre tolerancia de ponto flutuante). Ao
    contrario daquela, este teto e' RECALCULADO a cada entrada com o `stop_
    reais_por_unidade` DESSA entrada especifica (ex.: `stop_vol x volatilidade_
    atual x point_value_brl` no `CopaWin`, que muda de entrada pra entrada) --
    nunca com um valor ancorado num momento passado, que e' exatamente o
    defeito que derrubou a ideia do ratchet-skim acima.

    `stop_reais_por_unidade` e' parametro OBRIGATORIO, igual `margin_per_
    contract_brl` em `contracts_from_capital`: nunca uma constante interna,
    porque depende do STOP calibrado de cada robo (fixo em ticks, como
    `WdoGridReloadMaker`, ou por volatilidade do dia, como `CopaWin`) -- quem
    chama sempre sabe esse numero no instante da entrada, esta funcao nunca
    recalcula stop nenhum.

    `hard_cap`: mesma semantica de `contracts_from_capital` -- teto adicional
    aplicado DEPOIS (ex.: `teto_contratos` regulatorio), resultado e' sempre
    o MENOR dos dois. Combinar com `contracts_from_capital_com_reserva` (o
    chamador tira o `min()` dos dois resultados) da' as DUAS protecoes ao
    mesmo tempo -- margem/alavancagem E risco por trade -- nenhuma substitui
    a outra: alavancagem alta com risco baixo ainda so' abre o que o risco
    permite; risco alto com margem curta ainda so' abre o que a margem
    permite.

    Casos de borda: `cash_brl<=0` devolve `0` (nao erro -- caixa genuinamente
    insuficiente, mesmo espirito de `contracts_from_capital`). `risco_pct<=0`
    ou `stop_reais_por_unidade<=0` levanta `ValueError` -- um numero
    nao-positivo ali e' erro de quem chamou, nunca "sem teto"."""
    if risco_pct <= 0:
        raise ValueError(f"contracts_from_risk: risco_pct tem que ser positivo, recebeu {risco_pct!r}")
    if stop_reais_por_unidade <= 0:
        raise ValueError(
            f"contracts_from_risk: stop_reais_por_unidade tem que ser positivo, "
            f"recebeu {stop_reais_por_unidade!r}"
        )
    if cash_brl <= 0:
        unidades = 0
    else:
        unidades = int(math.floor(cash_brl * risco_pct / stop_reais_por_unidade + 1e-9))
        unidades = max(0, unidades)
    if hard_cap is not None:
        unidades = min(unidades, max(0, int(hard_cap)))
    return unidades
