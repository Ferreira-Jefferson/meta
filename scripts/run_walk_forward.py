"""Walk-forward da selecao de watchlist — mede o vies de escolher os tickers sabendo o futuro.

O problema
----------
A WATCHLIST oficial (`core/config.py`) foi escolhida por forward selection greedy
rodada em 2026 maximizando o capital final de 2010-2026. Ou seja: os 7 tickers
foram escolhidos JA SABENDO qual deles subiu. O CAGR de 36% do FULL nao e uma
expectativa — e o maximo de uma busca sobre o proprio periodo medido.

O que este script faz
---------------------
Refaz a selecao usando SO dado ate uma data de corte e mede o resultado no
periodo seguinte, as cegas. A diferenca entre o in-sample e o out-of-sample e a
mordida do vies de selecao.

Tres cortes (2016/2018/2020) para nao depender de um unico ponto de corte.

Comparacoes em cada janela OOS:
  - watchlist walk-forward (cega)        <- o numero honesto
  - watchlist oficial (contaminada)      <- o numero do diario
  - buy&hold equal-weight da WF          <- o robo adiciona valor sobre so comprar?
  - IBOV buy&hold                        <- o piso

Uso: python scripts/run_walk_forward.py [--target-n 7] [--min-adtv 0]

Aviso registrado no proprio resultado: o pool de candidatos sai de `data/raw/`,
que so contem empresas que AINDA negociam em 2026. Quem quebrou ou saiu da bolsa
entre 2010 e 2026 nao esta ali. Isso e vies de sobrevivencia residual e empurra
TODOS os numeros deste script para cima — inclusive os walk-forward.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from backtest.metrics import negative_years
from backtest.runner import run as run_bt
from core.config import BENCHMARK, WATCHLIST, BacktestConfig
from market_data.loader import load_one
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

INITIAL = 1000.0
CONFIG = BacktestConfig(initial_capital=INITIAL, lot_size=1)

SPLITS = [
    ("2010-01-01", "2015-12-31", "2016-01-01"),
    ("2010-01-01", "2017-12-31", "2018-01-01"),
    ("2010-01-01", "2019-12-31", "2020-01-01"),
]
OOS_END = "2026-08-19"

_PANELS: dict[str, pd.DataFrame] = {}


def panel(ticker: str) -> pd.DataFrame:
    """Painel do ticker, sem as linhas de close vazio.

    Varios parquets terminam com uma linha do pregao mais recente ainda sem
    close (download parcial). Se o robo estiver posicionado nesse dia, o equity
    do dia vira NaN e contamina `final_capital` — a metrica sai NaN sem que nada
    tenha falhado. Descartar a linha vazia e o comportamento correto: ela nao e
    um pregao, e um registro incompleto.
    """
    if ticker not in _PANELS:
        df = load_one(ticker)
        _PANELS[ticker] = df[df["close"].notna()]
    return _PANELS[ticker]


def candidate_pool(min_adtv: float, asof: str) -> list[str]:
    """Tickers com historico desde 2010 e liquidez suficiente NA DATA DE CORTE."""
    out = []
    for p in sorted(glob.glob("data/raw/*.parquet")):
        base = os.path.basename(p)[:-8]
        if base.startswith("_") or "_" not in base or base.startswith("DX-Y"):
            continue
        # WEGE3_SA -> WEGE3.SA (so o ultimo separador vira ponto)
        head, _, tail = base.rpartition("_")
        ticker = f"{head}.{tail}"
        try:
            df = panel(ticker)
        except Exception:
            continue
        if "close" not in df.columns:
            continue
        c = df["close"].dropna()
        if len(c) == 0:
            continue
        if c.index[0] > pd.Timestamp("2010-06-30") or c.index[-1] < pd.Timestamp("2026-06-01"):
            continue
        if min_adtv > 0:
            hist = df.loc[df.index <= pd.Timestamp(asof)].tail(252)
            if len(hist) < 200:
                continue
            adtv = (hist["close"] * hist["volume"]).median()
            if pd.isna(adtv) or adtv < min_adtv:
                continue
        out.append(ticker)
    return out


def backtest(tickers: list[str], start: str, end: str) -> dict:
    universe = {t: panel(t) for t in tickers}
    universe[BENCHMARK] = panel(BENCHMARK)
    r = run_bt(universe, DipTop1Portfolio(), CONFIG, start=start, end=end)
    m = r.metrics
    return {
        "final": float(m["final_capital"]),
        "cagr": float(m["cagr"]),
        "sharpe": float(m.get("sharpe", 0.0)),
        "max_dd": float(m["max_drawdown"]),
        "neg_yrs": negative_years(r.equity_curve),
        "trades": len(r.trades),
    }


def buy_hold(tickers: list[str], start: str, end: str) -> dict:
    """Equal-weight, comprado no primeiro pregao da janela, sem rebalance."""
    curves = []
    for t in tickers:
        c = panel(t)["close"].dropna()
        c = c.loc[(c.index >= pd.Timestamp(start)) & (c.index <= pd.Timestamp(end))]
        if len(c) < 2:
            continue
        curves.append(c / c.iloc[0])
    if not curves:
        return {"final": float("nan"), "cagr": float("nan"), "max_dd": float("nan"),
                "neg_yrs": 0, "trades": 0}
    eq = pd.concat(curves, axis=1).ffill().dropna().mean(axis=1) * INITIAL
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    return {
        "final": float(eq.iloc[-1]),
        "cagr": float((eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1),
        "sharpe": float("nan"),
        "max_dd": float((eq / eq.cummax() - 1.0).min()),
        "neg_yrs": negative_years(eq),
        "trades": len(curves),
    }


def greedy_select(pool: list[str], start: str, end: str, target_n: int) -> tuple[list[str], dict]:
    selected: list[str] = []
    remaining = list(pool)
    best_metrics: dict = {}
    for step in range(target_n):
        best_t, best_final, best_m = None, -1.0, None
        for t in remaining:
            try:
                r = backtest(selected + [t], start, end)
            except Exception:
                continue
            if r["final"] > best_final:
                best_t, best_final, best_m = t, r["final"], r
        if best_t is None:
            break
        selected.append(best_t)
        remaining.remove(best_t)
        best_metrics = best_m
        print(f"    passo {step + 1}: +{best_t.replace('.SA', ''):8s}  IS R$ {best_final:>10,.0f}  "
              f"CAGR {best_m['cagr'] * 100:6.2f}%  MaxDD {best_m['max_dd'] * 100:6.1f}%", flush=True)
    return selected, best_metrics


def fmt(label: str, m: dict) -> str:
    return (f"  {label:42s} R$ {m['final']:>11,.0f}  CAGR {m['cagr'] * 100:>6.2f}%  "
            f"MaxDD {m['max_dd'] * 100:>6.1f}%  NegYrs {m['neg_yrs']}  trades {m.get('trades', '-')}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-n", type=int, default=7)
    ap.add_argument("--min-adtv", type=float, default=0.0,
                    help="Filtro de liquidez na data de corte (R$/dia, mediana 252d). 0 = sem filtro.")
    args = ap.parse_args()

    print(f"\nWALK-FORWARD — selecao de watchlist com {args.target_n} tickers")
    print("estrategia: portfolio_dip2_hw40 (parametros CONGELADOS — ver nota no fim)")
    print(f"capital inicial R$ {INITIAL:,.0f} | lot_size 1 | OOS termina em {OOS_END}")
    if args.min_adtv > 0:
        print(f"filtro de liquidez: ADTV mediana 252d >= R$ {args.min_adtv:,.0f}/dia na data de corte")
    print()

    ibov_series = panel(BENCHMARK)["close"]

    for is_start, is_end, oos_start in SPLITS:
        pool = candidate_pool(args.min_adtv, is_end)
        print("=" * 100)
        print(f"CORTE {is_end}  |  IS {is_start} -> {is_end}  |  OOS {oos_start} -> {OOS_END}  "
              f"|  pool {len(pool)} tickers")
        print("=" * 100)

        selected, is_m = greedy_select(pool, is_start, is_end, args.target_n)
        print(f"\n  watchlist escolhida as cegas: {[t.replace('.SA', '') for t in selected]}\n")

        oos_wf = backtest(selected, oos_start, OOS_END)
        oos_off = backtest(list(WATCHLIST), oos_start, OOS_END)
        oos_bh = buy_hold(selected, oos_start, OOS_END)
        ib = ibov_series.loc[(ibov_series.index >= pd.Timestamp(oos_start)) &
                             (ibov_series.index <= pd.Timestamp(OOS_END))].dropna()
        oos_ibov = {
            "final": INITIAL * float(ib.iloc[-1] / ib.iloc[0]),
            "cagr": float((ib.iloc[-1] / ib.iloc[0]) ** (365.25 / (ib.index[-1] - ib.index[0]).days) - 1),
            "max_dd": float((ib / ib.cummax() - 1).min()),
            "neg_yrs": negative_years(ib),
            "trades": "-",
        }

        print(fmt("IN-SAMPLE  watchlist WF (o que a busca viu)", is_m))
        print(fmt("OOS  watchlist WF — CEGA", oos_wf))
        print(fmt("OOS  watchlist OFICIAL (contaminada)", oos_off))
        print(fmt("OOS  buy&hold equal-weight da WF", oos_bh))
        print(fmt("OOS  IBOV buy&hold", oos_ibov))
        print(f"\n  degradacao IS -> OOS: {is_m['cagr'] * 100:.2f}% -> {oos_wf['cagr'] * 100:.2f}% "
              f"({(oos_wf['cagr'] - is_m['cagr']) * 100:+.2f} p.p.)")
        print(f"  vies de selecao no OOS: oficial {oos_off['cagr'] * 100:.2f}% vs cega "
              f"{oos_wf['cagr'] * 100:.2f}% ({(oos_off['cagr'] - oos_wf['cagr']) * 100:+.2f} p.p.)\n")

    print("=" * 100)
    print("NOTAS")
    print("  1. Os PARAMETROS do robo (dip 2%, high_window 40, histerese 15%, confirm 2, selic 63d)")
    print("     tambem foram achados por busca sobre 2010-2026. Aqui eles ficam congelados, entao o")
    print("     numero 'cego' AINDA carrega o vies de parametro — e otimista.")
    print("  2. Pool de candidatos = data/raw/, que so tem empresas vivas em 2026. Vies de")
    print("     sobrevivencia residual, tambem empurra tudo para cima.")


if __name__ == "__main__":
    main()
