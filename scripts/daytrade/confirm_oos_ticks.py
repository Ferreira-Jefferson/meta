"""Confirmacao OOS -- UMA passada -- da geometria em ticks escolhida no IS.

Protocolo do repo: parametro se escolhe no IN-SAMPLE, e o OUT-OF-SAMPLE
confirma UMA vez. Reprovado no OOS = descarte, sem segunda tentativa (ver os
precedentes CMIN3, BBDC3, EQTL3, EUCA4). Este script existe para que essa
passada seja explicita, com a lista de candidatos FIXA no codigo -- e nao um
`run_backtest.py --unlock-oos` disparado com parametro digitado na hora, que
convida a "tentar mais um".

CANDIDATOS, congelados ANTES de qualquer leitura do OOS. Cada um e' o melhor
liquido da grade de 48 celulas do seu par
(`sweep_gremah_ticks_independentes.py`, alvo x espacamento x stop
independentes) no IS.

RODADA 1 -- 2026-08-26, ja GASTA:
    PMAM3 / tick : T1 E1 S2  -> IS +9,4%,  OOS -5,6%   REPROVADO (descartado)
    PMAM3 / m1   : T1 E1 S4  -> IS +11,5%, OOS +26,9%  APROVADO (adotado)

RODADA 2 -- os quatro pares cujo delta de IS passa de ~10%. Esse patamar nao e'
arbitrario: a rodada 1 mediu que um ganho de IS de +9,4% virou perda no OOS,
entao delta menor que isso, numa escolha de melhor-de-48, e' ruido de selecao e
nao vale a janela.

    PCAR3 / tick : T1 E1 S4  (IS R$ 491,14 contra R$ 310,51, +58,2%; e o MaxDD
                              cai de R$166,55 para R$40,74 -- o unico caso em
                              que o ganho aparece sobretudo no RISCO)
    CSAN3 / m1   : T1 E1 S8  (IS R$ 960,71 contra R$ 586,70, +63,7%)
    BMGB4 / tick : T1 E1 S8  (IS R$ 1.636,80 contra R$ 1.310,14, +24,9%)
    KLBN3 / m1   : T1 E1 S4  (IS R$ 1.563,39 contra R$ 1.269,48, +23,2%)

RESSALVA sobre a PCAR3/tick: o IS dela foi medido com `--tail-ticks 300000`
(o IS inteiro tem 874.602 registros e nao cabia em tempo util na grade de 48
celulas). A ESCOLHA do candidato saiu dessa janela capada; a confirmacao abaixo
roda o IS e o OOS INTEIROS. Se o numero de IS aqui nao parecer com o da
varredura, e' por isso, e nao invalida nada -- o que o OOS julga e' o candidato,
nao o IS.

Uso:
    python scripts/daytrade/confirm_oos_ticks.py --unlock-oos "MOTIVO"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _geometria_comum import (  # noqa: E402
    REGIME_START, calibracao_do_motor, carregar_economics, classe_do_motor,
)
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import PROFILES, config_for  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado, num_br  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from market_data_intraday.tick_storage import load_ticks  # noqa: E402
from strategy.daytrade.base import capital_minimo_brl  # noqa: E402

#: (simbolo, motor, alvo, espacamento, stop). FIXO -- ver a docstring.
CANDIDATOS = (
    ("PCAR3", "tick", 1, 1, 4),
    ("CSAN3", "m1", 1, 1, 8),
    ("BMGB4", "tick", 1, 1, 8),
    ("KLBN3", "m1", 1, 1, 4),
)


def _barras(symbol: str, motor: str) -> pd.DataFrame:
    if motor == "m1":
        return load_m1(symbol)
    ticks = load_ticks(symbol)
    return ticks_to_degenerate_bars(ticks) if not ticks.empty else pd.DataFrame()


def _rodar(profile, bars, econ, strat, preco_ref, label):
    config = config_for(
        profile, trade_tick_value=econ.trade_tick_value,
        trade_tick_size=econ.trade_tick_size,
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

    symbols = sorted({c[0] for c in CANDIDATOS})
    cache = Path(args.econ_cache) if args.econ_cache else ROOT / "data" / "_economics_cache.json"
    economics = carregar_economics(symbols, cache)

    for symbol, motor, alvo, espaco, stop in CANDIDATOS:
        profile = PROFILES[symbol]
        bars = _barras(symbol, motor)
        if bars.empty:
            print(f"{symbol}/{motor}: sem dado local")
            continue
        bars = bars.loc[bars.index >= pd.Timestamp(REGIME_START[symbol], tz="UTC")]

        split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
        locked = LockedBars(bars, split)
        is_bars = locked.in_sample()
        locked.unlock(args.unlock_oos)
        oos_bars = locked.out_of_sample()

        Classe = classe_do_motor(motor)
        calib = calibracao_do_motor(motor)[symbol]
        rotulo_atual = f"atual ({calib.profit_pct*100:.2f}%/{calib.stop_multiplier:.0f}x)"
        rotulo_novo = f"ticks T{alvo} E{espaco} S{stop}"

        for nome, janela in (("IN-SAMPLE", is_bars), ("OUT-OF-SAMPLE", oos_bars)):
            if janela.empty:
                print(f"\n{symbol}/{motor} {nome}: janela vazia")
                continue
            preco_ref = float(janela.iloc[0]["close"])
            precos = janela["close"]
            print(f"\n=== {symbol} / motor={motor} — {nome} ===")
            print(f"    {len(janela)} registros, {janela.index.min()} -> {janela.index.max()}")
            print(f"    preco: min R$ {num_br(float(precos.min()))} | "
                  f"mediana R$ {num_br(float(precos.median()))} | "
                  f"max R$ {num_br(float(precos.max()))}   "
                  f"(capital inicial R$ {num_br(capital_minimo_brl(preco_ref))})")

            linhas = [
                _rodar(profile, janela, economics[symbol], Classe(symbol=symbol),
                       preco_ref, rotulo_atual),
                _rodar(profile, janela, economics[symbol],
                       Classe(symbol=symbol, profit_ticks=alvo, spacing_ticks=espaco,
                              stop_ticks=stop),
                       preco_ref, rotulo_novo),
            ]
            print(cabecalho())
            for item in linhas:
                print(linha(item), flush=True)


if __name__ == "__main__":
    main()
