"""Confirmacao OOS -- UMA passada -- da geometria em ticks escolhida no IS.

Protocolo do repo: parametro se escolhe no IN-SAMPLE, e o OUT-OF-SAMPLE
confirma UMA vez. Reprovado no OOS = descarte, sem segunda tentativa (ver os
precedentes CMIN3, BBDC3, EQTL3, EUCA4). Este script existe para que essa
passada seja explicita, com a lista de candidatos FIXA no codigo -- e nao um
`run_backtest.py --unlock-oos` disparado com parametro digitado na hora, que
convida a "tentar mais um".

CANDIDATOS, congelados em 2026-08-26 ANTES de qualquer leitura do OOS. Os dois
sao o melhor liquido da grade de 48 celulas
(`sweep_gremah_ticks_independentes.py`, alvo x espacamento x stop
independentes) rodada no IS:

    PMAM3 / tick : T1 E1 S2  (IS R$ 867,61 contra R$ 792,99 da calibracao atual)
    PMAM3 / m1   : T1 E1 S4  (IS R$ 624,04 contra R$ 559,45 da calibracao atual)

MOTIVO da passada: a PMAM3 caiu de ~R$0,55 (mediana do IS) para ~R$0,14, e
nesse preco a calibracao percentual COLAPSA -- alvo, espacamento e stop viram
1 tick cada, sem diferenca entre arriscar e ganhar (ver
`mapa_geometria.py`). A geometria em ticks nao depende do preco, mas o IS nao
contem nenhum dado a R$0,14 para dizer se ela funciona la. A janela OOS
(13/06 em diante) contem. E' exatamente a pergunta que o OOS serve para
responder, e por isso vale gasta-lo.

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
    ("PMAM3", "tick", 1, 1, 2),
    ("PMAM3", "m1", 1, 1, 4),
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
