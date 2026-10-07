# -*- coding: utf-8 -*-
"""Etapa 1 da Z4: cortes descritivos 2024 x outros anos. Gera diag_tabelas.md (o diagnostico.md e' escrito a partir dele)."""
import numpy as np
import pandas as pd

import comum as C

df = C.carrega()  # base oficial (com a vela 18:30 em 2026; 2022-25 identico nas duas versoes)
df["hora_fill"] = pd.to_datetime(df.entrada, format="mixed").dt.hour
df["dur_min"] = (pd.to_datetime(df.saida, format="mixed") - pd.to_datetime(df.entrada, format="mixed")).dt.total_seconds() / 60
df["grupo"] = np.where(df.ano == "2024", "2024", "outros")
df["lado_txt"] = np.where(df.lado > 0, "compra", "venda")
df["tend_txt"] = np.where(df.tend_alinh > 0, "a favor do dia", "contra o dia")
df["h1_txt"] = np.where(df.h1_alinh > 0, "a favor EMA34 H1", "contra EMA34 H1")

# faixas: quantis de TODOS os anos juntos (descritivo; o mesmo corte para os dois grupos)
def q(col, k=4):
    return pd.qcut(df[col], k, duplicates="drop").astype(str)

cortes = {
    "hora da entrada (fill)": df.hora_fill.clip(9, 16).astype(str),
    "lado": df.lado_txt,
    "largura (pts)": q("larg"),
    "largura / ATR M15": q("larg_atr15"),
    "largura / ATR D1": q("larg_atrd"),
    "ATR D1 (pts)": q("atr_d"),
    "ATR M15 / ATR D1": q("atr15_atrd"),
    "variação abertura→decisão (ATR D1)": q("var_dia_atrd"),
    "entrada vs variação do dia": df.tend_txt,
    "entrada vs EMA34 H1": df.h1_txt,
    "distância à EMA34 M15 (ATR M15, no lado)": q("dist_ema15_atr15"),
    "amplitude do dia até a decisão (ATR D1)": q("faixa_dia_atrd"),
    "gap de abertura (ATR D1)": q("gap_atrd"),
    "motivo de saída": df.motivo,
    "duração (min)": q("dur_min"),
}


def tab(chave):
    g = df.groupby([cortes[chave], "grupo"]).agg(n=("liq", "size"), rs_op=("liq", "mean"), acerto=("ganhou", "mean"), soma=("liq", "sum"))
    g["acerto"] *= 100
    w = g.unstack("grupo")
    lin = [f"### {chave}\n", "| faixa | n 2024 | R$/op 2024 | acerto 2024 | soma 2024 | n outros | R$/op outros | acerto outros |", "|---|---|---|---|---|---|---|---|"]
    for f, r in w.iterrows():
        def v(c, gr, fmt):
            x = r.get((c, gr), np.nan)
            return "" if pd.isna(x) else format(x, fmt)
        lin.append(f"| {f} | {v('n','2024','.0f')} | {v('rs_op','2024','.1f')} | {v('acerto','2024','.0f')} | {v('soma','2024','.0f')} | "
                   f"{v('n','outros','.0f')} | {v('rs_op','outros','.1f')} | {v('acerto','outros','.0f')} |")
    return "\n".join(lin) + "\n"


out = ["# Z4 — tabelas do diagnóstico (geradas por diagnostico.py)\n",
       "Base: RetTF M15 (ajustes=True), R$2/op. 'outros' = 2022, 2023, 2025 (jan–set) e 2026 juntos. Faixas = quartis de todos os anos juntos.\n",
       "## Por ano\n", C.md(C.por_ano(df), index=False), "\n"]
# por ano x corte resumido (ano a ano) para os cortes categoricos principais
for chave in ["entrada vs variação do dia", "entrada vs EMA34 H1", "lado", "motivo de saída"]:
    g = df.groupby([cortes[chave], "ano"]).agg(n=("liq", "size"), rs_op=("liq", "mean")).round(1)
    out.append(f"### {chave} — ano a ano (n / R$/op)\n")
    w = g.unstack("ano")
    out.append("| faixa | " + " | ".join(C.ANOS) + " |\n|---|" + "---|" * len(C.ANOS))
    for f, r in w.iterrows():
        out.append(f"| {f} | " + " | ".join(f"{r.get(('n',a),0):.0f} / {r.get(('rs_op',a),np.nan):.1f}" for a in C.ANOS) + " |")
    out.append("")
for k in cortes:
    out.append(tab(k))

# curva mensal 2024 + mercado
m = df[df.ano == "2024"].groupby("mes").agg(ops=("liq", "size"), liq=("liq", "sum"), acerto=("ganhou", "mean"),
                                             larg=("larg", "median"), larg_atrd=("larg_atrd", "median"))
m["acum"] = m.liq.cumsum()
m["saldo_fim"] = 1000 + m.acum
m["acerto"] *= 100
# mercado no mes (M1 do periodo 2022-25): ATR D1 medio, variacao do mes em ATR, eficiencia (|var|/soma |var diaria|)
import port_z4  # noqa: E402
dados, P = port_z4.prepara("2022_2025")
m1 = dados.m1()
d = m1.groupby(m1.index.normalize()).agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"))
d["rng"] = d.h - d.l
d["mes"] = d.index.strftime("%Y-%m")
d["ret"] = d.c - d.o
mk = d.groupby("mes").agg(rng=("rng", "mean"), o=("o", "first"), c=("c", "last"), absret=("ret", lambda x: x.abs().sum()),
                          ret_dia_abs=("ret", lambda x: x.abs().mean()))
mk["var_mes_pts"] = mk.c - mk.o
mk["eficiencia"] = mk.var_mes_pts.abs() / mk.absret
mk["corpo_dia/faixa"] = mk.ret_dia_abs / mk.rng
mm = m.join(mk[["rng", "var_mes_pts", "eficiencia", "corpo_dia/faixa"]])
out.append("## Curva mensal de 2024 e o mercado no mês\n")
out.append("rng = faixa diária média (pts); var_mes = fechamento − abertura do mês (pts); eficiência = |var do mês| / soma |abertura→fechamento diário|; corpo/faixa = |abertura→fechamento| médio / faixa média do dia (alto = dias direcionais).\n")
out.append(C.md(mm.round(2)))
# mesmo resumo de mercado por ano
d["ano"] = d.index.year.astype(str)
ya = d.groupby("ano").agg(rng=("rng", "mean"), ret_dia_abs=("ret", lambda x: x.abs().mean()))
ya["corpo_dia/faixa"] = ya.ret_dia_abs / ya.rng
out.append("\n### mercado por ano (2022–2025; 2026 vem de outro arquivo)\n")
out.append(C.md(ya.round(2)))
# R$/op x faixa diaria e x corpo/faixa no proprio dia, todos os anos (dia da operacao, conhecido so' no fim: descritivo)
(C.AQUI / "diag_tabelas.md").write_text("\n".join(out), encoding="utf-8")
df.to_csv(C.AQUI / "trades" / "base_enriquecido.csv", index=False)
print("\n".join(out), flush=True)
