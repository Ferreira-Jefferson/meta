"""Roda um backtest intrabar contra o dado real salvo localmente,
respeitando o split congelado — por padrao so olha o trecho IN-SAMPLE.

Cada simbolo tem seu proprio `SymbolProfile` (split congelado, custo,
horario de flatten, tamanho de posicao) porque futuro (WIN) e acao
(PMAM3) tem economia MUITO diferente — mesmo ponto de preco significa
coisas diferentes, mesmo lote significa coisas diferentes. Ver `PROFILES`
abaixo para o que foi declarado e por que.

SPLIT CONGELADO por simbolo, DECLARADO ANTES de testar qualquer hipotese
(ver `backtest.intraday.frozen_split`) — corte nao muda depois de visto.

Uso:
    python scripts/daytrade/run_backtest.py --symbol WIN@ --strategy orb
    python scripts/daytrade/run_backtest.py --symbol PMAM3 --strategy orb
    python scripts/daytrade/run_backtest.py --symbol PMAM3 --unlock-oos "motivo explicito"
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
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


@dataclass(frozen=True)
class SymbolProfile:
    frozen_cutoff: str
    frozen_note: str
    fee_round_trip_brl: float
    fee_note: str
    session_end_time: time
    default_quantity: int


PROFILES: dict[str, SymbolProfile] = {
    "WIN@": SymbolProfile(
        frozen_cutoff="2026-06-01",
        frozen_note=(
            "corte declarado 2026-08-20 antes de testar qualquer hipotese de day trade; "
            "profundidade real 2025-12-01..2026-08-20 (~8,6 meses); "
            "~6 meses IS (2025-12-01..2026-05-31), ~2,6 meses OOS travado"
        ),
        # Corretagem Rico SEM RLP: R$0,49/contrato executado -> R$0,98 round-trip.
        # Taxa de liquidacao B3 (WIN): R$0,30/contrato executado -> R$0,60
        # round-trip, ANTES do desconto de day trade por ADV (nao aplicado,
        # ADV da conta desconhecido — este numero e' o PIOR CASO).
        # Pesquisado 2026-08-20. Com RLP ativo cairia para R$0,60.
        fee_round_trip_brl=1.58,
        fee_note="Rico, pior caso sem RLP/desconto ADV",
        # Calibrado do proprio dado salvo: fechamento real observado em
        # 177 de 179 pregoes, apos a correcao do fuso do servidor MT5.
        session_end_time=time(21, 24),
        default_quantity=1,
    ),
    "PMAM3": SymbolProfile(
        frozen_cutoff="2025-12-01",
        frozen_note=(
            "corte declarado 2026-08-21 antes de testar qualquer hipotese nesta acao; "
            "profundidade real 2023-04-11..2026-08-20 (~3,4 anos); "
            "~2,6 anos IS (2023-04-11..2025-11-30), ~8,7 meses OOS travado "
            "(mesma data absoluta de corte do perfil WIN@, por simplicidade)"
        ),
        # Lote PADRAO (100 acoes, nao fracionario): corretagem zero nas
        # DUAS leituras conflitantes da tarifa Rico encontradas em
        # 2026-08-21 (a tarifa de R$1,90 e' especifica do FRACIONARIO,
        # nunca se aplica a lote padrao; a leitura mais recente zera tudo).
        # Taxa B3 (negociacao+liquidacao day trade, ~0,025% do valor) sobre
        # ~R$14 de notional (100 acoes a R$0,14) e uma fracao de centavo —
        # arredondada a zero, imaterial nesta escala.
        fee_round_trip_brl=0.0,
        fee_note="lote padrao (100 acoes), corretagem zero + taxa B3 imaterial nesta escala",
        # Calibrado do proprio dado: fechamento mais comum nos pregoes
        # recentes (desde 2026-06-01) e 19:54 UTC — ha um cluster minoritario
        # em 20:54 UTC em todos os anos (provavel leilao de fechamento
        # estendido em dias especificos), mas o regime ATUAL e 19:54.
        session_end_time=time(19, 54),
        default_quantity=100,  # 1 lote padrao
    ),
}

STRATEGIES = {
    "orb": lambda symbol: OpeningRangeBreakout(symbol=symbol),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="WIN@", choices=sorted(PROFILES))
    parser.add_argument("--strategy", choices=sorted(STRATEGIES), default="orb")
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

    costs = FuturesCostModel.from_symbol_info(
        trade_tick_value=econ.trade_tick_value,
        trade_tick_size=econ.trade_tick_size,
        fee_round_trip_brl=profile.fee_round_trip_brl,
    )
    config = IntradayBacktestConfig(
        costs=costs,
        session_end_time=profile.session_end_time,
        default_quantity=profile.default_quantity,
    )
    strategy = STRATEGIES[args.strategy](args.symbol)

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
