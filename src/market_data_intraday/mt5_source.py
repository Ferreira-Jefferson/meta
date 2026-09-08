"""Busca M1 de futuros via o terminal MT5 local (pacote pip `MetaTrader5`).

Regra de fronteira (AGENTS.md #1): feature so importa `core/`. Este modulo
NAO importa `live/` nem `market_data/` — duplica o pequeno pedaco de
conexao/lazy-import que `live/feed.py::MT5Feed` ja usa, pelo mesmo motivo
que `live/feed.py::_parquet_path` duplica `market_data.download.
parquet_path` em vez de importa-lo: cada lado e uma feature/camada
diferente, e a duplicacao pequena e o preco de nao acoplar.

Import de `MetaTrader5` e SEMPRE LAZY (dentro de cada funcao), mesmo padrao
de `MT5Feed`: nem todo ambiente que importa este modulo tem (ou deveria
precisar ter) o pacote instalado.

`MAX_BARS_PER_REQUEST = 99999`: pedir exatamente 100000 barras devolve
"Invalid params" (medido contra o terminal da Clear em 2026-08-20) — off-by-
one no `maxbars` do terminal, nao documentado pelo pacote.

ATENCAO, mesmo aviso de fuso ja documentado em `live/feed.py::MT5Feed`: o
campo `time` que `copy_rates_*` devolve e o RELOGIO DO SERVIDOR do terminal,
NAO UTC — e' a hora de parede do servidor, so rotulada como epoch UTC sem
nenhuma correcao. Qual fuso e' esse esta MEDIDO e declarado em
`core.b3_session.MT5_SERVER_TIMEZONE` (hora de Brasilia, conferida de tres
formas independentes em 2024-01..2026-08); a conversao aqui e' feita pelo
FUSO e nao por um escalar, porque um escalar ficaria errado metade do ano se
o fuso do servidor passasse a ter horario de verao — e essa e' a familia de
bug que ja suprimiu 100% dos stops intradiarios em producao uma vez.

`server_utc_offset_hours` continua existindo como ESCAPE: passe um numero
explicito se voce mediu um offset diferente (troca de corretora/servidor) e
quer travar nele. `None` (default) = converte pelo fuso declarado.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

import pandas as pd

from core.b3_session import MT5_SERVER_TIMEZONE, server_utc_offset_hours


MAX_BARS_PER_REQUEST = 99999

#: Offset servidor<->UTC em horas, para quem precisa de um ESCALAR (o painel
#: reporta este numero, e `live/bar_feed.py` o usa em log). Derivado do fuso
#: declarado, nunca digitado a mao — ver docstring do modulo.
DEFAULT_SERVER_UTC_OFFSET_HOURS = server_utc_offset_hours()


@dataclass(frozen=True)
class SymbolEconomics:
    """Economia do contrato, lida do terminal — nunca hardcoded (mesma
    filosofia de `MT5Feed` autocalibrar o fuso do servidor em vez de
    assumir um numero)."""

    symbol: str
    point: float
    trade_contract_size: float
    trade_tick_size: float
    trade_tick_value: float


def _connect(mt5, login=None, password=None, server=None, path=None) -> bool:
    """Idempotente — mesmo padrao de `MT5Feed._connect`/`MT5Broker.connect`."""
    kwargs = {}
    if path:
        kwargs["path"] = path
    if login is not None:
        kwargs["login"] = login
        kwargs["password"] = password
        kwargs["server"] = server
    try:
        return bool(mt5.initialize(**kwargs))
    except Exception:
        return False


def _report_error(on_error: Optional[Callable[[str, Exception], None]], key: str, exc: Exception) -> None:
    if on_error is not None:
        on_error(key, exc)


def _falha_de_leitura(mt5, resultado, chamada: str) -> Optional[RuntimeError]:
    """Distingue "NAO HA barra nova" de "NAO CONSEGUI ler" -- devolve o erro
    da segunda, `None` na primeira.

    Gemeo de `mt5_ticks_source._falha_de_leitura`, duplicado pelo mesmo motivo
    de `_connect` (ver a docstring de la'): sao dois arquivos da mesma feature,
    e o pedaco e' pequeno demais para valer acoplamento. A docstring COMPLETA,
    com a medicao no terminal real que sustenta o corte em `< 0`, esta em
    `mt5_ticks_source.py` -- este caminho M1 nunca foi visto cegar, mas o
    `resultado is None or len(...) == 0 -> DataFrame()` era identico, e
    corrigir so' a instancia que mordeu e' como este repo perde a lembranca
    (2026-09-08, item 5.17 do `LICOES_DE_PRODUCAO.md`).
    """
    if resultado is None:
        return RuntimeError(f"{chamada} devolveu None (last_error={mt5.last_error()})")
    if len(resultado) == 0:
        erro = mt5.last_error()
        if isinstance(erro, (tuple, list)) and erro and int(erro[0]) < 0:
            return RuntimeError(f"{chamada} devolveu vazio com last_error={erro}")
    return None


def _bars_to_df(rates, server_utc_offset_hours: Optional[float]) -> pd.DataFrame:
    """Index em UTC de verdade, a partir da hora de parede do servidor.

    `server_utc_offset_hours=None` (o caminho normal) converte pelo FUSO
    declarado em `core.b3_session`; um numero explicito soma esse offset e
    ignora o fuso (escape para offset medido a mao — ver docstring do modulo).
    """
    df = pd.DataFrame(rates)
    # O campo cru NAO e' epoch UTC: e' a hora de parede do servidor. Por isso
    # decodificamos como naive primeiro e so depois dizemos em que fuso ela
    # esta — inverter isso e' o proprio bug de fuso.
    parede = pd.to_datetime(df["time"], unit="s")
    if server_utc_offset_hours is None:
        # `NaT` nas horas ambigua/inexistente de uma virada de horario de
        # verao: o Brasil nao tem desde 2019, e quando tinha a virada era a
        # meia-noite — com o mercado fechado. Descartar essas barras e' honesto;
        # rotula-las com a hora errada nao seria.
        utc = parede.dt.tz_localize(MT5_SERVER_TIMEZONE, ambiguous="NaT",
                                    nonexistent="NaT").dt.tz_convert("UTC")
    else:
        utc = parede.dt.tz_localize("UTC") + pd.Timedelta(hours=server_utc_offset_hours)
    df["time"] = utc
    df = df.dropna(subset=["time"]).set_index("time").sort_index()
    df.index.name = "time"
    return df


def fetch_m1_range(
    symbol: str,
    start: datetime,
    end: datetime,
    on_error: Optional[Callable[[str, Exception], None]] = None,
    server_utc_offset_hours: Optional[float] = None,
    **connect_kwargs,
) -> pd.DataFrame:
    """M1 de `symbol` entre `start` e `end`. DataFrame vazio (nunca excecao)
    se o terminal/simbolo falhar — mesmo contrato de `MT5Feed.quotes`."""
    try:
        import MetaTrader5 as mt5
    except Exception as exc:  # pragma: no cover - ambiente sem o pacote
        _report_error(on_error, "import", exc)
        return pd.DataFrame()

    if not _connect(mt5, **connect_kwargs):
        _report_error(
            on_error, "connect",
            RuntimeError(f"falha ao conectar ao terminal MT5 (last_error={mt5.last_error()})"),
        )
        return pd.DataFrame()

    try:
        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, start, end)
    except Exception as exc:
        _report_error(on_error, symbol, exc)
        return pd.DataFrame()

    falha = _falha_de_leitura(mt5, rates, "copy_rates_range")
    if falha is not None:
        _report_error(on_error, symbol, falha)
        return pd.DataFrame()
    if len(rates) == 0:
        return pd.DataFrame()
    return _bars_to_df(rates, server_utc_offset_hours)


def fetch_m1_recent(
    symbol: str,
    count: int = MAX_BARS_PER_REQUEST,
    on_error: Optional[Callable[[str, Exception], None]] = None,
    server_utc_offset_hours: Optional[float] = None,
    **connect_kwargs,
) -> pd.DataFrame:
    """As `count` barras M1 mais recentes de `symbol` (limitado a
    `MAX_BARS_PER_REQUEST` — ver docstring do modulo)."""
    count = min(count, MAX_BARS_PER_REQUEST)
    try:
        import MetaTrader5 as mt5
    except Exception as exc:  # pragma: no cover - ambiente sem o pacote
        _report_error(on_error, "import", exc)
        return pd.DataFrame()

    if not _connect(mt5, **connect_kwargs):
        _report_error(
            on_error, "connect",
            RuntimeError(f"falha ao conectar ao terminal MT5 (last_error={mt5.last_error()})"),
        )
        return pd.DataFrame()

    try:
        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, count)
    except Exception as exc:
        _report_error(on_error, symbol, exc)
        return pd.DataFrame()

    falha = _falha_de_leitura(mt5, rates, "copy_rates_from_pos")
    if falha is not None:
        _report_error(on_error, symbol, falha)
        return pd.DataFrame()
    if len(rates) == 0:
        return pd.DataFrame()
    return _bars_to_df(rates, server_utc_offset_hours)


def fetch_m1_full_history(
    symbol: str,
    on_error: Optional[Callable[[str, Exception], None]] = None,
    server_utc_offset_hours: Optional[float] = None,
    **connect_kwargs,
) -> pd.DataFrame:
    """Pagina `copy_rates_from_pos` com `start_pos` crescente ate um lote
    vazio (ou menor que o pedido) voltar — descobre a profundidade REAL do
    servidor em vez de assumir um numero fixo, porque essa profundidade MUDA
    dia a dia (a janela do broker rola para frente — nao e um arquivo
    acumulativo, e uma janela movel)."""
    try:
        import MetaTrader5 as mt5
    except Exception as exc:  # pragma: no cover - ambiente sem o pacote
        _report_error(on_error, "import", exc)
        return pd.DataFrame()

    if not _connect(mt5, **connect_kwargs):
        _report_error(
            on_error, "connect",
            RuntimeError(f"falha ao conectar ao terminal MT5 (last_error={mt5.last_error()})"),
        )
        return pd.DataFrame()

    try:
        mt5.symbol_select(symbol, True)
    except Exception as exc:
        _report_error(on_error, symbol, exc)
        return pd.DataFrame()

    chunks: list[pd.DataFrame] = []
    start_pos = 0
    while True:
        try:
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, start_pos, MAX_BARS_PER_REQUEST)
        except Exception as exc:
            _report_error(on_error, symbol, exc)
            break
        falha = _falha_de_leitura(mt5, rates, "copy_rates_from_pos")
        if falha is not None:
            _report_error(on_error, symbol, falha)
            break
        if len(rates) == 0:
            break
        chunks.append(_bars_to_df(rates, server_utc_offset_hours))
        if len(rates) < MAX_BARS_PER_REQUEST:
            break
        start_pos += len(rates)

    if not chunks:
        return pd.DataFrame()
    merged = pd.concat(chunks)
    return merged[~merged.index.duplicated(keep="last")].sort_index()


def symbol_economics(
    symbol: str,
    on_error: Optional[Callable[[str, Exception], None]] = None,
    **connect_kwargs,
) -> Optional[SymbolEconomics]:
    """`None` (nunca excecao) se o terminal/simbolo nao responder."""
    try:
        import MetaTrader5 as mt5
    except Exception as exc:  # pragma: no cover - ambiente sem o pacote
        _report_error(on_error, "import", exc)
        return None

    if not _connect(mt5, **connect_kwargs):
        _report_error(
            on_error, "connect",
            RuntimeError(f"falha ao conectar ao terminal MT5 (last_error={mt5.last_error()})"),
        )
        return None

    try:
        info = mt5.symbol_info(symbol)
    except Exception as exc:
        _report_error(on_error, symbol, exc)
        return None
    if info is None:
        return None
    return SymbolEconomics(
        symbol=symbol,
        point=float(info.point),
        trade_contract_size=float(info.trade_contract_size),
        trade_tick_size=float(info.trade_tick_size),
        trade_tick_value=float(info.trade_tick_value),
    )
