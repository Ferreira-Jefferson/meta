"""Roda a `GremahTick` (porte tick a tick da gremah, ver `strategy/daytrade/
lab/gremah_tick.py`) contra o tick a tick salvo localmente
(`backfill_ticks.py`), no MESMO regime de preco e split IS/OOS ja declarados
para o M1 do simbolo (`backtest.intraday.profiles.PROFILES`) -- comparar
maca com maca com o resultado M1 exige o mesmo recorte de tempo.

EXPLORATORIO: `GremahTick` ainda usa a calibracao (profit_pct/stop_multiplier)
medida em M1 como PONTO DE PARTIDA, nunca recalibrada em tick -- ver o aviso
no topo de `gremah_tick.py`.

Uso:
    python scripts/daytrade/run_backtest_ticks.py --symbol PMAM3
    python scripts/daytrade/run_backtest_ticks.py --symbol PMAM3 --unlock-oos "motivo explicito"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import PROFILES, config_for  # noqa: E402
from market_data_intraday.mt5_source import symbol_economics  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from market_data_intraday.tick_storage import load_ticks  # noqa: E402
from strategy.daytrade.lab.gremah_tick import GremahTick  # noqa: E402

#: Mesmo regime de preco declarado em `backtest/intraday/profiles.py` para o
#: M1 de cada simbolo (`_equity_profile(regime_start, ...)`) -- duplicado
#: aqui porque `profiles.py` so' guarda essa data dentro do texto de
#: `frozen_note`, nunca como campo separado. Ver a docstring de
#: `_equity_profile` para o porque do corte (profit_pct vira TICKS, o mesmo
#: percentual e' outro alvo em outro preco).
REGIME_START = {
    "PMAM3": "2025-12-16",
    "KLBN4": "2025-09-02",
    "CSAN3": "2025-09-22",
    "DASA3": "2025-09-11",
    "PCAR3": "2025-08-21",
    "CLSC4": "2025-05-12",
    "KLBN3": "2025-03-10",
    "GRND3": "2025-09-05",
    "LPSB3": "2022-12-20",
    "BMGB4": "2025-06-04",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, choices=sorted(PROFILES))
    parser.add_argument(
        "--unlock-oos", default=None, metavar="MOTIVO",
        help="so passar apos decidir isto DELIBERADAMENTE — destrava o trecho out-of-sample",
    )
    args = parser.parse_args()
    profile = PROFILES[args.symbol]

    ticks = load_ticks(args.symbol)
    if ticks.empty:
        print(f"[run_backtest_ticks] sem dado local para {args.symbol!r} — rode backfill_ticks.py primeiro")
        return

    regime_start = pd.Timestamp(REGIME_START[args.symbol], tz="UTC")
    ticks = ticks.loc[ticks.index >= regime_start]
    if ticks.empty:
        print(f"[run_backtest_ticks] {args.symbol}: tick salvo comeca depois do regime_start "
              f"({regime_start.date()}) -- nada para rodar ainda.")
        return
    bars = ticks_to_degenerate_bars(ticks)

    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
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
        print(f"[run_backtest_ticks] nao consegui ler symbol_economics de {args.symbol!r} — terminal MT5 aberto?")
        return

    strategy = GremahTick(symbol=args.symbol)
    config = config_for(
        profile,
        trade_tick_value=econ.trade_tick_value,
        trade_tick_size=econ.trade_tick_size,
        target_fills_as_maker=strategy.target_fills_as_maker,
        # Capital do teste = minimo real do simbolo no preco do primeiro
        # negocio rodado -- ver a docstring de
        # `IntradayBacktestConfig.initial_capital`.
        preco_atual=float(run_bars.iloc[0]["close"]),
    )
    costs = config.costs

    print(f"[run_backtest_ticks] {label}: {len(run_bars)} ticks, {run_bars.index.min()} -> {run_bars.index.max()}")
    print(f"[run_backtest_ticks] custo: point_value_brl={costs.point_value_brl} "
          f"fee_round_trip_brl={costs.fee_round_trip_brl} ({profile.fee_note}) "
          f"quantidade_default={profile.default_quantity}")

    result = run_intraday_backtest(run_bars, strategy, config)

    print(f"[run_backtest_ticks] {len(result.trades)} trade(s)")
    for k, v in result.metrics.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
