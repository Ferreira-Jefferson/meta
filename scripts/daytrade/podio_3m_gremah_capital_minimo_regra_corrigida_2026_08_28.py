"""Demonstra o EFEITO de `capital_minimo_so_na_entrada` (motor, 2026-08-28)
no caso que de fato o exercita: `gremah`/`gremah_tick` (PMAM3) com o capital
MINIMO ORIGINAL (R$30, sem o "+R$100" que o dono pediu depois) -- a rodada
onde "pulou 57d"/"pulou 54d" apareceu, porque R$30 e' EXATAMENTE 2x o lote
no preco de referencia (R$0,15, o mais BAIXO da janela de 3 meses) e por
isso falhava o piso de 2x em quase toda sessao mais antiga (preco mais alto).

Roda os MESMOS dois robos, MESMA janela de 3 meses, MESMO capital (R$30),
uma vez com a regra ANTIGA (2x toda sessao) e uma vez com a NOVA
(`capital_minimo_so_na_entrada=True`: 2x so' pra iniciar, 1x depois) --
lado a lado, pra isolar exatamente o que a correcao muda.

Uso: `python -u scripts/daytrade/podio_3m_gremah_capital_minimo_regra_corrigida_2026_08_28.py`
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, num_br, tabela  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from market_data_intraday.tick_storage import load_ticks  # noqa: E402
from strategy.daytrade.base import capital_minimo_brl  # noqa: E402
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

JANELA_INICIO = pd.Timestamp("2026-05-28", tz="UTC")


def _bars_m1(symbol: str) -> pd.DataFrame:
    df = load_m1(symbol).sort_index()
    return df.loc[df.index >= JANELA_INICIO]


def _bars_tick_pmam3() -> pd.DataFrame:
    ticks = load_ticks("PMAM3").sort_index()
    bars = ticks_to_degenerate_bars(ticks)
    return bars.loc[bars.index >= JANELA_INICIO]


def main() -> None:
    bars_tick = _bars_tick_pmam3()
    bars_m1_pmam3 = _bars_m1("PMAM3")
    preco = float(bars_m1_pmam3.iloc[-1]["close"])
    cash = capital_minimo_brl(preco)
    profile = profile_for("PMAM3")
    print(f"[demo] preco ref R${num_br(preco)} -> capital minimo (2x) = R${num_br(cash, 0)}")

    linhas = []
    for regra_nome, so_na_entrada in [("2x toda sessao (antiga)", False),
                                        ("2x so' pra iniciar, 1x depois (nova)", True)]:
        for robo_key, bars in [("gremah_tick", bars_tick), ("gremah", bars_m1_pmam3)]:
            robo = get_daytrade_robot(robo_key)
            cfg = config_for(
                profile, trade_tick_value=0.01, trade_tick_size=0.01,
                target_fills_as_maker=robo.target_fills_as_maker, initial_capital=cash,
            )
            cfg = dataclasses.replace(cfg, capital_minimo_so_na_entrada=so_na_entrada)
            resultado = run_intraday_backtest(bars, robo, cfg)
            pulou = len(resultado.sessoes_puladas_por_capital)
            linhas.append(linha_de_resultado(
                f"{robo_key} [{regra_nome}]", resultado, cash,
                extras={"pulou": f"{pulou}d"},
            ))

    print(f"\n=== gremah/gremah_tick, PMAM3, capital minimo R${num_br(cash, 0)} -- regra antiga vs nova ===")
    print(tabela(linhas, extras=("pulou",)))


if __name__ == "__main__":
    main()
