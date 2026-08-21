"""Backfill UNICO: puxa toda a profundidade de M1 que o servidor MT5 ainda
tem para o simbolo pedido, agora — a janela do broker ROLA PARA FRENTE
(achado #3 do plano de escopo de day trade, 2026-08-20), entao dado de hoje
que nao for salvo agora se perde depois. Rodar isto uma vez ao comecar a
trabalhar em day trade, e sempre que quiser garantir que nada foi perdido.

Uso:
    python scripts/daytrade/backfill_m1.py [--symbol WIN@]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from market_data_intraday.mt5_source import fetch_m1_full_history  # noqa: E402
from market_data_intraday.storage import merge_m1  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="WIN@")
    args = parser.parse_args()

    erros: list[tuple[str, Exception]] = []
    df = fetch_m1_full_history(args.symbol, on_error=lambda k, e: erros.append((k, e)))
    if df.empty:
        print(f"[backfill] {args.symbol}: nenhuma barra recebida do terminal. Erros: {erros}")
        return

    merged, n_novos = merge_m1(args.symbol, df)
    print(f"[backfill] {args.symbol}: {len(df)} barras baixadas, {n_novos} genuinamente novas "
          f"vs. o que ja estava salvo. Parquet agora tem {len(merged)} barras, "
          f"{merged.index.min()} -> {merged.index.max()}")
    if erros:
        print(f"[backfill] {len(erros)} erro(s) durante o backfill: {erros}")


if __name__ == "__main__":
    main()
