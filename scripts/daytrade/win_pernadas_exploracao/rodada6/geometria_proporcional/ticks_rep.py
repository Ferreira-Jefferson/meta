import pickle, json, os, numpy as np
import detail as D
HERE = os.path.dirname(os.path.abspath(__file__))
P = pickle.load(open(os.path.join(HERE, "ticks_sens.pkl"), "rb"))
fr = json.load(open(os.path.join(HERE, "congelado_ANTES_da_confirmacao.json")))["celulas"]
win = P["win"]; ix = {d: i for i, d in enumerate(win)}; nd = len(win); W = D.boot_W(nd)
def f(x, n=1): return "-" if x is None or not np.isfinite(x) else f"{x:.{n}f}".replace(".", ",")
def st(tr):
    t = dict(tr); t["day"] = np.array([ix[d] for d in tr["day"]], int)
    return D.stats(t, nd, W) if len(t["pnl"]) else None
print(f"Dias com tick (mar-jun, desc): {nd}\n")
print("| # | celula | modo | base | n | acerto% | BE emp% | pts/op | IC95 | t | seq perdas |")
print("|" + "---|" * 11)
for i, c in enumerate(fr):
    for mode, nm in ((0, "cons"), (1, "otim")):
        for base in ("m1", "tick"):
            tr = P[base if base == "m1" else "tick"]["cells"][(c["T"], c["fam"], c["g"], c["filt"], mode)]
            s = st(tr)
            if s is None: print(f"| {i+1} | {c['geom']} / {c['filtro']} | {nm} | {'M1' if base=='m1' else 'ticks'} | 0 | | | | | | |"); continue
            print(f"| {i+1} | T{c['T']} {c['geom']} / {c['filtro']} | {nm} | {'M1' if base=='m1' else 'ticks'} | {s['n']} | {f(100*s['acerto'])} | {f(100*s['be'])} | {f(s['mean'])} | [{f(s['lo'],0)}; {f(s['hi'],0)}] | {f(s['t'],2)} | {s['maxstreak']} |")
print("\nStop curto (E1 s=1/10 e E3 N=5, todos os r/alvos, sem filtro, conservador), mesmos dias:\n")
print("| familia | T | base | celulas | trades | acerto% | pts/op (media ponderada) |")
print("|---|---|---|---|---|---|---|")
for fam in ("E1", "E3"):
    for T in (250, 500, 750):
        for base in ("m1", "tick"):
            a = P[base]["agg"]; ks = [k for k in a if k[0] == T and k[1] == fam]
            n = sum(a[k][0] for k in ks); sm = sum(a[k][1] for k in ks); w = sum(a[k][2] for k in ks)
            print(f"| {fam} | {T} | {'M1' if base=='m1' else 'ticks'} | {len(ks)} | {n} | {f(100*w/max(n,1))} | {f(sm/max(n,1))} |")
