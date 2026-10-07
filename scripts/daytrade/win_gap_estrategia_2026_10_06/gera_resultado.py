# -*- coding: utf-8 -*-
"""Monta RESULTADO.md a partir de out/is_resumo.txt e out/valida_stdout.txt (tabelas copiadas, nao digitadas)."""
import re
from pathlib import Path

A = Path(__file__).resolve().parent
is_t = (A / "out" / "is_resumo.txt").read_text(encoding="utf-8")
va_t = (A / "out" / "valida_stdout.txt").read_text(encoding="utf-8")


def bloco(txt, ini, fim=None):
    i = txt.index(ini)
    j = txt.index(fim, i + len(ini)) if fim else len(txt)
    return txt[i:j].strip("\n")


def tab_linhas(b):
    return "\n".join(l for l in b.split("\n") if not l.startswith("===")).strip("\n")


is_a = tab_linhas(bloco(is_t, "=== IS, modo A (conta continua R$250), fill=toque ===", "=== IS, modo A (conta continua R$250), fill=atrav+1t"))
is_b = tab_linhas(bloco(is_t, "=== IS, modo B (R$250 por pregao, capital nocional), fill=toque ===", "=== IS, modo B (R$250 por pregao, capital nocional), fill=atrav+1t"))
is_b2 = tab_linhas(bloco(is_t, "=== IS, modo B (R$250 por pregao, capital nocional), fill=atrav+1t ===", "Criterio 1"))
crit = bloco(is_t, "Criterio 1", "Eixos:")
eixos = bloco(is_t, "Eixos:")
resumo = va_t[va_t.index("######## RESUMO ORDENADO"):]
resumo = resumo.replace("  excluidos:   INDICIO CRU", "  INDICIO CRU")
corpo = (A / "RESULTADO_texto.md").read_text(encoding="utf-8")
out = (corpo.replace("{{IS_A}}", is_a).replace("{{IS_B}}", is_b).replace("{{IS_B2}}", is_b2)
       .replace("{{CRIT}}", crit).replace("{{EIXOS}}", eixos).replace("{{VALIDA}}", resumo.split("\n", 1)[1]))
(A / "RESULTADO.md").write_text(out, encoding="utf-8")
print("ok", len(out))
