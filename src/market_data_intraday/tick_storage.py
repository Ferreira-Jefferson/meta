"""Armazenamento local do tick a tick baixado via `mt5_ticks_source.py`.

Parquet por simbolo, em `TICK_DATA_DIR` -- diretorio PROPRIO do M1 (ver
docstring de `core.config.TICK_DATA_DIR`). Reusa `storage._write_parquet_atomic`
por import direto: `tick_storage.py` e `storage.py` sao dois arquivos da
MESMA feature (`market_data_intraday`), e a regra de fronteira do AGENTS.md
#1 e' sobre uma feature importar OUTRA feature -- nao sobre arquivos dentro
dela. Duplicar essa funcao aqui so' divergiria as duas implementacoes do
mesmo truque (escrever num temporario + `os.replace`) sem ganhar nada.

Merge de tick e' DIFERENTE do merge de M1 (`storage.merge_m1`): M1 tem no
maximo UMA barra por minuto, entao `combine_first` por timestamp basta. Tick
pode ter VARIOS negocios no mesmo milissegundo -- colidir por timestamp
apagaria negocios genuinos e distintos. `merge_ticks` deduplica por LINHA
INTEIRA (todas as colunas), que so' descarta um tick repetido pela paginacao
de `mt5_ticks_source.fetch_ticks_full_history` (mesmo timestamp E mesmos
bid/ask/last/volume/flags)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.config import TICK_DATA_DIR
from market_data_intraday.storage import _write_parquet_atomic


def _parquet_path(symbol: str, data_dir: Path = TICK_DATA_DIR) -> Path:
    safe = symbol.replace("$", "_D_").replace("@", "_A_").replace(".", "_")
    return data_dir / f"{safe}.parquet"


def load_ticks(symbol: str, data_dir: Path = TICK_DATA_DIR) -> pd.DataFrame:
    """DataFrame vazio (nunca excecao) quando o parquet ainda nao existe."""
    path = _parquet_path(symbol, data_dir)
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    return df


def _dedupe_full_row(df: pd.DataFrame) -> pd.DataFrame:
    """`duplicated()` sozinho so' olha COLUNAS, ignorando o index -- dois
    negocios diferentes que por coincidencia tem bid/ask/last/volume/flags
    identicos (comum: mesmo lote redondo, mesmo preco) mas em timestamps
    DIFERENTES seriam apagados por engano. Inclui o timestamp na comparacao
    antes de deduplicar."""
    idx_name = df.index.name or "time"
    out = df.reset_index(names=idx_name)
    out = out[~out.duplicated(keep="last")].set_index(idx_name)
    return out.sort_index()


def merge_ticks(
    symbol: str, df_new: pd.DataFrame, data_dir: Path = TICK_DATA_DIR
) -> tuple[pd.DataFrame, int]:
    """Uniao idempotente entre o parquet existente e `df_new`, deduplicada por
    LINHA INTEIRA + timestamp (ver `_dedupe_full_row`). Devolve (df final,
    quantidade de linhas GENUINAMENTE novas)."""
    old = load_ticks(symbol, data_dir)
    if old.empty:
        merged = _dedupe_full_row(df_new)
        _write_parquet_atomic(merged, _parquet_path(symbol, data_dir))
        return merged, len(merged)

    combined = _dedupe_full_row(pd.concat([old, df_new]))
    n_novos = len(combined) - len(old)
    _write_parquet_atomic(combined, _parquet_path(symbol, data_dir))
    return combined, n_novos
