import pandas as pd, numpy as np
from pathlib import Path
A = Path(__file__).resolve().parent; X = A.parent / "x0"
N = ["Win", "Win_c1", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34"]
m1 = pd.read_parquet(A.parents[5] / "data" / "comparativo_win_2026" / "m1_WIN$N_2022_2025.parquet")
ult = m1.index.to_series().groupby(m1.index.date).max()
fim = {d: t.hour * 60 + t.minute + 1 for d, t in ult.items()}
out = []
def P(s=""): print(s, flush=True); out.append(s)
a = {n: pd.read_csv(X / "continuo" / f"{n}.csv") for n in N}
b = {n: pd.read_csv(A / "resultados_2022_2025" / f"{n}.csv") for n in N}
P("## Prova: dias com pregao >= 18:25 nao mudam")
for n in ["WinDeslocamentoMatinal", "WinCincoMedias"]:
    x, y = a[n].copy(), b[n].copy()
    for d in (x, y): d["dia"] = pd.to_datetime(d.entrada, format="mixed").dt.date
    dias = sorted(fim); longos = [d for d in dias if fim[d] >= 1105]; curtos = [d for d in dias if fim[d] < 1105]
    difs = []
    for d in dias:
        gx = x[x.dia == d].drop(columns="dia").reset_index(drop=True); gy = y[y.dia == d].drop(columns="dia").reset_index(drop=True)
        if not gx.equals(gy): difs.append(d)
    dl = [d for d in difs if fim[d] >= 1105]
    P(f"{n}: dias {len(dias)} (>=18:25: {len(longos)}, <18:25: {len(curtos)}); dias com operacao diferente: {len(difs)}; destes em dias >=18:25: {len(dl)} {dl[:10]}; em dias <18:25: {len(difs)-len(dl)}")
    P(f"  ops antes {len(x)} depois {len(y)}; liquido antes {x.rs.sum():,.0f} depois {y.rs.sum():,.0f}")
P(); P("## Tabela por ano (ops / liquido sem custo / liquido com R$2) antes -> depois")
def cel(d, ano):
    g = d[d.saida.str[:4] == ano] if ano != "total" else d
    return f"{len(g)} / {g.rs.sum():,.0f} / {(g.rs-2).sum():,.0f}"
P("| ano | " + " | ".join(N) + " |"); P("|---|" + "---|" * len(N))
for ano in ["2022", "2023", "2024", "2025", "total"]:
    P(f"| {ano} | " + " | ".join(f"{cel(a[n],ano)} -> {cel(b[n],ano)}" if n in ("WinCincoMedias","WinDeslocamentoMatinal") else cel(a[n],ano) for n in N) + " |")
P(); P("## Motivos de saida depois da correcao (overnight / de outro dia)")
for n in N:
    mo = b[n].motivo.value_counts()
    P(f"{n}: overnight={mo.get('overnight',0)}, de outro dia={mo.get('de outro dia',0)}; antes: overnight={(a[n].motivo=='overnight').sum()}, de outro dia={(a[n].motivo=='de outro dia').sum()}")
(A / "resumo.md").write_text("# X0b\n\n" + "\n".join(out) + "\n", encoding="utf-8")
