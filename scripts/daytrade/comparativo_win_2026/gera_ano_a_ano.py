"""Reescreve a tabela "Os robôs ano a ano" do modelo.html a partir de combinacoes/padrao_ano_a_ano.json
(+ gap_barra1_pagina.json, gerado por gera_gap_barra1_pagina.py, quando existir). Rodar antes de comparativo.py."""
import json, re
from pathlib import Path
AQ = Path(__file__).resolve().parent
D = json.loads((AQ / "combinacoes" / "padrao_ano_a_ano.json").read_text(encoding="utf-8"))
g = AQ / "gap_barra1_pagina.json"
if g.exists():
    D["WinGapBarra1"] = dict(tf="M5 · stop 1.200 sem alvo", anos=json.loads(g.read_text(encoding="utf-8"))["anos"])
ANOS = ["2022", "2023", "2024", "2025", "2026"]
br = lambda v: ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):,}".replace(",", ".")
linhas = []
for r, d in D.items():
    tot = sum(d["anos"][y]["liq"] for y in ANOS); pos = sum(d["anos"][y]["liq"] > 0 for y in ANOS)
    cel = ""
    for y in ANOS:
        a = d["anos"][y]
        extra = f'{a["ops"]} ops · mín. R${a["smin"]:,}'.replace(",", ".") if not a["quebra"] and a["smin"] > 0 else f'{a["ops"]} ops · <b style="color:var(--red)">quebra</b>'
        cel += f'<td class="m {"pos" if a["liq"] > 0 else "neg"}">{br(a["liq"])}<span class="n">{extra}</span></td>'
    pill = '<span class="pill ok">5/5</span>' if pos == 5 else ""
    linhas.append((tot, f'<tr><td class="nome l">{r}<small>{d["tf"]}</small></td>{cel}<td class="tot {"pos" if tot > 0 else "neg"}">{br(tot)}</td><td>{pos}/5 {pill}</td></tr>'))
rows = "".join(l for _, l in sorted(linhas, key=lambda x: -x[0]))
p = AQ / "modelo.html"; s = p.read_text(encoding="utf-8")
a = s.index("<h2>Os robôs ano a ano"); i = s.index("<tbody>", a) + 7; j = s.index("</tbody>", i)
p.write_text(s[:i] + rows + s[j:], encoding="utf-8")
print("ok", list(D))
