# -*- coding: utf-8 -*-
"""Etapa 3 da Z4: cada filtro (port re-rodado com o filtro ao ARMAR) contra a base, por ano, + filtro aleatorio.
Filtro aleatorio: SORTEIO SOBRE AS LINHAS DO CSV DA BASE. Em cada ano, mantem ao acaso o mesmo numero de operacoes que
o filtro teve naquele ano (= corta a mesma fracao; se o filtro tiver mais ops que a base no ano, mantem todas), soma o
liquido com custo dos 4 anos de conferencia (2022, 2023, 2025, 2026). 1.000 sorteios, semente fixa. Percentil = % dos
sorteios abaixo do total do filtro (empates contam meio).
Duas versoes da base em 2026: com o tick isolado das 18:30 do WIN$N (oficial Y4b) e sem ele (sempos). 2022-25 e' igual.
APROVADO (TODO Z4): 2024 nao quebra; melhora com custo em >= 3 dos 4 outros anos; nenhum ano quebra; total dos 4 > p95."""
import numpy as np
import pandas as pd

import comum as C

OUT = ["2022", "2023", "2025", "2026"]
N_SORT = 1000
rng = np.random.default_rng(20261006)
linhas = ["# Z4 — conferência dos filtros (gerado por conferencia.py)\n",
          "R$2/op; saldo recomeça em R$1.000 a cada ano; filtro aplicado ao ARMAR a entrada (port re-rodado); sorteio aleatório sobre as linhas do CSV da base, mesma fração cortada por ano, 1.000 sorteios.\n"]
resumo = []
for versao, sp in (("com 18:30 (oficial)", False), ("sem 18:30", True)):
    base = C.carrega("base", sp)
    tb = C.por_ano(base).set_index("ano")
    linhas.append(f"## Base 2026 {versao}\n")
    for f in ("f1", "f2", "f3", "f4"):
        fd = C.carrega(f, sp)
        tf = C.por_ano(fd).set_index("ano")
        # aleatorio
        tot = np.zeros(N_SORT)
        for a in OUT:
            lb = base[base.ano == a].liq.values
            k = min(int(tf.loc[a, "ops"]), len(lb))
            for i in range(N_SORT):
                tot[i] += lb[rng.choice(len(lb), k, replace=False)].sum()
        tot_f = float(tf.loc[OUT, "liquido"].sum())
        tot_b = float(tb.loc[OUT, "liquido"].sum())
        pct = ((tot < tot_f).mean() + 0.5 * (tot == tot_f).mean()) * 100
        p95 = float(np.percentile(tot, 95))
        melhora = int(sum(tf.loc[a, "liquido"] > tb.loc[a, "liquido"] for a in OUT))
        q24 = bool(tf.loc["2024", "quebra"])
        qout = [a for a in OUT if tf.loc[a, "quebra"]]
        ok = (not q24) and melhora >= 3 and not qout and tot_f > p95
        v = "APROVADO" if ok else "REFUTADO"
        motivos = []
        if q24: motivos.append("2024 quebra")
        if melhora < 3: motivos.append(f"melhora em {melhora}/4")
        if qout: motivos.append("quebra em " + ",".join(qout))
        if tot_f <= p95: motivos.append(f"total {tot_f:+,.0f} <= p95 {p95:+,.0f}")
        linhas.append(f"### {f} — {v}" + (f" ({'; '.join(motivos)})" if motivos else "") + "\n")
        linhas.append("| ano | base: líquido · ops · saldo mín | filtro: líquido · ops · saldo mín | Δ líquido | quebra (filtro) |")
        linhas.append("|---|---|---|---|---|")
        for a in C.ANOS:
            b, r = tb.loc[a], tf.loc[a]
            linhas.append(f"| {a}{' (criou)' if a == '2024' else ''} | {b.liquido:+,.0f} · {b.ops} · {b.saldo_min:,.0f} | "
                          f"{r.liquido:+,.0f} · {r.ops} · {r.saldo_min:,.0f} | {r.liquido - b.liquido:+,.0f} | {'SIM' if r.quebra else 'não'} |")
        linhas.append(f"\nTotal dos 4 anos de conferência: filtro {tot_f:+,.0f} contra base {tot_b:+,.0f}. Sorteio: mediana {np.median(tot):+,.0f}, "
                      f"p95 {p95:+,.0f}. **Percentil do filtro: {pct:.1f}**. Melhora em {melhora}/4 anos.\n")
        resumo.append(dict(base2026=versao, filtro=f, veredito=v, liq_2024=tf.loc["2024", "liquido"], saldo_min_2024=tf.loc["2024", "saldo_min"],
                           tot4=tot_f, tot4_base=tot_b, melhora=f"{melhora}/4", p95=round(p95), percentil=round(pct, 1),
                           **{f"liq_{a}": tf.loc[a, "liquido"] for a in OUT}))
r = pd.DataFrame(resumo)
r.to_csv(C.AQUI / "conferencia.csv", index=False)
linhas.append("## Resumo\n")
linhas.append(C.md(r, index=False))
(C.AQUI / "conferencia.md").write_text("\n".join(linhas), encoding="utf-8")
print("\n".join(linhas), flush=True)
