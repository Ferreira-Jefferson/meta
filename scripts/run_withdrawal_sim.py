"""Simulacao da politica de saque oficial de `portfolio_dip2_hw40` (janela FULL).

Politica escolhida em 2026-08-17: `FloorSkim(pct=1,0%/mes, piso 55x o capital
inicial, minimo R$1.000)` — ver o registro de decisao no topo de
`src/backtest/withdrawal.py`, com os numeros de todas as alternativas medidas e
descartadas.

Tres curvas:
  1. CARTEIRA        — equity investido (cai no dia do saque; nao e perda de mercado)
  2. CAIXA EXTERNO   — dinheiro sacado, rendendo Selic diaria (serie do BCB)
  3. PATRIMONIO      — (1) + (2). E aqui que o drawdown importa: o que o
                       investidor sente e o patrimonio total, nao a carteira.

Reporta tambem o MaxDD time-weighted (curva reinvestida), que neutraliza os
fluxos de saque e mostra que a ESTRATEGIA nao foi tocada.

Uso:  .venv/Scripts/python.exe scripts/run_withdrawal_sim.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# console do Windows costuma vir em cp1252 e engasga com setas/acentos
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

from backtest.metrics import cagr, calmar, max_drawdown, negative_years, sharpe
from backtest.runner import run as run_dispatch
from backtest.withdrawal import (
    OFFICIAL_FLOOR_MULTIPLE,
    FloorSkim,
    external_cash_curve,
    official_policy,
    reinvested_equity_curve,
)
from core.config import HISTORY_START, BacktestConfig
from market_data.loader import load_universe
from scheduler import latest_common_date
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

INITIAL = 1_000.0            # critério oficial de ranking
LOT = 1


def selic_daily_pct() -> pd.Series:
    """Selic diaria em % ao dia (formato da serie 11 do BCB)."""
    p = Path("data/raw/selic.parquet")
    if not p.exists():
        return pd.Series(dtype=float)
    return pd.read_parquet(p)["valor"]


def variants() -> list[tuple[str, object]]:
    """REF, a politica oficial e a vizinhanca do piso (contexto da escolha)."""
    return [
        ("REF — sem saque", None),
        (f"OFICIAL · 1,0%/mês > {OFFICIAL_FLOOR_MULTIPLE:.0f}k · mín. 1.000", official_policy(INITIAL)),
        ("1,0%/mês > 45k · mín. 1.000", FloorSkim(pct=0.010, floor=45 * INITIAL)),
        ("1,0%/mês > 50k · mín. 1.000", FloorSkim(pct=0.010, floor=50 * INITIAL)),
        ("1,0%/mês > 60k · mín. 1.000", FloorSkim(pct=0.010, floor=60 * INITIAL)),
        ("1,0%/mês > 55k · sem mínimo", FloorSkim(pct=0.010, floor=55 * INITIAL, min_amount=0.0)),
        ("1,0%/mês > 55k · guarda DD 15%", FloorSkim(pct=0.010, floor=55 * INITIAL, dd_guard=0.15)),
    ]


def money(v: float) -> str:
    return f"{v:>14,.0f}".replace(",", ".")


def worst_episode(series: pd.Series) -> tuple[str, float, str, float, float]:
    """Pior episodio de drawdown: (data do topo, topo, data do fundo, fundo, dd)."""
    peak = series.cummax()
    dd = series / peak - 1.0
    trough_date = dd.idxmin()
    peak_val = float(peak.loc[trough_date])
    peak_date = series.loc[:trough_date][series.loc[:trough_date] >= peak_val - 1e-9].index[-1]
    return (pd.Timestamp(peak_date).strftime("%Y-%m-%d"), peak_val,
            pd.Timestamp(trough_date).strftime("%Y-%m-%d"), float(series.loc[trough_date]),
            float(dd.min()))


def main() -> None:
    end = latest_common_date().strftime("%Y-%m-%d")
    start = HISTORY_START
    universe = load_universe()
    config = BacktestConfig(initial_capital=INITIAL, lot_size=LOT)
    selic = selic_daily_pct()

    print(f"\nJanela FULL: {start} → {end} | capital inicial R$ {INITIAL:,.0f} | lote {LOT}")
    print(f"Caixa sacado remunerado pela Selic diaria ({len(selic)} pontos)\n")

    rows = []
    for label, policy in variants():
        result = run_dispatch(universe, DipTop1Portfolio(), config,
                              start=start, end=end, withdrawal_policy=policy)
        eq = result.equity_curve
        events = result.withdrawals
        rate = selic.reindex(eq.index).ffill() if len(selic) else None

        cash_nom = external_cash_curve(events, eq.index, daily_rate_pct=None)
        cash_cdi = external_cash_curve(events, eq.index, daily_rate_pct=rate)
        wealth_nom = eq + cash_nom
        wealth_cdi = eq + cash_cdi
        twr = reinvested_equity_curve(eq, events)

        cut5 = eq.index[-1] - pd.DateOffset(years=5)
        dates = [pd.Timestamp(e.date) for e in events]
        d5 = [d for d in dates if d >= cut5]
        gaps5 = [(d5[i + 1] - d5[i]).days for i in range(len(d5) - 1)] or [0]
        vals = [e.executed for e in events]

        rows.append({
            "label": label,
            "n_saques": len(events),
            "n_saques_5a": len(d5),
            "sacado_nominal": float(sum(vals)),
            "caixa_cdi_final": float(cash_cdi.iloc[-1]),
            "carteira_final": float(eq.iloc[-1]),
            "patrimonio_final": float(wealth_cdi.iloc[-1]),
            "pct_vs_ref": 0.0,
            "cagr_patrimonio": cagr(wealth_cdi),
            "dd_patrimonio": max_drawdown(wealth_cdi),
            "dd_patrimonio_sem_juros": max_drawdown(wealth_nom),
            "dd_carteira": max_drawdown(eq),
            "dd_estrategia_twr": max_drawdown(twr),
            "dd_5a": max_drawdown(wealth_cdi.loc[cut5:]),
            "sharpe_patrimonio": sharpe(wealth_cdi),
            "calmar_patrimonio": calmar(wealth_cdi),
            "neg_years": negative_years(wealth_cdi),
            "menor": min(vals, default=0.0),
            "maior": max(vals, default=0.0),
            "gap5_med": sum(gaps5) / len(gaps5),
            "gap5_max": max(gaps5),
            "custo_saques": float(sum(e.fees_paid for e in events)),
            "shortfall": float(sum(e.shortfall for e in events)),
            "_events": events,
            "_wealth": wealth_cdi,
            "_eq": eq,
        })

    ref_total = rows[0]["patrimonio_final"]
    for r in rows:
        r["pct_vs_ref"] = r["patrimonio_final"] / ref_total - 1.0

    # ---------- tabela principal ----------
    print("=" * 152)
    print(f"{'VARIANTE':38s}{'#SAQ':>5s}{'SACADO':>13s}{'CAIXA+CDI':>13s}"
          f"{'CARTEIRA':>13s}{'PATRIMONIO':>13s}{'vs REF':>9s}{'CAGR':>8s}"
          f"{'DD 5A':>9s}{'DD FULL':>9s}{'DD ESTRAT':>11s}{'CALMAR':>8s}")
    print("=" * 152)
    for r in rows:
        print(f"{r['label']:38s}{r['n_saques']:>5d}"
              f"{money(r['sacado_nominal'])[1:]}{money(r['caixa_cdi_final'])[1:]}"
              f"{money(r['carteira_final'])[1:]}{money(r['patrimonio_final'])[1:]}"
              f"{r['pct_vs_ref']*100:>8.1f}%{r['cagr_patrimonio']*100:>7.1f}%"
              f"{r['dd_5a']*100:>8.2f}%{r['dd_patrimonio']*100:>8.2f}%"
              f"{r['dd_estrategia_twr']*100:>10.2f}%{r['calmar_patrimonio']:>8.2f}")
    print("=" * 152)
    print("DD 5A     = drawdown do patrimonio nos ultimos 5 anos  ← risco prospectivo, o que importa hoje")
    print("DD FULL   = drawdown do patrimonio na janela inteira (ancorado no evento de 2017, carteira em R$18,6 mil)")
    print("DD ESTRAT = drawdown time-weighted, saques neutralizados  ← prova que o robo nao foi tocado")

    # ---------- perfil da renda ----------
    print("\nPerfil da renda e enquadramento na isencao de IR:")
    print(f"  {'VARIANTE':38s}{'#SAQ':>5s}{'5A':>4s}{'MENOR':>10s}{'MAIOR':>10s}"
          f"{'INTERV. MÉD':>13s}{'MAIOR SECA':>12s}{'VENDA NOVA/MÊS':>16s}{'ISENTO?':>9s}")
    for r in rows[1:]:
        por_mes: dict[tuple, float] = {}
        for e in r["_events"]:
            key = (pd.Timestamp(e.date).year, pd.Timestamp(e.date).month)
            por_mes[key] = por_mes.get(key, 0.0) + sum(q * px for _t, q, px in e.liquidated)
        maior_venda = max(por_mes.values()) if por_mes else 0.0
        interv = f"{r['gap5_med']:.0f} dias"
        seca = f"{r['gap5_max']} dias"
        isento = "sim" if maior_venda <= 20_000 else "NAO"
        print(f"  {r['label']:38s}{r['n_saques']:>5d}{r['n_saques_5a']:>4d}"
              f"{money(r['menor'])[4:]:>10s}{money(r['maior'])[4:]:>10s}"
              f"{interv:>13s}{seca:>12s}{money(maior_venda)[2:]:>16s}{isento:>9s}")
    print("  Isencao: R$ 20.000 de VENDAS/mes (Lei 11.033/2004 art. 3, I). Saque em dia de venda do")
    print("  robo nao cria volume novo — a coluna mostra so a venda marginal gerada pelo saque.")

    # ---------- pior episodio ----------
    print("\nPior episodio de drawdown do PATRIMONIO (onde a dor acontece):")
    print(f"  {'VARIANTE':38s}{'TOPO':>12s}{'R$ TOPO':>13s}{'FUNDO':>12s}"
          f"{'R$ FUNDO':>13s}{'DD':>9s}{'% EM CAIXA NO TOPO':>21s}")
    for r in rows:
        pk_d, pk_v, tr_d, tr_v, dd = worst_episode(r["_wealth"])
        cash_at_peak = 0.0
        if r["_events"]:
            cash_series = r["_wealth"] - r["_eq"]
            cash_at_peak = float(cash_series.loc[pd.Timestamp(pk_d)]) / pk_v
        print(f"  {r['label']:38s}{pk_d:>12s}{money(pk_v)[1:]}{tr_d:>12s}{money(tr_v)[1:]}"
              f"{dd*100:>8.1f}%{cash_at_peak*100:>20.1f}%")

    # ---------- ano a ano da politica oficial ----------
    focus = rows[1]
    print(f"\nAno a ano — {focus['label']}:")
    print(f"  {'ANO':>5s}{'SAQUES':>8s}{'SACADO NO ANO':>16s}{'CARTEIRA (dez)':>16s}"
          f"{'CAIXA+CDI (dez)':>17s}{'PATRIMONIO (dez)':>18s}")
    ev_by_year: dict[int, list] = {}
    for e in focus["_events"]:
        ev_by_year.setdefault(pd.Timestamp(e.date).year, []).append(e)
    wealth, eq_focus = focus["_wealth"], focus["_eq"]
    for year, grp in sorted(wealth.groupby(wealth.index.year)):
        evs = ev_by_year.get(int(year), [])
        last_day = grp.index[-1]
        carteira = float(eq_focus.loc[last_day])
        patr = float(grp.iloc[-1])
        print(f"  {year:>5d}{len(evs):>8d}"
              f"{money(sum(e.executed for e in evs))[2:]:>16s}{money(carteira)[2:]:>16s}"
              f"{money(patr - carteira)[1:]:>17s}{money(patr)[0:]:>18s}")

    print(f"\n  Total sacado: R$ {focus['sacado_nominal']:,.0f}".replace(",", "."))
    print(f"  Custo de liquidar para sacar (taxas): R$ {focus['custo_saques']:,.2f}".replace(",", "."))
    if focus["shortfall"] > 0.5:
        print(f"  Nao levantado (voltou para a fila): R$ {focus['shortfall']:,.0f}".replace(",", "."))
    print("\n  Nota: com capital inicial de R$ 1.000, o piso de 55x só é cruzado em set/2020 —")
    print("  os primeiros 10 anos nao tem saque. Operando com capital real, releia o piso como")
    print("  multiplo do aporte (ver 'LEITURA DO PISO' em src/backtest/withdrawal.py).")


if __name__ == "__main__":
    main()
