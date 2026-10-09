"""Passo 1: roda o robo_v4 nos 90 dias e tabula por FONTE do trade x estrato (rot<0,15 / int / dir>=0,25)."""
import sys, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import *
from concurrent.futures import ProcessPoolExecutor, as_completed

def um(dia):
    return dia, cfg4.resultado_dia(dia, robo_v4.monta_v4())

if __name__ == "__main__":
    res = {}
    with ProcessPoolExecutor(5) as ex:
        for f in as_completed([ex.submit(um, d) for d in DIAS]):
            d, r = f.result(); res[d] = r
    json.dump(res, open(ER / "v4_90.json", "w"), indent=1)
    v = np.array([res[d]["brl"] for d in DIAS])
    print(f"v4 90 dias: total {v.sum():.1f} rep {repond(v):.2f} neg {(v<0).sum()} pior {v.min():.1f}", flush=True)
    for e in ("rot", "int", "dir"):
        m = EST3 == e; print(f"  {e}: dias {m.sum()}  R$/dia {v[m].mean():+.1f}  total {v[m].sum():+.1f}  neg {(v[m]<0).sum()}", flush=True)
    rows = []
    for d, e in zip(DIAS, EST3):
        for t in res[d]["trades"]: rows.append((t["fonte"], e, t["brl"], t["lado"]))
    import pandas as pd
    df = pd.DataFrame(rows, columns=["fonte", "est", "brl", "lado"])
    print(f"\nfonte (nome completo) | n_rot R$rot ac_rot R$/tr | n_int R$int R$/tr | n_dir R$dir R$/tr | n_fora R$fora R$/tr_fora")
    out = []
    for f, g in df.groupby("fonte"):
        r = g[g.est == "rot"]; i = g[g.est == "int"]; dd = g[g.est == "dir"]; fo = g[g.est != "rot"]
        sf = lambda x: x.brl.sum() if len(x) else 0.0
        mf = lambda x: x.brl.mean() if len(x) else float("nan")
        ac = (r.brl > 0).mean() if len(r) else float("nan")
        print(f"{f[:62]:62s} | {len(r):3d} {sf(r):+8.1f} {ac*100:4.0f}% {mf(r):+6.1f} | {len(i):3d} {sf(i):+8.1f} {mf(i):+6.1f} | {len(dd):3d} {sf(dd):+8.1f} {mf(dd):+6.1f} | {len(fo):3d} {sf(fo):+8.1f} {mf(fo):+6.1f}", flush=True)
        out.append(dict(fonte=f, n_rot=len(r), brl_rot=sf(r), ac_rot=ac, n_int=len(i), brl_int=sf(i), n_dir=len(dd), brl_dir=sf(dd), n_fora=len(fo), brl_fora=sf(fo)))
    json.dump(out, open(ER / "p1_fontes.json", "w"), indent=1)
    print(f"\nTOTAL trades {len(df)}  rot {(df.est=='rot').sum()} R$ {df[df.est=='rot'].brl.sum():+.1f} | int {(df.est=='int').sum()} R$ {df[df.est=='int'].brl.sum():+.1f} | dir {(df.est=='dir').sum()} R$ {df[df.est=='dir'].brl.sum():+.1f}")
