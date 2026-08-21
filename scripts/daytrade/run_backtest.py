"""Roda um backtest intrabar contra o `WIN@` real salvo localmente,
respeitando o split congelado — por padrao so olha o trecho IN-SAMPLE.

SPLIT CONGELADO, DECLARADO ANTES de testar qualquer hipotese (ver
`backtest.intraday.frozen_split`): corte em 2026-06-01. Profundidade real
disponivel e 2025-12-01 a 2026-08-20 (~8,6 meses — achado do plano de
escopo de day trade). 2025-12-01..2026-05-31 (~6 meses) fica IN-SAMPLE
para iterar hipotese; 2026-06-01..2026-08-20 (~2,6 meses) fica TRAVADO
como out-of-sample ate alguem decidir, de forma explicita e documentada,
olhar ali. Este corte nao muda depois de visto.

Uso:
    python scripts/daytrade/run_backtest.py [--strategy orb]
    python scripts/daytrade/run_backtest.py --unlock-oos "motivo explicito"
"""
from __future__ import annotations

import argparse
import sys
from datetime import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.costs import FuturesCostModel  # noqa: E402
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from market_data_intraday.mt5_source import symbol_economics  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.opening_range_breakout import OpeningRangeBreakout  # noqa: E402

FROZEN_CUTOFF = "2026-06-01"
FROZEN_NOTE = (
    "corte declarado 2026-08-20 antes de testar qualquer hipotese de day trade; "
    "~6 meses IS (2025-12-01..2026-05-31), ~2,6 meses OOS travado"
)

# Corretagem/emolumento por round-trip: PLACEHOLDER ZERADO. O usuario nao
# tinha o valor real da tabela de tarifas da Clear no momento desta
# implementacao (2026-08-20) — o MT5 nao expoe isso, e' tarifa da
# corretora, nao do terminal. NAO CONFIAR no resultado como retorno
# LIQUIDO real ate este numero ser calibrado contra a tarifa de verdade.
FEE_ROUND_TRIP_BRL_PLACEHOLDER = 0.0

# Horario de flatten forcado: calibrado do PROPRIO dado salvo (fechamento
# real observado em 177 de 179 pregoes, apos a correcao do fuso do
# servidor MT5) — nao e um chute.
SESSION_END_TIME = time(21, 24)

STRATEGIES = {
    "orb": lambda: OpeningRangeBreakout(),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="WIN@")
    parser.add_argument("--strategy", choices=sorted(STRATEGIES), default="orb")
    parser.add_argument(
        "--unlock-oos", default=None, metavar="MOTIVO",
        help="so passar apos decidir isto DELIBERADAMENTE — destrava o trecho out-of-sample",
    )
    args = parser.parse_args()

    bars = load_m1(args.symbol)
    if bars.empty:
        print(f"[run_backtest] sem dado local para {args.symbol!r} — rode backfill_m1.py primeiro")
        return

    split = declare_frozen_split(cutoff=FROZEN_CUTOFF, note=FROZEN_NOTE)
    locked = LockedBars(bars, split)

    if args.unlock_oos:
        locked.unlock(args.unlock_oos)
        run_bars = locked.out_of_sample()
        label = "OUT-OF-SAMPLE (destravado)"
    else:
        run_bars = locked.in_sample()
        label = "IN-SAMPLE"

    econ = symbol_economics(args.symbol)
    if econ is None:
        print(f"[run_backtest] nao consegui ler symbol_economics de {args.symbol!r} — terminal MT5 aberto?")
        return

    costs = FuturesCostModel.from_symbol_info(
        trade_tick_value=econ.trade_tick_value,
        trade_tick_size=econ.trade_tick_size,
        fee_round_trip_brl=FEE_ROUND_TRIP_BRL_PLACEHOLDER,
    )
    config = IntradayBacktestConfig(costs=costs, session_end_time=SESSION_END_TIME)
    strategy = STRATEGIES[args.strategy]()

    print(f"[run_backtest] {label}: {len(run_bars)} barras, {run_bars.index.min()} -> {run_bars.index.max()}")
    print(f"[run_backtest] custo: point_value_brl={costs.point_value_brl} "
          f"fee_round_trip_brl={costs.fee_round_trip_brl} (PLACEHOLDER — calibrar contra a tarifa real da Clear)")

    result = run_intraday_backtest(run_bars, strategy, config)

    print(f"[run_backtest] {len(result.trades)} trade(s)")
    for k, v in result.metrics.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
