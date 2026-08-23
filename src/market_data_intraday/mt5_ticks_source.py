"""Busca tick a tick (trade ticks) via o terminal MT5 local -- a menor
granularidade que o terminal oferece, abaixo do M1 de `mt5_source.py`.

Regra de fronteira (AGENTS.md #1): feature so importa `core/`. Mesmo padrao
de import LAZY do `MetaTrader5` de `mt5_source.py` -- nem todo ambiente que
importa este modulo tem o pacote instalado.

MT5 devolve tres tipos de tick misturados no mesmo stream: atualizacoes de
bid/ask (sem negocio nenhum), e ticks de NEGOCIO de verdade (`last`+`volume`
populados). So o segundo tipo importa para simular um robo maker (a decisao
"o preco tocou o nivel X" so' vale quando alguem efetivamente negociou ali) --
`mt5.COPY_TICKS_TRADE` ja filtra isso no proprio terminal, medido em
2026-08-22: um pedido com `COPY_TICKS_ALL` devolve 2 linhas por negocio (uma
de negocio, uma de bid/ask resultante); com `COPY_TICKS_TRADE` devolve so' a
linha de negocio.

Paginacao por TEMPO, nao por posicao: ao contrario de `copy_rates_from_pos`
(M1), a API de tick do MT5 nao tem "posicao" -- so' `copy_ticks_from(symbol,
data_inicio, count, flags)`. Cada pagina usa o `time_msc` do ULTIMO tick da
pagina anterior como proximo `data_inicio`, o que pode repetir esse tick na
pagina seguinte (o terminal nao documenta se a borda e inclusiva) -- por
isso `merge_ticks` (`tick_storage.py`) deduplica por LINHA INTEIRA, nao so'
por timestamp: dois negocios genuinos no MESMO milissegundo tem
bid/ask/last/volume proprios e sobrevivem; um tick repetido pela paginacao
tem todos os campos identicos e e' descartado.

`MAX_TICKS_PER_REQUEST`: sem limite documentado (testado ate 500k ticks
numa unica chamada sem erro), mas pagina em blocos menores por seguranca --
mesmo espirito defensivo de `mt5_source.MAX_BARS_PER_REQUEST`, so' que aqui
o numero e' precaucao, nao um limite medido do terminal."""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

import pandas as pd

from core.b3_session import MT5_SERVER_TIMEZONE, server_utc_offset_hours

MAX_TICKS_PER_REQUEST = 200_000

DEFAULT_SERVER_UTC_OFFSET_HOURS = server_utc_offset_hours()

#: Data de partida da paginacao de historico completo -- so' precisa ser
#: "antes de qualquer tick real existir". O terminal retorna o tick mais
#: antigo que realmente tem (medido 2026-08-22: PMAM3 comeca em 2024-11-01
#: mesmo pedindo desde 2000), entao um numero redondo aqui nao trava nada.
_GENESIS = datetime(2000, 1, 1)


def _connect(mt5, login=None, password=None, server=None, path=None) -> bool:
    """Identico a `mt5_source._connect` -- duplicado de proposito (feature
    nao importa feature, regra 1 do AGENTS.md; `mt5_source.py` e
    `mt5_ticks_source.py` sao dois arquivos da MESMA feature
    `market_data_intraday`, mas a conexao MT5 e' um detalhe pequeno o
    bastante para nao valer criar acoplamento entre os dois so' por isto)."""
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


def _ticks_to_df(ticks, server_utc_offset_hours: Optional[float]) -> pd.DataFrame:
    """Index em UTC de verdade (com milissegundo), a partir de `time_msc`
    (hora de parede do servidor, mesmo aviso de fuso de
    `mt5_source._bars_to_df` -- so' que em ms em vez de segundos inteiros,
    entao dois negocios no mesmo segundo nao colapsam num so' timestamp)."""
    df = pd.DataFrame(ticks)
    parede = pd.to_datetime(df["time_msc"], unit="ms")
    if server_utc_offset_hours is None:
        utc = parede.dt.tz_localize(MT5_SERVER_TIMEZONE, ambiguous="NaT",
                                    nonexistent="NaT").dt.tz_convert("UTC")
    else:
        utc = parede.dt.tz_localize("UTC") + pd.Timedelta(hours=server_utc_offset_hours)
    df = df[["bid", "ask", "last", "volume", "volume_real", "flags"]].copy()
    df.index = utc
    df.index.name = "time"
    df = df[df.index.notna()].sort_index()
    return df


def fetch_ticks_range(
    symbol: str,
    start: datetime,
    end: datetime,
    on_error: Optional[Callable[[str, Exception], None]] = None,
    server_utc_offset_hours: Optional[float] = None,
    **connect_kwargs,
) -> pd.DataFrame:
    """Trade ticks de `symbol` entre `start` e `end`. DataFrame vazio (nunca
    excecao) se o terminal/simbolo falhar -- mesmo contrato de
    `mt5_source.fetch_m1_range`."""
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
        ticks = mt5.copy_ticks_range(symbol, start, end, mt5.COPY_TICKS_TRADE)
    except Exception as exc:
        _report_error(on_error, symbol, exc)
        return pd.DataFrame()

    if ticks is None or len(ticks) == 0:
        return pd.DataFrame()
    return _ticks_to_df(ticks, server_utc_offset_hours)


def fetch_ticks_full_history(
    symbol: str,
    on_error: Optional[Callable[[str, Exception], None]] = None,
    server_utc_offset_hours: Optional[float] = None,
    **connect_kwargs,
) -> pd.DataFrame:
    """Pagina `copy_ticks_from` a partir de `_GENESIS` ate um lote menor que
    `MAX_TICKS_PER_REQUEST` voltar (= alcancou o tick mais recente
    disponivel) -- mesmo espirito de `mt5_source.fetch_m1_full_history`,
    adaptado para paginacao por tempo (ver docstring do modulo)."""
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
    cursor = _GENESIS
    while True:
        try:
            ticks = mt5.copy_ticks_from(symbol, cursor, MAX_TICKS_PER_REQUEST, mt5.COPY_TICKS_TRADE)
        except Exception as exc:
            _report_error(on_error, symbol, exc)
            break
        if ticks is None or len(ticks) == 0:
            break
        chunks.append(_ticks_to_df(ticks, server_utc_offset_hours))
        if len(ticks) < MAX_TICKS_PER_REQUEST:
            break
        cursor = pd.to_datetime(int(ticks[-1]["time_msc"]), unit="ms").to_pydatetime()

    if not chunks:
        return pd.DataFrame()
    merged = pd.concat(chunks)
    # `duplicated()` sozinho so' olha colunas, ignorando o index -- dois
    # negocios diferentes com bid/ask/last/volume/flags identicos por
    # coincidencia (comum: mesmo lote redondo, mesmo preco) mas em
    # timestamps DIFERENTES nao podem ser tratados como o mesmo tick
    # repetido pela paginacao. Inclui o timestamp na comparacao.
    merged = merged.reset_index(names="time")
    merged = merged[~merged.duplicated(keep="last")].set_index("time")
    return merged.sort_index()
