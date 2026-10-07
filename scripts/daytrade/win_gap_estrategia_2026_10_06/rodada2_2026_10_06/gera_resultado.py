# -*- coding: utf-8 -*-
"""Monta RESULTADO.md a partir de RESULTADO_texto.md + out/analise.txt (tabelas copiadas, nao digitadas)."""
from pathlib import Path

A = Path(__file__).resolve().parent
t = (A / "out" / "analise.txt").read_text(encoding="utf-8")


def sec(a, b=None):
    i = t.index(a)
    j = t.index(b, i + len(a)) if b else len(t)
    return t[i:j].strip("\n")


top = sec("=== TOP 10", "=== TODAS").split("\n", 1)[1].strip("\n")
fam = sec("=== FAMILIAS", "=== ENTRADAS").split("\n", 1)[1].strip("\n")
mat = sec("=== ENTRADAS x SAIDAS").split("\n", 1)[1].strip("\n")
sel = sec("=== SELECAO", "=== FAMILIAS").replace("=== METADES (modo B toque, liquido R$) ===", "METADES (modo B toque, liquido R$)")
fill = (A / "out" / "antes_depois.txt").read_text(encoding="utf-8")
fill = fill[fill.index("=== (b)"):].split(chr(10), 1)[1].strip(chr(10))
out = (A / "RESULTADO_texto.md").read_text(encoding="utf-8")
for k, v in dict(TOP10=top, FAMILIAS=fam, MATRIZ=mat, SELECAO=sel, FILL=fill).items():
    out = out.replace("{{%s}}" % k, v)
(A / "RESULTADO.md").write_text(out, encoding="utf-8")
print("ok", len(out))
