"""Confirmacao OOS -- UMA passada -- de UM candidato de geometria em ticks
(alvo/espacamento/stop) achado por `alvo_stop_grid_2026_08_27.py`, pra
qualquer simbolo da familia `gremah` (motor M1).

Generaliza `confirm_oos_ticks.py` (que tem a lista de candidatos FIXA no
codigo, de uma rodada ja fechada) pra rodada em andamento (2026-08-27,
"faca isso pra todos os ativos"): cada simbolo vira uma invocacao propria,
o candidato entra por linha de comando em vez de uma tupla nova por rodada.

Protocolo do repo (o mesmo de sempre): parametro se escolhe no IN-SAMPLE
(`alvo_stop_grid_2026_08_27.py`), o OUT-OF-SAMPLE confirma UMA vez.
Reprovado = descarte, sem segunda tentativa -- nao rode este script de novo
pro MESMO (simbolo, alvo, espaco, stop) so' porque o resultado nao agradou.

Capital = `capital_minimo_brl(preco_de_referencia_da_janela)`, portao de
capital LIGADO (`config_for` default pra acao) -- mesma regra do
`alvo_stop_grid_2026_08_27.py` (capital nunca e' um numero de teste
arbitrario, ver `feedback_capital_inicial_nunca_arbitrario` na memoria).

Uso:
    python scripts/daytrade/confirm_oos_candidato_2026_08_27.py \\
        --symbol KLBN4 --alvo 1 --espaco 1 --stop 6 \\
        --unlock-oos "MOTIVO"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _geometria_comum import REGIME_START, carregar_economics  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import PROFILES, config_for  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado, num_br  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.base import capital_minimo_brl  # noqa: E402
from strategy.daytrade.lab.gremah import Gremah  # noqa: E402

import pandas as pd  # noqa: E402


def _rodar(profile, bars, econ, strat, preco_ref, label):
    config = config_for(
        profile, trade_tick_value=econ.trade_tick_value, trade_tick_size=econ.trade_tick_size,
        target_fills_as_maker=strat.target_fills_as_maker, preco_atual=preco_ref,
    )
    result = run_intraday_backtest(bars, strat, config)
    return linha_de_resultado(label, result, capital_minimo_brl(preco_ref))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--alvo", type=int, required=True)
    parser.add_argument("--espaco", type=int, required=True)
    parser.add_argument("--stop", type=int, required=True)
    parser.add_argument("--unlock-oos", required=True,
                        help="motivo da passada unica -- fica no registro do split")
    parser.add_argument("--econ-cache", default=None)
    args = parser.parse_args()

    cache = Path(args.econ_cache) if args.econ_cache else ROOT / "data" / "_economics_cache.json"
    econ = carregar_economics([args.symbol], cache)[args.symbol]
    profile = PROFILES[args.symbol]

    bars = load_m1(args.symbol)
    if bars.empty:
        print(f"{args.symbol}: sem dado local")
        return
    bars = bars.loc[bars.index >= pd.Timestamp(REGIME_START[args.symbol], tz="UTC")]

    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    locked = LockedBars(bars, split)
    is_bars = locked.in_sample()
    locked.unlock(args.unlock_oos)
    oos_bars = locked.out_of_sample()

    rotulo_novo = f"ticks T{args.alvo} E{args.espaco} S{args.stop}"

    for nome, janela in (("IN-SAMPLE", is_bars), ("OUT-OF-SAMPLE", oos_bars)):
        if janela.empty:
            print(f"\n{args.symbol} {nome}: janela vazia")
            continue
        preco_ref = float(janela.iloc[0]["close"])
        precos = janela["close"]
        print(f"\n=== {args.symbol} / motor=m1 — {nome} ===")
        print(f"    {len(janela)} registros, {janela.index.min()} -> {janela.index.max()}")
        print(f"    preco: min R$ {num_br(float(precos.min()))} | "
              f"mediana R$ {num_br(float(precos.median()))} | "
              f"max R$ {num_br(float(precos.max()))}   "
              f"(capital inicial R$ {num_br(capital_minimo_brl(preco_ref))})")

        atual = Gremah(symbol=args.symbol)
        rotulo_atual = (
            f"atual (vol-adapt k={atual.alvo_vol_mult:.2f})" if atual.alvo_por_volatilidade
            else f"atual (ticks {atual.profit_ticks}/{atual.spacing_ticks}/{atual.stop_ticks})"
            if atual.profit_ticks is not None
            else f"atual ({atual.profit_pct*100:.2f}%/{atual.stop_multiplier:.0f}x)"
        )
        linhas = [
            _rodar(profile, janela, econ, atual, preco_ref, rotulo_atual),
            _rodar(profile, janela, econ,
                   Gremah(symbol=args.symbol, profit_ticks=args.alvo, spacing_ticks=args.espaco,
                          stop_ticks=args.stop),
                   preco_ref, rotulo_novo),
        ]
        print(cabecalho())
        for item in linhas:
            print(linha(item), flush=True)


if __name__ == "__main__":
    main()
