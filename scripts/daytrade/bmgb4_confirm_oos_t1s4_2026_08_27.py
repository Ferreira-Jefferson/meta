"""Confirmacao OOS -- UMA passada -- do candidato T1/E1/S4 achado na grade
`alvo_stop_grid_2026_08_27.py --symbol BMGB4` (484 celulas, IN-SAMPLE,
capital MINIMO REAL do ativo -- `capital_minimo_brl`, portao ligado).

Candidato, congelado ANTES de olhar o OOS: BMGB4 / m1, alvo=1 espaco=1 stop=4,
IS R$ 1.214,12 liquido contra R$ 990,14 da producao dinamica (vol-adapt
k=0,05/s=8,0), capital inicial R$ 658,00 -- +22,6%.

(Um candidato ANTERIOR, T1/E1/S6, tinha vencido uma 1a versao desta grade que
usava capital de teste arbitrario de R$50.000 com o portao desligado --
descartado sem chegar a esta confirmacao, ver `feedback_capital_inicial_
nunca_arbitrario` na memoria: capital errado pode mudar qual celula vence.)

Protocolo do repo (mesmo de `confirm_oos_ticks.py`): parametro se escolhe no
IN-SAMPLE, o OUT-OF-SAMPLE confirma UMA vez. Reprovado = descarte, sem
segunda tentativa.

Uso:
    python scripts/daytrade/bmgb4_confirm_oos_t1s4_2026_08_27.py --unlock-oos "MOTIVO"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

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

SYMBOL = "BMGB4"
ALVO, ESPACO, STOP = 1, 1, 4


def _rodar(profile, bars, econ, strat, preco_ref, label):
    config = config_for(
        profile, trade_tick_value=econ.trade_tick_value, trade_tick_size=econ.trade_tick_size,
        target_fills_as_maker=strat.target_fills_as_maker, preco_atual=preco_ref,
    )
    result = run_intraday_backtest(bars, strat, config)
    return linha_de_resultado(label, result, capital_minimo_brl(preco_ref))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unlock-oos", required=True,
                        help="motivo da passada unica -- fica no registro do split")
    parser.add_argument("--econ-cache", default=None)
    args = parser.parse_args()

    cache = Path(args.econ_cache) if args.econ_cache else ROOT / "data" / "_economics_cache.json"
    econ = carregar_economics([SYMBOL], cache)[SYMBOL]
    profile = PROFILES[SYMBOL]

    bars = load_m1(SYMBOL)
    if bars.empty:
        print(f"{SYMBOL}: sem dado local")
        return
    bars = bars.loc[bars.index >= pd.Timestamp(REGIME_START[SYMBOL], tz="UTC")]

    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    locked = LockedBars(bars, split)
    is_bars = locked.in_sample()
    locked.unlock(args.unlock_oos)
    oos_bars = locked.out_of_sample()

    rotulo_atual = "atual (vol-adapt k=0,05/s=8,0)"
    rotulo_novo = f"ticks T{ALVO} E{ESPACO} S{STOP}"

    for nome, janela in (("IN-SAMPLE", is_bars), ("OUT-OF-SAMPLE", oos_bars)):
        if janela.empty:
            print(f"\n{SYMBOL} {nome}: janela vazia")
            continue
        preco_ref = float(janela.iloc[0]["close"])
        precos = janela["close"]
        print(f"\n=== {SYMBOL} / motor=m1 — {nome} ===")
        print(f"    {len(janela)} registros, {janela.index.min()} -> {janela.index.max()}")
        print(f"    preco: min R$ {num_br(float(precos.min()))} | "
              f"mediana R$ {num_br(float(precos.median()))} | "
              f"max R$ {num_br(float(precos.max()))}   "
              f"(capital inicial R$ {num_br(capital_minimo_brl(preco_ref))})")

        linhas = [
            _rodar(profile, janela, econ, Gremah(symbol=SYMBOL), preco_ref, rotulo_atual),
            _rodar(profile, janela, econ,
                   Gremah(symbol=SYMBOL, profit_ticks=ALVO, spacing_ticks=ESPACO,
                          stop_ticks=STOP),
                   preco_ref, rotulo_novo),
        ]
        print(cabecalho())
        for item in linhas:
            print(linha(item), flush=True)


if __name__ == "__main__":
    main()
