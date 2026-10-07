"""Y4: roda port_ret_tf para (tf, periodo). Uso: python run_tf.py <tf_min> <2026|2022_2025> [prova]
2022_2025: shim x_fixas/x0 (modo continuo, ticks sinteticos 4/M1, sem parar por saldo).
2026: dados.py real. 'prova' = limite_equity original (0.0) e saida em prova/; senao -1e18 e saida em trades/."""
import os, sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
BASE = AQUI.parents[2]
tf, per = int(sys.argv[1]), sys.argv[2]
prova = len(sys.argv) > 3 and sys.argv[3] == "prova"
if per == "2022_2025":
    os.environ["DADOS_VAL_MODO"] = "continuo"
    sys.path.insert(0, str(BASE / "combinacoes" / "x_fixas" / "x0"))
    import dados_val
    sys.modules["dados"] = dados_val
    dados = dados_val
else:
    sys.path.insert(0, str(BASE))
    import dados
sys.path.insert(0, str(AQUI))
import pandas as pd
import port_ret_tf as P
ea = P.roda(verbose=False, tf=tf, limite_equity=(0.0 if (prova and per == "2026") else -1e18))
out = AQUI / ("prova" if prova else "trades")
out.mkdir(exist_ok=True)
f = out / (f"ret_M{tf}_{per}.csv")
pd.DataFrame(ea.trades, columns=dados.COLUNAS).to_csv(f, index=False)
print(f"M{tf} {per} ops={len(ea.trades)} liq={sum(t['rs'] for t in ea.trades):.2f} parou={ea.parou} -> {f}", flush=True)
