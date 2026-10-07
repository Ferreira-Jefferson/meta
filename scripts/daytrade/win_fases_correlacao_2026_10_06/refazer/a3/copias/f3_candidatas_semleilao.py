import sys as _sy; _sy.path[:0] = [r'C:\Users\Jeffe\Documents\study\meta\scripts\daytrade', r'C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\win_fases_correlacao_2026_10_06\refazer\a3\copias']
"""f3 candidatas congeladas (so' 2026 foi rodado). Cada funcao: (ano, dados_m30) -> resumo de rodar_janelas.
  ST_H1_SAIDA : sai tambem quando o Supertrend(10,3) em H1 (so' barras H1 fechadas) esta' contra a posicao.
  ADX_DI_ENTRADA : so' entra com DI+>DI- (compra) / DI->DI+ (venda), ADX/DI(14) Wilder em M30, vela do sinal fechada.
  COMBO : as duas juntas."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import f3_feat_semleilao as X

X.ativar()
W = X.W


def _run(ano, dados, ent=None, sai=None):
    return W.rodar_janelas(ano, dados=dados,
                           extra=X.F(*ent) if ent else None,
                           saida_extra=X.S(*sai) if sai else None)[1]


def st_h1_saida(ano, dados_m30):
    return _run(ano, dados_m30, sai=("st_h1", 10, 3))


def adx_di_entrada(ano, dados_m30):
    return _run(ano, dados_m30, ent=("adx_di", "di", 0))


def combo(ano, dados_m30):
    return _run(ano, dados_m30, ent=("adx_di", "di", 0), sai=("st_h1", 10, 3))


CANDIDATAS = {"ST_H1_SAIDA": st_h1_saida, "ADX_DI_ENTRADA": adx_di_entrada, "COMBO": combo}
