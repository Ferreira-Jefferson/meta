"""liqflop -- complemento do split IS/OOS: a vantagem depende do HORIZONTE?

O split IS/OOS (`run_liqflop_is_oos.py`) responde "o edge existe nas duas
metades da base?". Este responde a outra metade da pergunta do dono do capital,
que o ranking oficial levanta e o split nao resolve: o robo ganha em FULL (16,6
anos) e perde em 5 anos e em 1 ano. Isso e' efeito de ter sido ajustado no
passado, ou e' o horizonte de medicao?

Metodo: TODAS as janelas de N anos com inicio mensal, do primeiro inicio
possivel ate o ultimo que ainda cabe na base. Nenhuma janela e' escolhida --
por isso nao ha como cherry-pick aqui. Cada janela comeca com R$ 1.000 e e'
comparada com o IBOV na MESMA janela (memoria `feedback_honest_period_comparison`).

Config identica ao ranking oficial (`scheduler.CHAMPION_*`): lote 1, caixa na
Selic, custos padrao, sem a taxa fixa do fracionario (igual ao ranking).
IBOV em pontos, sem dividendos -- assimetria declarada, vale para toda janela.

Uso: .venv/Scripts/python.exe scripts/run_liqflop_rolling.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from backtest.runner import run as run_bt
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.lab.fee_capacity.hip_03_pausa_apos_perdas import (
    LiquidFocusLossStreakPause as Liqflop,
)

CAPITAL = 1_000.0
SELIC = "data/raw/selic.parquet"
BASE_FIM = pd.Timestamp("2026-08-21")
BASE_INICIO = pd.Timestamp("2010-01-01")
HORIZONTES = (1, 3, 5, 10)


def janela(universo, start: pd.Timestamp, anos: int) -> dict | None:
    end = start + pd.DateOffset(years=anos)
    cfg = BacktestConfig(initial_capital=CAPITAL, lot_size=1, cash_yield_path=SELIC)
    r = run_bt(universo, Liqflop(), cfg, start=str(start.date()), end=str(end.date()))
    eq = r.equity_curve
    if len(eq) < 200 * anos:
        return None
    bench = r.benchmark_curve.reindex(eq.index).ffill().dropna()
    if len(bench) < 2:
        return None
    robo = float(eq.iloc[-1])
    ibov = float(CAPITAL * bench.iloc[-1] / bench.iloc[0])
    return {
        "inicio": str(start.date()), "anos": anos,
        "robo": robo, "ibov": ibov, "razao": robo / ibov,
        "robo_cagr": float(r.metrics["cagr"]),
        "ibov_cagr": float(r.metrics["benchmark_cagr"]),
        "dd": float(r.metrics["max_drawdown"]),
        "trades": len([t for t in r.trades if t.exit_date is not None]),
    }


def main() -> None:
    s = Liqflop()
    universo = load_universe(tickers=s.universe_tickers)
    print(f"universo: {len(universo)} paineis\n")
    todas: list[dict] = []
    t0 = time.perf_counter()

    hdr = (f"{'horiz':>6s} {'n':>4s} {'bate ibov':>10s} {'robo<0':>7s} "
           f"{'razao p10':>10s} {'mediana':>9s} {'p90':>8s} {'pior robo':>10s} "
           f"{'CAGR med robo':>14s} {'CAGR med ibov':>14s} {'trd med':>8s}")
    print(hdr)
    print("-" * len(hdr))
    for anos in HORIZONTES:
        inicios = pd.date_range(BASE_INICIO, BASE_FIM - pd.DateOffset(years=anos), freq="MS")
        linhas = [m for i in inicios if (m := janela(universo, i, anos)) is not None]
        todas.extend(linhas)
        if not linhas:
            continue
        df = pd.DataFrame(linhas)
        print(f"{anos:5d}a {len(df):4d} {int((df['razao'] > 1).sum()):5d}/{len(df):<4d} "
              f"{int((df['robo'] < CAPITAL).sum()):7d} "
              f"{np.percentile(df['razao'], 10):9.2f}x {df['razao'].median():8.2f}x "
              f"{np.percentile(df['razao'], 90):7.2f}x {df['robo'].min():10,.0f} "
              f"{df['robo_cagr'].median()*100:13.2f}% {df['ibov_cagr'].median()*100:13.2f}% "
              f"{df['trades'].median():8.0f}", flush=True)

    out = pd.DataFrame(todas)
    destino = Path("scripts/swing_lab/liqflop_rolling.csv")
    out.to_csv(destino, index=False)
    print(f"\n{len(out)} janelas em {time.perf_counter()-t0:.0f}s -> {destino}")

    print("\nrazao robo/IBOV por ANO DE INICIO, janelas de 5 anos "
          "(mostra QUANDO a vantagem apareceu, sem escolher janela):")
    cinco = out[out["anos"] == 5].copy()
    cinco["ano"] = cinco["inicio"].str[:4]
    for ano, g in cinco.groupby("ano"):
        barra = "#" * min(40, max(1, int(g["razao"].median() * 4)))
        print(f"  {ano}  n={len(g):2d}  mediana {g['razao'].median():5.2f}x  "
              f"min {g['razao'].min():5.2f}x  max {g['razao'].max():5.2f}x  {barra}")


if __name__ == "__main__":
    main()
