"""Armazenamento local do M1 baixado via `mt5_source.py`.

Parquet por simbolo, em `INTRADAY_DATA_DIR` (nunca em `DATA_DIR` — ver
docstring de `core.config.INTRADAY_DATA_DIR`). Duplica o padrao de
`market_data.download` (`parquet_path`/`write_parquet_atomico`/
`merge_preserving_history`) em vez de importa-lo — regra de fronteira
(AGENTS.md #1), feature so importa `core/`.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from core.config import INTRADAY_DATA_DIR


def _parquet_path(symbol: str, data_dir: Path = INTRADAY_DATA_DIR) -> Path:
    """Sanitiza chars que simbolos de futuro usam e que nao sao seguros em
    nome de arquivo (`$`, `@`) — `market_data.download.parquet_path` so
    trata `^`/`.`, insuficiente aqui (ex.: `WIN@` -> `WIN_A_`)."""
    safe = symbol.replace("$", "_D_").replace("@", "_A_").replace(".", "_")
    return data_dir / f"{safe}.parquet"


def _write_parquet_atomic(df: pd.DataFrame, path: Path) -> Path:
    """Mesma tecnica de `market_data.download.write_parquet_atomico`: grava
    num temporario no MESMO diretorio e usa `os.replace` (atomico), para um
    leitor concorrente (dashboard, outro backtest) nunca ver um parquet
    truncado no meio da escrita."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        df.to_parquet(tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def load_m1(symbol: str, data_dir: Path = INTRADAY_DATA_DIR) -> pd.DataFrame:
    """DataFrame vazio (nunca excecao) quando o parquet ainda nao existe."""
    path = _parquet_path(symbol, data_dir)
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    return df


def merge_m1(
    symbol: str, df_new: pd.DataFrame, data_dir: Path = INTRADAY_DATA_DIR
) -> tuple[pd.DataFrame, int]:
    """Uniao idempotente entre o parquet existente e `df_new`, indexada por
    timestamp. Em timestamp sobreposto o fetch NOVO vence (mesma regra de
    `market_data.download.merge_preserving_history` — correcao legitima do
    provedor vale); barra antiga ausente do fetch novo e SEMPRE resgatada,
    nunca descartada — a janela do servidor MT5 rola para frente, entao uma
    barra que sair da janela hoje pode ser a UNICA copia que vai existir
    dela para sempre.

    Grava o resultado e devolve (df final, quantidade de linhas
    GENUINAMENTE novas — timestamps que o parquet anterior nao tinha)."""
    old = load_m1(symbol, data_dir)
    if old.empty:
        merged = df_new.sort_index()
        _write_parquet_atomic(merged, _parquet_path(symbol, data_dir))
        return merged, len(merged)

    novos = df_new.index.difference(old.index)
    merged = df_new.combine_first(old).sort_index()
    _write_parquet_atomic(merged, _parquet_path(symbol, data_dir))
    return merged, len(novos)
