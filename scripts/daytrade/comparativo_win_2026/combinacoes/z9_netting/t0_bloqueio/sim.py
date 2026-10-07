"""Z9-T0 bloqueio: comportamento atual dos EAs (pulam a entrada se ha' posicao no simbolo). Quem entra primeiro fica."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import base

ef = []
for ano in range(2022, 2027):
    t = base.operacoes(ano); livre = pd.Timestamp.min
    for r in t.itertuples():
        if r.entrada >= livre:
            ef.append(r._asdict()); livre = r.saida
e = pd.DataFrame(ef)
e.to_csv(Path(__file__).parent / "trades_t0.csv", index=False)
res = base.resumo(e)
iso = base.resumo(pd.concat(base.operacoes(a) for a in range(2022, 2027)))
for a in res:
    print(a, "T0", res[a], "| isolado", iso[a]["liq"], flush=True)
print(e.groupby(["ano", "estrategia"]).rs.count().unstack())
