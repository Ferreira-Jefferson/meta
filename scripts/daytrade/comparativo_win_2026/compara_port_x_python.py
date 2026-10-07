# -*- coding: utf-8 -*-
"""Port tick a tick x Python G41 (barra a barra), por mes. Requer ref_python_g41_trades.csv (compara_python_g41.py).
Tres linhas: Python (liquido, com custos do motor), Python bruto (pontos*0,20), port fiel ao .mq5, port com o contador-fantasma do Python."""
import sys
from pathlib import Path
import pandas as pd
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import port_retangulo_ema34 as P, dados  # noqa: E402

py = pd.read_csv(AQUI / "ref_python_g41_trades.csv")
py["pts"] = py.lado * (py.preco_saida - py.preco_entrada); py["bruto"] = py.pts * 0.2
py["mes"] = py.saida.str[:7]
dias = [d for d in dados.dias() if d < pd.Timestamp("2026-10-01").date()]
res = {}
for nome, fant in (("fiel", False), ("fantasma", True)):
    ea = P.roda(dias, verbose=False, py_fantasma=fant)
    df = pd.DataFrame(ea.trades); df["mes"] = df.saida.str[:7]; res[nome] = df
    print(nome, "alvo_marcavel", ea.stats["alvo_marcavel"], flush=True)
t = pd.DataFrame({
    "py_n": py.groupby("mes").size(), "py_liq": py.groupby("mes").rs.sum(), "py_bruto": py.groupby("mes").bruto.sum(),
    "fant_n": res["fantasma"].groupby("mes").size(), "fant_rs": res["fantasma"].groupby("mes").rs.sum(),
    "fiel_n": res["fiel"].groupby("mes").size(), "fiel_rs": res["fiel"].groupby("mes").rs.sum()})
t.loc["TOTAL"] = t.sum()
print(t.round(1).to_string(), flush=True)
# casamento trade a trade (minuto de entrada + lado)
def chave(d, col): return pd.to_datetime(d[col], format="mixed").dt.floor("min").astype(str) + d.lado.astype(str)
py["k"] = chave(py, "entrada")
for nome in ("fantasma", "fiel"):
    d = res[nome]; d["k"] = chave(d, "entrada")
    m = d.merge(py, on="k", suffixes=("_m", "_p"))
    print(f"{nome}: port {len(d)} py {len(py)} casados {len(m)}; motivo igual {(m.motivo_m.replace({'alvo':'target'})==m.motivo_p).mean():.3f}; "
          f"pontos casados port {m.pontos.sum():.0f} py {m.pts.sum():.0f}", flush=True)
