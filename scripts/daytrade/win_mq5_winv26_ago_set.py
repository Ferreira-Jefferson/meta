"""Simula mt5/Win.mq5 (padroes do EA) em WINV26 M1, agosto (validacao) e setembro (refino)/2026.
Sinal: M5 fechada (vela inteira fora da WMA34 + SMMA34 do lado oposto); entra na abertura da M5 seguinte.
Alvo dinamico 600 (teto=inicial=600, entao fixo), stop 300, trailing 100/60. Dentro de uma barra M1 o stop vale antes do alvo.
Custo: 5 pts/op + 2 pts de slippage no stop (premissa do backtest de origem). R$0,20/pt, 1 contrato."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
import MetaTrader5 as mt5
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from core.indicators import lwma, smma
sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))
from win_ema8_wma8_sim_m1 import simular

assert mt5.initialize()
rows = []
for d0 in pd.date_range("2026-07-01", "2026-10-02", freq="5D"):
    r = mt5.copy_rates_range("WINV26", mt5.TIMEFRAME_M1, d0.to_pydatetime(), (d0 + pd.Timedelta(days=5)).to_pydatetime())
    if r is not None and len(r): rows.append(pd.DataFrame(r))
m1 = pd.concat(rows).drop_duplicates("time")
m1.index = pd.to_datetime(m1["time"], unit="s"); m1 = m1.sort_index()[["open","high","low","close"]].astype(float)
print("M1 WINV26:", m1.index.min(), m1.index.max(), len(m1), flush=True)
m5 = m1.resample("5min").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()
e, w = smma(m5.close, 34), lwma(m5.close, 34)
s5 = pd.Series(np.where((m5.low > w) & (e < w), 1, np.where((m5.high < w) & (e > w), -1, 0)), index=m5.index)
s5[e.isna() | w.isna()] = 0
for mes, papel in (("2026-09", "refino"), ("2026-08", "validacao")):
    x = m1[m1.index.strftime("%Y-%m") == mes].copy()
    x["sinal"] = pd.Series(s5.values, index=s5.index + pd.Timedelta(minutes=5)).reindex(x.index).fillna(0).astype(int)
    x["troca"] = False; x["abre5"] = x.index.minute % 5 == 0
    t = simular(x, 300, 600)
    if t.empty: print(mes, papel, "sem trades"); continue
    print(f"{mes} ({papel}): trades={len(t)} liquido R$ {t.rs.sum():.2f} win%={100*(t.rs>0).mean():.1f} pregoes={t.dia.nunique()}/{x.index.normalize().nunique()} motivos={t.mot.value_counts().to_dict()}", flush=True)
