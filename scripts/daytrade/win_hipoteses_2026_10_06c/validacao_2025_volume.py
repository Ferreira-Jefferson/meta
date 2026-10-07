"""VALIDACAO 2025 do volume — rodada UMA vez, 2026-10-06. Lista congelada antes de
tocar 2025: baseline v2 (M30) e a unica candidata de volume (c2a), mais o gemeo de
preco dela (mesma regra com range no lugar do volume) como controle declarado.
c1 (volume na entrada) nao congelou nenhuma."""
import sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI)); sys.path.insert(0, str(AQUI.parent))
import win_cinco_medias as wcm
wcm.ARQUIVOS[2025] = "WIN@_M1_202412020900_202510311824.csv"
wcm.FIM_DADOS[2025] = "2025-10-01"
import c2_volume_saida_contexto as c2

def roda(ano, d, saida_fn=None):
    d2 = c2.features(d)
    kw = {} if saida_fn is None else dict(saida_fn=saida_fn, saida_escopo="todos")
    return c2.wcm_rodar(ano, d2, **kw) if hasattr(c2, "wcm_rodar") else _rodar(ano, d2, **kw)

def _rodar(ano, d2, **kw):
    orig = wcm.simula
    wcm.simula = c2.simula
    try:
        return wcm.rodar_janelas(ano, dados=d2, **kw)[1]
    finally:
        wcm.simula = orig

for ano in (2026, 2025):
    d = wcm.carregar(ano)
    base = wcm.rodar_janelas(ano, dados=d)[1]
    print(ano, "BASELINE v2            ", base, flush=True)
    print(ano, "c2a climax volume q90  ", roda(ano, d, c2.fn_climax("v_rel", 0.90, "contra")), flush=True)
    print(ano, "controle: climax range ", roda(ano, d, c2.fn_climax("r_rel", 0.90, "contra")), flush=True)
