"""Y2 -- roda port_cinco_tf para UM tempo grafico e UM periodo.
Uso: python roda_y2.py <tf_min> <2022_2025|2026> [saida.csv]
 2022_2025: shim x0b (dados_val continuo, ticks sinteticos 4/M1, ZERAR = min(18:24, fim_dia-1) por dia)
 2026: dados.py real (ZERAR 18:24 fixo, como o original)."""
import os, sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
BASE = AQUI.parents[2]
tf, per = int(sys.argv[1]), sys.argv[2]
saida = Path(sys.argv[3]) if len(sys.argv) > 3 else AQUI / "trades" / f"cinco_M{tf}_{per}.csv"
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(AQUI))
import pandas as pd
if per == "2022_2025":
    os.environ["DADOS_VAL_MODO"] = "continuo"
    sys.path.insert(0, str(BASE / "combinacoes" / "x_fixas" / "x0"))
    import dados_val
    FIM = {d: g.index.max().hour * 60 + g.index.max().minute + 1 for d, g in dados_val._por_dia().items()}
    import types
    class Shim:
        def __getattr__(self, k): return getattr(dados_val, k)
        def ticks(self, dia):
            port.ZERAR = min(18 * 60 + 24, FIM[dia] - 1)
            return dados_val.ticks(dia)
    sys.modules["dados"] = Shim()
    D = dados_val
else:
    import dados as D
import port_cinco_tf as port
print(f"[M{tf} {per}] preparando", flush=True)
P = port.prepara(tf=tf)
tr = port.simular(P, D.INICIO, D.FIM, verbose=False)
saida.parent.mkdir(exist_ok=True, parents=True)
pd.DataFrame(tr, columns=D.COLUNAS).to_csv(saida, index=False)
print(f"[M{tf} {per}] {len(tr)} trades, liq {sum(t['rs'] for t in tr):.2f} -> {saida}", flush=True)
