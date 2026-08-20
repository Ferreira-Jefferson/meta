"""Walk-forward de PARAMETROS — o tuning do robo sobrevive fora da amostra?

Complementa `run_walk_forward.py`, que so refazia a escolha da watchlist. Aqui o
grid de parametros do `portfolio_dip2_hw40` (dip, janela do high, histerese,
lookback do momentum) e re-otimizado DENTRO de cada corte e o vencedor e medido
as cegas no periodo seguinte.

Tres perguntas, tres saidas:

  A. TRILHA OFICIAL — watchlist oficial fixa, so os parametros re-otimizados.
     Isola o vies de PARAMETRO. E aqui que a pergunta "o dip de 2% atrapalha?"
     e respondida fora da amostra, em vez de no FULL contaminado.

  B. TRILHA CEGA — watchlist re-selecionada no IS (importada de
     `run_walk_forward.py`) mais parametros re-otimizados no mesmo IS. Vies
     total: nada nessa linha viu o futuro.

  C. DIAGNOSTICO DO TUNING — correlacao de Spearman entre o ranking IS e o
     ranking OOS do grid inteiro. Se for perto de zero, escolher parametro pelo
     in-sample e sorteio, e todo numero "otimizado" do repositorio e ruido.

Uso: python scripts/run_walk_forward_params.py
"""
from __future__ import annotations

import sys
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from backtest.metrics import negative_years
from backtest.runner import run as run_bt
from core.config import BENCHMARK, WATCHLIST, BacktestConfig
from market_data.loader import load_one
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

INITIAL = 1000.0
CONFIG = BacktestConfig(initial_capital=INITIAL, lot_size=1)
OOS_END = "2026-08-19"

# Watchlists cegas vindas de run_walk_forward.py (greedy no proprio IS de cada corte).
CUTS = [
    {
        "is_start": "2010-01-01", "is_end": "2015-12-31", "oos_start": "2016-01-01",
        "blind": ["EQTL3.SA", "BGIP4.SA", "TIMS3.SA", "BBAS3.SA", "BAZA3.SA", "BMEB4.SA", "BOVA11.SA"],
    },
    {
        "is_start": "2010-01-01", "is_end": "2017-12-31", "oos_start": "2018-01-01",
        "blind": ["RADL3.SA", "KEPL3.SA", "USIM5.SA", "SANB11.SA", "ROMI3.SA", "TAEE11.SA", "WEGE3.SA"],
    },
    {
        "is_start": "2010-01-01", "is_end": "2019-12-31", "oos_start": "2020-01-01",
        "blind": ["EQTL3.SA", "ENEV3.SA", "SANB11.SA", "ROMI3.SA", "TIMS3.SA", "UGPA3.SA", "BAZA3.SA"],
    },
]

GRID_DIP = [0.00, 0.01, 0.02, 0.05]
GRID_HW = [20, 40, 60]
GRID_HYST = [0.00, 0.15, 0.30]
GRID_LOOKBACK = [126, 252, 504]

OFFICIAL = {"dip": 0.02, "hw": 40, "hyst": 0.15, "lb": 252}

_PANELS: dict[str, pd.DataFrame] = {}


def panel(ticker: str) -> pd.DataFrame:
    """Painel sem as linhas de close vazio (download parcial do ultimo pregao)."""
    if ticker not in _PANELS:
        df = load_one(ticker)
        _PANELS[ticker] = df[df["close"].notna()]
    return _PANELS[ticker]


def spearman(a: pd.Series, b: pd.Series, perms: int = 10_000) -> tuple[float, float]:
    """Correlacao de postos + p-valor por permutacao.

    Sem scipy de proposito: AGENTS.md pede justificativa para dependencia nova, e
    aqui bastam postos (`Series.rank`) e um teste de permutacao com numpy.
    """
    ra, rb = a.rank().to_numpy(), b.rank().to_numpy()
    rho = float(np.corrcoef(ra, rb)[0, 1])
    rng = np.random.default_rng(0)
    null = np.array([np.corrcoef(ra, rng.permutation(rb))[0, 1] for _ in range(perms)])
    p = float((np.abs(null) >= abs(rho)).mean())
    return rho, p


def build(dip: float, hw: int, hyst: float, lb: int) -> DipTop1Portfolio:
    s = DipTop1Portfolio(dip_pct=dip, high_window=hw, lookback=lb)
    s._hysteresis = hyst
    return s


def measure(tickers: list[str], combo: dict, start: str, end: str) -> dict:
    universe = {t: panel(t) for t in tickers}
    universe[BENCHMARK] = panel(BENCHMARK)
    r = run_bt(universe, build(**combo), CONFIG, start=start, end=end)
    m = r.metrics
    return {
        "final": float(m["final_capital"]),
        "cagr": float(m["cagr"]),
        "max_dd": float(m["max_drawdown"]),
        "neg_yrs": negative_years(r.equity_curve),
        "trades": len(r.trades),
    }


