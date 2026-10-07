# -*- coding: utf-8 -*-
from pathlib import Path
A = Path(__file__).resolve().parent
NL = chr(10)
t = (A / "out" / "analise4.txt").read_text(encoding="utf-8")
h = (A / "out" / "holdout4.txt").read_text(encoding="utf-8")
c = (A / "out" / "crosscheck4.txt").read_text(encoding="utf-8")
tab = (A / "out" / "tabela_escolha.txt").read_text(encoding="utf-8")


def sec(txt, a, b=None):
    i = txt.index(a)
    j = txt.index(b, i + len(a)) if b else len(txt)
    return txt[i:j].strip(NL)


heat = sec(t, "=== LIQUIDO B (R$, 2 contratos", "=== LIQUIDO B, fill atrav") 
heat = heat.replace("=== LIQUIDO B (R$, 2 contratos, fill toque) — linhas = stop, colunas = alvo ===", "LIQUIDO B (R$, 2 contratos, fill toque)")
heat = heat.replace("=== R$ POR TRADE (B, toque) ===", "R$ POR TRADE (B, toque)")
heat += NL * 2 + sec(t, "=== LIQUIDO A (conta continua", "=== p do nulo").replace("=== LIQUIDO A (conta continua R$1.000, toque) ===", "LIQUIDO A (conta continua R$1.000, toque)")
heat += NL * 2 + sec(t, "=== p do nulo", "=== LIQUIDO B abr").replace("===", "").strip()
heat += NL * 2 + sec(t, "=== LIQUIDO B abr", "=== CENSURA").replace("===", "").strip()
cens = sec(t, "=== CENSURA MODO A", "=== PLATO").replace("===", "").strip()
plato = sec(t, "=== PLATO", "=== ESCOLHA").replace("===", "").strip()
esc = sec(t, "=== ESCOLHA", "=== SELECAO").replace("===", "").strip()
sel = sec(t, "=== SELECAO NA GRADE").replace("===", "").strip()
hold = h.strip().replace("===", "")
out = (A / "RESULTADO_texto.md").read_text(encoding="utf-8")
for k, v in dict(HEAT=heat, CENSURA=cens, PLATO=plato, ESCOLHA=esc, SELECAO=sel, HOLD=hold, CROSS=c.strip(), TABELA=tab.strip()).items():
    out = out.replace("{{%s}}" % k, v)
(A / "RESULTADO.md").write_text(out, encoding="utf-8")
print("ok", len(out), out.count("{{"))
