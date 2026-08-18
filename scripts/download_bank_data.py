"""Baixa OHLCV dos bancos listados na B3 para o laboratorio de robo bancario.

Uso: python scripts/download_bank_data.py

Nao mexe na WATCHLIST oficial nem nos parquets dos robos em producao — so
adiciona os tickers bancarios abaixo em data/raw/, seguindo a mesma
mecanica de merge_preserving_history + consensus_calendar + fill_gaps do
download_all() (protege contra o gap-flapping do yfinance documentado em
market_data/download.py).
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market_data.download import (
    download_one, save_parquet, merge_preserving_history, incremental_start,
)
from market_data.quality import check, consensus_calendar, fill_gaps
from core.config import DATA_DIR, HISTORY_START

# Universo candidato de bancos B3 — grandes + regionais. Tickers sem historico
# minimo (252 pregoes) ou que falharem no download sao pulados e reportados;
# nao interrompe o lote.
BANK_TICKERS = [
    "ITUB4.SA", "BBDC4.SA", "BBAS3.SA", "SANB11.SA", "BPAC11.SA",
    "BRSR6.SA", "ABCB4.SA", "BPAN4.SA", "BMGB4.SA", "PINE4.SA",
    "BEES3.SA", "BGIP4.SA", "BMEB4.SA", "BAZA3.SA",
]


def main():
    print(f"\n{'='*60}\n  DOWNLOAD — universo bancario ({len(BANK_TICKERS)} tickers)\n{'='*60}")
    frames = {}
    for t in BANK_TICKERS:
        t_start = incremental_start(t, HISTORY_START, DATA_DIR)
        try:
            df = download_one(t, start=t_start)
        except Exception as e:
            print(f"  [FAIL] {t}: {e}")
            continue
        df, rescued = merge_preserving_history(t, df, DATA_DIR)
        if len(df) < 252:
            print(f"  [SKIP] {t}: apenas {len(df)} pregoes de historico")
            continue
        frames[t] = df
        print(f"  [OK]   {t}: {len(df)} pregoes ({df.index.min().date()} -> {df.index.max().date()})")

    if not frames:
        print("\n  Nenhum ticker baixado com sucesso.")
        return

    calendar = consensus_calendar(frames)
    for t, df in frames.items():
        if calendar is not None:
            df, filled = fill_gaps(df, calendar)
            if filled:
                print(f"  [GAP]  {t}: {len(filled)} sessao(oes) preenchida(s) vs consenso")
        report = check(t, df, calendar)
        if not report.ok():
            print(f"  [QUAL] {t}: nan={report.nan_count} gap_max={report.max_gap_days}d "
                  f"dup={report.duplicated_index} missing={len(report.missing_sessions)}")
        save_parquet(t, df)

    print(f"\n  {len(frames)}/{len(BANK_TICKERS)} tickers bancarios disponiveis em data/raw/")


if __name__ == "__main__":
    main()
