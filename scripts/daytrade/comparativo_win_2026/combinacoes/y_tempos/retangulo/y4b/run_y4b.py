"""Y4b: python run_y4b.py <tf_min> <2026|2022_2025> <aj|orig|prova>
aj = ajustes=True (RetTF) -> trades/rettf_M{tf}_{per}.csv ; orig/prova = ajustes=False (prova/ ou trades/ret_...)."""
import os, sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
BASE = AQUI.parents[3]
tf, per, modo = int(sys.argv[1]), sys.argv[2], sys.argv[3]
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
import port_ret_tf_v2 as P
aj = modo == "aj"
ea = P.roda(verbose=False, tf=tf, limite_equity=(0.0 if (modo == "prova" and per == "2026") else -1e18), ajustes=aj)
out = AQUI / ("prova" if modo == "prova" else "trades")
out.mkdir(exist_ok=True)
f = out / (f"{'rettf' if aj else 'ret'}_M{tf}_{per}.csv")
pd.DataFrame(ea.trades, columns=dados.COLUNAS).to_csv(f, index=False)
print(f"M{tf} {per} {modo} ops={len(ea.trades)} liq={sum(t['rs'] for t in ea.trades):.2f} parou={ea.parou} -> {f}", flush=True)
