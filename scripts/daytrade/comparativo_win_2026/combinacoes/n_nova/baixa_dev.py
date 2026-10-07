"""Baixa do MT5 as M1 do WIN$N (cru, grade de 5 pts) de 2021-12-01 a 2025-09-30 -- blocos DEV e VAL da frente N.
Mesmo metodo de ../../baixa_dados.py: dia a dia (janela estreita no copy_rates_range ja' devolveu horario errado).
Saida: data/comparativo_win_2026/m1_WIN$N_2022_2025.parquet. Confere a grade de 5 pontos ao final.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parents[5]
DADOS = ROOT / "data" / "comparativo_win_2026"
SIMB = "WIN$N"


def utc(d):
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def main():
    assert mt5.initialize(), mt5.last_error()
    mt5.symbol_select(SIMB, True)
    partes, d0, fim = [], date(2021, 12, 1), date(2025, 10, 1)
    while d0 < fim:
        r = mt5.copy_rates_range(SIMB, mt5.TIMEFRAME_M1, utc(d0), utc(d0 + timedelta(days=1)))
        if r is not None and len(r):
            partes.append(pd.DataFrame(r))
        if d0.day == 1:
            print(d0, sum(len(p) for p in partes), flush=True)
        d0 += timedelta(days=1)
    m1 = pd.concat(partes).drop_duplicates("time")
    m1["time"] = pd.to_datetime(m1.time, unit="s")
    m1 = m1.set_index("time").sort_index()[["open", "high", "low", "close", "tick_volume", "real_volume"]]
    m1.to_parquet(DADOS / "m1_WIN$N_2022_2025.parquet")
    fora = ((m1[["open", "high", "low", "close"]] % 5) != 0).any(axis=1)
    print("M1", len(m1), m1.index[0], m1.index[-1], "dias", len(set(m1.index.date)),
          "fora da grade de 5:", int(fora.sum()), flush=True)


if __name__ == "__main__":
    main()
