"""Rodada 1 da frente "padroes de candlestick" (pedido do dono, 2026-08-26):
varre o catalogo de `strategy.daytrade.lab.candle_patterns.PATTERNS` (21
padroes) x WIN@/WDO@ (SEPARADOS) x 3 horizontes (~1h/~4h/~1 pregao em M15),
mede retorno condicional + assimetria MFE/MAE, e reporta TODOS os
resultados -- teste multiplo por construcao, nenhum recorte silencioso.

So' `.in_sample()` (split congelado `backtest.intraday.profiles.OOS_CUTOFF`).
Uso: `python scripts/daytrade/candle_measure.py`.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # candle_lab.py mora ao lado deste script

from candle_lab import (  # noqa: E402
    HORIZONS,
    SYMBOLS,
    PatternCellResult,
    evaluate_pattern,
    in_sample_bars,
)
from strategy.daytrade.lab.candle_patterns import PATTERNS  # noqa: E402

TIMEFRAME = "M15"


def _fmt_pct(x: float) -> str:
    return "—" if x != x else f"{x:+.3f}%"


def _fmt_p(x: float) -> str:
    return "—" if x != x else f"{x:.4f}"


def _fmt_brl(x: float) -> str:
    return "—" if x != x else f"{x:+.2f}"


_HEADER = (
    f"{'padrao':<24}{'dir':<9}{'simb':<6}{'h':>4}{'n':>7}{'taxa%':>8}"
    f"{'ret%':>10}{'p_ret':>8}{'fav%':>8}{'adv%':>8}{'asym%':>9}{'p_asym':>8}"
    f"{'ret R$':>10}{'custo R$':>10}{'liq R$':>10}"
)


def _row(r: PatternCellResult) -> str:
    return (
        f"{r.pattern:<24}{r.direction:<9}{r.symbol:<6}{r.horizon_bars:>4}{r.n_occurrences:>7}"
        f"{r.occurrence_rate_pct:>7.2f}%"
        f"{_fmt_pct(r.mean_ret_pct):>10}{_fmt_p(r.ret_p_value):>8}"
        f"{_fmt_pct(r.mean_favorable_pct):>8}{_fmt_pct(r.mean_adverse_pct):>8}"
        f"{_fmt_pct(r.asymmetry_pct):>9}{_fmt_p(r.asymmetry_p_value):>8}"
        f"{_fmt_brl(r.mean_ret_brl_per_contract):>10}{r.round_trip_cost_brl:>10.2f}"
        f"{_fmt_brl(r.net_brl_per_contract):>10}"
    )


def run(n_perm: int = 300, seed: int = 0) -> list[PatternCellResult]:
    results: list[PatternCellResult] = []
    bars_cache: dict[str, "pd.DataFrame"] = {}
    for symbol in SYMBOLS:
        bars_cache[symbol] = in_sample_bars(symbol, TIMEFRAME)
        df = bars_cache[symbol]
        pregoes = len(set(df.index.date))
        print(f"[candle_measure] {symbol} {TIMEFRAME} in-sample: {len(df)} barras, "
              f"{pregoes} pregoes, {df.index.min()} .. {df.index.max()}", flush=True)

    print()
    print(_HEADER)
    print("-" * len(_HEADER))

    t0 = time.time()
    for pattern_name, spec in PATTERNS.items():
        occ_cache: dict[str, "pd.Series"] = {}
        for symbol in SYMBOLS:
            df = bars_cache[symbol]
            for horizon in HORIZONS:
                r = evaluate_pattern(
                    df, symbol, TIMEFRAME, pattern_name, spec.detector, spec.direction,
                    horizon, n_perm=n_perm, seed=seed,
                )
                results.append(r)
                print(_row(r), flush=True)
    print(f"\n[candle_measure] {len(results)} celulas em {time.time()-t0:.1f}s", flush=True)
    return results


def summarize(results: list[PatternCellResult]) -> None:
    print("\n=== resumo do lote (teste multiplo) ===")
    total = len(results)
    for label, pred in [
        ("p_ret < 0.05", lambda r: r.ret_p_value == r.ret_p_value and r.ret_p_value < 0.05),
        ("p_ret < 0.01", lambda r: r.ret_p_value == r.ret_p_value and r.ret_p_value < 0.01),
        ("p_asym < 0.05", lambda r: r.asymmetry_p_value == r.asymmetry_p_value and r.asymmetry_p_value < 0.05),
        ("p_asym < 0.01", lambda r: r.asymmetry_p_value == r.asymmetry_p_value and r.asymmetry_p_value < 0.01),
        ("liquido R$ > 0 E p_ret<0.05", lambda r: r.net_brl_per_contract == r.net_brl_per_contract
         and r.net_brl_per_contract > 0 and r.ret_p_value == r.ret_p_value and r.ret_p_value < 0.05),
    ]:
        n = sum(1 for r in results if pred(r))
        print(f"  {label}: {n}/{total} ({100.0*n/total:.1f}%)")

    print("\n=== top 15 por p_ret (mais extremo primeiro) ===")
    ordered = sorted([r for r in results if r.ret_p_value == r.ret_p_value], key=lambda r: r.ret_p_value)
    print(_HEADER)
    for r in ordered[:15]:
        print(_row(r))


if __name__ == "__main__":
    all_results = run()
    summarize(all_results)
