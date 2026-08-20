"""Rodada 2 — finalistas contra JANELAS ROLANTES de 5 anos, e o custo do imposto.

Por que mudar de protocolo
--------------------------
Os tres cortes da rodada 1 (`run_safety_walkforward.py`) compartilham o mesmo fim
de janela (agosto/2026). Se os ultimos 18 meses forem bons, os tres cortes ficam
bons juntos — a evidencia parece triplicada e nao e. Aqui cada janela e um
periodo de 5 anos FECHADO, com universo montado por liquidez no primeiro dia e
nada depois. E a pergunta que o usuario realmente faz: "se eu tivesse ligado o
robo em 2014, e em 2016, e em 2018... o que teria acontecido em cada caso?"

Tambem responde ao que faltava: os numeros aqui saem LIQUIDOS DE IR (15% sobre
ganho realizado, apuracao mensal, prejuizo compensa, sem contar com a isencao de
R$20k/mes — que so vale enquanto o capital e pequeno).

Uso: python scripts/run_safety_rolling.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from safety_lab import (INITIAL, Variant, combined_equity, liquid_universe, metrics, panel,
                        split_sleeves)

from backtest.metrics import negative_years
from backtest.runner import run as run_bt
from core.config import BENCHMARK, BacktestConfig
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

WINDOWS = [
    ("2014-01-01", "2018-12-31"),
    ("2016-01-01", "2020-12-31"),
    ("2018-01-01", "2022-12-31"),
    ("2020-01-01", "2024-12-31"),
    ("2021-08-19", "2026-08-19"),
]

IR = 0.15


def cfg(stop: float = 0.15) -> BacktestConfig:
    return BacktestConfig(initial_capital=INITIAL, lot_size=1, stop_loss_pct=stop)


def ensemble() -> list:
    return [lambda: DipTop1Portfolio(),
            lambda: DipTop1Portfolio(dip_pct=0.0, high_window=20),
            lambda: DipTop1Portfolio(dip_pct=0.05, high_window=60)]


VARIANTS = [
    Variant("V0_1conta", "1 conta (concentracao atual)", [lambda: DipTop1Portfolio()], sleeves=1, config=cfg()),
    Variant("V1_3contas", "3 contas independentes", [lambda: DipTop1Portfolio()], sleeves=3, config=cfg()),
    Variant("V2_5contas", "5 contas independentes", [lambda: DipTop1Portfolio()], sleeves=5, config=cfg()),
    Variant("V8_3x3_ensemble", "3 contas x 3 parametros", ensemble(), sleeves=3, config=cfg()),
    Variant("V11_5x3_ensemble", "5 contas x 3 parametros", ensemble(), sleeves=5, config=cfg()),
]


def tax_drag(variant: Variant, tickers: list[str], start: str, end: str) -> float:
    """IR pago, em R$, somando a apuracao de cada conta independente.

    Cada sleeve e uma conta separada, entao prejuizo de uma NAO compensa ganho de
    outra — que e como funciona de fato quando sao CPFs/corretoras diferentes, e
    e o caso conservador. Se tudo estiver no mesmo CPF a compensacao e cruzada e
    o imposto sai menor; nunca maior.
    """
    groups = split_sleeves(tickers, variant.sleeves)
    n_accounts = len(groups) * len(variant.factories)
    per_account = INITIAL / n_accounts
    c = BacktestConfig(initial_capital=per_account, lot_size=variant.config.lot_size,
                       stop_loss_pct=variant.config.stop_loss_pct, costs=variant.config.costs)
    total_tax = 0.0
    for group in groups:
        universe = {t: panel(t) for t in group}
        universe[BENCHMARK] = panel(BENCHMARK)
        for factory in variant.factories:
            r = run_bt(universe, factory(), c, start=start, end=end)
            monthly: dict[tuple[int, int], float] = {}
            for t in r.trades:
                if t.pnl_brl is None or t.exit_date is None:
                    continue
                k = (t.exit_date.year, t.exit_date.month)
                monthly[k] = monthly.get(k, 0.0) + float(t.pnl_brl)
            carry = 0.0
            for k in sorted(monthly):
                g = monthly[k]
                if g > 0:
                    use = min(carry, g)
                    carry -= use
                    total_tax += (g - use) * IR
                else:
                    carry += -g
    return total_tax


def dd_duration_months(eq: pd.Series) -> float:
    """Maior tempo continuo abaixo do topo anterior, em meses."""
    peak = eq.cummax()
    under = eq < peak * (1 - 1e-9)
    best = cur = 0
    start = None
    for d, u in under.items():
        if u:
            if start is None:
                start = d
            cur = (d - start).days
            best = max(best, cur)
        else:
            start = None
    return best / 30.44


def main() -> None:
    print("\nJANELAS ROLANTES DE 5 ANOS — universo por liquidez no 1o dia, nada depois")
    print(f"R$ {INITIAL:,.0f} inicial | IR {IR * 100:.0f}% sobre ganho realizado, apurado por conta\n")

    unis = {s: liquid_universe(s, 20) for s, _ in WINDOWS}
    for s, e in WINDOWS:
        print(f"  {s[:7]}: {[t.replace('.SA', '') for t in unis[s]][:10]} ...")
    print()

    ib = {}
    for s, e in WINDOWS:
        c = panel(BENCHMARK)["close"].loc[s:e].dropna()
        yrs = (c.index[-1] - c.index[0]).days / 365.25
        ib[s] = {"cagr": float((c.iloc[-1] / c.iloc[0]) ** (1 / yrs) - 1),
                 "max_dd": float((c / c.cummax() - 1).min())}

    hdr = f"{'variante':20s} " + "".join(f"| {s[2:7]:>13s} " for s, _ in WINDOWS) + "|  pior   mediana"
    print(hdr)
    print("-" * len(hdr))
    print(f"{'IBOV':20s} " + "".join(
        f"| {ib[s]['cagr'] * 100:6.1f}% {ib[s]['max_dd'] * 100:5.0f}% " for s, _ in WINDOWS) +
        f"| {min(ib[s]['cagr'] for s, _ in WINDOWS) * 100:5.1f}%  "
        f"{np.median([ib[s]['cagr'] for s, _ in WINDOWS]) * 100:5.1f}%")

    store = {}
    for v in VARIANTS:
        cells, rows = [], []
        for s, e in WINDOWS:
            eq, n = combined_equity(v, unis[s], s, e)
            m = metrics(eq, n)
            m["tax"] = tax_drag(v, unis[s], s, e)
            m["net_final"] = m["final"] - m["tax"]
            yrs = (eq.index[-1] - eq.index[0]).days / 365.25
            m["net_cagr"] = (m["net_final"] / INITIAL) ** (1 / yrs) - 1
            m["dd_months"] = dd_duration_months(eq)
            rows.append(m)
            cells.append(f"| {m['net_cagr'] * 100:6.1f}% {m['max_dd'] * 100:5.0f}% ")
        store[v.key] = (v, rows)
        nets = [m["net_cagr"] for m in rows]
        print(f"{v.key:20s} " + "".join(cells) +
              f"| {min(nets) * 100:5.1f}%  {np.median(nets) * 100:5.1f}%", flush=True)

    print("\n(CAGR mostrado ja e LIQUIDO de IR; MaxDD e bruto)\n")
    print("=" * 110)
    print(f"{'variante':20s} {'CAGR liq med':>12s} {'CAGR liq pior':>13s} {'MaxDD pior':>11s} "
          f"{'meses submerso':>15s} {'pior 12m':>9s} {'jan. negativas':>15s}")
    print("=" * 110)
    for key, (v, rows) in store.items():
        nets = [m["net_cagr"] for m in rows]
        print(f"{key:20s} {np.median(nets) * 100:11.2f}% {min(nets) * 100:12.2f}% "
              f"{min(m['max_dd'] for m in rows) * 100:10.1f}% "
              f"{max(m['dd_months'] for m in rows):14.0f} "
              f"{min(m['worst_12m'] for m in rows) * 100:8.1f}% "
              f"{sum(1 for x in nets if x < 0):8d} de {len(nets)}")
    ibc = [ib[s]["cagr"] for s, _ in WINDOWS]
    print(f"{'IBOV':20s} {np.median(ibc) * 100:11.2f}% {min(ibc) * 100:12.2f}% "
          f"{min(ib[s]['max_dd'] for s, _ in WINDOWS) * 100:10.1f}%")

    print("\nCUSTO DO IMPOSTO por janela (R$ sobre R$ 1.000 iniciais)")
    print(f"{'variante':20s} " + "".join(f"{s[2:7]:>9s}" for s, _ in WINDOWS))
    for key, (v, rows) in store.items():
        print(f"{key:20s} " + "".join(f"{m['tax']:9.0f}" for m in rows))


if __name__ == "__main__":
    main()
