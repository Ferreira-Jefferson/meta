"""Confere se o `tick_size` que a ESTRATEGIA usa bate com o tick REAL do ativo.

O buraco (achado 2026-08-26): a familia `gremah` recebe `tick_size` no
construtor com default fixo --

    def __init__(self, symbol="PMAM3", tick_size: float = 0.01, ...)

-- e NENHUM chamador o sobrescreve. `registry.py::get_daytrade_robot` instancia
`cls(symbol=symbol)` e pronto; `run_backtest.py`, `run_backtest_ticks.py` e os
dois sweeps tambem. Enquanto isso, o `IntradayCostModel` recebe o tick REAL
lido do terminal (`config_for(..., trade_tick_size=econ.trade_tick_size)`).

Ou seja: existem DOIS `tick_size` no sistema, um real e um presumido, e nada
force os dois a baterem. Hoje eles coincidem porque as 10 acoes calibradas
negociam de centavo em centavo -- mas isso e' coincidencia de calendario, nao
invariante. Se a B3 mudar o tick de um papel (ou se alguem calibrar um simbolo
que nao negocie em centavo), a estrategia passa a calcular alvo e stop numa
unidade que nao existe no book, e o backtest infla em silencio.

Isso importa mais do que parece porque o alvo desses robos vive NO PISO de 1
tick (`max(1, round(...))`): a unidade errada nao desloca o alvo um pouco, ela
o desloca inteiro.

Sai com codigo != 0 se algum simbolo divergir, para poder virar portao de CI.

Uso:
    python scripts/daytrade/check_tick_size_sync.py
    python scripts/daytrade/check_tick_size_sync.py --symbol PMAM3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _geometria_comum import MOTORES, SIMBOLOS, classe_do_motor  # noqa: E402
from market_data_intraday.mt5_source import symbol_economics  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", action="append", choices=list(SIMBOLOS), default=None)
    args = parser.parse_args()
    symbols = args.symbol or list(SIMBOLOS)

    print(f"{'simbolo':<10}{'motor':<8}{'estrategia':>14}{'terminal':>14}   veredito")
    print("-" * 62)

    divergencias = 0
    indisponiveis = 0
    for symbol in symbols:
        econ = symbol_economics(symbol)
        if econ is None:
            indisponiveis += 1
            print(f"{symbol:<10}{'-':<8}{'-':>14}{'-':>14}   SEM LEITURA (terminal MT5 aberto?)")
            continue
        real = float(econ.trade_tick_size)
        for motor in MOTORES:
            strat = classe_do_motor(motor)(symbol=symbol)
            presumido = float(strat.tick_size)
            bate = abs(presumido - real) < 1e-12
            if not bate:
                divergencias += 1
            print(f"{symbol:<10}{motor:<8}{presumido:>14.8f}{real:>14.8f}   "
                  f"{'ok' if bate else 'DIVERGE'}")

    print("")
    if indisponiveis:
        print(f"{indisponiveis} simbolo(s) sem leitura do terminal -- verificacao INCOMPLETA.")
    if divergencias:
        print(f"{divergencias} divergencia(s): a estrategia calcula alvo/stop numa unidade "
              "que nao e' o tick do ativo.")
        sys.exit(1)
    if indisponiveis:
        sys.exit(2)
    print("Todos os simbolos batem: o tick presumido pela estrategia e' o tick real do ativo.")


if __name__ == "__main__":
    main()
