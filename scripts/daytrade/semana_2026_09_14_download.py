"""Baixa do terminal MT5 os dados da semana de referencia 2026-09-14..18 que
faltam na base local, para as 6 medicoes de `semana_referencia_2026_09_14.py`.

NAO sobrescreve nenhum parquet canonico -- grava em arquivos SEPARADOS,
seguindo o padrao ja usado por `wdo_tick_update_semana_2026_09_14.py` /
`scripts/daytrade/evo/dados.py` (TICK_SEMANA_NOVA): os scripts de analise
concatenam canonico + semana na leitura.

Baixa:
  - tick WDOV26 14..18/09  -> data/raw_ticks/WDO_A_semana_2026_09_14.parquet
  - tick WINV26 14..18/09  -> data/raw_ticks/WIN_A_semana_2026_09_14.parquet
  - M1   WDOV26 16..18/09  -> data/raw_intraday/WDO_A_semana_2026_09_14_M1.parquet
  - M1   WINV26 16..18/09  -> data/raw_intraday/WIN_A_semana_2026_09_14_M1.parquet
  - M1   PMAM3  14..18/09  -> data/raw_intraday/PMAM3_semana_2026_09_14_M1.parquet

Fuso: mesma receita de `live/tick_feed.py::_limite_servidor` -- o pacote
`MetaTrader5` chama `.timestamp()` no limite recebido, entao o limite tem de
chegar com o relogio de PAREDE do servidor rotulado como UTC.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

from core.b3_session import utc_to_server_wall_clock  # noqa: E402
from market_data_intraday.mt5_ticks_source import fetch_ticks_range  # noqa: E402
from market_data_intraday.mt5_source import fetch_m1_range  # noqa: E402

DIAS = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]


def _limite_servidor(instant_utc: datetime) -> datetime:
    return utc_to_server_wall_clock(instant_utc).replace(tzinfo=timezone.utc)


def _baixar_tick(simbolo_real: str, dias: list[str], destino: Path) -> None:
    erros: list[str] = []

    def on_error(chave: str, exc: Exception) -> None:
        erros.append(f"{chave}: {exc}")

    pedacos = []
    for dia in dias:
        inicio = pd.Timestamp(f"{dia} 10:00", tz="UTC").to_pydatetime()
        fim = pd.Timestamp(f"{dia} 22:30", tz="UTC").to_pydatetime()
        df = fetch_ticks_range(simbolo_real, _limite_servidor(inicio), _limite_servidor(fim),
                                on_error=on_error)
        if df.empty:
            print(f"[tick {simbolo_real}] {dia}: VAZIO {erros[-1] if erros else ''}", flush=True)
            continue
        print(f"[tick {simbolo_real}] {dia}: {len(df):,} ticks  "
              f"{df.index.min()} -> {df.index.max()}", flush=True)
        pedacos.append(df)

    if not pedacos:
        print(f"[tick {simbolo_real}] nada baixado. erros={erros}")
        return

    todo = pd.concat(pedacos).sort_index(kind="mergesort")
    destino.parent.mkdir(parents=True, exist_ok=True)
    todo.to_parquet(destino)
    print(f"[tick {simbolo_real}] {len(todo):,} ticks gravados em {destino}\n")


def _baixar_m1(simbolo_real: str, dias: list[str], destino: Path) -> None:
    erros: list[str] = []

    def on_error(chave: str, exc: Exception) -> None:
        erros.append(f"{chave}: {exc}")

    pedacos = []
    for dia in dias:
        inicio = pd.Timestamp(f"{dia} 09:00", tz="UTC").to_pydatetime()
        fim = pd.Timestamp(f"{dia} 23:00", tz="UTC").to_pydatetime()
        df = fetch_m1_range(simbolo_real, _limite_servidor(inicio), _limite_servidor(fim),
                             on_error=on_error)
        if df.empty:
            print(f"[m1 {simbolo_real}] {dia}: VAZIO {erros[-1] if erros else ''}", flush=True)
            continue
        print(f"[m1 {simbolo_real}] {dia}: {len(df):,} barras  "
              f"{df.index.min()} -> {df.index.max()}", flush=True)
        pedacos.append(df)

    if not pedacos:
        print(f"[m1 {simbolo_real}] nada baixado. erros={erros}")
        return

    todo = pd.concat(pedacos).sort_index(kind="mergesort")
    destino.parent.mkdir(parents=True, exist_ok=True)
    todo.to_parquet(destino)
    print(f"[m1 {simbolo_real}] {len(todo):,} barras gravadas em {destino}\n")


def main() -> None:
    _baixar_tick("WDOV26", DIAS, RAIZ / "data" / "raw_ticks" / "WDO_A_semana_2026_09_14.parquet")
    _baixar_tick("WINV26", DIAS, RAIZ / "data" / "raw_ticks" / "WIN_A_semana_2026_09_14.parquet")
    _baixar_m1("WDOV26", ["2026-09-16", "2026-09-17", "2026-09-18"],
               RAIZ / "data" / "raw_intraday" / "WDO_A_semana_2026_09_14_M1.parquet")
    _baixar_m1("WINV26", ["2026-09-16", "2026-09-17", "2026-09-18"],
               RAIZ / "data" / "raw_intraday" / "WIN_A_semana_2026_09_14_M1.parquet")
    _baixar_m1("PMAM3", DIAS, RAIZ / "data" / "raw_intraday" / "PMAM3_semana_2026_09_14_M1.parquet")


if __name__ == "__main__":
    main()
