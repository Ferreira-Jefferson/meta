# -*- coding: utf-8 -*-
"""Escada de capital para um COMECO FRIO dentro do trecho OOS (2026-06-15 a
2026-09-11, 64 pregoes) -- e' o teste que decide de verdade, porque um
deploy NOVO de capital comeca frio, nao com o colchao acumulado do IS.

Complementa `win_orb_port_2026_09_11.py`: aquele mostrou que a caminhada
CONTINUA (IS+OOS, sem reset) sobrevive a R$250 porque o IS lucrativo
constroi colchao ANTES do trecho fraco comecar -- exatamente o vies que
`wdo_orb.py` ja documenta na propria janela do WDO@ ("a caminhada REAL de
caixa... travou com R$375 na 1a semana e meia... so' sobreviveu a janela OOS
INTEIRA com capital de R$500"). Aqui mede-se a MESMA pergunta.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from win_orb_port_2026_09_11 import (  # noqa: E402
    range_abertura_ticks, monta_estrategia, roda, br,
)


def main() -> None:
    from backtest.intraday.report import cabecalho, linha, linha_de_resultado, maxdd_brl
    from backtest.intraday.profiles import OOS_CUTOFF
    from market_data_intraday.storage import load_m1

    m1_full = load_m1("WIN@").sort_index()
    ranges = range_abertura_ticks(m1_full)
    p25, p75 = ranges.quantile([.25, .75])
    stop_min, stop_max = int(round(p25)), int(round(p75))

    cutoff = pd.Timestamp(OOS_CUTOFF, tz="UTC")
    m1_oos = m1_full[m1_full.index >= cutoff]
    dias_oos = sorted(set(m1_oos.index.date))
    print(f"OOS: {len(dias_oos)} pregoes ({dias_oos[0]} a {dias_oos[-1]})\n")

    strat = monta_estrategia(stop_min, stop_max, entrada_ttl_bars=15)

    print("=" * 78)
    print("ESCADA DE CAPITAL -- COMECO FRIO NO OOS, fila ZERO, M1")
    print("=" * 78)
    print(cabecalho())
    escada = [250.0, 375.0, 500.0, 750.0, 1000.0, 1500.0, 2000.0, 3000.0,
              4000.0, 6000.0]
    for cap in escada:
        res = roda(m1_oos, strat, cap, queue_ent=0.0, queue_sai=0.0)
        li = linha_de_resultado(f"cap R${br(cap,0)}", res, cap)
        equity = res.equity_curve
        caixa_min = float(equity.min()) if equity is not None and not equity.empty else float("nan")
        print(linha(li) + f"   caixa_min={br(caixa_min)}")


if __name__ == "__main__":
    main()
