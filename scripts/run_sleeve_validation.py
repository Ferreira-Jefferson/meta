"""Valida os robos `liquid_sleeve` / `liquid_sleeves5` contra o desenho aprovado.

O desenho que passou no walk-forward (`run_safety_rolling.py`, variante
V2_5contas) era um ARRANJO DE TESTE, nao um robo: o universo liquido era montado
por um script, fora da estrategia, e congelado no primeiro dia da janela; as
cinco contas eram cinco backtests somados. Os robos deste repositorio agora
fazem isso por dentro — e por dentro tres coisas mudaram:

  D1  o universo se REFAZ a cada 12 meses em vez de congelar por 5 anos
      (o arranjo de teste envelhecia: em 2026 ainda operava o top-20 de 2021)
  D2  `liquid_sleeves5` divide UMA conta em vez de somar cinco separadas
  D3  o ranking de liquidez agora e calculado dentro da estrategia

Cada uma pode ter estragado o resultado sem ninguem notar. Este script isola as
tres e mede o robo final nas MESMAS cinco janelas de cinco anos, com o mesmo
imposto, contra a mesma referencia.

  H1  o universo escolhido DENTRO do robo e igual ao do arranjo de teste?
  H2  refazer o universo todo ano ajuda ou atrapalha? (5 contas, refresh on/off)
  H3  uma conta com caixa compartilhado replica cinco contas separadas?
  H4  o robo final passa nos mesmos portoes de seguranca?

Uso: .venv/Scripts/python.exe scripts/run_sleeve_validation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from safety_lab import INITIAL, liquid_universe, metrics, panel, split_sleeves

from backtest.runner import run as run_bt
from core.config import BENCHMARK, BacktestConfig
from strategy.liquid_sleeve import POOL, LiquidSleeve
from strategy.liquid_sleeves5 import LiquidSleeves5
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

WINDOWS = [
    ("2014-01-01", "2018-12-31"),
    ("2016-01-01", "2020-12-31"),
    ("2018-01-01", "2022-12-31"),
    ("2020-01-01", "2024-12-31"),
    ("2021-08-19", "2026-08-19"),
]
IR = 0.15
NO_REFRESH = 600  # meses: uma epoca so, universo congelado no 1o dia da janela


def full_panels() -> dict[str, pd.DataFrame]:
    u = {t: panel(t) for t in POOL}
    u[BENCHMARK] = panel(BENCHMARK)
    return u


def tax_on(trades) -> float:
    """IR de uma conta: 15% do ganho realizado, apuracao mensal, prejuizo compensa."""
    monthly: dict[tuple[int, int], float] = {}
    for t in trades:
        if t.pnl_brl is None or t.exit_date is None:
            continue
        k = (t.exit_date.year, t.exit_date.month)
        monthly[k] = monthly.get(k, 0.0) + float(t.pnl_brl)
    carry = tax = 0.0
    for k in sorted(monthly):
        g = monthly[k]
        if g > 0:
            use = min(carry, g)
            carry -= use
            tax += (g - use) * IR
        else:
            carry += -g
    return tax


def dd_months(eq: pd.Series) -> float:
    peak = eq.cummax()
    under = eq < peak * (1 - 1e-9)
    best = 0
    start = None
    for d, u in under.items():
        if u:
            start = d if start is None else start
            best = max(best, (d - start).days)
        else:
            start = None
    return best / 30.44


def combine(curves: list[pd.Series]) -> pd.Series:
    idx = curves[0].index
    for c in curves[1:]:
        idx = idx.union(c.index)
    return sum(c.reindex(idx).ffill().bfill() for c in curves)


def wrap(eq: pd.Series, trades: int, tax: float) -> dict:
    m = metrics(eq, trades)
    m["tax"] = tax
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    m["net_cagr"] = ((m["final"] - tax) / INITIAL) ** (1 / years) - 1
    m["dd_months"] = dd_months(eq)
    return m


# --------------------------------------------------------------------- arranjos


def run_separate_sleeves(start: str, end: str, refresh: int) -> dict:
    """Cinco contas independentes, cada uma um `LiquidSleeve` com capital/5."""
    panels = full_panels()
    cfg = BacktestConfig(initial_capital=INITIAL / 5, lot_size=1)
    curves, n, tax = [], 0, 0.0
    for i in range(5):
        s = LiquidSleeve(sleeve_index=i, sleeve_count=5, refresh_months=refresh)
        r = run_bt(panels, s, cfg, start=start, end=end)
        curves.append(r.equity_curve)
        n += len(r.trades)
        tax += tax_on(r.trades)
    return wrap(combine(curves), n, tax)


def run_one_account(start: str, end: str, refresh: int) -> dict:
    """`liquid_sleeves5` — o robo operavel, uma conta com caixa compartilhado."""
    cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1)
    r = run_bt(full_panels(), LiquidSleeves5(refresh_months=refresh), cfg, start=start, end=end)
    return wrap(r.equity_curve, len(r.trades), tax_on(r.trades))


def run_flow(start: str, end: str) -> dict:
    """`liquid_flow5` — universo continuo com banda de rank, sem cadencia."""
    from strategy.liquid_flow5 import LiquidFlow5

    cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1)
    r = run_bt(full_panels(), LiquidFlow5(), cfg, start=start, end=end)
    return wrap(r.equity_curve, len(r.trades), tax_on(r.trades))


def run_test_rig(start: str, end: str) -> dict:
    """V2_5contas do `run_safety_rolling.py` — universo montado FORA, congelado."""
    tickers = liquid_universe(start, 20)
    cfg = BacktestConfig(initial_capital=INITIAL / 5, lot_size=1)
    curves, n, tax = [], 0, 0.0
    for group in split_sleeves(tickers, 5):
        u = {t: panel(t) for t in group}
        u[BENCHMARK] = panel(BENCHMARK)
        r = run_bt(u, DipTop1Portfolio(), cfg, start=start, end=end)
        curves.append(r.equity_curve)
        n += len(r.trades)
        tax += tax_on(r.trades)
    return wrap(combine(curves), n, tax)


def ibov(start: str, end: str) -> dict:
    c = panel(BENCHMARK)["close"].loc[start:end].dropna()
    eq = INITIAL * c / c.iloc[0]
    return wrap(eq, 0, 0.0)


# ------------------------------------------------------------------------- H1


def check_universe(start: str) -> tuple[list[str], list[str]]:
    """Universo do arranjo de teste vs o que o robo monta sozinho na mesma data."""
    external = liquid_universe(start, 20)
    panels = full_panels()
    s = LiquidSleeve(sleeve_index=0, sleeve_count=1, refresh_months=12)
    # Historico COMPLETO, como o engine faz (`engine_portfolio.py:75` chama
    # `initialize(raw_panels, ibov)` antes de recortar a janela). Passar o
    # painel ja recortado daria 252 pregoes de aquecimento em branco e o robo
    # apareceria sem universo nenhum — que foi o primeiro resultado deste teste.
    s.initialize(panels, panels[BENCHMARK])
    elig = s._eligible
    d = elig.index[elig.index.searchsorted(pd.Timestamp(start))]
    internal = [t for t in elig.columns if bool(elig.at[d, t])]
    return external, internal


def main() -> None:
    print("\nVALIDACAO DOS ROBOS liquid_sleeve / liquid_sleeves5")
    print(f"5 janelas fechadas de 5 anos | R$ {INITIAL:,.0f} | CAGR liquido de IR {IR*100:.0f}%\n")

    print("H1 — o universo que o ROBO monta sozinho bate com o do arranjo de teste?")
    print(f"  {'janela':>10s} {'iguais':>7s} {'so no teste':>32s} {'so no robo':>32s}")
    for s, _ in WINDOWS:
        ext, int_ = check_universe(s)
        inter = set(ext) & set(int_)
        only_e = sorted(set(ext) - set(int_))
        only_i = sorted(set(int_) - set(ext))
        fmt = lambda xs: ",".join(x.replace(".SA", "") for x in xs) or "-"
        print(f"  {s[:7]:>10s} {len(inter):>4d}/20 {fmt(only_e):>32s} {fmt(only_i):>32s}")

    print("\nH2/H3/H4 — resultado por janela (CAGR liquido de IR / MaxDD)\n")
    arranjos = {
        "arranjo de teste (V2)": lambda s, e: run_test_rig(s, e),
        "5 contas, refresh 5 anos": lambda s, e: run_separate_sleeves(s, e, 60),
        "5 contas, refresh anual": lambda s, e: run_separate_sleeves(s, e, 12),
        "liquid_sleeves5 (1 conta)": lambda s, e: run_one_account(s, e, 12),
        "liquid_flow5 (sem cadencia)": lambda s, e: run_flow(s, e),
        "IBOV": lambda s, e: ibov(s, e),
    }

    hdr = f"{'arranjo':28s} " + "".join(f"| {s[2:7]:>14s} " for s, _ in WINDOWS) + "|  pior   mediana"
    print(hdr)
    print("-" * len(hdr))

    store: dict[str, list[dict]] = {}
    for label, fn in arranjos.items():
        rows = [fn(s, e) for s, e in WINDOWS]
        store[label] = rows
        nets = [m["net_cagr"] for m in rows]
        cells = "".join(f"| {m['net_cagr']*100:6.1f}% {m['max_dd']*100:6.0f}% " for m in rows)
        print(f"{label:28s} {cells}| {min(nets)*100:5.1f}%  {np.median(nets)*100:5.1f}%", flush=True)

    print("\n" + "=" * 118)
    print(f"{'arranjo':28s} {'CAGR med':>9s} {'CAGR pior':>10s} {'MaxDD pior':>11s} "
          f"{'submerso(m)':>12s} {'pior 12m':>9s} {'jan. neg':>9s} {'trades':>7s}")
    print("=" * 118)
    for label, rows in store.items():
        nets = [m["net_cagr"] for m in rows]
        print(f"{label:28s} {np.median(nets)*100:8.2f}% {min(nets)*100:9.2f}% "
              f"{min(m['max_dd'] for m in rows)*100:10.1f}% "
              f"{max(m['dd_months'] for m in rows):11.0f} "
              f"{min(m['worst_12m'] for m in rows)*100:8.1f}% "
              f"{sum(1 for x in nets if x < 0):5d} de {len(nets)} "
              f"{int(np.median([m['trades'] for m in rows])):7d}")

    ib = store["IBOV"]
    gates_target = {
        "G1 pior CAGR liq > 0": lambda r: min(m["net_cagr"] for m in r) > 0,
        "G2 pior MaxDD > -45%": lambda r: min(m["max_dd"] for m in r) > -0.45,
        "G3 CAGR med >= IBOV": lambda r: np.median([m["net_cagr"] for m in r]) >= np.median(
            [m["net_cagr"] for m in ib]),
        "G5 pior 12m > -35%": lambda r: min(m["worst_12m"] for m in r) > -0.35,
    }
    print("\nPORTOES DE SEGURANCA")
    print(f"{'arranjo':28s} " + "".join(f"{g:>22s}" for g in gates_target))
    for label, rows in store.items():
        if label == "IBOV":
            continue
        print(f"{label:28s} " + "".join(
            f"{('PASSA' if fn(rows) else 'falha'):>22s}" for fn in gates_target.values()))


if __name__ == "__main__":
    main()
