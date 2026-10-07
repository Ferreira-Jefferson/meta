"""X0 -- emenda: junta X0 (2022-01 -> 2023-12) com V0 (2024-01 -> 2025-09) e confere buracos/duplicatas.
Se existir `continuo/` (rodada unica 2022-01 -> 2025-09), compara a emenda contra ela."""
import pandas as pd
from pathlib import Path
A = Path(__file__).resolve().parent; V = A.parents[1] / "v_validacao" / "v0"
N = ["Win", "Win_c1", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34"]
(A / "resultados_2022_2025").mkdir(exist_ok=True)
for n in N:
    a = pd.read_csv(A / "resultados" / f"{n}.csv"); b = pd.read_csv(V / "resultados" / f"{n}.csv")
    j = pd.concat([a, b], ignore_index=True)
    dup = j.duplicated(subset=["entrada", "saida", "lado"]).sum()
    assert j.entrada.is_monotonic_increasing and dup == 0, (n, dup)
    j.to_csv(A / "resultados_2022_2025" / f"{n}.csv", index=False)
    print(f"{n:24s} X0 {len(a)} + V0 {len(b)} = {len(j)} ops | duplicatas {dup} | ultima X0 {a.saida.max()} | primeira V0 {b.entrada.min()}", flush=True)
for nome, v0 in (("votos", "votos_val"), ("eventos", "eventos_val")):
    a = pd.read_parquet(A / f"{nome}_dev.parquet"); b = pd.read_parquet(V / f"{v0}.parquet")
    assert list(a.columns) == list(b.columns)
    j = pd.concat([a, b]); j.to_parquet(A / f"{nome}_2022_2025.parquet")
    if nome == "votos":
        ix = j.index; assert ix.is_unique and ix.is_monotonic_increasing
        d = pd.Series(ix.date).value_counts()
        dd = sorted(set(ix.date)); m1 = pd.read_parquet(A.parents[5] / "data" / "comparativo_win_2026" / "m1_WIN$N_2022_2025.parquet")
        dm = sorted(d_ for d_ in set(m1.index.date) if dd[0] <= d_ <= dd[-1])
        print(f"votos: {len(j)} linhas, {dd[0]}..{dd[-1]}, dias {len(dd)} vs m1 {len(dm)}, dias faltando {sorted(set(dm)-set(dd))}, extras {sorted(set(dd)-set(dm))}", flush=True)
        print(f"  linhas por dia == barras do m1 no dia: {all(d[x] == (m1.index.date == x).sum() for x in dd[:5] + dd[-5:])}; jan/24 entre X0 e V0: {a.index.max()} -> {b.index.min()}", flush=True)
    else:
        assert not j.duplicated(subset=["estrategia", "entrada", "saida", "lado"]).any()
        print(f"eventos: {len(a)} + {len(b)} = {len(j)} linhas, sem duplicata", flush=True)
