"""Perguntas v3 = subconjunto das v2 que mudam a decisao da etapa 2 (ablacao real em 340 velas de TREINO; ver ../perguntas_v3.md).
Textos IDENTICOS aos da v2 (nao se reescreveu nada: so se cortou). Gestao: so `v2_g_acao` (a `v2_estrutura_preservada` nao era usada no modo A)."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import perguntas_v2 as pv

IDS_V3 = ["v2_dia_tipo", "v2_preco_vs_ref", "v2_rompe_dia", "v2_seguimento", "v2_lateral_morta", "v2_swing_rompido",
          "v2_perna_esgotada", "v2_tendencia_limpa"]
# estado reduzido (decidido em estado_api.py, treino): ver perguntas_v3.md
ESTADO_N_VELAS = 16
ESTADO_DIARIO_N = 0
ESTADO_H1_DIAS = 0

M3 = [d for d in pv.M if d["id"] in IDS_V3]
QUESTOES_MERCADO_V3 = {d["id"]: pv._q(d["texto"], d["tipo"], d["crit"], pv.SUF) for d in M3}
QUESTOES_FINAIS_A3 = dict(pv.QUESTOES_FINAIS_A)           # acao/stop/alvo/mao; acao manda considerar as respostas da etapa 1
QUESTOES_GESTAO_V3 = {"v2_g_acao": pv.QUESTOES_GESTAO_V2["v2_g_acao"]}
# fusao (1 chamada): perguntas v3 + finais sem a frase das respostas
QUESTOES_FUSAO = {**QUESTOES_MERCADO_V3, **{d["id"]: pv._q(d["texto"], d["tipo"], d["crit"], pv.SUF) for d in pv.FINAIS}}


def texto_respostas(resp):
    return pv.texto_respostas(resp, ids=IDS_V3)
