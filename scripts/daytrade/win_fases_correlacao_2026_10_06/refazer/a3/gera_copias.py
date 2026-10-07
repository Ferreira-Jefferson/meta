"""Gera copias *_semleilao das cópias de `simula` da rodada b-f (c2, d1, d2, f1, f3), com 3 mudancas mecanicas:
 1) importam win_cinco_medias_semleilao (e as irmas _semleilao) no lugar da lib antiga;
 2) a zeragem de fim de pregao tambem dispara em `ultima_continua` (quando o dado traz a coluna);
 3) as ancoras do exec (assinatura de simula) acompanham a assinatura da lib nova (saida_st).
Os originais NAO sao tocados. Rodar: python gera_copias.py"""
import re
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DT = AQUI.parents[2]
DEST = AQUI / "copias"
ORIG = {
    "c2_volume_saida_contexto": "win_hipoteses_2026_10_06c", "c2_candidatas": "win_hipoteses_2026_10_06c",
    "d1_stop": "win_hipoteses_2026_10_06d", "d1_candidatas": "win_hipoteses_2026_10_06d",
    "d2_alvo": "win_hipoteses_2026_10_06d", "d2_candidatas": "win_hipoteses_2026_10_06d",
    "f1_candle": "win_hipoteses_2026_10_06f", "f1_candidatas": "win_hipoteses_2026_10_06f",
    "f3_feat": "win_hipoteses_2026_10_06f", "f3_candidatas": "win_hipoteses_2026_10_06f",
}
INJ = f"import sys as _sy; _sy.path[:0] = [r'{DT}', r'{DEST}']\n"
ST = "saida_st=(ST_H1_N, ST_H1_M) if SAIDA_ST_H1 else None"
for nome, pasta in ORIG.items():
    s = (DT / pasta / f"{nome}.py").read_text(encoding="utf-8")
    s = s.replace("import win_cinco_medias as", "import win_cinco_medias_semleilao as").replace("from win_cinco_medias import", "from win_cinco_medias_semleilao import")
    for outro in ORIG:
        s = re.sub(rf"^(\s*)import {outro}( as| *$)", rf"\1import {outro}_semleilao\2", s, flags=re.M)
        s = re.sub(rf"^(\s*)from {outro} import", rf"\1from {outro}_semleilao import", s, flags=re.M)
        s = s.replace(f"import {outro}_semleilao as", f"import {outro}_semleilao as")
    # imports sem 'as' ficam com o nome novo: aliasar de volta
    for outro in ORIG:
        s = re.sub(rf"^(\s*)import {outro}_semleilao\s*$", rf"\1import {outro}_semleilao as {outro}", s, flags=re.M)
    # (3) ancoras do exec
    s = s.replace("aperta=(STOP_APERTA_N, STOP_APERTA_K)):", f"aperta=(STOP_APERTA_N, STOP_APERTA_K), {ST}):")
    s = s.replace("aperta=(STOP_APERTA_N, STOP_APERTA_K), saida_extra=None):", f"aperta=(STOP_APERTA_N, STOP_APERTA_K), {ST}, saida_extra=None):")
    s = s.replace("aperta=(STOP_APERTA_N, STOP_APERTA_K), saida_x=None):", f"aperta=(STOP_APERTA_N, STOP_APERTA_K), {ST}, saida_x=None):")
    # (2) zeragem na ultima barra continua
    if "dias[t + 1] != dias[t]):" in s and "def simula" in s:
        s = s.replace("    dias, hora, n = idx.normalize(), idx.time, len(idx)\n",
                      "    dias, hora, n = idx.normalize(), idx.time, len(idx)\n"
                      "    ult = d[\"ultima_continua\"].to_numpy(bool)[sel] if \"ultima_continua\" in d.columns else None\n", 1)
        s = s.replace("dias[t + 1] != dias[t]):", "dias[t + 1] != dias[t] or (ult is not None and ult[t])):")
    # f*: base = v2.02
    if nome.startswith("f"):
        s = re.sub(r"(import win_cinco_medias_semleilao as (\w+))", r"\1; \2.usar_v202()", s, count=1)
    # injeta paths
    if "from __future__ import annotations\n" in s:
        s = s.replace("from __future__ import annotations\n", "from __future__ import annotations\n" + INJ, 1)
    else:
        s = INJ + s
    (DEST / f"{nome}_semleilao.py").write_text(s, encoding="utf-8")
    print("ok", nome, "ult" if "ult is not None" in s else "")
