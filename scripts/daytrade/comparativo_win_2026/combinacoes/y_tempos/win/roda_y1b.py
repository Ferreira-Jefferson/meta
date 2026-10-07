"""Y1b: wrapper de roda_y1.py para H1..H4 (estende SUP sem tocar port_win_tf.py). Uso: roda_y1b.py <Win|Win_c1> <tf_min> <2026|2225>"""
import os, sys
from datetime import date
from pathlib import Path
AQUI = Path(__file__).resolve().parent
BASE = AQUI.parents[2]
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
SUPB = {60: 180, 120: 360, 180: 720, 240: 720}
p = dict(P.PARAMS_C1 if robo == "Win_c1" else P.PARAMS)
p["tf_min"], p["sup_min"] = tf, SUPB[tf]
out = P.rodar(robo, p, ini, fim, salvar=False, verbose=False)
dst = AQUI / "trades" / f"{robo}_M{tf}_{per}.csv"
pd.DataFrame(out, columns=D.COLUNAS).to_csv(dst, index=False)
print("ok", dst.name, len(out), flush=True)
