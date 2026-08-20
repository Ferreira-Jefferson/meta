"""Ablacao dos gatilhos do campeao — o sinal decide alguma coisa, ou e a watchlist?

Cada gatilho do `portfolio_dip2_hw40` e desligado (ou substituido por ruido) e o
resultado FULL e remedido. Duas perguntas separadas:

  1. O gatilho ADICIONA valor? -> comparar cada ablacao com o REF.
  2. O gatilho DECIDE alguma coisa? -> comparar o REF com N sorteios aleatorios
     usando exatamente as mesmas regras de cadencia, dip, histerese e stop.
     Se o REF cair no meio da distribuicao aleatoria, quem gerou o retorno foi a
     watchlist (7 papeis bons escolhidos com hindsight), nao o momentum 12-1.

Tambem mede risco de ruina: pior gap diario de cada papel do universo e o que ele
faria com 100% do capital numa unica posicao (que e o desenho do robo).

Uso: python scripts/run_trigger_ablation.py [--sims 300]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from backtest.metrics import negative_years
from backtest.runner import run as run_bt
from core.config import WATCHLIST, BacktestConfig
from market_data.loader import load_universe
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

START, END = "2010-01-01", "2026-08-19"
INITIAL = 1000.0


class RandomScore(DipTop1Portfolio):
    """Mesmas regras do campeao, ranking por ruido em vez de momentum 12-1.

    O ruido e um passeio aleatorio suave (nao i.i.d. por dia) para nao virar
    rotacao diaria artificial: o objetivo e trocar a INFORMACAO do sinal, nao a
    cadencia de decisao.
    """

    name = "random_score"
    candidate = False

    def __init__(self, seed: int, invert: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._seed = seed
        self._invert = invert

    def initialize(self, panels, ibov):
        super().initialize(panels, ibov)
        if self._invert:
            self._scores = {t: -s for t, s in self._scores.items()}
            return
        rng = np.random.default_rng(self._seed)
        for t, s in self._scores.items():
            noise = pd.Series(rng.standard_normal(len(s.index)), index=s.index).rolling(63).mean()
            self._scores[t] = noise.where(s.notna())  # so pontua onde o real pontuaria


def measure(strategy, config: BacktestConfig, universe) -> dict:
    r = run_bt(universe, strategy, config, start=START, end=END)
    m = r.metrics
    return {
        "final": float(m["final_capital"]),
        "cagr": float(m["cagr"]),
        "max_dd": float(m["max_drawdown"]),
        "neg_yrs": negative_years(r.equity_curve),
        "trades": len(r.trades),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=300)
    args = ap.parse_args()

    universe = load_universe()
    base_cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1)

    print(f"\nABLACAO DE GATILHOS — {START} -> {END}, R$ {INITIAL:,.0f} inicial\n")

    ref = measure(DipTop1Portfolio(), base_cfg, universe)
    rows = [("REF campeao (todos os gatilhos)", ref)]

    variants = [
        ("sem filtro de dip (dip_pct=0)", DipTop1Portfolio(dip_pct=0.0), base_cfg),
        ("dip mais exigente (dip_pct=5%)", DipTop1Portfolio(dip_pct=0.05), base_cfg),
        ("janela do high 20 (era 40)", DipTop1Portfolio(high_window=20), base_cfg),
        ("sem gate de Selic (threshold alto)", DipTop1Portfolio(selic_threshold=99.0), base_cfg),
        ("sem stop de 15%", DipTop1Portfolio(), BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.0)),
        ("stop apertado 8%", DipTop1Portfolio(), BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=0.08)),
        ("momentum 6-1 (lookback 126)", DipTop1Portfolio(lookback=126), base_cfg),
        ("momentum 24-1 (lookback 504)", DipTop1Portfolio(lookback=504), base_cfg),
        ("ANTI-momentum (score invertido)", RandomScore(seed=0, invert=True), base_cfg),
    ]

    no_hyst = DipTop1Portfolio()
    no_hyst._hysteresis = 0.0
    variants.insert(3, ("sem histerese (rotaciona sempre)", no_hyst, base_cfg))

    for label, strat, cfg in variants:
        try:
            rows.append((label, measure(strat, cfg, universe)))
        except Exception as e:  # noqa: BLE001
            print(f"  [ERRO] {label}: {e}")

    print(f"{'variante':38s} {'final':>12s} {'CAGR':>8s} {'MaxDD':>8s} {'NegYr':>6s} {'trades':>7s} {'vs REF':>9s}")
    for label, m in rows:
        delta = m["final"] / ref["final"] - 1.0
        print(f"{label:38s} {m['final']:12,.0f} {m['cagr'] * 100:7.2f}% {m['max_dd'] * 100:7.1f}% "
              f"{m['neg_yrs']:6d} {m['trades']:7d} {delta * 100:+8.1f}%")

    # ---- ranking aleatorio: o sinal decide, ou e a watchlist? ----
    print(f"\nRANKING ALEATORIO — {args.sims} sorteios, mesmas regras, sem momentum")
    finals, cagrs, dds = [], [], []
    for seed in range(args.sims):
        try:
            m = measure(RandomScore(seed=seed), base_cfg, universe)
        except Exception:
            continue
        finals.append(m["final"])
        cagrs.append(m["cagr"])
        dds.append(m["max_dd"])
        if (seed + 1) % 50 == 0:
            print(f"  ... {seed + 1}/{args.sims}", flush=True)

    arr = np.array(finals)
    cg = np.array(cagrs)
    pct = float((arr < ref["final"]).mean() * 100)
    print(f"\n  capital final aleatorio  p05 {np.percentile(arr, 5):>10,.0f} | "
          f"p50 {np.percentile(arr, 50):>10,.0f} | p95 {np.percentile(arr, 95):>10,.0f}")
    print(f"  CAGR aleatorio           p05 {np.percentile(cg, 5) * 100:>9.2f}% | "
          f"p50 {np.percentile(cg, 50) * 100:>9.2f}% | p95 {np.percentile(cg, 95) * 100:>9.2f}%")
    print(f"  MaxDD aleatorio          p05 {np.percentile(dds, 5) * 100:>9.1f}% | "
          f"p50 {np.percentile(dds, 50) * 100:>9.1f}% | p95 {np.percentile(dds, 95) * 100:>9.1f}%")
    print(f"  REF R$ {ref['final']:,.0f} fica no percentil {pct:.1f} do ranking aleatorio")
    print(f"  quantos sorteios batem o REF: {(arr >= ref['final']).sum()}/{len(arr)}")
    print(f"  quantos sorteios perdem dinheiro (< R$ {INITIAL:,.0f}): {(arr < INITIAL).sum()}/{len(arr)}")
    print(f"  pior sorteio: R$ {arr.min():,.0f}   |   melhor: R$ {arr.max():,.0f}")

    # ---- risco de ruina: gap de um papel com 100% do capital ----
    print("\nRISCO DE GAP — o robo carrega 100% do capital em UM papel")
    print("  o stop de 15% nao protege de gap: engine executa em min(open, stop) (engine_portfolio.py:300)")
    print(f"\n  {'ticker':8s} {'pior gap open-to-open':>22s} {'data':>12s} {'dias com gap < -10%':>21s}")
    for t in WATCHLIST:
        df = universe[t]
        o = df["open"].dropna()
        gap = (o / o.shift(1) - 1.0).dropna()
        worst = gap.min()
        print(f"  {t.replace('.SA', ''):8s} {worst * 100:21.1f}% {gap.idxmin().date()!s:>12s} "
              f"{int((gap < -0.10).sum()):21d}")


if __name__ == "__main__":
    main()
