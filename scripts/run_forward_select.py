"""Seleção forward greedy: encontra as 10 melhores empresas para o universo.

Lê os CSVs gerados por run_sector_scan.py, ordena os candidatos por CAGR FULL,
e adiciona 1 ticker por vez escolhendo o que maximiza capital final do conjunto.

Uso: python scripts/run_forward_select.py [--top-candidates 25] [--target-n 10]
"""
from __future__ import annotations
import sys, time, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from backtest.engine import run_backtest
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.h3_hysteresis import DipTop1Hysteresis

INITIAL = 1000.0


def run_combo(tickers: list[str], start: str, end: str) -> dict:
    universe = load_universe(tickers=tickers, include_benchmark=True)
    config = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)
    result = run_backtest(universe, DipTop1Hysteresis(), config, start=start, end=end)
    m = result.metrics
    eq = result.equity_curve
    yearly = eq.resample("YE").agg(["first", "last"])
    yearly["ret"] = yearly["last"] / yearly["first"] - 1
    neg = int((yearly["ret"] < 0).sum())
    return {
        "final": float(m["final_capital"]),
        "cagr":  float(m["cagr"]),
        "sharpe": float(m.get("sharpe", 0)),
        "max_dd": float(m["max_drawdown"]),
        "neg_yrs": neg,
    }


def load_all_candidates() -> pd.DataFrame:
    frames = []
    for path in sorted(Path("data").glob("scan_group_*.csv")):
        df = pd.read_csv(path)
        frames.append(df)
    if not frames:
        raise RuntimeError("Nenhum CSV de scan encontrado em data/. Rode run_sector_scan.py primeiro.")
    return pd.concat(frames, ignore_index=True).drop_duplicates("ticker")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-candidates", type=int, default=25,
                        help="Quantos melhores candidatos do solo usar (default 25)")
    parser.add_argument("--target-n", type=int, default=10,
                        help="Tamanho final do universo (default 10)")
    args = parser.parse_args()

    all_df = load_all_candidates()
    print(f"\nTotal de candidatos com dados: {len(all_df)}")

    # Filtra por CAGR positivo no FULL e ordena
    valid = all_df[all_df["cagr"] > 0].copy()
    valid = valid.sort_values("cagr", ascending=False)
    candidates = valid["ticker"].tolist()[:args.top_candidates]

    print(f"Top-{args.top_candidates} por CAGR FULL usados na seleção:")
    for i, t in enumerate(candidates, 1):
        row = valid[valid["ticker"] == t].iloc[0]
        print(f"  {i:2d}. {t.replace('.SA',''):12s}  CAGR {row['cagr']*100:.2f}%  Sharpe {row.get('sharpe',0):.2f}")

    # Referência de datas
    ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
    today = ref.index[-1].strftime("%Y-%m-%d")
    three_y = (pd.Timestamp(today) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")

    print(f"\n{'='*65}")
    print(f"  FORWARD SELECTION — alvo {args.target_n} tickers")
    print(f"  FULL: 2010-01-01 -> {today}")
    print(f"{'='*65}\n")

    selected: list[str] = []
    remaining = list(candidates)

    for step in range(args.target_n):
        if not remaining:
            break

        best_ticker = None
        best_final = -1.0
        best_metrics = None

        for t in remaining:
            trial = selected + [t]
            try:
                r = run_combo(trial, "2010-01-01", today)
                if r["final"] > best_final:
                    best_final = r["final"]
                    best_ticker = t
                    best_metrics = r
            except Exception as e:
                print(f"    [ERR] {t}: {e}")

        if best_ticker is None:
            break

        selected.append(best_ticker)
        remaining.remove(best_ticker)
        r3 = None
        try:
            r3 = run_combo(selected, three_y, today)
        except Exception:
            pass

        print(f"  Passo {step+1:2d}: +{best_ticker.replace('.SA',''):10s}  "
              f"FULL R${best_metrics['final']:8.2f} CAGR {best_metrics['cagr']*100:.2f}% "
              f"Sharpe {best_metrics['sharpe']:.2f} MaxDD {best_metrics['max_dd']*100:.2f}% "
              f"NegYr {best_metrics['neg_yrs']}"
              + (f"  |  3Y R${r3['final']:7.2f} CAGR {r3['cagr']*100:.2f}%" if r3 else ""))
        print(f"         universo atual: {[t.replace('.SA','') for t in selected]}")

    print(f"\n{'='*65}")
    print(f"  RESULTADO FINAL — {len(selected)} tickers selecionados:")
    for i, t in enumerate(selected, 1):
        print(f"  {i:2d}. {t}")

    # Backtest final do universo completo
    print(f"\n  Backtest universo final:")
    rf = run_combo(selected, "2010-01-01", today)
    r3 = run_combo(selected, three_y, today)
    print(f"    FULL: R${rf['final']:.2f}  CAGR {rf['cagr']*100:.2f}%  Sharpe {rf['sharpe']:.2f}  MaxDD {rf['max_dd']*100:.2f}%  NegYrs {rf['neg_yrs']}")
    print(f"    3Y:   R${r3['final']:.2f}  CAGR {r3['cagr']*100:.2f}%  Sharpe {r3['sharpe']:.2f}  MaxDD {r3['max_dd']*100:.2f}%  NegYrs {r3['neg_yrs']}")
    print(f"\n  Referência atual TOP-3 (WEGE+RADL+VALE):")
    ref3 = run_combo(["WEGE3.SA", "RADL3.SA", "VALE3.SA"], "2010-01-01", today)
    ref3y = run_combo(["WEGE3.SA", "RADL3.SA", "VALE3.SA"], three_y, today)
    print(f"    FULL: R${ref3['final']:.2f}  CAGR {ref3['cagr']*100:.2f}%  Sharpe {ref3['sharpe']:.2f}  MaxDD {ref3['max_dd']*100:.2f}%  NegYrs {ref3['neg_yrs']}")
    print(f"    3Y:   R${ref3y['final']:.2f}  CAGR {ref3y['cagr']*100:.2f}%  Sharpe {ref3y['sharpe']:.2f}  MaxDD {ref3y['max_dd']*100:.2f}%  NegYrs {ref3y['neg_yrs']}")


if __name__ == "__main__":
    main()
