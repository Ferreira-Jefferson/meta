"""Stop 'aperta' (apos N velas fechadas no negativo, stop -> entrada -/+ k x ATR):
N de 1 a 10, k em {0,75; 1; 1,5}. Pedido do dono, 2026-10-06. 2025 ja' foi visto
nesta familia (validacao do N=2), entao a coluna 2025 aqui e' informativa."""
import sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI)); sys.path.insert(0, str(AQUI.parent))
import pandas as pd
import win_cinco_medias as wcm
wcm.ARQUIVOS[2025] = "WIN@_M1_202412020900_202510311824.csv"; wcm.FIM_DADOS[2025] = "2025-10-01"
import d1_stop as s

D = {a: wcm.colunas_volume(wcm.carregar(a)) for a in (2026, 2025)}
L = []
for k in (0.75, 1.0, 1.5):
    for N in [0] + list(range(1, 11)):
        lin = dict(k=k, N=N if N else "sem stop")
        for a in (2026, 2025):
            r = s.rodar(D[a], a, stop=None if N == 0 else dict(aperta=(N, k)))[1]
            lin[f"liq {a}"] = r["liquido"]; lin[f"PF {a}"] = r["PF"]; lin[f"pior {a}"] = r["pior"]; lin[f"DD {a}"] = r["maior_DD"]
        L.append(lin); print(lin, flush=True)
        if N == 0 and k != 0.75:
            continue
pd.set_option("display.width", 250)
print(pd.DataFrame(L).drop_duplicates(subset=["N", "liq 2026", "liq 2025"]).to_string(index=False))
