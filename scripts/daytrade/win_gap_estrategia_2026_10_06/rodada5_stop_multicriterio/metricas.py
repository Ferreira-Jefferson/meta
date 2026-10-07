import pickle, numpy as np, pandas as pd
from pathlib import Path
OUT = Path(__file__).resolve().parent / "out"
STOPS = [300, 400, 500, 600, 700, 800, 900, 1000, 1200, 1500]
JANS = ["2022", "2023", "2024", "2025", "2026"]
CUSTO = 2.0

def metr(tr, cap=1000.0):
    t = sorted(tr, key=lambda x: x["saida"])
    saldo, pico, dd, ddp, mn, quebra, xs, datas = cap, cap, 0.0, 0.0, cap, None, [], []
    for r in t:
        x = r["rs"] - CUSTO * r["qtd"]
        saldo += x; xs.append(x); datas.append(r["saida"][:10]); mn = min(mn, saldo)
        pico = max(pico, saldo)
        if pico - saldo > dd: dd = pico - saldo
        ddp = max(ddp, (pico - saldo) / pico * 100)
        if saldo <= 0:
            quebra = r["saida"][:10]; break
    xs = np.array(xs); n = len(xs)
    g, p = xs[xs > 0].sum(), -xs[xs < 0].sum()
    seq = mx = 0
    for x in xs:
        seq = seq + 1 if x < 0 else 0; mx = max(mx, seq)
    mes = pd.Series(xs, index=pd.to_datetime(datas).strftime("%Y-%m")).groupby(level=0).sum() if n else pd.Series(dtype=float)
    return dict(n=n, liq=xs.sum(), win=100 * (xs > 0).mean() if n else 0, wins=int((xs > 0).sum()),
                payoff=(xs[xs > 0].mean() / -xs[xs < 0].mean()) if (xs > 0).any() and (xs < 0).any() else np.nan,
                ganhos=g, perdas=p, pf=g / p if p else np.inf, dd=dd, ddp=ddp, rf=xs.sum() / dd if dd else np.inf, smin=mn,
                quebrou=quebra is not None, data_quebra=quebra, seqperd=mx, pior_mes=mes.min() if n else 0,
                mes_pos=100 * (mes > 0).mean() if n else 0, n_mes=len(mes))

def carrega():
    return {(s, j): metr(pickle.load(open(OUT / f"trades_{s}_{j}.pkl", "rb"))) for s in STOPS for j in JANS}

def agrega(M):
    A = {}
    for s in STOPS:
        w = [M[s, j] for j in JANS]
        liq = sum(x["liq"] for x in w); G = sum(x["ganhos"] for x in w); L = sum(x["perdas"] for x in w)
        A[s] = dict(rf_pool=liq / max(x["dd"] for x in w), rf_med=float(np.median([x["rf"] for x in w])),
                    pf=G / L, win=100 * sum(x["wins"] for x in w) / sum(x["n"] for x in w),
                    jan_pos=sum(x["liq"] > 0 for x in w), pior_liq=min(x["liq"] for x in w),
                    seq=max(x["seqperd"] for x in w), pior_ddp=max(x["ddp"] for x in w),
                    quebra=any(x["quebrou"] for x in w), liq=liq, n=sum(x["n"] for x in w))
    return A

def ranking(A):
    df = pd.DataFrame(A).T
    spec = [("rf_pool", False, 1), ("rf_med", False, 1), ("pf", False, 1), ("win", False, 1), ("jan_pos", False, 1),
            ("pior_liq", False, 1), ("seq", True, 1), ("pior_ddp", True, 1)]
    df["score"] = sum(w * df[c].astype(float).rank(ascending=asc, method="average") for c, asc, w in spec) / 8.0
    sc = df.score.values; fin = []
    for i in range(len(sc)):
        viz = [sc[k] for k in (i - 1, i, i + 1) if 0 <= k < len(sc)]
        fin.append(np.mean(viz))
    df["final"] = fin
    df["pos"] = df["final"].rank(method="min")
    elegiveis = df[~df.quebra.astype(bool)]
    escolhido = int(elegiveis.sort_values(["final"], kind="stable").index[0]) if len(elegiveis) else None
    if len(elegiveis):
        mn = elegiveis.final.min(); escolhido = int(min(elegiveis.index[np.isclose(elegiveis.final, mn)]))
    return df, escolhido
