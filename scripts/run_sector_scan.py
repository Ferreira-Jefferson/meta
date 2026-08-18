"""Sector scan: download + backtest solo para grupo de tickers.

Uso: python scripts/run_sector_scan.py --group A
     python scripts/run_sector_scan.py --tickers VALE3.SA,WEGE3.SA
"""
from __future__ import annotations
import sys, argparse, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from backtest.engine import run_backtest
from core.config import BacktestConfig, DATA_DIR
from market_data.download import download_one, save_parquet
from market_data.loader import load_universe
from strategy.h3_hysteresis import DipTop1Hysteresis

INITIAL = 1000.0

# ---------------------------------------------------------------------------
# Grupos por setor
# ---------------------------------------------------------------------------
GROUPS: dict[str, list[str]] = {
    # Mineração / Siderurgia (like VALE) + Industrial/Manufatura (like WEGE)
    "A": [
        "VALE3.SA", "CMIN3.SA", "CSNA3.SA", "USIM5.SA",
        "GGBR4.SA", "GOAU4.SA", "BRAP4.SA", "FESA4.SA",
        "WEGE3.SA", "ROMI3.SA", "TUPY3.SA", "RAPT4.SA",
        "FRAS3.SA", "MYPK3.SA", "KEPL3.SA", "POMO4.SA",
        "LEVE3.SA", "EUCA4.SA",
    ],
    # Farmácia (like RADL) + Saúde + Saneamento
    "B": [
        "RADL3.SA", "PNVL3.SA", "BLAU3.SA",
        "HAPV3.SA", "RDOR3.SA", "FLRY3.SA", "DASA3.SA",
        "QUALS3.SA", "PARD3.SA", "AALR3.SA", "MATD3.SA",
        "SBSP3.SA", "SAPR11.SA", "CSMG3.SA",
    ],
    # Energia — primeira metade
    "C": [
        "EGIE3.SA", "CPFE3.SA", "ENGI11.SA", "TAEE11.SA",
        "CMIG4.SA", "CPLE6.SA", "TRPL4.SA", "EQTL3.SA",
        "CESP6.SA", "ELET3.SA", "ELET6.SA", "NEOE3.SA",
    ],
    # Energia — segunda metade + Telefonia + Seguros
    "D": [
        "ALUP11.SA", "ENEV3.SA", "EMAE4.SA", "ENBR3.SA",
        "CGAS3.SA", "UGPA3.SA", "AESB3.SA",
        "VIVT3.SA", "TIMS3.SA",
        "BBSE3.SA", "IRBR3.SA", "PSSA3.SA", "CXSE3.SA",
    ],
}


def _parquet_path(ticker: str) -> Path:
    safe = ticker.replace("^", "_").replace(".", "_")
    return DATA_DIR / f"{safe}.parquet"


def ensure_downloaded(ticker: str) -> bool:
    """Baixa se o parquet ainda não existir. Retorna False se falhar."""
    path = _parquet_path(ticker)
    if path.exists():
        return True
    try:
        df = download_one(ticker)
        if len(df) < 252:
            print(f"  [SKIP] {ticker}: apenas {len(df)} dias de histórico")
            return False
        save_parquet(ticker, df)
        return True
    except Exception as e:
        print(f"  [FAIL] {ticker}: {e}")
        return False


