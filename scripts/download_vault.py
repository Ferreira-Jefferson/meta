"""Baixa o COFRE 1998-2009 da B3 para `data/vault_1998_2009/`.

REGRA DE OURO: este diretorio e um holdout VIRGEM. Nenhuma busca de hipotese,
nenhum agente de exploracao e nenhum tuning pode ler daqui. Ele e aberto UMA
VEZ, no fim, contra candidatos declarados nominalmente antes.

Por que 1998 e nao 2000: o ranking de liquidez exige 504 pregoes de historico
antes de montar universo. Comecando o download em 1998 o universo fica
disponivel desde ~2000-2002, sem o handicap de "dois anos sem universo" que o
holdout de 2010-2013 teve de declarar.

Reaproveita a mesma maquinaria de qualidade de `market_data` (calendario de
consenso + fill_gaps + drop de rabo incompleto) para que o cofre nao tenha os
defeitos de dado listados na secao 7 do protocolo.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from core.config import BENCHMARK
from market_data.download import (
    download_macro,
    download_one,
    save_parquet,
)
from market_data.quality import consensus_calendar, fill_gaps
from strategy.liquid_sleeve import POOL

VAULT_DIR = Path(__file__).resolve().parents[1] / "data" / "vault_1998_2009"
START = "1998-01-01"
END = "2009-12-31"


def main() -> None:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    universe = list(POOL)
    if BENCHMARK not in universe:
        universe.append(BENCHMARK)

    frames: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for t in universe:
        try:
            df = download_one(t, start=START)
        except Exception as e:
            missing.append(t)
            print(f"[skip] {t}: {e}")
            continue
        df = df.loc[:END]
        if df.empty or len(df) < 60:
            missing.append(t)
            print(f"[skip] {t}: {len(df)} pregoes ate {END}")
            continue
        frames[t] = df

    calendar = consensus_calendar(frames)
    for t, df in frames.items():
        if calendar is not None:
            df, filled = fill_gaps(df, calendar)
            if filled:
                print(f"[gap] {t}: {len(filled)} sessao(oes) preenchida(s)")
        save_parquet(t, df, out_dir=VAULT_DIR)

    download_macro(start=START, out_dir=VAULT_DIR)

    print(f"\n=== COFRE {START}..{END} ===")
    print(f"tickers com dado: {len(frames)}  |  sem dado: {len(missing)}")
    prim = pd.DataFrame(
        [(t, d.index.min().date(), d.index.max().date(), len(d)) for t, d in frames.items()],
        columns=["ticker", "start", "end", "rows"],
    ).sort_values("start")
    print(prim.to_string(index=False))
    # Quantos papeis existem em cada ano-inicio -> largura disponivel p/ top-20
    for yr in range(1999, 2006):
        cut = pd.Timestamp(f"{yr}-01-01")
        n = sum(1 for d in frames.values() if d.index.min() <= cut - pd.Timedelta(days=730))
        print(f"  com 504+ pregoes antes de {yr}-01: {n} papeis")
    print(f"\nsem dado: {sorted(missing)}")


if __name__ == "__main__":
    main()
