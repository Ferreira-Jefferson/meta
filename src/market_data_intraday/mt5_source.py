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
NAO UTC. Medido contra o WIN@ salvo em 2026-08-20 (barra `_bars_to_df` sem
correcao): o ultimo horario de cada pregao ficava ~18:24, que bate com o
FECHAMENTO REAL do WIN em horario de Brasilia (nao em UTC, que seria por
volta de 21:24) — ou seja, o campo cru E hora local do servidor, so
rotulada como UTC sem nenhuma correcao. `server_utc_offset_hours` default
3.0 reusa o MESMO offset ja medido para cotacao ao vivo nesta corretora
(`tests/test_live_feed.py::test_mt5feed_autocalibra_offset_utc_menos_3_
com_ticks_reais_da_clear`, Clear, 2026-08-20) — nao e recalibrado aqui a
cada fetch (nao ha tick vivo fresco disponivel na maioria das vezes que
se busca HISTORICO, diferente de cotacao ao vivo): passe um valor
diferente explicitamente se a corretora/terminal mudar, ou se o offset
migrar (troca de servidor, mudanca de fuso).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

import pandas as pd


MAX_BARS_PER_REQUEST = 99999

# Offset servidor<->UTC (em horas, somado ao `time` cru) — ver aviso de fuso
# na docstring do modulo. Mesmo valor ja medido para `live.feed.MT5Feed`
# contra o terminal da Clear.
DEFAULT_SERVER_UTC_OFFSET_HOURS = 3.0


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


def _bars_to_df(rates, server_utc_offset_hours: float) -> pd.DataFrame:
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True) + pd.Timedelta(hours=server_utc_offset_hours)
    df = df.set_index("time").sort_index()
    df.index.name = "time"
    return df


def fetch_m1_range(
    symbol: str,
    start: datetime,
    end: datetime,
    on_error: Optional[Callable[[str, Exception], None]] = None,
    server_utc_offset_hours: float = DEFAULT_SERVER_UTC_OFFSET_HOURS,
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

    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    return _bars_to_df(rates, server_utc_offset_hours)


def fetch_m1_recent(
    symbol: str,
    count: int = MAX_BARS_PER_REQUEST,
    on_error: Optional[Callable[[str, Exception], None]] = None,
    server_utc_offset_hours: float = DEFAULT_SERVER_UTC_OFFSET_HOURS,
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

    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    return _bars_to_df(rates, server_utc_offset_hours)


def fetch_m1_full_history(
    symbol: str,
    on_error: Optional[Callable[[str, Exception], None]] = None,
    server_utc_offset_hours: float = DEFAULT_SERVER_UTC_OFFSET_HOURS,
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
        if rates is None or len(rates) == 0:
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