def run_solo(ticker: str, start: str, end: str) -> dict | None:
    try:
        universe = load_universe(tickers=[ticker], include_benchmark=True)
        config = BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.15)
        result = run_backtest(universe, DipTop1Hysteresis(), config, start=start, end=end)
        m = result.metrics
        eq = result.equity_curve
        yearly = eq.resample("YE").agg(["first", "last"])
        yearly["ret"] = yearly["last"] / yearly["first"] - 1
        neg = int((yearly["ret"] < 0).sum())
        return {
            "ticker": ticker,
            "final": float(m["final_capital"]),
            "cagr":  float(m["cagr"]),
            "sharpe": float(m.get("sharpe", 0)),
            "max_dd": float(m["max_drawdown"]),
            "neg_yrs": neg,
            "trades": int(m.get("trades_count", 0)),
        }
    except Exception as e:
        print(f"  [ERR] {ticker}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=list(GROUPS.keys()), help="Grupo de tickers")
    parser.add_argument("--tickers", help="Lista separada por vírgula")
    args = parser.parse_args()

    if args.group:
        tickers = GROUPS[args.group]
        label = f"Grupo {args.group}"
    elif args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
        label = "Custom"
    else:
        parser.error("Informe --group ou --tickers")

    # Referência de data
    ref = pd.read_parquet("data/raw/WEGE3_SA.parquet")["close"].dropna()
    today = ref.index[-1].strftime("%Y-%m-%d")
    three_y = (pd.Timestamp(today) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"  SECTOR SCAN — {label} ({len(tickers)} tickers)")
    print(f"  FULL: 2010-01-01 -> {today}  |  3Y: {three_y} -> {today}")
    print(f"{'='*60}")

    # Download
    print("\n[1/2] Download de dados...")
    available = []
    for t in tickers:
        ok = ensure_downloaded(t)
        if ok:
            available.append(t)
    print(f"  {len(available)}/{len(tickers)} tickers disponíveis\n")

    # Backtests
    print("[2/2] Backtests FULL + 3Y...\n")
    hdr = f"  {'Ticker':12s}  {'FinalFULL':>10}  {'CAGRFULL':>8}  {'SharpeFULL':>10}  {'MaxDD':>7}  {'NegYr':>6}  {'Final3Y':>9}  {'CAGR3Y':>7}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    rows_full = []
    rows_3y = []
    for t in available:
        t0 = time.perf_counter()
        rf = run_solo(t, "2010-01-01", today)
        r3 = run_solo(t, three_y, today)
        dt = time.perf_counter() - t0
        if rf is None:
            continue
        rows_full.append(rf)
        if r3 is not None:
            rows_3y.append(r3)
        f3_final = f"R${r3['final']:7.2f}" if r3 else "  N/A   "
        f3_cagr  = f"{r3['cagr']*100:6.2f}%" if r3 else "   N/A "
        print(f"  {t.replace('.SA',''):12s}  R${rf['final']:8.2f}  {rf['cagr']*100:7.2f}%  {rf['sharpe']:10.2f}  {rf['max_dd']*100:6.2f}%  {rf['neg_yrs']:>6}  {f3_final}  {f3_cagr}  ({dt:.1f}s)")

    # Ranking FULL por capital final
    print(f"\n{'='*60}")
    print("  RANKING por capital final FULL:")
    rows_full.sort(key=lambda x: x["final"], reverse=True)
    for i, r in enumerate(rows_full, 1):
        print(f"  {i:2d}. {r['ticker'].replace('.SA',''):12s}  R${r['final']:8.2f}  CAGR {r['cagr']*100:.2f}%  Sharpe {r['sharpe']:.2f}  NegYrs {r['neg_yrs']}")

    print(f"\n{'='*60}")
    print("  RANKING por CAGR FULL (top-10):")
    by_cagr = sorted(rows_full, key=lambda x: x["cagr"], reverse=True)
    for i, r in enumerate(by_cagr[:10], 1):
        print(f"  {i:2d}. {r['ticker'].replace('.SA',''):12s}  CAGR {r['cagr']*100:.2f}%  Sharpe {r['sharpe']:.2f}  MaxDD {r['max_dd']*100:.2f}%")

    # Salva CSV para agregação posterior
    out_path = Path(f"data/scan_group_{args.group or 'custom'}.csv")
    df_out = pd.DataFrame(rows_full)
    df_3y = pd.DataFrame(rows_3y).rename(columns={"final": "final_3y", "cagr": "cagr_3y", "sharpe": "sharpe_3y",
                                                    "max_dd": "max_dd_3y", "neg_yrs": "neg_yrs_3y", "trades": "trades_3y"})
    if not df_3y.empty:
        df_out = df_out.merge(df_3y[["ticker","final_3y","cagr_3y","sharpe_3y","max_dd_3y","neg_yrs_3y"]], on="ticker", how="left")
    df_out.to_csv(out_path, index=False)
    print(f"\n  Resultados salvos em {out_path}")


if __name__ == "__main__":
    main()
