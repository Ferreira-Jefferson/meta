"""Fonte de preco, com procedencia declarada.

Regra de fronteira (AGENTS.md #6): `live/` nao decide nada, so busca dado e
declara a verdade sobre esse dado. Um `QuoteFeed` NUNCA maquia o proprio
atraso — o atraso declarado (`delay_seconds`) e o que permite ao runtime
recusar decisao intra-dia sobre dado velho (ver `staleness_report` abaixo e
`Quote.staleness_seconds` em `core/live_models.py`).

Tres implementacoes de producao (`src/`):

  - `ParquetCloseFeed`  — dado historico (D-1 ou mais velho), honesto por
    construcao: `delay_seconds` e a IDADE REAL do dado, calculada contra
    `now`, nao um numero fixo.
  - `YFinanceFeed`      — intradiario, best-effort, ~15min de atraso conhecido
    e documentado (ver docstring da classe).
  - `MT5Feed`           — intradiario, le o tick do MESMO terminal MT5 que
    `MT5Broker` usa para executar (ver docstring da classe para o aviso sobre
    o fuso do relogio do SERVIDOR do terminal).

`ReplayFeed` (dirigido a mao, para teste e simulacao deterministica) mora em
`tests/doubles.py` (FEAT-001) — nunca em `src/`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional, Sequence

import pandas as pd

from core import b3_session
from core.config import DATA_DIR
from core.live_models import Quote, SessionPhase
from live import clock


def _parquet_path(ticker: str, data_dir: Path) -> Path:
    """Mesma convencao de nome de `market_data.download.parquet_path`.

    Nao importamos de `market_data` aqui por acidente de conveniencia: e a
    regra de fronteira do AGENTS.md, `live/` PODE importar feature (o modulo
    inteiro `market_data`), entao poderiamos reusar `parquet_path` direto.
    Mantemos a funcao local, pequena e sem estado, para nao acoplar o feed ao
    layout interno de `market_data.download` (que pode evoluir para escrever
    em outro formato de arquivo sem quebrar este feed).
    """
    safe = ticker.replace("^", "_").replace(".", "_")
    return data_dir / f"{safe}.parquet"


class QuoteFeed(ABC):
    """Fonte de cotacao. Contrato: devolve preco + de onde ele veio.

    `is_realtime` e derivado de `delay_seconds` (nao um flag independente)
    para impedir que uma implementacao declare "tempo real" e ao mesmo tempo
    admita atraso — as duas coisas tem de concordar.
    """

    name: str

    @property
    @abstractmethod
    def delay_seconds(self) -> float:
        """Atraso DECLARADO da fonte, em segundos. Parte do contrato, nao
        um detalhe de implementacao — ver docstring de `Quote`."""
        raise NotImplementedError

    @property
    def is_realtime(self) -> bool:
        return self.delay_seconds <= 1.0

    @abstractmethod
    def quotes(self, tickers: Sequence[str]) -> dict[str, Quote]:
        """Cotacao para os tickers pedidos. Tickers sem cotacao disponivel
        ficam AUSENTES do dict (nao viram `None` nem erro) — quem chama decide
        o que fazer com a lacuna."""
        raise NotImplementedError

    def quote(self, ticker: str) -> Optional[Quote]:
        """Conveniencia para pedir um unico ticker."""
        return self.quotes([ticker]).get(ticker)


class ParquetCloseFeed(QuoteFeed):
    """Ultimo `close` dos parquets em `data/raw` (ou `data_dir` injetado).

    `delay_seconds` NAO e um numero fixo: e a diferenca real entre `now` (o
    instante da chamada, ou um `now` injetado para teste) e o timestamp da
    ultima barra do parquet. Se o parquet foi atualizado ontem, o feed declara
    ~86400s de atraso sem que ninguem precise lembrar de configurar isso —
    a honestidade vem da propria conta, nao de uma constante que alguem
    esqueceu de manter.
    """

    name = "parquet_close"
    source = "parquet"

    def __init__(
        self,
        data_dir: Path = DATA_DIR,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._data_dir = Path(data_dir)
        self._now_fn = now_fn
        self._last_age_seconds = 0.0

    @property
    def delay_seconds(self) -> float:
        """Idade do dado MAIS RECENTEMENTE lido (ver `quotes`). Antes de
        qualquer leitura, 0.0 — nao ha dado ainda para ter idade."""
        return self._last_age_seconds

    def quotes(self, tickers: Sequence[str]) -> dict[str, Quote]:
        now = self._now_fn()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        result: dict[str, Quote] = {}
        max_age = 0.0
        for ticker in tickers:
            path = _parquet_path(ticker, self._data_dir)
            if not path.exists():
                continue
            df = pd.read_parquet(path)
            if df.empty or "close" not in df.columns:
                continue
            df = df.sort_index()
            last_ts = pd.Timestamp(df.index[-1])
            ts = last_ts.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = max(0.0, (now - ts).total_seconds())
            max_age = max(max_age, age)
            result[ticker] = Quote(
                ticker=ticker,
                price=float(df["close"].iloc[-1]),
                ts=ts,
                source=self.source,
                delay_seconds=age,
                volume=(float(df["volume"].iloc[-1]) if "volume" in df.columns else None),
            )
        # guarda a maior idade observada nesta chamada para expor via
        # `delay_seconds` do feed (propriedade agregada, ver docstring acima).
        self._last_age_seconds = max_age
        return result


class YFinanceFeed(QuoteFeed):
    """Cotacao intradiaria via `yfinance`.

    ATENCAO, sem eufemismo: cotacao de ativo `.SA` no yfinance e ATRASADA em
    ~15 minutos, e o endpoint intradiario usado por baixo dos panos NAO e uma
    API oficial nem documentada pela B3/Yahoo — pode mudar ou cair sem aviso.
    Este feed serve para ACOMPANHAR a operacao (dashboard, alerta visual), e
    NAO para disparar stop com precisao: um stop avaliado sobre preco de 15
    minutos atras dispara DEPOIS do movimento, no fundo dele — a defesa que
    deveria evitar perda a executa tarde. Para decisao intra-dia real, use
    `staleness_report` para recusar a decisao, nunca confie neste feed sozinho.

    Import de `yfinance` e LAZY (dentro de `quotes`), de proposito: o resto do
    sistema (e os testes) nao deveria pagar o custo desse import nem falhar
    por falta de rede so por importar este modulo.
    """

    name = "yfinance"
    source = "yfinance"
    _DELAY_SECONDS = 900.0  # 15 minutos — atraso conhecido do provedor p/ .SA

    def __init__(self, on_error: Optional[Callable[[str, Exception], None]] = None) -> None:
        self._on_error = on_error

    @property
    def delay_seconds(self) -> float:
        return self._DELAY_SECONDS

    @property
    def is_realtime(self) -> bool:
        return False

    def quotes(self, tickers: Sequence[str]) -> dict[str, Quote]:
        """Busca cotacao intradiaria. Falha de rede (ou de qualquer ticker
        individual) NAO propaga excecao: devolve o que conseguiu (dict vazio
        ou parcial) e reporta o erro via `on_error`, se houver callback —
        porque um feed que explode em rede instavel derruba o runtime inteiro
        por um problema que e, por natureza, temporario."""
        try:
            import yfinance as yf  # lazy: ver docstring da classe
        except Exception as exc:  # pragma: no cover - ambiente sem yfinance
            self._report_error("import", exc)
            return {}

        result: dict[str, Quote] = {}
        now = datetime.now(timezone.utc)
        for ticker in tickers:
            try:
                fast = yf.Ticker(ticker).fast_info
                price = fast.get("last_price") if isinstance(fast, dict) else fast.last_price
                if price is None:
                    continue
                result[ticker] = Quote(
                    ticker=ticker,
                    price=float(price),
                    ts=now,
                    source=self.source,
                    delay_seconds=self._DELAY_SECONDS,
                )
            except Exception as exc:
                self._report_error(ticker, exc)
                continue
        return result

    def _report_error(self, ticker: str, exc: Exception) -> None:
        if self._on_error is not None:
            self._on_error(ticker, exc)


class MT5Feed(QuoteFeed):
    """Cotacao intradiaria via o MESMO terminal MT5 que `MT5Broker` usa para
    executar (pacote pip `MetaTrader5`).

    ATENCAO, sem eufemismo, MESMA FAMILIA de ressalva ja documentada no topo de
    `live/broker_mt5.py` (shares_per_lot/symbol_map/filling_type/comissao),
    agora um 5o item: `tick.time` (o instante do tick, segundo o pacote
    `MetaTrader5`) e o horario do RELOGIO DO SERVIDOR do terminal, NAO
    necessariamente UTC — corretoras costumam configurar o servidor MT5 num
    fuso proprio (ex.: GMT+2/GMT+3, ou UTC-3 no caso medido na Clear em
    2026-08-20), deslocado de UTC por horas. Esse offset, nao calibrado,
    SUBESTIMA o atraso real quando o servidor esta ADIANTADO em relacao a UTC
    (cotacao parecendo mais fresca do que e) — exatamente a direcao perigosa
    para o invariante de stop nunca disparar sobre dado velho (ver
    `live.runtime.intraday_tick`) — e, quando o servidor esta ATRASADO (caso
    medido na Clear, UTC-3), SOBRESTIMA o atraso a ponto de fazer `tick.time`
    parecer horas mais velho do que e, o que tambem e perigoso: com
    `staleness_report(max_quote_age=300)` isso faz TODA cotacao parecer velha
    demais e SUPRIME todo stop intradiario, silenciosamente, sem erro nenhum.

    O offset servidor<->UTC vem do FUSO DECLARADO E MEDIDO em
    `core.b3_session.MT5_SERVER_TIMEZONE` (hora de Brasilia), nao de uma
    inferencia. Este feed AUTOCALIBRAVA o offset a partir da idade aparente do
    tick mais novo do lote, e isso foi REMOVIDO em 2026-08-21 porque a
    inferencia e' ambigua por construcao: "tick de 1h atras" e "fuso 1h
    errado" produzem exatamente o mesmo numero. Medido no terminal real da
    Rico no mesmo dia, com o mercado ja fechado, a autocalibracao adotou
    **+4.0h** (o correto e' +3.0h) porque o tick mais novo do lote era de um
    papel iliquido que nao negociava havia ~1h — e um offset 1h errado troca a
    FASE do robo de day trade (ancora fixa vs rolante) e o minuto do flatten,
    o dia inteiro, sem erro nenhum. Nem `delay_seconds` servia de guarda: ele
    e' calculado COM o offset ja calibrado, logo e' circular.

    O que ficou no lugar: o offset declarado + uma CONFERENCIA que so acusa
    quando ha prova, nunca troca o numero por conta propria
    (`server_clock_alarm`, `verify_server_clock`). Um tick no FUTURO e' prova
    (nenhum atraso de dado explica isso); um tick velho nao e' — pode ser so
    iliquidez. Para resolver o caso ambiguo existe
    `core.b3_session.CLOCK_REFERENCE_TICKER`, um papel liquido o suficiente
    para que "sem tick" nao seja explicacao aceitavel dentro do pregao. Quem
    mediu outro offset e quer travar nele passa `server_utc_offset_hours`
    explicito no construtor.

    `now_fn` e injetavel (mesma convencao de `ParquetCloseFeed`) por isso: sem
    relogio injetavel, a idade do tick nao e testavel de forma deterministica
    — so aproximada, com tolerancia larga e instavel.

    Import de `MetaTrader5` e SEMPRE LAZY (dentro de `quotes`), mesmo motivo e
    mesmo padrao de `MT5Broker`/`YFinanceFeed`: nem todo ambiente que importa
    este modulo tem (ou deveria precisar ter) o pacote instalado.
    """

    name = "mt5"
    source = "mt5"

    #: quanto um tick pode aparecer no FUTURO antes de virar alarme. Cobre
    #: dessincronia normal entre o relogio desta maquina e o do servidor
    #: (NTP, latencia); acima disso o offset declarado esta errado, porque
    #: nenhum atraso de dado faz um tick chegar adiantado.
    _FUTURE_TOLERANCE_SECONDS = 120.0

    #: idade a partir da qual um tick do ticker de REFERENCIA (liquido), com o
    #: pregao aberto, e' tratada como prova de relogio errado. Uma hora inteira
    #: menos uma folga: o erro de fuso realista e' de 1h, e o papel de
    #: referencia nao fica 45min sem negociar durante o continuo.
    _REFERENCE_STALE_ALARM_SECONDS = 2700.0

    def __init__(
        self,
        symbol_map: Optional[dict[str, str]] = None,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        path: Optional[str] = None,
        on_error: Optional[Callable[[str, Exception], None]] = None,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        server_utc_offset_hours: Optional[float] = None,
        on_info: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._symbol_map = dict(symbol_map) if symbol_map else {}
        self._login = login
        self._password = password
        self._server = server
        self._path = path
        self._on_error = on_error
        self._on_info = on_info
        self._now_fn = now_fn
        self._connected = False
        self._last_delay_seconds = 0.0
        # Offset servidor<->UTC (horas somadas ao `tick.time`). Sem valor
        # explicito, vem do FUSO declarado e medido — nunca de inferencia
        # (ver docstring da classe).
        if server_utc_offset_hours is not None:
            self._offset_hours = float(server_utc_offset_hours)
            self._offset_source = "explicito"
        else:
            self._offset_hours = b3_session.server_utc_offset_hours()
            self._offset_source = "fuso_declarado"
        self._clock_alarm: Optional[str] = None

    @property
    def delay_seconds(self) -> float:
        """Maior atraso observado na leitura MAIS RECENTE (ver `quotes`).
        Antes de qualquer leitura, 0.0 — nao ha dado ainda para ter idade."""
        return self._last_delay_seconds

    @property
    def server_utc_offset_hours(self) -> float:
        """Offset (em horas) somado ao `tick.time` (relogio do servidor MT5)
        para chegar em UTC. Vem do fuso declarado em `core.b3_session`, ou do
        valor explicito passado ao construtor."""
        return self._offset_hours

    @property
    def offset_source(self) -> str:
        """`"fuso_declarado"` ou `"explicito"`. Nunca "auto": este feed nao
        infere mais o offset (ver docstring da classe)."""
        return self._offset_source

    @property
    def server_clock_alarm(self) -> Optional[str]:
        """Motivo, em texto, de o relogio do servidor NAO estar batendo com o
        fuso declarado — ou `None` se nada foi provado errado.

        Quem opera dinheiro real deve tratar isso como impedimento, nao como
        aviso: um robo que nao sabe que horas sao no servidor nao sabe quando
        achatar nem em que fase esta. Preenchido por `quotes` (tick no futuro,
        que e' prova incondicional) e por `verify_server_clock` (tick velho no
        papel liquido durante o continuo, que e' prova condicionada)."""
        return self._clock_alarm

    def symbol_for(self, ticker: str) -> str:
        """Ticker interno (`"WEGE3.SA"`) -> nome do simbolo no terminal MT5.

        Replica deliberadamente `MT5Broker.symbol_for` (ver docstring da
        classe, risco ativo aceito em ACTION-PLAN FEAT-004 §5): duplicacao
        pequena, mitigada porque `scripts/run_live.py::build()` passa o MESMO
        `symbol_map`/credenciais para os dois."""
        if ticker in self._symbol_map:
            return self._symbol_map[ticker]
        if ticker.endswith(".SA"):
            return ticker[: -len(".SA")]
        return ticker

    def _connect(self, mt5) -> bool:
        """Idempotente, mesmo padrao de `MT5Broker.connect()`: chamar
        `mt5.initialize()` de novo sem necessidade e, na pratica de alguns
        terminais, um jeito de perder estado de ordens em voo a toa."""
        if self._connected:
            return True
        kwargs = {}
        if self._path:
            kwargs["path"] = self._path
        if self._login is not None:
            kwargs["login"] = self._login
            kwargs["password"] = self._password
            kwargs["server"] = self._server
        try:
            ok = bool(mt5.initialize(**kwargs))
        except Exception:
            ok = False
        self._connected = ok
        return ok

    def quotes(self, tickers: Sequence[str]) -> dict[str, Quote]:
        """Busca cotacao intradiaria no terminal MT5. Falha de conexao (ou de
        qualquer ticker individual) NAO propaga excecao: devolve o que
        conseguiu (dict vazio ou parcial) e reporta via `on_error`, mesmo
        padrao de `YFinanceFeed`/`MT5Broker.place`."""
        try:
            import MetaTrader5 as mt5  # lazy: ver docstring da classe
        except Exception as exc:  # pragma: no cover - ambiente sem o pacote
            self._report_error("import", exc)
            return {}

        if not self._connect(mt5):
            try:
                code, desc = mt5.last_error()
            except Exception:
                code, desc = (None, "desconhecido")
            self._report_error(
                "connect",
                RuntimeError(f"falha ao conectar ao terminal MT5 (last_error={code}: {desc})"),
            )
            return {}

        now = self._now_fn()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        raw_ticks: dict[str, object] = {}
        for ticker in tickers:
            try:
                symbol = self.symbol_for(ticker)
                mt5.symbol_select(symbol, True)
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    continue
                raw_ticks[ticker] = tick
            except Exception as exc:
                self._report_error(ticker, exc)
                continue

        self._check_for_future_tick(raw_ticks, now)

        # Converte preco e horario com o offset declarado, igual para todos os
        # tickers do lote.
        result: dict[str, Quote] = {}
        max_delay = 0.0
        for ticker, tick in raw_ticks.items():
            try:
                last = getattr(tick, "last", None)
                price = float(last) if last else (float(tick.bid) + float(tick.ask)) / 2.0
                # `tick.time`: instante do tick segundo o RELOGIO DO SERVIDOR
                # do terminal — ver aviso de fuso na docstring da classe.
                # Corrigido pelo offset servidor<->UTC antes de comparar com
                # `now` (que esta em UTC) — sem essa correcao o `delay`
                # calculado aqui herda o offset inteiro do servidor.
                tick_time = self._tick_time_utc(tick)
                delay = max(0.0, (now - tick_time).total_seconds())
                max_delay = max(max_delay, delay)
                result[ticker] = Quote(
                    ticker=ticker,
                    price=price,
                    ts=tick_time,
                    source=self.source,
                    delay_seconds=delay,
                )
            except Exception as exc:
                self._report_error(ticker, exc)
                continue
        self._last_delay_seconds = max_delay
        return result

    def _tick_time_utc(self, tick: object) -> datetime:
        """`tick.time` (hora de parede do servidor) corrigido para UTC."""
        return datetime.fromtimestamp(tick.time, tz=timezone.utc) + timedelta(
            hours=self._offset_hours
        )

    def _check_for_future_tick(self, raw_ticks: dict[str, object], now: datetime) -> None:
        """Acende `server_clock_alarm` se algum tick do lote chega ADIANTADO.

        Este e o unico teste que da prova incondicional a partir de uma
        leitura qualquer: atraso de dado sempre empurra o tick para o
        passado, entao um tick no futuro so pode significar que o offset
        aplicado esta grande demais — ou seja, o fuso declarado nao e o do
        servidor. O contrario (tick velho) NAO e' prova: e' indistinguivel de
        iliquidez, e foi exatamente essa ambiguidade que fez a antiga
        autocalibracao adotar +4h. Ver `verify_server_clock` para o teste que
        resolve o caso ambiguo.
        """
        if not raw_ticks:
            self._clock_alarm = None
            return
        mais_novo = max(self._tick_time_utc(t) for t in raw_ticks.values())
        adiantado = (mais_novo - now).total_seconds()
        if adiantado > self._FUTURE_TOLERANCE_SECONDS:
            self._clock_alarm = (
                f"tick do servidor MT5 esta {adiantado:.0f}s NO FUTURO com o offset "
                f"declarado de {self._offset_hours:+.1f}h — o fuso do servidor mudou? "
                "Nenhum atraso de dado explica um tick adiantado."
            )
            self._report_error("relogio", RuntimeError(self._clock_alarm))
        else:
            self._clock_alarm = None

    def verify_server_clock(
        self, reference_ticker: Optional[str] = None
    ) -> Optional[str]:
        """Confere o relogio do servidor contra um papel LIQUIDO e devolve o
        motivo do alarme (ou `None` se esta tudo coerente).

        Chame isto no inicio da sessao, e nao a cada barra: e' uma leitura
        extra de tick. O papel de referencia
        (`core.b3_session.CLOCK_REFERENCE_TICKER`) e' o que torna o teste
        conclusivo — durante o continuo ele negocia todo minuto, entao um tick
        velho dele nao tem a desculpa de iliquidez que o papel operado tem.

        Fora da fase OPEN a conferencia por ATRASO nao roda (com o mercado
        fechado, todo tick fica velho por definicao — foi assim que a
        autocalibracao antiga errou). O teste de tick no futuro vale sempre.
        """
        ticker = reference_ticker or b3_session.CLOCK_REFERENCE_TICKER
        quotes = self.quotes([ticker])
        if self._clock_alarm is not None:
            return self._clock_alarm  # tick no futuro: ja e' prova
        quote = quotes.get(ticker)
        if quote is None:
            return None  # sem tick nenhum nao ha o que concluir
        if clock.phase() != SessionPhase.OPEN:
            return None
        if quote.delay_seconds > self._REFERENCE_STALE_ALARM_SECONDS:
            self._clock_alarm = (
                f"tick de {ticker} (papel de referencia, liquido) esta "
                f"{quote.delay_seconds / 60:.0f}min velho com o pregao ABERTO e offset "
                f"declarado de {self._offset_hours:+.1f}h — o relogio do servidor MT5 "
                "provavelmente nao esta no fuso declarado."
            )
            self._report_error("relogio", RuntimeError(self._clock_alarm))
        return self._clock_alarm

    def _report_error(self, ticker: str, exc: Exception) -> None:
        if self._on_error is not None:
            self._on_error(ticker, exc)


def staleness_report(
    quotes: dict[str, Quote], now: datetime, max_age_seconds: float
) -> dict[str, float]:
    """Tickers cujo dado passou do limite de idade aceitavel.

    Devolve APENAS os tickers estragados (ticker -> staleness_seconds), nao o
    universo inteiro — o runtime usa isso para se recusar a decidir sobre
    quem aparece aqui, em vez de precisar filtrar o dict inteiro toda vez.
    """
    stale: dict[str, float] = {}
    for ticker, quote in quotes.items():
        age = quote.staleness_seconds(now)
        if age > max_age_seconds:
            stale[ticker] = age
    return stale
