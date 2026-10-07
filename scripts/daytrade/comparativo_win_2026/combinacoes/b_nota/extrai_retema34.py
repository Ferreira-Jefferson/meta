"""Roda o port do WinRetanguloEma34 (sem salvar em resultados/) so' para registrar, por trade, a distancia do stop e do alvo INICIAL
(0,45L / 0,90L da largura L do retangulo na entrada). Saida: b_nota/retema34_niveis.csv (entrada, stop_pts, alvo0_pts, larg)."""
import sys
from pathlib import Path
AQ = Path(__file__).resolve().parent
BASE = AQ.parents[1]
sys.path.insert(0, str(BASE))
import pandas as pd
import port_retangulo_ema34 as P
reg = []
orig = P.Ea._fecha
def f(self, t, k, px, motivo):
    pos = self.pos
    reg.append(dict(t_ent=pos["t_ent"], entry=pos["entry"], stop_pts=abs(pos["entry"] - pos["stop"]),
                    alvo0_pts=P.ALVO_F * pos["larg_pos"], larg=pos["larg_pos"]))
    return orig(self, t, k, px, motivo)
P.Ea._fecha = f
ea = P.roda(verbose=False)
df = pd.DataFrame(reg); df["n"] = len(ea.trades)
tr = pd.DataFrame(ea.trades)
df["rs"] = tr.rs.values; df["entrada"] = tr.entrada.values; df["motivo"] = tr.motivo.values
df.to_csv(AQ / "retema34_niveis.csv", index=False)
print("ok", len(df), df.rs.sum(), flush=True)