def sweep(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    rows = []
    for dip, hw, hyst, lb in product(GRID_DIP, GRID_HW, GRID_HYST, GRID_LOOKBACK):
        combo = {"dip": dip, "hw": hw, "hyst": hyst, "lb": lb}
        try:
            m = measure(tickers, combo, start, end)
        except Exception:
            continue
        rows.append({**combo, **m})
    return pd.DataFrame(rows)


def run_track(label: str, tickers: list[str], cut: dict) -> dict:
    print(f"\n  {'-' * 92}")
    print(f"  {label}  |  {len(tickers)} tickers: {[t.replace('.SA', '') for t in tickers]}")
    print(f"  {'-' * 92}")

    is_df = sweep(tickers, cut["is_start"], cut["is_end"])
    oos_df = sweep(tickers, cut["oos_start"], OOS_END)
    key = ["dip", "hw", "hyst", "lb"]
    merged = is_df.merge(oos_df, on=key, suffixes=("_is", "_oos"))

    best = merged.loc[merged["final_is"].idxmax()]
    off = merged[(merged.dip == OFFICIAL["dip"]) & (merged.hw == OFFICIAL["hw"]) &
                 (merged.hyst == OFFICIAL["hyst"]) & (merged.lb == OFFICIAL["lb"])].iloc[0]
    nodip = merged[(merged.dip == 0.0) & (merged.hw == OFFICIAL["hw"]) &
                   (merged.hyst == OFFICIAL["hyst"]) & (merged.lb == OFFICIAL["lb"])].iloc[0]

    rho, pval = spearman(merged["final_is"], merged["final_oos"])
    oos_rank_of_is_best = int((merged["final_oos"] > best["final_oos"]).sum()) + 1

    def line(tag: str, row) -> str:
        return (f"    {tag:34s} dip {row['dip'] * 100:>4.0f}% hw {int(row['hw']):>2d} "
                f"hyst {row['hyst'] * 100:>3.0f}% lb {int(row['lb']):>3d} | "
                f"IS CAGR {row['cagr_is'] * 100:>6.2f}% | OOS R$ {row['final_oos']:>9,.0f} "
                f"CAGR {row['cagr_oos'] * 100:>6.2f}% MaxDD {row['max_dd_oos'] * 100:>6.1f}%")

    print(line("melhor combo no IS (cego)", best))
    print(line("combo OFICIAL do repo", off))
    print(line("oficial mas SEM dip (dip=0)", nodip))
    print(f"\n    grid OOS: p05 {np.percentile(merged['cagr_oos'], 5) * 100:.2f}% | "
          f"mediana {np.percentile(merged['cagr_oos'], 50) * 100:.2f}% | "
          f"p95 {np.percentile(merged['cagr_oos'], 95) * 100:.2f}%  ({len(merged)} combos)")
    print(f"    o combo escolhido pelo IS ficou em {oos_rank_of_is_best}o de {len(merged)} no OOS")
    print(f"    Spearman IS x OOS: rho {rho:+.3f} (p={pval:.3f})  "
          f"{'-> tuning IS nao informa o OOS' if pval > 0.05 else '-> alguma persistencia'}")

    dipg = merged.groupby("dip").agg(is_cagr=("cagr_is", "median"), oos_cagr=("cagr_oos", "median"),
                                     oos_dd=("max_dd_oos", "median")).reset_index()
    print(f"\n    efeito do DIP (mediana sobre {len(merged) // len(GRID_DIP)} combos por nivel):")
    print(f"      {'dip':>6s} {'IS CAGR':>9s} {'OOS CAGR':>9s} {'OOS MaxDD':>10s}")
    for _, r in dipg.iterrows():
        print(f"      {r['dip'] * 100:5.0f}% {r['is_cagr'] * 100:8.2f}% {r['oos_cagr'] * 100:8.2f}% "
              f"{r['oos_dd'] * 100:9.1f}%")

    return {"merged": merged, "best": best, "official": off, "nodip": nodip, "rho": rho, "p": pval}


def main() -> None:
    print("\nWALK-FORWARD DE PARAMETROS")
    print(f"grid: dip {GRID_DIP} x high_window {GRID_HW} x histerese {GRID_HYST} x lookback {GRID_LOOKBACK}")
    print(f"= {len(GRID_DIP) * len(GRID_HW) * len(GRID_HYST) * len(GRID_LOOKBACK)} combos por corte, "
          f"medidos no IS e no OOS\n")

    summary = []
    for cut in CUTS:
        print("=" * 100)
        print(f"CORTE {cut['is_end']}  |  IS {cut['is_start']} -> {cut['is_end']}  |  "
              f"OOS {cut['oos_start']} -> {OOS_END}")
        print("=" * 100)
        a = run_track("TRILHA A — watchlist OFICIAL (isola vies de parametro)", list(WATCHLIST), cut)
        b = run_track("TRILHA B — watchlist CEGA (vies total)", cut["blind"], cut)
        summary.append({"cut": cut["is_end"], "A": a, "B": b})

    print("\n" + "=" * 100)
    print("RESUMO — CAGR OOS")
    print("=" * 100)
    print(f"{'corte':>10s} | {'A oficial+tuned':>16s} {'A oficial+repo':>15s} {'A sem dip':>10s} | "
          f"{'B cega+tuned':>13s} {'B cega+repo':>12s} {'B cega sem dip':>15s}")
    for s in summary:
        a, b = s["A"], s["B"]
        print(f"{s['cut']:>10s} | {a['best']['cagr_oos'] * 100:>15.2f}% {a['official']['cagr_oos'] * 100:>14.2f}% "
              f"{a['nodip']['cagr_oos'] * 100:>9.2f}% | {b['best']['cagr_oos'] * 100:>12.2f}% "
              f"{b['official']['cagr_oos'] * 100:>11.2f}% {b['nodip']['cagr_oos'] * 100:>14.2f}%")

    rhos = [s[t]["rho"] for s in summary for t in ("A", "B")]
    print(f"\nSpearman IS x OOS nos 6 grids: {[f'{r:+.2f}' for r in rhos]}  media {np.mean(rhos):+.3f}")
    print("Se essa media for perto de zero, escolher parametro pelo in-sample nao carrega informacao")
    print("para o periodo seguinte — inclusive a escolha do dip de 2%.")


if __name__ == "__main__":
    main()
