"""Dois parametros do robo que AINDA nao tinham evidencia: cadencia e despejo.

`run_sleeve_validation.py` mostrou que o robo com refresh anual reprova o portao
G1 (uma janela negativa em cinco) enquanto o arranjo de teste com universo
congelado passa. Duas causas possiveis, e as duas sao decisoes de desenho que eu
tomei sem medir:

  P1  CADENCIA — de quanto em quanto tempo o universo liquido e refeito.
      Nunca refazer nao e opcao: em 20 anos de operacao o robo estaria negociando
      o top-20 de 2026 para sempre. Mas refazer todo ano pode ser churn puro.

  P2  DESPEJO — o que fazer com uma posicao aberta cujo papel saiu do top-N na
      virada. `evict_on_refresh=True` vende no dia seguinte; `False` deixa a
      histerese decidir com o momentum real do papel (o refresh so proibe
      COMPRAR fora do universo, nao segurar o que ja se tem).

Regra deste teste, para nao repetir o erro que este projeto ja cometeu duas
vezes: a escolha so vale se a metrica de RISCO for monotona no parametro. Se o
CAGR mediano oscilar sem padrao, escolher pelo CAGR e curve-fitting sobre as
mesmas cinco janelas — exatamente o que invalidou a watchlist oficial.

Uso: .venv/Scripts/python.exe scripts/run_sleeve_tuning.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from run_sleeve_validation import WINDOWS, dd_months, full_panels, tax_on, wrap

from backtest.runner import run as run_bt
from core.config import BacktestConfig
from strategy.liquid_sleeves5 import LiquidSleeves5

INITIAL = 1000.0
CADENCES = [12, 24, 36, 60, 120]


def measure(refresh: int, evict: bool, start: str, end: str) -> dict:
    cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1)
    bot = LiquidSleeves5(refresh_months=refresh, evict_on_refresh=evict)
    r = run_bt(full_panels(), bot, cfg, start=start, end=end)
    return wrap(r.equity_curve, len(r.trades), tax_on(r.trades))


def main() -> None:
    print("\nCADENCIA DE REFRESH x DESPEJO — liquid_sleeves5, 5 janelas de 5 anos")
    print(f"R$ {INITIAL:,.0f} | CAGR liquido de IR 15%\n")

    hdr = (f"{'cadencia':>9s} {'despejo':>8s} " + "".join(f"| {s[2:7]:>7s} " for s, _ in WINDOWS) +
           f"| {'med':>7s} {'pior':>7s} {'MaxDD':>7s} {'12m':>7s} {'neg':>4s} {'trd':>4s}")
    print(hdr)
    print("-" * len(hdr))

    table = {}
    for evict in (True, False):
        for refresh in CADENCES:
            rows = [measure(refresh, evict, s, e) for s, e in WINDOWS]
            nets = [m["net_cagr"] for m in rows]
            table[(refresh, evict)] = rows
            print(f"{refresh:>7d}m {('sim' if evict else 'nao'):>8s} " +
                  "".join(f"| {m['net_cagr'] * 100:6.1f}% " for m in rows) +
                  f"| {np.median(nets) * 100:6.2f}% {min(nets) * 100:6.2f}% "
                  f"{min(m['max_dd'] for m in rows) * 100:6.1f}% "
                  f"{min(m['worst_12m'] for m in rows) * 100:6.1f}% "
                  f"{sum(1 for x in nets if x < 0):4d} "
                  f"{int(np.median([m['trades'] for m in rows])):4d}", flush=True)
        print()

    print("MONOTONIA — a metrica melhora sempre que a cadencia afrouxa?")
    print(f"{'metrica':>22s} " + "".join(f"{c:>8d}m" for c in CADENCES) + "   monotona?")
    for evict in (True, False):
        tag = "despejo sim" if evict else "despejo nao"
        for label, fn in (
            ("pior CAGR", lambda r: min(m["net_cagr"] for m in r) * 100),
            ("pior MaxDD", lambda r: min(m["max_dd"] for m in r) * 100),
            ("pior 12m", lambda r: min(m["worst_12m"] for m in r) * 100),
            ("CAGR mediano", lambda r: float(np.median([m["net_cagr"] for m in r])) * 100),
        ):
            vals = [fn(table[(c, evict)]) for c in CADENCES]
            mono = all(b >= a for a, b in zip(vals, vals[1:]))
            print(f"{tag + ' / ' + label:>22s} " + "".join(f"{v:>9.2f}" for v in vals) +
                  f"   {'sim' if mono else 'NAO'}")
        print()


if __name__ == "__main__":
    main()
