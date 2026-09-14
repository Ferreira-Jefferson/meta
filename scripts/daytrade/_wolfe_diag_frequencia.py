"""Diagnostico RAPIDO (vetorizado, sem motor): quantos pivos/ondas de Wolfe
aparecem no historico inteiro do WDO@, por limiar de zigzag -- so' para
decidir se vale a pena rodar o motor caro (tick a tick) depois."""
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from ondas_wolfe_wdo_lab import ZigzagCausal, detectar_onda

t0 = time.time()
df = pd.read_parquet(RAIZ / "data" / "raw_ticks" / "WDO_A_.parquet", columns=["last"])
print("parquet lido dt=", time.time() - t0, "ticks=", len(df), flush=True)

m1 = df["last"].resample("1min").ohlc().dropna()
print("M1 pronto dt=", time.time() - t0, "barras=", len(m1), flush=True)

n_dias = len(set(m1.index.date))
print("dias:", n_dias, flush=True)

for limiar_ticks in (12.0, 16.0, 20.0, 24.0, 32.0, 40.0, 60.0):
    limiar = limiar_ticks * 0.5
    zz = ZigzagCausal(limiar)
    n_ondas = 0
    n_ondas_long = 0
    n_ondas_short = 0
    dia_atual = None
    for ts, row in m1.iterrows():
        d = ts.date()
        if d != dia_atual:
            zz.reset()
            dia_atual = d
        pivo = zz.update(ts, row["high"], row["low"])
        if pivo is not None:
            onda = detectar_onda(zz.pivos)
            if onda is not None:
                n_ondas += 1
                if onda.direcao == "long":
                    n_ondas_long += 1
                else:
                    n_ondas_short += 1
    print(f"limiar={limiar_ticks:5.1f}t  ondas_validas={n_ondas:5d}  "
          f"long={n_ondas_long:4d} short={n_ondas_short:4d}  "
          f"ondas/dia={n_ondas/n_dias:.3f}  dt={time.time()-t0:.1f}s", flush=True)
