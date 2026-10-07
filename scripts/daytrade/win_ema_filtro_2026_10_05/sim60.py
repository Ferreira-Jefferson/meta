"""60 meses WIN@D M1: base C1 (win_c1_filtros_forward: prepara/sinal_filtrado/simula, porte do M_core) +- filtro EMA.
Uso: python sim60.py check"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import win_c1_filtros_forward as ff

CSV = ff.ROOT / "data" / "wdo-mt5" / "WIN@D_M1_202110010900_202610011717.csv"

def carregar():
    d = pd.read_csv(CSV, sep="\t")
    d.index = pd.to_datetime(d["<DATE>"] + " " + d["<TIME>"], format="%Y.%m.%d %H:%M:%S")
    d = d.rename(columns={"<OPEN>": "open", "<HIGH>": "high", "<LOW>": "low", "<CLOSE>": "close"})[["open", "high", "low", "close"]].astype(float)
    return ff.prepara_m1(d.sort_index())

def barras():
    m1 = carregar()
    return ff.prepara(ff.reamostra(m1, 5))

def sinal(b, m15=True, ema=None, modo="close"):
    ok = (b.idade <= ff.P["idade_max"]) & (b.dist >= ff.DIST_MIN) & (b.gap < ff.P["gap_max"]) & (b.ext >= ff.P["ext_min"]) \
        & (b.cver >= ff.P["dverde_min"]) & (b.toq <= ff.P["toques_max"])
    if m15: ok &= b.m15ok
    s = b.sig0
    if ema:
        e = b.close.ewm(span=ema, adjust=False, min_periods=ema).mean()
        if modo == "close": f = np.where(s == 1, b.close > e, np.where(s == -1, b.close < e, False))
        else: f = np.where(s == 1, b.low > e, np.where(s == -1, b.high < e, False))
        ok &= pd.Series(f, index=b.index)
    sg = s.where(ok.fillna(False), 0).astype(int)
    sg[np.isin((b.index + pd.Timedelta(minutes=5)).hour, list(ff.P["horas_sem"]))] = 0
    return sg

if __name__ == "__main__":
    b = barras(); print(b.index[0], b.index[-1], len(b), flush=True)
    for m15 in (False, True):
        T, _ = ff.simula(b, sinal(b, m15), b.index[0])
        print("m15", m15, ff.metricas(T.pnl.to_numpy()), flush=True)
