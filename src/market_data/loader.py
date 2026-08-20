from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from core.config import BENCHMARK, DATA_DIR, WATCHLIST


def _path_for(ticker: str, out_dir: Path = DATA_DIR) -> Path:
    safe = ticker.replace("^", "_").replace(".", "_")
    return out_dir / f"{safe}.parquet"


def load_one(ticker: str, out_dir: Path = DATA_DIR) -> pd.DataFrame:
    path = _path_for(ticker, out_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"Parquet para {ticker} não encontrado em {path}. Rode scripts/download_data.py."
        )
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    return _drop_incomplete_tail(df.sort_index(), ticker)


def _drop_incomplete_tail(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Corta pregoes do FIM da serie que ainda nao tem fechamento.

    Um download feito com o mercado aberto grava a barra do dia com `open`
    preenchido e `close` vazio. Isso nao e um pregao — e meio pregao. Em
    2026-08-20, 40 dos 63 papeis de `strategy/liquid_sleeve.py::POOL` estavam
    assim, e a consequencia nao era um erro visivel: o backtest ia ate o fim,
    fechava a posicao aberta a mercado no ultimo dia e produzia um trade com
    preco de saida NaN. Esse trade ia para o diario, `fees_total` NaN virava
    NULL no SQLite e o INSERT estourava NOT NULL — derrubando a run inteira de
    ranking. Era por isso que o podio so tinha o robo da WATCHLIST: os sete
    papeis dela por acaso tinham fechamento, os do pool nao.

    So o RABO e cortado. Buraco no meio da serie e outro problema, tratado na
    origem por `market_data/quality.py` (`consensus_calendar` + `fill_gaps`) —
    apagar dado do meio aqui esconderia justamente o que aquele modulo procura.
    """
    if "close" not in df.columns or df.empty:
        return df
    validos = df["close"].notna().to_numpy().nonzero()[0]
    if len(validos) == 0:
        return df.iloc[:0]
    ultimo = int(validos[-1])
    return df if ultimo == len(df) - 1 else df.iloc[: ultimo + 1]


def load_universe(
    tickers: Iterable[str] = WATCHLIST,
    include_benchmark: bool = True,
    out_dir: Path = DATA_DIR,
) -> dict[str, pd.DataFrame]:
    result = {t: load_one(t, out_dir) for t in tickers}
    if include_benchmark:
        result[BENCHMARK] = load_one(BENCHMARK, out_dir)
    return result


MACRO_SERIES: tuple[str, ...] = ("selic", "usd_brl")


def _frame_digest(df: pd.DataFrame, cols: Iterable[str] | None = None) -> bytes:
    """Digest do CONTEUDO de um painel (indice + colunas de preco).

    Deliberadamente sobre conteudo, nao sobre o arquivo: um novo download que
    devolve exatamente os mesmos numeros produz o mesmo digest (nao forca
    retrabalho), mas qualquer revisao de close ajustado pelo provedor muda o
    digest — que e justamente o caso que passava batido.
    """
    h = hashlib.sha256()
    idx = df.index
    h.update(np.asarray(getattr(idx, "asi8", idx.astype("int64"))).tobytes())
    for col in (cols if cols is not None else ("open", "high", "low", "close")):
        if col not in df.columns:
            continue
        h.update(str(col).encode())
        h.update(np.ascontiguousarray(df[col].to_numpy(dtype="float64")).tobytes())
    return h.digest()


def universe_fingerprint(
    tickers: Iterable[str] = WATCHLIST,
    include_benchmark: bool = True,
    macros: Iterable[str] = MACRO_SERIES,
    out_dir: Path = DATA_DIR,
) -> str:
    """Impressao digital de TODO dado de entrada de um backtest oficial.

    Serve para detectar que uma run gravada no diario ficou stale: comparar
    apenas `period_end` nao basta, porque o provedor revisa closes ajustados
    retroativamente sem mover a ultima data. Ver
    `scheduler.refresh_champion_rankings()`.
    """
    h = hashlib.sha256()
    names = list(tickers) + ([BENCHMARK] if include_benchmark else [])
    for ticker in sorted(names):
        h.update(ticker.encode())
        try:
            h.update(_frame_digest(load_one(ticker, out_dir)))
        except FileNotFoundError:
            h.update(b":missing")
    for macro in sorted(macros):
        h.update(macro.encode())
        path = out_dir / f"{macro}.parquet"
        if not path.exists():
            h.update(b":missing")
            continue
        dfm = pd.read_parquet(path)
        h.update(_frame_digest(dfm, cols=list(dfm.columns)))
    return h.hexdigest()[:32]


def slice_period(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if start:
        df = df.loc[df.index >= pd.Timestamp(start)]
    if end:
        df = df.loc[df.index <= pd.Timestamp(end)]
    return df
