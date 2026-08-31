"""Pedido do dono (2026-08-31): "entao muda pra 16" -- depois de eu mostrar que
T1/E1/S16 nunca trava e sempre fecha positivo na varredura de capital
(`gremah_pmam3_stop16_capital_2026_08_31.py`, historico INTEIRO, IS+OOS
misturados).

Antes de tocar em `_GEOMETRIA_TICKS_BY_SYMBOL["PMAM3"]` (producao), o
protocolo do repo exige checar isso do jeito que decidiu o S4 atual: grade em
IN-SAMPLE primeiro (`sweep_gremah_ticks_independentes.py`), UMA confirmacao
OOS depois -- nunca decidir por um numero que mistura as duas janelas.

Sinal de alerta: a grade original de 48 celulas (`STOP_TICKS_GRID = (2, 4, 8,
15, 25, 40)`) ja incluia um vizinho quase identico do S16 -- o S15 -- e ele
NAO venceu (o vencedor foi T1/E1/S4, e' o que virou producao). Este script
confere isso direto: roda T1/E1/S4 (baseline atual) contra T1/E1/S16 (pedido
do dono) na MESMA janela IN-SAMPLE congelada que gerou aquela decisao -- sem
tocar no OOS ainda. So' se S16 vencer aqui e' que faz sentido gastar a
passada (unica) de confirmacao OOS.

Uso: `python -u scripts/daytrade/pmam3_s16_vs_s4_is_2026_08_31.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _geometria_comum import carregar_economics, carregar_is  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado  # noqa: E402
from strategy.daytrade.base import capital_minimo_brl  # noqa: E402
from strategy.daytrade.lab.gremah import Gremah  # noqa: E402

SYMBOL = "PMAM3"


def _rodar(profile, bars, econ, strat, preco_ref, label):
    config = config_for(
        profile, trade_tick_value=econ.trade_tick_value,
        trade_tick_size=econ.trade_tick_size,
        target_fills_as_maker=strat.target_fills_as_maker, preco_atual=preco_ref,
    )
    result = run_intraday_backtest(bars, strat, config)
    return linha_de_resultado(label, result, capital_minimo_brl(preco_ref))


def main() -> None:
    economics = carregar_economics([SYMBOL], ROOT / "data" / "_economics_cache.json")
    run_bars, profile, preco_ref = carregar_is(SYMBOL, "m1")
    if run_bars.empty:
        print(f"{SYMBOL}: sem dado IS local")
        return

    print(f"=== {SYMBOL} / m1 — IN-SAMPLE (mesma janela congelada da decisao S4) ===")
    print(f"    {len(run_bars)} registros, {run_bars.index.min()} -> {run_bars.index.max()}")
    print(f"    preco referencia (1a barra): R$ {preco_ref:.4f}\n")

    econ = economics[SYMBOL]
    candidatos = [
        (4, "T1 E1 S4 (producao atual)"),
        (15, "T1 E1 S15 (ja estava na grade original de 48, perdeu p/ S4)"),
        (16, "T1 E1 S16 (pedido do dono)"),
    ]
    linhas = []
    for stop, label in candidatos:
        strat = Gremah(symbol=SYMBOL, profit_ticks=1, spacing_ticks=1, stop_ticks=stop)
        linhas.append(_rodar(profile, run_bars, econ, strat, preco_ref, label))

    print(cabecalho())
    for item in linhas:
        print(linha(item), flush=True)

    base, s15, s16 = linhas
    print()
    if s16.liquido_brl > base.liquido_brl:
        delta = (s16.liquido_brl / base.liquido_brl - 1.0) * 100 if base.liquido_brl else float("nan")
        print(f"*** S16 BATE o S4 atual no IS (+{delta:.1f}%) -- justifica gastar a "
              f"passada de confirmacao OOS. ***")
    else:
        print("*** S16 PERDE (ou empata) para o S4 atual no IS -- mesmo destino do S15 "
              "na grade original. NAO gastar a passada de OOS: protocolo do repo e' "
              "descartar aqui, sem repescagem (mesma regra que descartou CMIN3/BBDC3/"
              "EQTL3/EUCA4). ***")


if __name__ == "__main__":
    main()
