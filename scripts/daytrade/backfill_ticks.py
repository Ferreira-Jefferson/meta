"""Backfill UNICO de tick a tick (trade ticks) -- mesma logica de
`backfill_m1.py`, granularidade abaixo do M1 (ver
`market_data_intraday/mt5_ticks_source.py` para o porque de M1 ser o piso
das barras OHLC e tick ser o unico dado mais fino que o MT5 oferece).

A janela de tick que o terminal guarda e' BEM mais curta que a de M1 --
medido 2026-08-22: PMAM3 tem M1 desde 2023-04-11 mas tick so' desde
2024-11-01. Rodar isto cedo e sempre que quiser garantir que nada foi
perdido (a janela tambem rola para frente).

Uso:
    python scripts/daytrade/backfill_ticks.py --symbol PMAM3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from market_data_intraday.mt5_ticks_source import fetch_ticks_full_history  # noqa: E402
from market_data_intraday.tick_storage import merge_ticks  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    args = parser.parse_args()

    erros: list[tuple[str, Exception]] = []
    df = fetch_ticks_full_history(args.symbol, on_error=lambda k, e: erros.append((k, e)))
    if df.empty:
        print(f"[backfill_ticks] {args.symbol}: nenhum tick recebido do terminal. Erros: {erros}")
        return

    merged, n_novos = merge_ticks(args.symbol, df)
    print(f"[backfill_ticks] {args.symbol}: {len(df)} ticks baixados, {n_novos} genuinamente novos "
          f"vs. o que ja estava salvo. Parquet agora tem {len(merged)} ticks, "
          f"{merged.index.min()} -> {merged.index.max()}")
    if erros:
        print(f"[backfill_ticks] {len(erros)} erro(s) durante o backfill: {erros}")


if __name__ == "__main__":
    main()
