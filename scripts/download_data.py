"""Baixa OHLCV de todos os tickers da watchlist + IBOV."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_data.download import download_all
from market_data.loader import load_one
from market_data.quality import check


def main() -> None:
    written = download_all()
    print(f"{len(written)} arquivos baixados.")
    for ticker, path in written.items():
        if ticker.startswith("macro:"):
            continue
        report = check(ticker, load_one(ticker))
        status = "OK" if report.ok() else "REVER"
        print(
            f"[{status}] {ticker:>10} rows={report.rows:>5} "
            f"start={report.start.date()} end={report.end.date()} "
            f"nan={report.nan_count} gap_max={report.max_gap_days}d dup={report.duplicated_index}"
        )


if __name__ == "__main__":
    main()
