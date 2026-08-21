"""Roda um backtest intrabar contra o dado real salvo localmente,
respeitando o split congelado — por padrao so olha o trecho IN-SAMPLE.

Cada simbolo tem seu proprio `SymbolProfile` (split congelado, custo,
horario de flatten, tamanho de posicao) porque a economia de um instrumento
nao se transfere para outro. `PROFILES` mudou de casa em 2026-08-21 (de aqui
para `backtest/intraday/profiles.py`) porque a operacao ao vivo passou a
precisar dos mesmos numeros — ver a docstring de la para o que foi declarado
e por que.

`--symbol` e `--strategy` sao OBRIGATORIOS: um default aqui roda o backtest
no ativo (ou com o robo) errado sem nenhum sinal de que isso aconteceu.

SPLIT CONGELADO por simbolo, DECLARADO ANTES de testar qualquer hipotese
(ver `backtest.intraday.frozen_split`) — corte nao muda depois de visto.

Uso:
    python scripts/daytrade/run_backtest.py --symbol PMAM3 --strategy gremah
    python scripts/daytrade/run_backtest.py --symbol PMAM3 --strategy orb
    python scripts/daytrade/run_backtest.py --symbol PMAM3 --strategy gremah \\
        --unlock-oos "motivo explicito"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import PROFILES, config_for  # noqa: E402
from market_data_intraday.mt5_source import symbol_economics  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.gremah import Gremah  # noqa: E402
from strategy.daytrade.opening_range_breakout import OpeningRangeBreakout  # noqa: E402

STRATEGIES = {
    "orb": lambda symbol: OpeningRangeBreakout(symbol=symbol),
    "gremah": lambda symbol: Gremah(symbol=symbol),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, choices=sorted(PROFILES))
    parser.add_argument("--strategy", choices=sorted(STRATEGIES), required=True)
    parser.add_argument(
        "--unlock-oos", default=None, metavar="MOTIVO",
        help="so passar apos decidir isto DELIBERADAMENTE — destrava o trecho out-of-sample",
    )
    args = parser.parse_args()
    profile = PROFILES[args.symbol]

    bars = load_m1(args.symbol)
    if bars.empty:
        print(f"[run_backtest] sem dado local para {args.symbol!r} — rode backfill_m1.py primeiro")
        return

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
        print(f"[run_backtest] nao consegui ler symbol_economics de {args.symbol!r} — terminal MT5 aberto?")
        return

    strategy = STRATEGIES[args.strategy](args.symbol)
    config = config_for(
        profile,
        trade_tick_value=econ.trade_tick_value,
        trade_tick_size=econ.trade_tick_size,
        # Vem da ESTRATEGIA: este CLI ficava no default `False` enquanto
        # `scripts/run_live.py` passava `True`, entao o robo validado aqui nao
        # era o robo que operava. Na gremah isso vale a diferenca entre
        # -R$288 e +R$621 no mesmo periodo.
        target_fills_as_maker=strategy.target_fills_as_maker,
    )
    costs = config.costs

    print(f"[run_backtest] {label}: {len(run_bars)} barras, {run_bars.index.min()} -> {run_bars.index.max()}")
    print(f"[run_backtest] custo: point_value_brl={costs.point_value_brl} "
          f"fee_round_trip_brl={costs.fee_round_trip_brl} ({profile.fee_note}) "
          f"quantidade_default={profile.default_quantity}")

    result = run_intraday_backtest(run_bars, strategy, config)

    print(f"[run_backtest] {len(result.trades)} trade(s)")
    for k, v in result.metrics.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
