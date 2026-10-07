"""Baixa do MT5 a base do comparativo WIN 2026: M1 do WIN$N (preco cru do contrato principal, grade de 5 pts)
de 2025-10-01 a 2026-10-05 e os ticks reais do WIN$N de cada pregao (existem a partir de 2026-02-20).

Por que WIN$N e nao WIN@: no MT5 da Rico as barras M1 do WIN@ vem AJUSTADAS (80% dos precos fora da grade de 5
pts antes da ultima rolagem; 10/06 abre 176154 contra 169265 negociado), enquanto os ticks do WIN@ vem crus.
O WIN$N e' cru nos dois e o tick de 10/06 09:02 (169265) bate com a abertura da M1 dele.

Ticks: o WIN$N so' traz `last` (bid=ask=0). Guardamos (time_msc, last, volume) compactados: tick com o mesmo
`last` do anterior e no MESMO minuto e' fundido (volume somado) -- nao muda nenhum disparo de stop/limite.
"""
import sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import numpy as np, pandas as pd
import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parents[3]
DADOS = ROOT / "data" / "comparativo_win_2026"
TK = DADOS / "ticks"
SIMB = "WIN$N"


def utc(d, h=0, m=0):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)


def main():
    assert mt5.initialize(), mt5.last_error()
    mt5.symbol_select(SIMB, True)
    TK.mkdir(parents=True, exist_ok=True)
    partes, d0, fim = [], date(2025, 10, 1), date(2026, 10, 6)
    while d0 < fim:  # dia a dia: janela estreita no copy_rates_range ja' devolveu horario errado
        r = mt5.copy_rates_range(SIMB, mt5.TIMEFRAME_M1, utc(d0), utc(d0 + timedelta(days=1)))
        if r is not None and len(r):
            partes.append(pd.DataFrame(r))
        d0 += timedelta(days=1)
    m1 = pd.concat(partes).drop_duplicates("time")
    m1["time"] = pd.to_datetime(m1.time, unit="s")
    m1 = m1.set_index("time").sort_index()[["open", "high", "low", "close", "tick_volume", "real_volume"]]
    m1.to_parquet(DADOS / "m1_WIN$N.parquet")
    print("M1", len(m1), m1.index[0], m1.index[-1], flush=True)
    dias = sorted({d for d in m1.index.date if d >= date(2026, 1, 1)})
    for d in dias:
        arq = TK / f"{d}.npz"
        if arq.exists():
            continue
        t0 = time.time()
        r = mt5.copy_ticks_range(SIMB, utc(d, 8, 0), utc(d, 19, 0), mt5.COPY_TICKS_ALL)
        if r is None:
            print(d, "ERRO", mt5.last_error(), flush=True); continue
        if len(r) == 0:
            print(d, "sem ticks", flush=True); continue
        x = pd.DataFrame(r)[["time_msc", "last", "volume"]]
        x = x[x["last"] > 0]
        mn = x.time_msc // 60000
        novo = (x["last"].ne(x["last"].shift())) | (mn.ne(mn.shift()))
        g = novo.cumsum()
        y = x.groupby(g).agg(time_msc=("time_msc", "first"), last=("last", "first"), volume=("volume", "sum"))
        np.savez_compressed(arq, t=y.time_msc.to_numpy(np.int64), p=y["last"].to_numpy(np.int64), v=y.volume.to_numpy(np.int64))
        print(d, len(r), "->", len(y), f"{time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
