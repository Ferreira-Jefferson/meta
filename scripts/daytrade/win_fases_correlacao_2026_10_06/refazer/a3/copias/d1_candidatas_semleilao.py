import sys as _sy; _sy.path[:0] = [r'C:\Users\Jeffe\Documents\study\meta\scripts\daytrade', r'C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\win_fases_correlacao_2026_10_06\refazer\a3\copias']
"""Candidatas congeladas D1 (familia STOP) sobre WinCincoMedias v2.01. Escolhidas so com 2026.
Cada funcao: f(ano, dados=None) -> resumo (formato de rodar_janelas). Usa d1_stop.simula (stop a mercado, 1 tick, sem look-ahead).
Parametros EXATOS:
  D1_aperta_N2_k1.0     : stop = dict(aperta=(2, 1.0))            -> apos 2 barras fechadas com trade negativo, stop = entrada -/+ 1,0 x ATR14(M30 na entrada)
  D1_aperta_N2_k1.0_BE1 : stop = dict(aperta=(2, 1.0), be=1.0)    -> idem + break-even (stop = preco de entrada) apos MFE de fechamento >= 1,0 x ATR
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import d1_stop_semleilao as _s
import win_cinco_medias_semleilao as _w


def _roda(ano, dados, stop):
    d = _w.carregar(ano) if dados is None else dados
    if "vrel" not in d.columns:
        d = _w.colunas_volume(d)
    _, resumo = _s.rodar(d, ano, stop=stop)
    return resumo


def d1_aperta_n2_k1(ano=2026, dados=None):
    return _roda(ano, dados, dict(aperta=(2, 1.0)))


def d1_aperta_n2_k1_be1(ano=2026, dados=None):
    return _roda(ano, dados, dict(aperta=(2, 1.0), be=1.0))


CANDIDATAS = {"D1_aperta_N2_k1.0": d1_aperta_n2_k1, "D1_aperta_N2_k1.0_BE1": d1_aperta_n2_k1_be1}
