"""Paridade EA x simulador Python.

Uso:
  1) rode o EA `Qullamaggie` no Testador do MT5 (D1, mesmo símbolo/período, modelo "Cada tick
     baseado em ticks reais", capital >= o do script) com os MESMOS inputs que estão em
     PARAMS abaixo. Ao terminar, o EA grava `qm_trades_<SIMBOLO>.csv` em
     %APPDATA%\\MetaQuotes\\Terminal\\Common\\Files.
  2) python scripts/qullamaggie/qm_parity.py HASH11 2022-01-01 2026-09-30
     -> puxa as MESMAS barras D1 da Rico, simula em Python e compara trade a trade:
        data de entrada, preço de entrada, data e preço de saída.

Leitura: divergência de PREÇO no mesmo dia é esperada (o Python decide entre barra-diária
pessimista; o testador usa ticks). Divergência de DATA de entrada = regra diferente = bug.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from qm_core import QmParams, make_arrays, trades_for_symbol   # noqa: E402

RICO = r"C:\Program Files\Rico - MetaTrader 5\terminal64.exe"
COMMON = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\Common\Files")

# = defaults dos inputs do EA (mudou um, mude o outro)
PARAMS = QmParams()


def bars_from_mt5(sym: str, ini: str, fim: str) -> pd.DataFrame:
    import MetaTrader5 as mt5
    assert mt5.initialize(RICO), mt5.last_error()
    mt5.symbol_select(sym, True)
    r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 6000)
    mt5.shutdown()
    d = pd.DataFrame(r)
    d["date"] = pd.to_datetime(d["time"], unit="s").dt.normalize()
    d = d.set_index("date")
    d["volume"] = d["real_volume"].where(d["real_volume"] > 0, d["tick_volume"])
    return d[["open", "high", "low", "close", "volume"]]


def main():
    sym, ini, fim = sys.argv[1], sys.argv[2], sys.argv[3]
    df = bars_from_mt5(sym, ini, fim)
    a = make_arrays(df)
    py = [t for t in trades_for_symbol(a, PARAMS, "breakout")
          if np.datetime64(ini) <= a["date"][t["e"]] <= np.datetime64(fim)]
    rows = [dict(ent=str(a["date"][t["e"]])[:10], p_ent=t["entry"], sai=str(a["date"][t["x"]])[:10],
                 motivo=t["reason"], ret=t["ret"]) for t in py]
    pyd = pd.DataFrame(rows)
    print(f"Python: {len(pyd)} trades em {sym} {ini}..{fim}")
    print(pyd.to_string(index=False) if len(pyd) else "(nenhum)")
    f = os.path.join(COMMON, f"qm_trades_{sym}.csv")
    if not os.path.exists(f):
        print(f"\nSem {f}: rode o EA no testador primeiro.")
        return
    ea = pd.read_csv(f, sep=";")
    ea["data"] = pd.to_datetime(ea["time"]).dt.strftime("%Y-%m-%d")
    entradas = ea[ea["entry"] == 0][["data", "price"]].rename(columns={"data": "ent", "price": "ea_ent"})
    saidas = ea[ea["entry"] == 1].groupby("data").price.last().reset_index().rename(
        columns={"data": "sai", "price": "ea_sai"})
    print(f"\nEA: {len(entradas)} entradas, {len(saidas)} dias com saída")
    m = pyd.merge(entradas, on="ent", how="outer", indicator=True)
    print(m.to_string(index=False))
    both = (m["_merge"] == "both").sum()
    print(f"\nentradas casadas por DATA: {both} de {len(pyd)} (Python) / {len(entradas)} (EA)")
    if both:
        diff = (m["p_ent"] / m["ea_ent"] - 1).abs().dropna()
        print(f"diferença média de preço de entrada: {diff.mean() * 100:.3f}%")


if __name__ == "__main__":
    main()
