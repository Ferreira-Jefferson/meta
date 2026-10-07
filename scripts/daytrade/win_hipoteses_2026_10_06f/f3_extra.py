"""f3 etapa 2: vizinhanca (platô) da melhor saida (Supertrend H1 virando contra) + combo com DI+/DI-. So' 2026. 10 sementes."""
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import numpy as np
import pandas as pd
import f3_feat as X

X.ativar(); W = X.W
_D = None


def rodar(spec):
    global _D
    if _D is None:
        _D = W.carregar(2026)
    d = _D
    nome, ent, sai = spec
    fe = X.F(*ent) if ent else None
    fs = X.S(*sai) if sai else None
    tab, res = W.rodar_janelas(2026, dados=d, extra=fe, saida_extra=fs)
    rl = []
    for sd in range(10):
        e = X.rand_entrada(X.frac_passa(fe, d), sd) if fe else None
        s = X.rand_saida(X.frac_saida(fs, d), sd + 100) if fs else None
        rl.append(float(W.rodar_janelas(2026, dados=d, extra=e, saida_extra=s)[1]["liquido"]))
    return nome, tab, res, rl


if __name__ == "__main__":
    specs = [("S:st_h1(10,2.5)", None, ("st_h1", 10, 2.5)), ("S:st_h1(10,4)", None, ("st_h1", 10, 4)),
             ("S:st_h1(14,3)", None, ("st_h1", 14, 3)), ("S:st_h1(5,3)", None, ("st_h1", 5, 3)),
             ("S:st_h1(12,3)", None, ("st_h1", 12, 3)), ("S:st_h1(10,3.5)", None, ("st_h1", 10, 3.5)),
             ("COMBO F:adx_di(di)+S:st_h1(10,3)", ("adx_di", "di", 0), ("st_h1", 10, 3))]
    tb, rb = W.rodar_janelas(2026, dados=W.carregar(2026))
    bm = dict(zip(tb.janela, tb.liquido))
    rows = []
    with ProcessPoolExecutor(max_workers=6) as ex:
        fut = [ex.submit(rodar, s) for s in specs]
        for f in as_completed(fut):
            nome, tab, r, rl = f.result()
            m = dict(zip(tab.janela, tab.liquido))
            row = dict(nome=nome, liq=float(r["liquido"]), jan=r["janelas_pos"], pior=float(r["pior"]), PF=r["PF"], trades=r["trades"],
                       DD=float(r["maior_DD"]), sem_set=float(r["liquido_sem_set"]),
                       melhores=sum(m.get(j, 0) > bm[j] for j in bm), piores=sum(m.get(j, 0) < bm[j] for j in bm),
                       rand_media=round(float(np.mean(rl)), 1), rand_max=round(max(rl), 1),
                       pct=round(100 * float(np.mean([x < r["liquido"] for x in rl])), 0))
            rows.append(row); print(row, flush=True)
    df = pd.DataFrame(rows); df.to_csv(AQUI / "f3_extra_resumo.csv", index=False)
    pd.set_option("display.width", 250)
    print(df.sort_values("nome").to_string(index=False))
