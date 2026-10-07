"""Puxa D1 do terminal Rico (MT5) para data/qullamaggie/<SIMBOLO>.parquet.

Universo: as ações da watchlist (data/raw/*_SA.parquet) + índices/ETFs B3 + cripto B3
(ETFs de Bitcoin e futuro BIT). Só entra o que o MT5 da Rico lista E permite operar
(`trade_mode` != DISABLED) — pedido do dono: o que a corretora não opera, descarta.
"""
from __future__ import annotations
import glob, os, sys
import MetaTrader5 as mt5
import pandas as pd

RICO = r"C:\Program Files\Rico - MetaTrader 5\terminal64.exe"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "data", "qullamaggie")
EXTRA = {
    "indice": ["BOVA11", "SMAL11", "IBOV11", "IVVB11", "DIVO11", "FIND11", "MATB11", "GOVE11",
               "IND@D", "WIN@D"],
    "cripto": ["HASH11", "QBTC11", "BITH11", "BITI11", "BTCI11", "EBIT11", "BITB39", "IBIT39",
               "GBTC11", "NBIT11", "BITC11", "GBIT11", "XBIT11", "BIT@D"],
}

def main():
    assert mt5.initialize(RICO), mt5.last_error()
    os.makedirs(OUT, exist_ok=True)
    acoes = sorted(os.path.basename(f)[:-len("_SA.parquet")] for f in glob.glob(
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw", "*_SA.parquet")))
    jobs = [(s, "acao") for s in acoes] + [(s, k) for k, v in EXTRA.items() for s in v]
    rows = []
    for sym, cls in jobs:
        info = mt5.symbol_info(sym)
        if info is None:
            rows.append((sym, cls, "ausente", 0, "", "")); continue
        mt5.symbol_select(sym, True)
        r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 6000)
        if r is None or len(r) == 0:
            rows.append((sym, cls, "sem_dados", 0, "", "")); continue
        d = pd.DataFrame(r)
        d["date"] = pd.to_datetime(d["time"], unit="s").dt.normalize()
        d = d.set_index("date")[["open", "high", "low", "close", "tick_volume", "real_volume"]]
        d["volume"] = d["real_volume"].where(d["real_volume"] > 0, d["tick_volume"])
        d.to_parquet(os.path.join(OUT, f"{sym.replace('@','_')}.parquet"))
        rows.append((sym, cls, f"trade_mode={info.trade_mode}", len(d), d.index[0].date(), d.index[-1].date()))
    t = pd.DataFrame(rows, columns=["sym", "classe", "status", "barras", "ini", "fim"])
    t.to_csv(os.path.join(OUT, "_universo.csv"), index=False)
    print(t[t.classe != "acao"].to_string())
    a = t[(t.classe == "acao") & (t.barras > 0)]
    print("acoes ok:", len(a), "ausentes:", (t[t.classe == "acao"].barras == 0).sum())
    print(a.barras.describe()); print(a.ini.astype(str).str[:4].value_counts().sort_index().to_string())

main()
