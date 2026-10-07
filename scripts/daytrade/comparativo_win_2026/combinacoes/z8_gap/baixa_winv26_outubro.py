"""Z8: completa os dados do WINV26 ate' 05/10/2026 para o esperado no Testador de 01/10 a 05/10.

- M1: z_padrao/m1_WINV26.parquet (ate' 02/10) + M1 do WINV26 de 05/10 tirado do MT5 (dia inteiro, nunca range
  estreito) -> z8_gap/m1_WINV26_ate_0510.parquet.
- Ticks: data/cache_win_ticks/WINV26 vai ate' 01/10; 02/10 e 05/10 vem do MT5 (COPY_TICKS_ALL, dia inteiro) e ficam em
  z8_gap/ticks_WINV26/<dia>.pkl, no mesmo formato do cache (time_msc, bid, ask, last, volume, flags).
"""
from datetime import datetime, timezone
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

AQUI = Path(__file__).resolve().parent
ZP = AQUI.parent / "z_padrao"
SYM = "WINV26"

assert mt5.initialize(), "abra o terminal do MT5"
mt5.symbol_select(SYM, True)


def dia_utc(d):
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


m = pd.read_parquet(ZP / "m1_WINV26.parquet")
r = mt5.copy_rates_range(SYM, mt5.TIMEFRAME_M1, dia_utc(pd.Timestamp("2026-10-05")), dia_utc(pd.Timestamp("2026-10-06")))
n = pd.DataFrame(r)
n.index = pd.to_datetime(n["time"], unit="s")
n = n[n.index.date == pd.Timestamp("2026-10-05").date()][["open", "high", "low", "close", "tick_volume", "real_volume"]]
mm = pd.concat([m, n])
mm = mm[~mm.index.duplicated(keep="first")].sort_index()
mm.to_parquet(AQUI / "m1_WINV26_ate_0510.parquet")
print("M1 05/10:", len(n), n.index.min(), n.index.max(), "| total", len(mm), mm.index.max(), flush=True)

out = AQUI / "ticks_WINV26"
out.mkdir(exist_ok=True)
for d in ("2026-10-02", "2026-10-05"):
    t0 = pd.Timestamp(d)
    t = mt5.copy_ticks_range(SYM, dia_utc(t0), dia_utc(t0 + pd.Timedelta(days=1)), mt5.COPY_TICKS_ALL)
    x = pd.DataFrame(t)[["time_msc", "bid", "ask", "last", "volume", "flags"]]
    x = x[pd.to_datetime(x.time_msc, unit="ms").dt.date == t0.date()]
    x.to_pickle(out / f"{d}.pkl")
    print(d, len(x), "ticks,", int((x["last"] > 0).sum()), "com last;", pd.to_datetime(x.time_msc.min(), unit="ms"),
          "->", pd.to_datetime(x.time_msc.max(), unit="ms"), flush=True)
mt5.shutdown()
