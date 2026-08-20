"""Aplica cada melhoria aprendida e mede TODAS sob walk-forward, com criterio de seguranca.

Protocolo (nao negociavel — e o que os testes anteriores mostraram ser necessario):
  - Universo escolhido as cegas na data de corte, so por LIQUIDEZ (nunca por retorno).
  - Parametros congelados nos defaults do repo (nunca re-otimizados no teste).
  - Tres cortes independentes; o veredito e a PIOR janela, nao a media.
  - Criterio de aceite por SEGURANCA. Capital menor e aceitavel; janela negativa,
    drawdown fundo e tempo submerso longo nao sao.

Portoes de aceite (todos precisam passar):
  G1  pior janela com CAGR > 0
  G2  pior MaxDD melhor que -45%
  G3  CAGR mediano >= CAGR mediano do IBOV nas mesmas janelas
  G4  tempo submerso mediano nao pior que o do IBOV nas mesmas janelas
  G5  pior retorno de 12 meses melhor que -35%

Uso: python scripts/run_safety_walkforward.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from safety_lab import (INITIAL, CooldownAfterStop, TrendGated, Variant, combined_equity,
                        liquid_universe, metrics, panel)

from backtest.metrics import negative_years
from core.config import BENCHMARK, BacktestConfig
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

OOS_END = "2026-08-19"
CUTS = [("2015-12-31", "2016-01-01"), ("2017-12-31", "2018-01-01"), ("2019-12-31", "2020-01-01")]

GATES = {"min_cagr": 0.0, "max_dd": -0.45, "worst_12m": -0.35}


def cfg(stop: float = 0.15) -> BacktestConfig:
    return BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=stop)


def ensemble_factories() -> list:
    """Tres combos de parametros em vez de um 'melhor'.

    O walk-forward de parametros mostrou que o combo vencedor do in-sample cai na
    posicao mediana (55 de 108) fora da amostra. Se a escolha nao informa, a
    resposta racional nao e escolher melhor — e nao escolher: rodar varios e
    dividir o capital, o que troca o risco de errar o combo pela media deles.
    """
    return [
        lambda: DipTop1Portfolio(),                                  # oficial
        lambda: DipTop1Portfolio(dip_pct=0.0, high_window=20),       # sem dip, janela curta
        lambda: DipTop1Portfolio(dip_pct=0.05, high_window=60),      # dip alto, janela longa
    ]


VARIANTS = [
    Variant("V0_base_liquid20", "REF: campeao, universo liquido top-20, 1 conta",
            [lambda: DipTop1Portfolio()], sleeves=1, config=cfg()),
    Variant("V1_sleeves3", "3 contas independentes (diversifica concentracao)",
            [lambda: DipTop1Portfolio()], sleeves=3, config=cfg()),
    Variant("V2_sleeves5", "5 contas independentes",
            [lambda: DipTop1Portfolio()], sleeves=5, config=cfg()),
    Variant("V3_sleeves5_nostop", "5 contas, SEM stop (evita whipsaw)",
            [lambda: DipTop1Portfolio()], sleeves=5, config=cfg(0.0)),
    Variant("V4_sleeves5_stop25", "5 contas, stop largo 25%",
            [lambda: DipTop1Portfolio()], sleeves=5, config=cfg(0.25)),
    Variant("V5_sleeves5_trend", "5 contas + trava de tendencia IBOV>SMA200",
            [lambda: TrendGated()], sleeves=5, config=cfg()),
    Variant("V6_sleeves5_cooldown", "5 contas + quarentena de 2 meses apos stop",
            [lambda: CooldownAfterStop()], sleeves=5, config=cfg()),
    Variant("V7_sleeves5_dip5", "5 contas + dip 5% (ferramenta de DD)",
            [lambda: DipTop1Portfolio(dip_pct=0.05)], sleeves=5, config=cfg()),
    Variant("V8_sleeves3_ensemble", "3 contas x 3 combos de parametro (9 contas)",
            ensemble_factories(), sleeves=3, config=cfg()),
    Variant("V9_liquid40_sleeves5", "universo top-40, 5 contas",
            [lambda: DipTop1Portfolio()], sleeves=5, config=cfg(), universe_n=40),
    Variant("V10_full_stack", "5 contas + tendencia + stop 25% + ensemble",
            [lambda: TrendGated(), lambda: TrendGated(dip_pct=0.0, high_window=20),
             lambda: TrendGated(dip_pct=0.05, high_window=60)],
            sleeves=5, config=cfg(0.25)),
]


def ibov_metrics(start: str, end: str) -> dict:
    c = panel(BENCHMARK)["close"].loc[start:end].dropna()
    years = (c.index[-1] - c.index[0]).days / 365.25
    dd = c / c.cummax() - 1.0
    r12 = c / c.shift(252) - 1.0
    return {"final": INITIAL * float(c.iloc[-1] / c.iloc[0]),
            "cagr": float((c.iloc[-1] / c.iloc[0]) ** (1 / years) - 1),
            "max_dd": float(dd.min()), "underwater": float((dd < -0.01).mean()),
            "worst_12m": float(r12.min()), "neg_yrs": negative_years(c), "trades": 0}


def main() -> None:
    print("\nWALK-FORWARD DE SEGURANCA — cada melhoria medida nas 3 janelas cegas")
    print(f"universo point-in-time por liquidez | parametros congelados | R$ {INITIAL:,.0f} inicial\n")

    universes = {cut: liquid_universe(cut, 20) for cut, _ in CUTS}
    universes40 = {cut: liquid_universe(cut, 40) for cut, _ in CUTS}
    for cut, oos in CUTS:
        print(f"  universo em {cut}: {[t.replace('.SA', '') for t in universes[cut]]}")
    print()

    ibov = {oos: ibov_metrics(oos, OOS_END) for _, oos in CUTS}
    print(f"{'IBOV':38s} " + "".join(
        f"| {ibov[o]['cagr'] * 100:6.2f}% {ibov[o]['max_dd'] * 100:6.1f}% " for _, o in CUTS))
    print()

    results = {}
    header = f"{'variante':38s} " + "".join(f"| {'CAGR':>6s} {'MaxDD':>7s} " for _ in CUTS) + "| veredito"
    print(header)
    print("-" * len(header))

    for v in VARIANTS:
        per_window = []
        for cut, oos in CUTS:
            tickers = (universes40 if v.universe_n == 40 else universes)[cut]
            eq, n = combined_equity(v, tickers, oos, OOS_END)
            per_window.append(metrics(eq, n))
        results[v.key] = (v, per_window)

        cagrs = [m["cagr"] for m in per_window]
        dds = [m["max_dd"] for m in per_window]
        uw = [m["underwater"] for m in per_window]
        w12 = [m["worst_12m"] for m in per_window]
        ib_med = float(np.median([ibov[o]["cagr"] for _, o in CUTS]))
        ib_uw = float(np.median([ibov[o]["underwater"] for _, o in CUTS]))
        gates = {
            "G1": min(cagrs) > GATES["min_cagr"],
            "G2": min(dds) > GATES["max_dd"],
            "G3": float(np.median(cagrs)) >= ib_med,
            "G4": float(np.median(uw)) <= ib_uw,
            "G5": min(w12) > GATES["worst_12m"],
        }
        tag = "PASSA" if all(gates.values()) else "falha " + ",".join(k for k, ok in gates.items() if not ok)
        row = f"{v.key:38s} " + "".join(
            f"| {m['cagr'] * 100:6.2f}% {m['max_dd'] * 100:6.1f}% " for m in per_window) + f"| {tag}"
        print(row, flush=True)

    print("\n" + "=" * 118)
    print("DETALHE — mediana das 3 janelas e a PIOR delas")
    print("=" * 118)
    print(f"{'variante':38s} {'CAGR med':>9s} {'CAGR pior':>10s} {'MaxDD pior':>11s} "
          f"{'submerso med':>13s} {'pior 12m':>9s} {'trades':>7s}")
    for key, (v, ms) in results.items():
        cagrs = [m["cagr"] for m in ms]
        print(f"{key:38s} {np.median(cagrs) * 100:8.2f}% {min(cagrs) * 100:9.2f}% "
              f"{min(m['max_dd'] for m in ms) * 100:10.1f}% "
              f"{np.median([m['underwater'] for m in ms]) * 100:12.1f}% "
              f"{min(m['worst_12m'] for m in ms) * 100:8.1f}% "
              f"{int(np.median([m['trades'] for m in ms])):7d}")
    ib_c = [ibov[o]["cagr"] for _, o in CUTS]
    print(f"{'IBOV (referencia)':38s} {np.median(ib_c) * 100:8.2f}% {min(ib_c) * 100:9.2f}% "
          f"{min(ibov[o]['max_dd'] for _, o in CUTS) * 100:10.1f}% "
          f"{np.median([ibov[o]['underwater'] for _, o in CUTS]) * 100:12.1f}% "
          f"{min(ibov[o]['worst_12m'] for _, o in CUTS) * 100:8.1f}% {0:7d}")

    print(f"\nportoes: G1 pior CAGR>0 | G2 pior MaxDD>-45% | G3 CAGR med>=IBOV med "
          f"({np.median(ib_c) * 100:.2f}%) | G4 submerso med<=IBOV | G5 pior 12m>-35%")


if __name__ == "__main__":
    main()
