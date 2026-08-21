"""Coletor INCREMENTAL: busca so as barras M1 novas desde o ultimo timestamp
salvo e as acrescenta ao parquet local. Pensado para rodar 1x/dia (ou via
`scripts/daytrade/backfill_m1.py` se nunca rodou antes) — a janela do
servidor MT5 rola para frente, entao acumular localmente e a unica forma
de nao perder o dado de hoje mais adiante.

Uso:
    python scripts/daytrade/collect_m1_daily.py [--symbol WIN@]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from market_data_intraday.mt5_source import fetch_m1_full_history, fetch_m1_range  # noqa: E402
from market_data_intraday.storage import load_m1, merge_m1  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="WIN@")
    args = parser.parse_args()

    erros: list[tuple[str, Exception]] = []
    existing = load_m1(args.symbol)
    if existing.empty:
        print(f"[collect] {args.symbol}: nenhum parquet local ainda — rode "
              f"scripts/daytrade/backfill_m1.py primeiro. Fazendo backfill completo agora.")
        df = fetch_m1_full_history(args.symbol, on_error=lambda k, e: erros.append((k, e)))
    else:
        last_ts = existing.index.max()
        now = datetime.now(timezone.utc)
        # folga de 1 dia: reconfirma o ultimo pregao salvo em vez de assumir
        # que ele fechou definitivo (mesmo espirito de `INCREMENTAL_LOOKBACK_DAYS`
        # em `market_data.download`).
        start = (last_ts - timedelta(days=1)).to_pydatetime()
        df = fetch_m1_range(args.symbol, start, now, on_error=lambda k, e: erros.append((k, e)))

    if df.empty:
        print(f"[collect] {args.symbol}: nenhuma barra nova recebida do terminal. Erros: {erros}")
        return

    merged, n_novos = merge_m1(args.symbol, df)
    print(f"[collect] {args.symbol}: {n_novos} barra(s) genuinamente nova(s). "
          f"Parquet agora tem {len(merged)} barras, {merged.index.min()} -> {merged.index.max()}")
    if erros:
        print(f"[collect] {len(erros)} erro(s) durante a coleta: {erros}")


if __name__ == "__main__":
    main()
