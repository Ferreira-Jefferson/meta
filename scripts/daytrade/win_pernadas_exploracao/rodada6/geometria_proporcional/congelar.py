"""Selecao das celulas a congelar (SO descoberta jan-jun). Escreve congelado_ANTES_da_confirmacao.json."""
import pickle, json, os, sys
import numpy as np, pandas as pd
import detail as D, stage as st
HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(HERE, "congelado_ANTES_da_confirmacao.json")) and "--forcar" not in sys.argv:
    sys.exit("ja congelado")
out = pickle.load(open(os.path.join(HERE, "grid_desc.pkl"), "rb"))
cols = ["T", "fam", "g", "filt", "n", "mean", "t"]
real = pd.DataFrame(out[-1], columns=cols)
real["fam"] = real["fam"].astype(int)
nulls = [pd.DataFrame(v, columns=cols) for s, v in out.items() if s > 0]
NMIN = 40
mx = np.array([n[n.n >= NMIN].t.replace([np.inf], np.nan).max() for n in nulls])
cnt3 = np.array([((n.n >= NMIN) & (n.t >= 3) & (n["mean"] > 0)).sum() for n in nulls])
print("nulos:", len(nulls), "max t por sorteio: media %.2f p50 %.2f p95 %.2f max %.2f" % (mx.mean(), np.median(mx), np.percentile(mx, 95), mx.max()))
print("celulas n>=40 e t>=3 no nulo (media): %.1f ; no real: %d" % (cnt3.mean(), ((real.n >= NMIN) & (real.t >= 3) & (real["mean"] > 0)).sum()))
real["famn"] = [st.FAMS[i] for i in real.fam]
key = {(r.T, r.famn, int(r.g), int(r.filt)): (r.n, r["mean"]) for _, r in real.iterrows()} if False else None
d = {}
for T, f, g, k, n, m, t in zip(real["T"], real["famn"], real.g, real.filt, real.n, real["mean"], real.t):
    d[(int(T), f, int(g), int(k))] = (n, m)
def plateau(T, f, g, k):
    ix = D.g_decode(f, g); dims = D.DIMS[f]; pos = ex = 0
    for ax in range(3):
        for dlt in (-1, 1):
            j = list(ix); j[ax] += dlt
            if 0 <= j[ax] < dims[ax]:
                v = d.get((T, f, D.g_encode(f, j), k))
                if v and v[0] >= 20:
                    ex += 1; pos += v[1] > 0
    return pos, ex
rows = []
el = real[(real.n >= NMIN) & (real["mean"] > 0) & np.isfinite(real.t)]
for _, r in el.iterrows():
    T, f, g, k = int(r["T"]), r.famn, int(r.g), int(r.filt)
    p, e = plateau(T, f, g, k)
    rows.append(dict(T=T, fam=f, g=g, filt=k, n=int(r.n), mean=float(r["mean"]), t=float(r.t), pl_pos=p, pl_n=e,
                     p_fwer=float((mx >= r.t).mean())))
df = pd.DataFrame(rows).sort_values("t", ascending=False)
df["plateau"] = df.pl_pos / df.pl_n.clip(lower=1)
ok = df[(df.pl_n >= 3) & (df.plateau >= 0.6)]
print("elegiveis", len(df), "com platô", len(ok))
sel = []; cT = {}; cTF = {}
for _, r in ok.iterrows():
    if cTF.get((r["T"], r.fam), 0) >= 2 or cT.get(r["T"], 0) >= 4: continue
    sel.append(r); cT[r["T"]] = cT.get(r["T"], 0) + 1; cTF[(r["T"], r.fam)] = cTF.get((r["T"], r.fam), 0) + 1
    if len(sel) == 10: break
print(df.head(15).to_string())
fr = []
for r in sel:
    fr.append(dict(T=int(r["T"]), fam=r.fam, g=int(r.g), filt=int(r.filt), geom=D.g_label(r.fam, int(r.g)), filtro=D.filt_label(int(r.filt)),
                   desc_n=int(r.n), desc_mean=float(r["mean"]), desc_t=float(r.t), plateau=float(r.plateau), p_fwer=float(r.p_fwer)))
json.dump(dict(criterio="desc jan-jun, conservador, n>=40, media>0, platô>=0.6 (>=3 vizinhos n>=20), max 2 por (T,fam), max 4 por T, ordenado por t",
               n_celulas_grid=int(len(real)), n_elegiveis=int(len(df)), n_com_plato=int(len(ok)),
               nulo_max_t_p95=float(np.percentile(mx, 95)), celulas=fr), open(os.path.join(HERE, "congelado_ANTES_da_confirmacao.json"), "w"), indent=1, ensure_ascii=False)
for x in fr: print(x)
