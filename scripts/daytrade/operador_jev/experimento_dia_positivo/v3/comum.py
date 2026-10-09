"""Utilidades da v3: estado reduzido (menos velas M15 / secoes) e conversao de decisao. Reusa mercado.py / decisoes.py do operador."""
from __future__ import annotations
import sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
EXP = AQUI.parent
PAI = EXP.parent
for p in (str(PAI), str(EXP)):
    if p not in sys.path:
        sys.path.insert(0, p)
from mercado import montar_pacote, PREAMBULO  # noqa: E402


def estado_v(mk, dia, k, pos=None, n_velas=40, diario_n=10, h1_dias=2):
    """Igual a mercado.montar_estado(derivados=True), com cortes: n_velas M15 (padrao v2 = 40), diario_n dias na secao DIARIO
    (v2 = 10), h1_dias = quantos dias ANTERIORES aparecem na secao H1 (v2 = 2). Os DERIVADOS nao mudam (calculados do historico completo)."""
    est = dict(pos=pos, pend=None, pts=0, brl=0, ntrades=0)
    txt = montar_pacote(mk, dia, k, est, [], [], n_velas=n_velas, derivados=True)
    cab = txt.split("\nPOSICAO:")[0]
    linha = None
    if pos:
        from mercado import _hm
        linha = [x for x in txt.split("\n") if x.startswith("POSICAO:")][0] + f" | entrada na vela {_hm(dia.m15_t[pos['k_ent']])}"
    if diario_n != 10 or h1_dias != 2:
        L = cab.split("\n")
        out, sec = [], None
        dias_diario = [l for l in L if l.startswith("d-") and l.split(" ")[0][2:].isdigit() and l.count(" ") == 5 and ":" not in l.split(" ")[1]]
        keep_d = set(dias_diario[-diario_n:]) if 0 < diario_n < 10 else (set() if diario_n == 0 else set(dias_diario))
        for l in L:
            if l.startswith("DIARIO"):
                sec = "D"
                if diario_n == 0:
                    continue
                out.append(l.replace("ultimos 10 dias", f"ultimos {diario_n} dias"))
                continue
            if l.startswith("H1 ("):
                sec = "H"
                out.append(l.replace("hoje e 2 dias anteriores", "hoje" if h1_dias == 0 else f"hoje e {h1_dias} dia(s) anterior(es)"))
                continue
            if l.startswith("M15 ("):
                sec = "M"
            if l == "":
                if sec == "D" and diario_n == 0:
                    sec = None
                    continue
                sec = None
            if sec == "D" and l.startswith("d-") and l not in keep_d:
                continue
            if sec == "H" and l.startswith("d-"):
                off = int(l.split(" ")[0][2:])
                if off > h1_dias:
                    continue
            out.append(l)
        cab = "\n".join(out)
    if linha:
        cab += "\n" + linha
    return PREAMBULO + "\n" + cab
