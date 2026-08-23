"""Passo 3 da calibracao da `gremah_tick` (ver o aviso no topo de
`strategy/daytrade/lab/gremah_tick.py`): varredura fina de profit_pct x
stop_multiplier, so' dentro do regime de preco e so' ate' OOS_CUTOFF -- os
MESMOS 4 passos que produziram `gremah._CALIBRATION_BY_SYMBOL` (M1), agora
repetidos em tick em vez de herdar o numero.

Capital do teste = R$100 (nao R$20k): medido nesta mesma conversa que o
capital do backtest afeta o TAMANHO das posicoes (`_lotes_por_realocacao`),
que por sua vez afeta com que frequencia uma perda estoura o orcamento FIXO
de perda diaria (`capital_minimo_brl`-based, independente do capital do
teste) -- R$20k gera posicoes desproporcionais ao proprio limite de risco
do dia. R$100 e' o capital real declarado pelo dono (ver memoria
`capital_real_100_mes`).

So' IN-SAMPLE aqui -- a confirmacao OOS e' UMA passada so', manual, depois
de escolher o par (ver `run_backtest_ticks.py --unlock-oos`).

Uso:
    python scripts/daytrade/sweep_gremah_tick.py --symbol PMAM3
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

# Mesmo regime de preco declarado para o M1 do simbolo (`run_backtest_ticks.py`
# duplica a mesma tabela -- ver a docstring la para o porque).
REGIME_START = {
    "PMAM3": "2025-12-16", "KLBN4": "2025-09-02", "CSAN3": "2025-09-22",
    "DASA3": "2025-09-11", "PCAR3": "2025-08-21", "CLSC4": "2025-05-12",
    "KLBN3": "2025-03-10", "GRND3": "2025-09-05", "LPSB3": "2022-12-20",
    "BMGB4": "2025-06-04",
}

CAPITAL_TESTE = 100.0
PROFIT_PCT_GRID = [0.0015, 0.0020, 0.0025, 0.0032, 0.0040, 0.0050, 0.0060]
STOP_MULTIPLIER_GRID = [5.0, 8.0, 10.0, 15.0, 20.0, 30.0]
MIN_TRADES_CONFIAVEL = 30  # abaixo disso, marca como amostra pequena demais


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, choices=sorted(PROFILES))
    args = parser.parse_args()
    symbol = args.symbol
    profile = PROFILES[symbol]

    ticks = load_ticks(symbol)
    if ticks.empty:
        print(f"[sweep] sem dado local para {symbol!r} — rode backfill_ticks.py primeiro")
        return
    regime_start = pd.Timestamp(REGIME_START[symbol], tz="UTC")
    ticks = ticks.loc[ticks.index >= regime_start]
    bars = ticks_to_degenerate_bars(ticks)

    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    run_bars = LockedBars(bars, split).in_sample()
    print(f"[sweep] {symbol} IN-SAMPLE: {len(run_bars)} ticks, "
          f"{run_bars.index.min()} -> {run_bars.index.max()}\n")

    econ = symbol_economics(symbol)
    if econ is None:
        print(f"[sweep] nao consegui ler symbol_economics de {symbol!r} — terminal MT5 aberto?")
        return

    rows = []
    for profit_pct in PROFIT_PCT_GRID:
        for stop_multiplier in STOP_MULTIPLIER_GRID:
            strat = GremahTick(symbol=symbol, profit_pct=profit_pct, stop_multiplier=stop_multiplier)
            config = config_for(profile, trade_tick_value=econ.trade_tick_value,
                                 trade_tick_size=econ.trade_tick_size,
                                 target_fills_as_maker=strat.target_fills_as_maker,
                                 initial_capital=CAPITAL_TESTE)
            result = run_intraday_backtest(run_bars, strat, config)
            n = len(result.trades)
            final = CAPITAL_TESTE + sum(t.pnl_brl for t in result.trades)
            m = result.metrics
            rows.append({
                "profit_pct": profit_pct, "stop_multiplier": stop_multiplier,
                "n_trades": n, "final": final,
                "win_rate": m.get("win_rate"), "profit_factor": m.get("profit_factor"),
                "max_drawdown": m.get("max_drawdown"),
                "confiavel": n >= MIN_TRADES_CONFIAVEL,
            })

    rows.sort(key=lambda r: r["final"], reverse=True)
    print(f"{'profit_pct':>10} {'stop_x':>6} {'trades':>7} {'final':>12} {'win_rate':>9} "
          f"{'pf':>6} {'maxdd':>8} {'confiavel':>9}")
    for r in rows:
        print(f"{r['profit_pct']*100:>9.2f}% {r['stop_multiplier']:>6.0f} {r['n_trades']:>7} "
              f"R${r['final']:>10.2f} {r['win_rate']*100:>8.1f}% {r['profit_factor']:>6.2f} "
              f"{r['max_drawdown']*100:>7.1f}% {'sim' if r['confiavel'] else 'NAO (<'+str(MIN_TRADES_CONFIAVEL)+')':>9}")


if __name__ == "__main__":
    main()
