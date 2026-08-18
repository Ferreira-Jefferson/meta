"""Sweep de `FloorSkim` — fronteira entre dinheiro sacado, custo e regularidade.

A escolha de piso/percentual não é estatística (não se otimiza piso por
backtest — ele é a declaração de "a partir de quanto eu considero que já ganhei"),
mas a FRONTEIRA é informativa: mostra o que se ganha e o que se perde ao andar na
grade, e onde a regularidade do saque quebra. É a ferramenta para refazer a
escolha com um capital inicial diferente — basta mudar `INITIAL`.

Usa o `min_amount` default de `FloorSkim` (R$ 1.000), igual à política oficial.
O piso escolhido está marcado na saída. Ver o registro de decisão no topo de
`src/backtest/withdrawal.py`.

Uso:  .venv/Scripts/python.exe scripts/run_withdrawal_sweep.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

from backtest.metrics import max_drawdown
from backtest.runner import run as run_dispatch
from backtest.withdrawal import (
    OFFICIAL_FLOOR_MULTIPLE,
    OFFICIAL_PCT,
    FloorSkim,
    external_cash_curve,
)
from core.config import HISTORY_START, BacktestConfig
from market_data.loader import load_universe
from scheduler import latest_common_date
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

INITIAL = 1_000.0
LOT = 1
PCTS = (0.005, 0.0075, 0.010, 0.0125, 0.015)
FLOORS = (30, 40, 45, 50, 55, 60, 70, 80)   # múltiplos do capital inicial


def money(v: float) -> str:
    return f"{v:>12,.0f}".replace(",", ".")


def main() -> None:
    end = latest_common_date().strftime("%Y-%m-%d")
    universe = load_universe()
    config = BacktestConfig(initial_capital=INITIAL, lot_size=LOT)
    selic = pd.read_parquet("data/raw/selic.parquet")["valor"]

    def measure(policy) -> dict:
        res = run_dispatch(universe, DipTop1Portfolio(), config,
                           start=HISTORY_START, end=end, withdrawal_policy=policy)
        eq, evs = res.equity_curve, res.withdrawals
        rate = selic.reindex(eq.index).ffill()
        wealth = eq + external_cash_curve(evs, eq.index, daily_rate_pct=rate)
        cut5 = eq.index[-1] - pd.DateOffset(years=5)
        meses5 = len({(d.year, d.month) for d in eq.loc[cut5:].index})
        n5 = sum(1 for e in evs if pd.Timestamp(e.date) >= cut5)
        return {
            "sacado": sum(e.executed for e in evs),
            "patrimonio": float(wealth.iloc[-1]),
            "carteira": float(eq.iloc[-1]),
            "dd5a": max_drawdown(wealth.loc[cut5:]),
            "n": len(evs), "n5": n5, "meses5": meses5,
            "menor": min((e.executed for e in evs), default=0.0),
            "eq": eq, "evs": evs,
        }

    ref = measure(None)
    ref_dd5 = abs(ref["dd5a"])
    print(f"\nJanela FULL {HISTORY_START} → {end} | REF: patrimônio {money(ref['patrimonio'])} "
          f"| DD5A {ref['dd5a']*100:.2f}%\n")
    print("=" * 118)
    print(f"{'PCT/MÊS':>8s}{'PISO':>8s}{'SACADO':>12s}{'CARTEIRA':>12s}{'PATRIMÔNIO':>13s}"
          f"{'vs REF':>9s}{'DD5A':>9s}{'RAZÃO':>8s}{'R$/R$':>7s}{'SAQUES 5A':>11s}{'MENOR':>10s}")
    print("=" * 118)
    best = None
    for pct in PCTS:
        for mult in FLOORS:
            m = measure(FloorSkim(pct=pct, floor=mult * INITIAL))
            vs = m["patrimonio"] / ref["patrimonio"] - 1.0
            gain = 1.0 - abs(m["dd5a"]) / ref_dd5
            razao = gain / -vs if vs < -1e-9 else float("inf")
            por_real = (ref["patrimonio"] - m["patrimonio"]) / m["sacado"] if m["sacado"] else 0
            oficial = (pct == OFFICIAL_PCT and mult == OFFICIAL_FLOOR_MULTIPLE)
            marca = "  <== OFICIAL" if oficial else ""
            cadencia = f"{m['n5']}/{m['meses5']}"
            print(f"{pct*100:>7.2f}%{mult:>7d}k{money(m['sacado'])}{money(m['carteira'])}"
                  f"{money(m['patrimonio'])}{vs*100:>8.1f}%{m['dd5a']*100:>8.2f}%"
                  f"{razao:>8.2f}{por_real:>7.2f}{cadencia:>11s}"
                  f"{money(m['menor'])[2:]:>10s}{marca}")
            if best is None or m["patrimonio"] > best[1]["patrimonio"]:
                best = ((pct, mult), m)
        print("-" * 118)
    print("SAQUES 5A = meses com saque / meses da janela. Com o mínimo de R$ 1.000 a cadência")
    print("deixa de ser mensal por desenho: parcelas pequenas se somam em saques maiores.")
    if best:
        (pct, mult), m = best
        print(f"\nMaior patrimônio da grade: {pct*100:.2f}%/mês acima de {mult}k → "
              f"{money(m['patrimonio'])} — mas saca só R$ {m['sacado']:,.0f} em {m['n5']} "
              f"meses. Patrimônio máximo é 'não sacar'; a escolha é de preferência "
              f"temporal.".replace(",", "."))

    # ---------- diagnóstico: quando a OFICIAL pula meses ----------
    alvo = measure(FloorSkim(pct=OFFICIAL_PCT, floor=OFFICIAL_FLOOR_MULTIPLE * INITIAL))
    eq, evs = alvo["eq"], alvo["evs"]
    cut5 = eq.index[-1] - pd.DateOffset(years=5)
    pagos = {(pd.Timestamp(e.date).year, pd.Timestamp(e.date).month) for e in evs}
    print(f"\nDiagnóstico da OFICIAL ({OFFICIAL_PCT * 100:.1f}%/mês acima de "
          f"{OFFICIAL_FLOOR_MULTIPLE:.0f}k) — meses SEM saque nos últimos 5 anos:")
    print(f"  {'MÊS':>9s}{'NO 3º PREGÃO':>15s}{'FIM DO MÊS':>13s}{'MOTIVO':>30s}")
    faltas = 0
    for (ano, mes), grp in eq.loc[cut5:].groupby([eq.loc[cut5:].index.year,
                                                  eq.loc[cut5:].index.month]):
        if (ano, mes) in pagos:
            continue
        faltas += 1
        # a decisão olha o equity do 3º pregão do mês, não o do fim
        eq_dec = float(grp.iloc[2]) if len(grp) >= 3 else float(grp.iloc[-1])
        eq_fim = float(grp.iloc[-1])
        motivo = ("carteira sob o piso no dia" if eq_dec <= OFFICIAL_FLOOR_MULTIPLE * INITIAL
                  else "mês com menos de 3 pregões")
        print(f"  {ano}-{mes:02d}{money(eq_dec)[2:]:>15s}{money(eq_fim)[3:]:>13s}{motivo:>30s}")
    print(f"  total: {faltas} meses sem saque de {alvo['meses5']}")


if __name__ == "__main__":
    main()
