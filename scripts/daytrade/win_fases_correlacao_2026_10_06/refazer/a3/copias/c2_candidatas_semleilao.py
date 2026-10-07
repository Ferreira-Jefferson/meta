import sys as _sy; _sy.path[:0] = [r'C:\Users\Jeffe\Documents\study\meta\scripts\daytrade', r'C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\win_fases_correlacao_2026_10_06\refazer\a3\copias']
"""Candidatas congeladas C2 (volume na saida). Uso: from c2_candidatas import CANDIDATAS; CANDIDATAS[nome](ano, dados) -> resumo
(mesmo formato de win_cinco_medias.rodar_janelas, so o resumo). dados = M30 de carregar(ano) (colunas o,h,l,c,v,tv).
Volume so de velas fechadas; normalizacao pelo mesmo horario dos 20 pregoes anteriores; quantil expandido do passado."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import c2_volume_saida_contexto_semleilao as c2
import win_cinco_medias_semleilao as wcm


def _rodar(ano, dados, **kw):
    d = c2.features(dados)
    wcm.simula = c2.simula
    _, resumo = wcm.rodar_janelas(ano, dados=d, **kw)
    return resumo


def c2a_climax_contra_vrel_q90(ano, dados):
    """Vela M30 fechada com volume relativo (v / mediana do mesmo horario, 20 pregoes) >= quantil 90 expandido do
    passado e corpo CONTRA a posicao -> sai a mercado na abertura seguinte (1 tick de deslize). Escopo: todos."""
    return _rodar(ano, dados, saida_fn=c2.fn_climax("v_rel", 0.90, "contra"), saida_escopo="todos")


CANDIDATAS = {"c2a_climax_contra_vrel_q90": c2a_climax_contra_vrel_q90}

if __name__ == "__main__":
    for n, f in CANDIDATAS.items():
        print(n, f(2026, wcm.carregar(2026)))
