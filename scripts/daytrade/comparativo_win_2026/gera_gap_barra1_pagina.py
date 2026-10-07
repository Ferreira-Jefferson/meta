"""Gera os blocos do WinGapBarra1 para a pagina "Robos no WIN 2026": a entrada de D.estrategias (testador/custo, mesmo
formato de comparativo.resumo) e a linha ano a ano (2022-2025 set, 2026 ate' 05/10; cada ano recomeca com R$1.000,
R$2 por operacao, 'quebra' se o saldo chega a zero). Saida: gap_barra1_pagina.json"""
import json, sys
from pathlib import Path
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import comparativo as C  # noqa: E402

t26 = pd.read_csv(AQUI / "resultados" / "WinGapBarra1.csv").sort_values("saida", kind="stable")
t25 = pd.read_csv(AQUI / "resultados_anos_gap_barra1" / "WinGapBarra1_2022_2025.csv")
est = dict(nome="WinGapBarra1", testador=C.resumo(t26, 0.0), custo=C.resumo(t26, C.CUSTO_OP))


def ano(t, a):
    t = t[t.saida.str[:4] == str(a)].sort_values("saida", kind="stable")
    saldo, minimo, quebra, rs = 1000.0, 1000.0, False, []
    for r in t.itertuples():
        x = r.rs - 2.0 * r.qtd
        saldo += x; rs.append(x); minimo = min(minimo, saldo)
        if saldo <= 0:
            quebra = True
            break
    rs = pd.Series(rs)
    return dict(liq=round(float(rs.sum())), ops=len(rs), smin=round(minimo), quebra=quebra,
                pf=round(float(rs[rs > 0].sum() / -rs[rs < 0].sum()), 2) if (rs < 0).any() else None,
                ac=round(100 * float((rs > 0).mean()), 1))


anos = {str(a): ano(t25, a) for a in (2022, 2023, 2024, 2025)}
anos["2026"] = ano(t26, 2026)
out = dict(estrategia=est, anos=anos)
(AQUI / "gap_barra1_pagina.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
for k in ("testador", "custo"):
    e = est[k]
    print(k, {x: e[x] for x in ("total", "final", "n", "acerto", "pf", "dd", "meses_pos", "meses_op", "quebra")})
    print({m: (v["rs"], v["n"]) for m, v in e["meses"].items()})
print(json.dumps(anos, ensure_ascii=False))
