"""Checagem EMPIRICA da familia de series continuas de WIN exposta pelo
terminal MT5.

RESULTADO JA VERIFICADO uma vez contra o terminal da Clear (2026-08-20,
100446 barras M1, 2025-12-01 -> 2026-08-20, atravessando pelo menos 4
rolagens de contrato WIN no periodo): `WIN$` e `WIN@` sao BYTE-IDENTICOS
em toda a profundidade disponivel — nenhuma das duas familias aplica
ajuste sintetico neste terminal/corretora. A hipotese original ("$" =
ajustado, "@" = concatenacao bruta) estava ERRADA; nao ha diferenca
alguma a escolher entre elas aqui. Isto pode nao valer para outra
corretora/feed — por isso o script continua existindo, para reverificar
se o terminal ou o provedor de dado mudar.

A comparacao usa a profundidade TOTAL (nao so as ultimas N barras): checar
so um trecho recente e inconclusivo por construcao, porque so revela
diferenca de ajuste se o trecho atravessar uma rolagem — e um trecho de
poucos dias normalmente nao atravessa nenhuma.

Uso:
    python scripts/daytrade/verify_continuous_symbol.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from market_data_intraday.mt5_source import fetch_m1_full_history  # noqa: E402

CONTINUOUS_CANDIDATES = ["WIN$", "WIN$D", "WIN$N", "WIN@", "WIN@D", "WIN@N"]


def main() -> None:
    erros: list[tuple[str, Exception]] = []
    reference_symbol = CONTINUOUS_CANDIDATES[0]
    reference_df = fetch_m1_full_history(reference_symbol, on_error=lambda k, e: erros.append((k, e)))
    if reference_df.empty:
        print(f"[verify] sem dado para {reference_symbol!r} — nada para comparar contra. Erros: {erros}")
        return
    print(f"[verify] {reference_symbol}: {len(reference_df)} barras, "
          f"{reference_df.index.min()} -> {reference_df.index.max()} (referencia)")

    for symbol in CONTINUOUS_CANDIDATES[1:]:
        df = fetch_m1_full_history(symbol, on_error=lambda k, e: erros.append((k, e)))
        if df.empty:
            print(f"[verify] {symbol}: sem dado")
            continue
        common_ts = reference_df.index.intersection(df.index)
        if len(common_ts) == 0:
            print(f"[verify] {symbol}: nenhum timestamp em comum com {reference_symbol}")
            continue
        diff = (df.loc[common_ts, "close"] - reference_df.loc[common_ts, "close"]).abs()
        print(f"[verify] {symbol} vs {reference_symbol}: {len(common_ts)} barras em comum, "
              f"diff absoluta max={diff.max():.4f} media={diff.mean():.4f} "
              f"({'IDENTICO' if diff.max() < 0.5 else 'DIFERE (ha ajuste sintetico em algum lado)'})")

    if erros:
        print(f"[verify] {len(erros)} erro(s) durante a checagem: {erros}")


if __name__ == "__main__":
    main()
