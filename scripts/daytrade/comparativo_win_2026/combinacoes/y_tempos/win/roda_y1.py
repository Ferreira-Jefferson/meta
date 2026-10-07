"""Y1: roda Win / Win_c1 em um tempo grafico. Uso: python roda_y1.py <Win|Win_c1> <tf_min> <2026|2225>
2225 = 2022-01-03..2025-09-30 pelo shim x0 (modo continuo, 4 ticks sinteticos/M1); 2026 = dados.py real."""
import os, sys
from datetime import date
from pathlib import Path
AQUI = Path(__file__).resolve().parent
BASE = AQUI.parents[1]; BASE = AQUI.parents[2]          # comparativo_win_2026
robo, tf, per = sys.argv[1], int(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(BASE))
if per == "2225":
    os.environ["DADOS_VAL_MODO"] = "continuo"
    sys.path.insert(0, str(BASE / "combinacoes" / "x_fixas" / "x0"))
    import dados_val as D
    ini, fim = date(2022, 1, 3), date(2025, 9, 30)
else:
    import dados as D
    ini, fim = date(2026, 1, 2), date(2026, 10, 5)
sys.modules["dados"] = D
sys.path.insert(0, str(AQUI))
import pandas as pd
import port_win_tf as P
p = dict(P.PARAMS_C1 if robo == "Win_c1" else P.PARAMS)
p["tf_min"], p["sup_min"] = tf, P.SUP[tf]
out = P.rodar(robo, p, ini, fim, salvar=False, verbose=False)
dst = AQUI / "trades" / f"{robo}_M{tf}_{per}.csv"
pd.DataFrame(out, columns=D.COLUNAS).to_csv(dst, index=False)
print("ok", dst.name, len(out), flush=True)
