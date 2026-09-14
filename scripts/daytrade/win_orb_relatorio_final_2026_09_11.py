# -*- coding: utf-8 -*-
"""Relatorio final da hipotese "ORB no WIN@ com fila propria", no capital
MINIMO que sobrevive ao comeco FRIO no OOS sem zerar (R$750, medido em
`win_orb_oos_escada_2026_09_11.py`) -- IS e OOS, metricas completas."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from win_orb_port_2026_09_11 import (  # noqa: E402
    range_abertura_ticks, monta_estrategia, roda, br, relatorio_detalhado,
)

CAPITAL = 750.0


def main() -> None:
    from backtest.intraday.profiles import OOS_CUTOFF
    from market_data_intraday.storage import load_m1

    m1_full = load_m1("WIN@").sort_index()
    ranges = range_abertura_ticks(m1_full)
    p25, p75 = ranges.quantile([.25, .75])
    stop_min, stop_max = int(round(p25)), int(round(p75))
    strat = monta_estrategia(stop_min, stop_max, entrada_ttl_bars=15)

    cutoff = pd.Timestamp(OOS_CUTOFF, tz="UTC")
    m1_is = m1_full[m1_full.index < cutoff]
    m1_oos = m1_full[m1_full.index >= cutoff]

    res_is = roda(m1_is, strat, CAPITAL, queue_ent=0.0, queue_sai=0.0)
    res_oos = roda(m1_oos, strat, CAPITAL, queue_ent=0.0, queue_sai=0.0)

    relatorio_detalhado(f"IS -- capital {br(CAPITAL,0)} -- fila ZERO", res_is, CAPITAL)
    relatorio_detalhado(f"OOS -- capital {br(CAPITAL,0)} -- fila ZERO", res_oos, CAPITAL)

    # combinado (IS+OOS), so' para o n agregado de win% / IC
    trades_tot = list(res_is.trades) + list(res_oos.trades)
    from win_orb_port_2026_09_11 import wilson_ci
    venc = sum(1 for t in trades_tot if t.pnl_brl > 0)
    n = len(trades_tot)
    lo, hi = wilson_ci(venc, n)
    print(f"\n===== COMBINADO IS+OOS (capital {br(CAPITAL,0)}) =====")
    print(f"n={n}  vencedores={venc}  win%={100*venc/n:.2f}%  "
          f"IC95%=[{100*lo:.2f}% ; {100*hi:.2f}%]")
    perdas = [t for t in trades_tot if t.pnl_brl <= 0]
    ganhos = [t for t in trades_tot if t.pnl_brl > 0]
    ganho_medio = sum(t.pnl_brl for t in ganhos) / len(ganhos)
    perda_media = abs(sum(t.pnl_brl for t in perdas)) / len(perdas)
    be = 100 * perda_media / (ganho_medio + perda_media)
    print(f"breakeven empirico combinado: {be:.2f}%")
    print(f"liquido combinado: R${br(sum(t.pnl_brl for t in trades_tot))}")


if __name__ == "__main__":
    main()
