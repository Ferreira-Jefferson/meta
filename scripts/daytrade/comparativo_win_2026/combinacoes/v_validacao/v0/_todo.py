"""Atualiza so' a secao V0 do TODO.md. Uso: python _todo.py STATUS FASE FEITO FALTA ARQUIVOS ULTIMO"""
import sys, re
from pathlib import Path
f = Path(__file__).resolve().parents[2] / "TODO.md"
s = f.read_text(encoding="utf-8")
st, fase, feito, falta, arq, ult = sys.argv[1:7]
i = s.index("### V0 ")
j = s.index("### V1 ")
cab = s[i:s.index("\n", i)]
novo = f"{cab}\nStatus: {st}\nFase: {fase}\nFeito: {feito}\nFalta: {falta}\nArquivos: {arq}\nÚltimo resultado: {ult}\n"
f.write_text(s[:i] + novo + s[j:], encoding="utf-8")
