import pickle, numpy as np, pandas as pd
from pathlib import Path
OUT = Path(__file__).resolve().parent / "out"
STOPS = list(range(400, 1501, 100)); MULTS = [2, 3, 4, 0]; CUSTO = 5.0; MESES = ["2026-01", "2026-02", "2026-03", "2026-04"]
NOME = {2: "2x", 3: "3x", 4: "4x", 0: "sem"}
D = {(s, m): pickle.load(open(OUT / f"cel_{s}_{m}.pkl", "rb")) for s in STOPS for m in MULTS}

def metr(tr, cap=1000.0):
    t = sorted(tr, key=lambda x: x["saida"]); saldo = pico = cap; dd = ddp = 0.0; mn = cap; quebra = False; xs = []; ms = []; mot = []
    for r in t:
        x = r["rs"] - CUSTO * r["qtd"]; saldo += x; xs.append(x); ms.append(r["saida"][:7]); mot.append(r["motivo"]); mn = min(mn, saldo)
        pico = max(pico, saldo); dd = max(dd, pico - saldo); ddp = max(ddp, (pico - saldo) / pico * 100)
        if saldo <= 0: quebra = True; break
    xs = np.array(xs); n = len(xs); g = xs[xs > 0].sum(); p = -xs[xs < 0].sum()
    seq = mx = 0
    for x in xs: seq = seq + 1 if x < 0 else 0; mx = max(mx, seq)
    mes = pd.Series(xs, index=ms).groupby(level=0).sum().reindex(MESES).fillna(0.0)
    return dict(n=n, liq=xs.sum(), win=100 * (xs > 0).mean(), payoff=(xs[xs > 0].mean() / -xs[xs < 0].mean()) if (xs > 0).any() and (xs < 0).any() else np.nan,
                pf=g / p if p else np.inf, dd=dd, ddp=ddp, rf=xs.sum() / dd if dd else np.inf, pior=xs.min(), perda_med=xs[xs < 0].mean() if (xs < 0).any() else 0.0,
                seq=mx, ex_stop=mot.count("stop"), ex_alvo=mot.count("alvo"), ex_fl=mot.count("flatten"), jan=mes[MESES[0]], fev=mes[MESES[1]], mar=mes[MESES[2]], abr=mes[MESES[3]],
                meses_pos=int((mes > 0).sum()), pior_mes=mes.min(), rf_med=float(np.median(mes.values)) / dd if dd else np.inf, smin=mn, quebrou=quebra)

rows = []
for (s, m), d in D.items():
    r = metr(d["real"]); r.update(stop=s, mult=m); rows.append(r)
df = pd.DataFrame(rows).set_index(["mult", "stop"]).sort_index()
df["rf"] = df.rf.replace(np.inf, 99.0); df["rf_med"] = df.rf_med.replace(np.inf, 99.0)
spec = [("rf", False), ("rf_med", False), ("pf", False), ("win", False), ("meses_pos", False), ("pior_mes", False), ("seq", True), ("ddp", True)]
df["score"] = sum(df[c].astype(float).rank(ascending=a, method="average") for c, a in spec) / 8.0
fin = pd.Series(index=df.index, dtype=float)
for m in MULTS:
    sc = df.loc[m].score.values
    for i, s in enumerate(STOPS):
        fin[(m, s)] = np.mean([sc[k] for k in (i - 1, i, i + 1) if 0 <= k < len(sc)])
df["final"] = fin
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 50)
f = lambda x: f"{x:,.0f}".replace(",", ".")
L = []
L.append("== CELULAS (liquido apos R$5/saida a mercado) ==")
cols = ["n", "liq", "win", "payoff", "pf", "dd", "ddp", "rf", "pior", "perda_med", "seq", "ex_stop", "ex_alvo", "ex_fl", "jan", "fev", "mar", "abr", "smin", "quebrou", "score", "final"]
t = df[cols].reset_index(); t["mult"] = t.mult.map(NOME)
L.append(t.round(2).to_string(index=False))
for nome, c in (("LIQUIDO R$", "liq"), ("FATOR DE RECUPERACAO", "rf"), ("MAXDD %", "ddp")):
    L.append(f"\n== HEAT {nome} (linhas=stop) =="); h = df[c].unstack(0)[[2, 3, 4, 0]]; h.columns = [NOME[x] for x in h.columns]; L.append(h.round(2).to_string())
