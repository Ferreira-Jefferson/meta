"""extra.py <per> : (1) terciis de ATR(5 pregoes anteriores) ; (2) nulo RAW (velas cruas embaralhadas) x CHAIN, T750 d5."""
import sys
import numpy as np, pandas as pd
from lib import *

per = sys.argv[1]
T, div = 750, 5
(rec, trd), nulls = carrega(T, div, per)
NR = [n[0] for n in nulls]; NT = [n[1] for n in nulls]
raw = carrega_raw(T, div, per)
# limiares de ATR: tercis na DESCOBERTA (fixos)
(rd, _), _n = carrega(T, div, "desc")
q1, q2 = rd.drop_duplicates("dia").atr.quantile([1 / 3, 2 / 3])
print(f"tercis ATR (descoberta): {q1:.1f} {q2:.1f}", flush=True)


def tag(d):
    d["vol"] = np.where(d.atr < q1, "v1:baixa", np.where(d.atr < q2, "v2:media", "v3:alta"))
    return d


def S_(R):
    e = tag(R[R.elig & R.res.isin(["S", "M"])].copy()); e["val"] = (e.res == "S").astype(float); e["nul"] = (T - T / div) / T; return e


def P1(Tr):
    e = tag(Tr[(Tr.j == 1) & Tr.elig & Tr.first_ok.notna()].copy()); e["val"] = e.first_ok; e["nul"] = e.risk / e.r; return e


def G5(Tr):
    e = tag(Tr[Tr.elig].copy()); e["val"] = (e.mfe >= 5).astype(float); e["nul"] = 1 / 6; return e


pd.set_option("display.width", 200)
for nome, fn, A_, N_ in (("P(recuo supera | confirmado)", S_, rec, NR), ("P(supera de primeira)", P1, trd, NT), ("P(alvo 5R antes do stop)", G5, trd, NT)):
    c = compara(fn(A_), [fn(x) for x in N_], ["vol"], "val", "nul")
    mostra(c, f"E1  {nome} por tercil de ATR")
    o = open(f"out_txt/extra_{per}.txt", "a", encoding="utf-8"); o.write(f"\n## {nome} por tercil ATR\n" + c.round(3).to_string() + "\n"); o.close()

# alcance medio por tercil
AL = tag(rec[rec.elig & (rec.causa_fim != "fim")].copy()); AL["v"] = AL.alcance / T
ALN = [tag(n[n.elig & (n.causa_fim != "fim")].copy().assign(v=lambda d: d.alcance / T)) for n in NR]
c = compara(AL, ALN, ["vol"], "v", ic=False)
mostra(c, "E1d  alcance (em T) a partir do topo do recuo por tercil de ATR")
open(f"out_txt/extra_{per}.txt", "a", encoding="utf-8").write("\n## alcance por ATR\n" + c.round(3).to_string() + "\n")

# raw x chain
rows = []
def met(R, Tr):
    out = {}
    e = R[R.elig & R.res.isin(["S", "M"])]
    out["P(S|conf)"] = (e.res == "S").mean()
    j1 = Tr[(Tr.j == 1) & Tr.elig & Tr.first_ok.notna()]
    out["P(1a)"] = j1.first_ok.mean()
    S2 = R[R.elig & (R.res == "S")].sort_values(["dia", "sgn", "ep", "k_total"])
    g = S2.groupby(["dia", "sgn", "ep"], sort=False)
    S2 = S2.assign(nxd=g["depth"].shift(-1), nxk=g["k_total"].shift(-1))
    S2 = S2[S2.nxk == S2.k_total + 1]
    out["P(r2<r1)"] = (S2[S2.k == "1"].nxd < S2[S2.k == "1"].depth).mean()
    tr = Tr[Tr.elig & (Tr.j == 1)]
    for K in (3, 5, 10):
        out[f"P({K}R)"] = (tr.mfe >= K).mean()
    out["trios cresc"] = np.nan
    out["gap candles (media pts)"] = np.nan
    return out
rr = met(rec, trd)
mc = pd.DataFrame([met(a, b) for a, b in nulls]); mr = pd.DataFrame([met(a, b) for a, b in raw])
t = pd.DataFrame({"real": pd.Series(rr), "chain(40)": mc.mean(), "sd_chain": mc.std(), "raw(10)": mr.mean(), "sd_raw": mr.std()}).dropna(how="all")
mostra(t, "E2  nulo CHAIN (reconstroi precos encadeando) x RAW (velas cruas embaralhadas) - T750 m150")
open(f"out_txt/extra_{per}.txt", "a", encoding="utf-8").write("\n## raw x chain\n" + t.round(3).to_string() + "\n")
