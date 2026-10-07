"""Y3: roda port_desloc_tf.py para (tf, periodo). periodo: '2026' (dados.py real) | '2225' (shim x0b continuo + patch da zeragem).
Uso: python run_y3.py <tf> <2026|2225> [saida.csv]"""
import os, sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
BASE = AQUI.parents[2]                    # comparativo_win_2026
tf, per = int(sys.argv[1]), sys.argv[2]
out = Path(sys.argv[3]) if len(sys.argv) > 3 else AQUI / "trades" / f"M{tf}_{per}.csv"
import pandas as pd
if per == "2225":
    os.environ["DADOS_VAL_MODO"] = "continuo"
    sys.path.insert(0, str(AQUI.parents[1] / "x_fixas" / "x0"))
    import dados_val as D
    FIM = {}
    for d, g in D._por_dia().items():
        FIM[d] = g.index.max().hour * 60 + g.index.max().minute + 1
    sys.modules["dados"] = D
else:
    sys.path.insert(0, str(BASE))
    import dados as D
src = (AQUI / "port_desloc_tf.py").read_text(encoding="utf-8")
G = {"__name__": "y3port", "__file__": str(AQUI / "port_desloc_tf.py")}
if per == "2225":
    a = 't_zera = ini + (p["fim_min"] - p["zerar_min"]) * 60000'
    assert src.count(a) == 1
    src = src.replace(a, 't_zera = ini + (min(FIM_DIA[dia], p["fim_min"]) - p["zerar_min"]) * 60000')
    G["FIM_DIA"] = FIM
exec(compile(src, G["__file__"], "exec"), G)
dias, m1 = D.dias(), D.m1()
def gt(d):
    r = D.ticks(d); return r[0], r[1]
tr, saldo, q, dg = G["rodar"](dias, m1, gt, tf=tf)
pd.DataFrame(tr, columns=D.COLUNAS).to_csv(out, index=False)
print(f"M{tf} {per}: {len(tr)} ops, saldo {saldo:.2f}, quebrou {q}, diag {dg}", flush=True)
