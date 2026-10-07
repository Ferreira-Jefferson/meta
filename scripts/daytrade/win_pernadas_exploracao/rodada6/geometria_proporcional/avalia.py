import json, os, pickle, sys
import numpy as np
import detail as D, stage as st, geomlib as G
HERE = os.path.dirname(os.path.abspath(__file__))
fr = json.load(open(os.path.join(HERE, "congelado_ANTES_da_confirmacao.json")))["celulas"]
R = {}
for w in ("desc", "conf", "set"):
    fb = os.path.join(HERE, f"built_{w}.pkl")
    if not os.path.exists(fb): continue
    win, built, dates = pickle.load(open(fb, "rb"))
    nd = len(win); W = D.boot_W(nd)
    nulls = []
    fg = os.path.join(HERE, f"grid_{w}.pkl")
    if os.path.exists(fg):
        g = pickle.load(open(fg, "rb")); nulls = [v for s, v in g.items() if s > 0]
    for i, c in enumerate(fr):
        for mode in (0, 1):
            tr = D.cell_trades(built, win, c["T"], c["fam"], c["g"], c["filt"], mode)
            s = D.stats(tr, nd, W)
            if s is not None and mode == 0:
                fi = st.FAMS.index(c["fam"])
                nm = []
                for a in nulls:
                    k = (a[:, 0] == c["T"]) & (a[:, 1] == fi) & (a[:, 2] == c["g"]) & (a[:, 3] == c["filt"])
                    nm.append(a[k, 5][0] if k.any() else np.nan)
                nm = np.array(nm, float)
                if len(nm):
                    s["nulo_mean"] = float(np.nanmean(nm)); s["nulo_p"] = float((nm >= s["mean"]).sum() + 1) / (np.isfinite(nm).sum() + 1)
            R[(w, i, mode)] = (s, tr)
pickle.dump(R, open(os.path.join(HERE, "avalia.pkl"), "wb"))
def f(x, n=1): return "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{n}f}".replace(".", ",")
for mode, nome in ((0, "CONSERVADOR"), (1, "OTIMISTA")):
    print(f"\n### {nome}\n")
    print("| # | celula | janela | ordens | n | fill% | acerto% | BE emp% | nulo p0% | pts/op | IC95 | t | nulo analit. | nulo emb. (p) | seq perdas | op/dia | payoff nom/real | stop% |")
    print("|" + "---|" * 18)
    for i, c in enumerate(fr):
        for w in ("desc", "conf", "set"):
            if (w, i, mode) not in R or R[(w, i, mode)][0] is None: continue
            s = R[(w, i, mode)][0]
            print(f"| {i+1} | T{c['T']} {c['geom']} / {c['filtro']} | {w} | {s['n_orders']} | {s['n']} | {f(100*s['fill'],0)} | {f(100*s['acerto'])} | {f(100*s['be'])} | {f(100*s['p0'])} | {f(s['mean'])} | [{f(s['lo'],0)}; {f(s['hi'],0)}] | {f(s['t'],2)} | {f(s['null_exp'])} | {f(s.get('nulo_mean'))} ({f(s.get('nulo_p'),3)}) | {s['maxstreak']} | {f(s['opd'],2)} | {f(s['payoff_nom'])}/{f(s['payoff_real'])} | {f(100*s['stop_pct'],0)} |")
