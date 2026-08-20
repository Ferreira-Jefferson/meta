"""Smoke test da INFRA do cofre. NAO mede desempenho — de proposito.

O cofre (`data/vault_1998_2009/`) abre uma vez so, no fim, por
`scripts/run_vault_verdict.py`. Este script existe para responder uma pergunta
puramente estrutural ANTES de a busca comecar: o harness consegue montar
universo naquele dado, ou a busca inteira seria desperdicada?

Por isso ele imprime contagem de papeis elegiveis e presenca de colunas, e
NUNCA CAGR, MaxDD ou capital. Ver as janelas e o desempenho aqui queimaria o
cofre pela porta dos fundos.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from market_data.loader import load_one
from strategy.liquid_sleeve import POOL

VAULT = Path(__file__).resolve().parents[1] / "data" / "vault_1998_2009"


def main() -> None:
    disponiveis, faltando = {}, []
    for t in POOL:
        try:
            disponiveis[t] = load_one(t, out_dir=VAULT)
        except FileNotFoundError:
            faltando.append(t)

    print(f"papeis no cofre: {len(disponiveis)} / {len(POOL)}  (faltando {len(faltando)})")
    ibov = load_one("^BVSP", out_dir=VAULT)
    print(f"IBOV: {ibov.index.min().date()} .. {ibov.index.max().date()}  ({len(ibov)} pregoes)")
    selic = pd.read_parquet(VAULT / "selic.parquet")
    print(f"Selic: {selic.index.min().date()} .. {selic.index.max().date()}  ({len(selic)} pontos)")

    # Elegibilidade estrutural: quantos papeis tem 504 pregoes + volume valido
    # no primeiro pregao de cada inicio de janela declarado no protocolo.
    print("\nelegiveis (504+ pregoes, volume nao-nulo) por inicio de janela:")
    for start in [pd.Timestamp(f"{y}-{m:02d}-01") for y in (2003, 2004) for m in (1, 7)]:
        n = 0
        for t, df in disponiveis.items():
            hist = df.loc[:start]
            if len(hist) >= 504 and "volume" in df.columns and hist["volume"].tail(252).median() > 0:
                n += 1
        marca = "OK" if n >= 20 else "INSUFICIENTE p/ top-20"
        print(f"  {start.date()}  ->  {n:3d} papeis   [{marca}]")

    cols = {c for df in disponiveis.values() for c in df.columns}
    print(f"\ncolunas presentes: {sorted(cols)}")
    nan_close = {t: int(df['close'].isna().sum()) for t, df in disponiveis.items() if df['close'].isna().any()}
    print(f"papeis com close NaN: {len(nan_close)}  {dict(list(nan_close.items())[:5])}")
    print(f"\nsem dado no cofre: {sorted(faltando)}")


if __name__ == "__main__":
    main()