L.append("\n== RANKING TOP 10 (final suavizado, nao-quebra) ==")
el = df[~df.quebrou].reset_index().sort_values(["final", "stop"], kind="stable").head(10); el["mult"] = el.mult.map(NOME)
L.append(el[["mult", "stop", "final", "score", "n", "liq", "win", "payoff", "pf", "dd", "ddp", "rf", "pior", "perda_med", "seq", "ex_stop", "ex_alvo", "ex_fl", "jan", "fev", "mar", "abr", "smin"]].round(2).to_string(index=False))
top = el.iloc[0]; tm = {v: k for k, v in NOME.items()}[top["mult"]]; ts = int(top["stop"])
L.append(f"\nTOP: stop {ts} alvo {top['mult']}")
# ---- nulos: matriz por dia
def dia_pnl(tr): return {r["entrada"][:10]: r["rs"] - CUSTO for r in tr}
dias = sorted({d for v in D.values() for k in ("c", "v") for d in dia_pnl(v[k])})
for v in D.values():   # consistencia real x forcado
    pr = dia_pnl(v["real"]); 
    for d, x in pr.items(): assert x in (dia_pnl(v["c"]).get(d), dia_pnl(v["v"]).get(d))
cells = list(D)
A = np.zeros((len(cells), len(dias), 2))
for i, k in enumerate(cells):
    pc, pv = dia_pnl(D[k]["c"]), dia_pnl(D[k]["v"])
    for j, d in enumerate(dias): A[i, j, 0] = pc.get(d, 0.0); A[i, j, 1] = pv.get(d, 0.0)
rng = np.random.default_rng(20261006); N = 20000
S = rng.integers(0, 2, size=(N, len(dias)))
liq = np.zeros((N, len(cells))); rfn = np.zeros((N, len(cells)))
for i in range(len(cells)):
    x = np.where(S == 0, A[i, :, 0], A[i, :, 1])           # N x dias
    cs = 1000 + np.cumsum(x, axis=1); pk = np.maximum(1000, np.maximum.accumulate(cs, axis=1)); dd = (pk - cs).max(axis=1)
    liq[:, i] = x.sum(axis=1); rfn[:, i] = np.where(dd > 0, x.sum(axis=1) / np.where(dd > 0, dd, 1), 99)
it = cells.index((ts, tm)) if (ts, tm) in cells else None
it = [i for i, k in enumerate(cells) if k == (ts, tm)][0]
obs_l = df.loc[(tm, ts), "liq"]; obs_r = df.loc[(tm, ts), "rf"]
L.append(f"\nsinais/dias com trade em algum lado: {len(dias)}; sorteios {N}")
L.append(f"NULO celula top: liquido obs {obs_l:.0f}; nulo media {liq[:, it].mean():.0f} dp {liq[:, it].std():.0f}; p95 {np.percentile(liq[:, it], 95):.0f}; p(liq>=obs)={(liq[:, it] >= obs_l).mean():.4f}; p(RF>=obs)={(rfn[:, it] >= obs_r).mean():.4f}")
mx_l = liq.max(axis=1); mx_r = rfn.max(axis=1)
L.append(f"MAX-STAT 48 celulas: max nulo liquido media {mx_l.mean():.0f} p95 {np.percentile(mx_l, 95):.0f}; p_corrigido(liq>=obs)={(mx_l >= obs_l).mean():.4f}; p_corrigido(RF>=obs)={(mx_r >= obs_r).mean():.4f}")
# poder: sd por trade
x = np.array([r["rs"] - CUSTO for r in D[(ts, tm)]["real"]]); n = len(x)
L.append(f"PODER (celula top): n={n}, media/trade {x.mean():.1f}, dp/trade {x.std(ddof=1):.1f}, t={x.mean()/(x.std(ddof=1)/np.sqrt(n)):.2f}; efeito minimo detectavel 80% poder alfa 5% unilateral ~ {(1.645+0.84)*x.std(ddof=1)/np.sqrt(n):.0f} R$/trade ({(1.645+0.84)*x.std(ddof=1)*np.sqrt(n):.0f} R$ no total)")
open(OUT / "resultado.txt", "w", encoding="utf-8").write("\n".join(L)); print("\n".join(L))
df.to_csv(OUT / "celulas.csv")
