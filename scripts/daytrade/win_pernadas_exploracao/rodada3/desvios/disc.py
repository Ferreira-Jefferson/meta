from lib import *
import time
t0 = time.time()
days = load("2026.01.01", "2026.06.30")
tmp = {}
for d, g in days.items():
    rng = (g.high - g.low).values; t = g.time.values
    for i in range(30, len(g)):
        mm = int(t[i][3:5]); hr = int(t[i][:2])
        if mm % 5 == 4:
            tmp.setdefault((hr * 60 + mm + 1) // 15, []).append(rng[i - 29:i + 1].mean())
volmed = {k: float(np.median(v)) for k, v in tmp.items()}
json.dump(volmed, open("volmed.json", "w"))
ev = events(days, volmed)
print("eventos", len(ev), "dias", ev.dia.nunique(), flush=True)
ev.to_pickle("ev_desc.pkl")
base = basecols(ev)
dayidx = pd.factorize(ev.dia)[0]; nd = dayidx.max() + 1
rng = np.random.default_rng(1); B = 1000
W = np.stack([np.bincount(rng.integers(0, nd, nd), minlength=nd) for _ in range(B)]).astype(float)
cells = cellmasks(ev)
print("celulas", len(cells), "testes max", len(cells) * len(OUTS), flush=True)
res = []
for key, m in cells.items():
    if m.sum() < 200:
        continue
    for o in OUTS:
        if o in ('novaMax','novaMin') and any(d in ('dMaxDia','dMinDia','posRange','zRecuo') for d,_ in key):
            continue  # tautologia: perto do extremo, extremo novo e' quase certo
        s = stats_cell(ev, m, o, base, dayidx, W, nd)
        if s is None:
            continue
        n, ndias, p, pb, lo, hi = s
        res.append(dict(cell=key_str(key), k=len(key), out=o, n=n, dias=ndias, p=p, base=pb, diff=p - pb, lo=lo, hi=hi))
r = pd.DataFrame(res); r.to_pickle("res_desc.pkl")
print("testes com n>=200:", len(r), "celulas distintas", r.cell.nunique(), flush=True)
sig = r[(r.dias >= 30) & (r["diff"].abs() >= 0.10) & (np.sign(r.lo) == np.sign(r.hi)) & (r.lo != 0)].copy()
sig["marg"] = np.where(sig["diff"] > 0, sig.lo, -sig.hi)
sig = sig.sort_values("marg", ascending=False)
sig.to_csv("sig_desc.csv", index=False)
print("passam:", len(sig), "| esperados por acaso ~", round(len(r) * 0.005, 1), flush=True)
key2 = {key_str(k): m for k, m in cells.items()}
sel = []; masks = []; used = set()
for _, row in sig.iterrows():
    m = key2[row.cell]
    if row.cell in used:
        continue
    if any((m & mm).sum() / (m | mm).sum() > 0.5 for mm in masks):
        continue
    sel.append(row); masks.append(m); used.add(row.cell)
    if len(sel) >= 20:
        break
fz = pd.DataFrame(sel)
fz[["cell", "out", "n", "dias", "p", "base", "diff", "lo", "hi"]].to_csv("congelada.csv", index=False)
print(fz[["cell", "out", "n", "dias", "p", "base", "diff", "lo", "hi"]].round(3).to_string())
print("tempo", time.time() - t0)
