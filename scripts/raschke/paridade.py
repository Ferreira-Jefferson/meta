"""Imprime os SINAIS do Python no mesmo formato do EA (`LogSinais=true`) para
comparar com o Journal do Testador do MT5.

Uso: python -m scripts.raschke.paridade WINV26 H1 ANTI "modo=stoch;recuo=1" 2026.04.15 2026.10.01
Formato:  SINAL 2026.05.04 10:00 lado=1 entrada=... stop=...   (hora = INICIO da barra do sinal)
"""
from __future__ import annotations
import sys
import pandas as pd
from . import dados, nucleo, varredura as v


def main() -> None:
    sym, tf, setup, params, ini, fim = sys.argv[1:7]
    csv = dados.RAIZ / "data" / "wdo-mt5" / "WINV26_M1_202604151210_202610011824.csv"
    base = dados._csv_mt5(csv)
    base = base[(base.index.hour * 60 + base.index.minute) < 18 * 60 + 20]
    rule = {"M5": "5min", "M15": "15min", "H1": "1h"}[tf]
    d = base if tf == "M1" else dados._resample(base, rule)
    bph = {"M5": 12, "M15": 4, "H1": 1}[tf]
    b, idx = dados.para_barras(d, True, bph)
    fn, _, _ = v.GRADES[setup]
    kw = {}
    for kv in params.split(";"):
        k, val = kv.split("=")
        kw[k] = val if k == "modo" else (float(val) if "." in val else int(val))
    for o in fn(b, 5.0, **kw):
        t = idx[o.i]
        if pd.Timestamp(ini.replace(".", "-")) <= t <= pd.Timestamp(fim.replace(".", "-")):
            print(f"SINAL {t:%Y.%m.%d %H:%M} lado={o.lado} entrada={o.entrada:.4f} stop={o.stop:.4f}")


if __name__ == "__main__":
    main()
