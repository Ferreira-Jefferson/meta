"""Niveis (stop e alvo inicial) do WinRetanguloEma34 no periodo 2024-01..2025-09, como b_nota/extrai_retema34.py faz em 2026
(mesmo monkeypatch do port, sem editar nada) mas com o shim dados_val. Insumo do C12 (resize). Confere com v0/resultados."""
import sys
from pathlib import Path
AQ = Path(__file__).resolve().parent
V0 = AQ.parent / "v0"; BASE = AQ.parents[2]
sys.path.insert(0, str(V0)); sys.path.insert(0, str(BASE))
import dados_val
sys.modules["dados"] = dados_val
import pandas as pd
import port_retangulo_ema34 as P
reg = []
orig = P.Ea._fecha
def f(self, t, k, px, motivo):
    pos = self.pos
    reg.append(dict(t_ent=pos["t_ent"], entry=pos["entry"], stop_pts=abs(pos["entry"] - pos["stop"]), alvo0_pts=P.ALVO_F * pos["larg_pos"], larg=pos["larg_pos"]))
    return orig(self, t, k, px, motivo)
P.Ea._fecha = f
ea = P.roda(verbose=False)
df = pd.DataFrame(reg); tr = pd.DataFrame(ea.trades)
df["rs"] = tr.rs.values; df["entrada"] = tr.entrada.values; df["motivo"] = tr.motivo.values
df.to_csv(AQ / "retema34_niveis_val.csv", index=False)
ref = pd.read_csv(V0 / "resultados" / "WinRetanguloEma34.csv")
same = len(ref) == len(tr) and (ref[["entrada", "saida", "preco_saida", "rs"]].astype(str).values == tr[["entrada", "saida", "preco_saida", "rs"]].astype(str).values).all()
print("niveis", len(df), "ops; identico ao v0/resultados:", same, flush=True)
