"""60 meses WIN@D, simulador M1 do HTML (simular_canal de win_mq5_winv26_setembro_html.py, extraido por ast: o script e' top-level e
nao importavel) com o sinal da base (win_c1_filtros_forward.prepara/sinal) +- filtro EMA. Uso: python sim60_m1.py check"""
import ast, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_c1_filtros_forward as ff
import sim60
SRC = (Path(__file__).resolve().parents[1] / "win_mq5_winv26_setembro_html.py").read_text(encoding="utf-8")
_g = dict(np=np, pd=pd, CUSTO=5.0, SLIP=2.0, R=0.20, SEM_ENTRADA=17 * 60 + 30, ZERAR=17 * 60 + 50)
for n in ast.parse(SRC).body:
    if isinstance(n, ast.FunctionDef) and n.name == "simular_canal":
        exec(compile(ast.Module([n], []), "simular_canal", "exec"), _g)
simular_canal = _g["simular_canal"]

def preparar(m1=None):
    m1 = sim60.carregar() if m1 is None else m1
    b = ff.prepara(ff.reamostra(m1, 5))
    return m1, b

def rodar(m1, b, m15=True, ema=None, modo="close"):
    sg = sim60.sinal(b, m15, ema, modo)
    x = m1.copy(); desl = b.index + pd.Timedelta(minutes=5)
    x["sinal"] = pd.Series(sg.values, index=desl).reindex(x.index).fillna(0).astype(int)
    x["abre5"] = x.index.minute % 5 == 0
    for col, serie in (("verde", b.smma), ("roxa", b.wma), ("fech", b.close), ("fatr", b.atr)):
        x[col] = pd.Series(serie.values, index=desl).reindex(x.index)
    x["onda"] = 0
    return simular_canal(x, "roxa", 0.0, 0, "sempre", folga_atr=0.6, esticada=(2.5, 0.75))

if __name__ == "__main__":
    m1, b = preparar()
    for m15 in (False, True):
        t = rodar(m1, b, m15); print("m15", m15, ff.metricas(t.rs.to_numpy()), flush=True)
