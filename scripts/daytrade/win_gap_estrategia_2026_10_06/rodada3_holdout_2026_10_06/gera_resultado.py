# -*- coding: utf-8 -*-
from pathlib import Path

A = Path(__file__).resolve().parent
t = (A / "out" / "holdout.txt").read_text(encoding="utf-8")
NL = chr(10)


def sec(a, b=None):
    i = t.index(a)
    j = t.index(b, i + len(a)) if b else len(t)
    return t[i:j].strip(NL)


def corpo(s):
    return s.split(NL, 1)[1].strip(NL)


lado = corpo(sec("=== lado a lado", "referencia IS rodada 2")) + NL + sec("referencia IS rodada 2", "=== sensibilidade")
tab_h = corpo(sec("=== HOLDOUT", "=== IS 2026"))
tab_is = corpo(sec("=== IS 2026", "=== lado a lado"))
modoa = corpo(sec("=== modo A", "=== poder"))
poder = corpo(sec("=== poder"))
sens = (A / "out" / "sens_gap.txt").read_text(encoding="utf-8").strip(NL)
out = (A / "RESULTADO_texto.md").read_text(encoding="utf-8")
for k, v in dict(LADO=lado, TAB_H=tab_h, TAB_IS=tab_is, MODOA=modoa, PODER=poder, SENS=sens).items():
    out = out.replace("{{%s}}" % k, v)
(A / "RESULTADO.md").write_text(out, encoding="utf-8")
print("ok", len(out))
