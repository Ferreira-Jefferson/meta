"""Baixa barras M1 de um simbolo do MT5 (padrao WIN@D, 5 anos) e grava no MESMO
formato da exportacao manual do MT5 (TSV <DATE> <TIME> <OPEN> ... <SPREAD>) em
data/wdo-mt5/. Pede UM MES inteiro por chamada (janela estreita ja devolveu
barra de horario errado nesses simbolos) e filtra depois.

Uso: python scripts/daytrade/baixa_m1_mt5_csv.py [SIMBOLO] [ANOS] [M1|M5]
Precisa do terminal da Rico aberto e logado.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TERMINAL = r"C:\Program Files\Rico - MetaTrader 5\terminal64.exe"
SIMBOLO = sys.argv[1] if len(sys.argv) > 1 else "WIN@D"
ANOS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
TF = (sys.argv[3] if len(sys.argv) > 3 else "M1").upper()


def main() -> None:
    if not mt5.initialize(path=TERMINAL):
        raise SystemExit(f"mt5: {mt5.last_error()}")
    mt5.symbol_select(SIMBOLO, True)
    fim = datetime.now() + timedelta(days=1)
    ini = (fim - timedelta(days=365 * ANOS)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    partes, cur = [], ini
    while cur < fim:
        prox = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        r = mt5.copy_rates_range(SIMBOLO, getattr(mt5, f"TIMEFRAME_{TF}"), cur, min(prox, fim))
        n = 0 if r is None else len(r)
        print(f"{cur:%Y-%m}: {n} barras", flush=True)
        if n:
            partes.append(pd.DataFrame(r))
        cur = prox
    mt5.shutdown()
    if not partes:
        raise SystemExit(f"nenhuma barra para {SIMBOLO}: {mt5.last_error()}")

    df = pd.concat(partes).drop_duplicates("time").sort_values("time")
    t = pd.to_datetime(df["time"], unit="s")  # relogio do servidor, igual ao export manual
    out = pd.DataFrame({
        "<DATE>": t.dt.strftime("%Y.%m.%d"), "<TIME>": t.dt.strftime("%H:%M:%S"),
        "<OPEN>": df["open"].map("{:.3f}".format), "<HIGH>": df["high"].map("{:.3f}".format),
        "<LOW>": df["low"].map("{:.3f}".format), "<CLOSE>": df["close"].map("{:.3f}".format),
        "<TICKVOL>": df["tick_volume"], "<VOL>": df["real_volume"], "<SPREAD>": df["spread"],
    })
    nome = f"{SIMBOLO}_{TF}_{t.iloc[0]:%Y%m%d%H%M}_{t.iloc[-1]:%Y%m%d%H%M}.csv"
    dest = ROOT / "data" / "wdo-mt5" / nome
    out.to_csv(dest, sep="\t", index=False)
    print(f"{len(out)} barras · {t.iloc[0]} a {t.iloc[-1]} -> {dest}", flush=True)


if __name__ == "__main__":
    main()
