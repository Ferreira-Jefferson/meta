"""VALIDACAO 2025 de stop/alvo — rodada UMA vez, 2026-10-06. Lista congelada antes
de tocar 2025: baseline v2.01 + 2 candidatas de stop (d1) + 3 de alvo (d2)."""
import sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI)); sys.path.insert(0, str(AQUI.parent))
import win_cinco_medias as wcm
wcm.ARQUIVOS[2025] = "WIN@_M1_202412020900_202510311824.csv"
wcm.FIM_DADOS[2025] = "2025-10-01"
import d1_candidatas as d1, d2_candidatas as d2

for ano in (2026, 2025):
    d = wcm.carregar(ano)
    print(ano, "BASELINE v2.01", wcm.rodar_janelas(ano, dados=d)[1], flush=True)
    for n, f in d1.CANDIDATAS.items():
        print(ano, n, f(ano, d.copy()), flush=True)
    dv = wcm.colunas_volume(d)
    for n, f in d2.CANDIDATAS.items():
        print(ano, n, f(ano, dv.copy()), flush=True)
