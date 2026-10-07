"""Experimentos: padrão das correções dentro das pernadas do WIN e fator que normaliza entre dias.

Pernada = zigzag sobre máximas/mínimas das velas do gráfico (mesma regra da página).
Correção = todo recuo de >= 1 tick (5 pts) dentro da pernada seguido de novo extremo,
medido em % do tamanho TOTAL da pernada (pctLeg) e em % do avanço até ali (retrAdv).
"""
import sys, json, math
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed

ARQ = r"C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
TFS = {"M5": "5min", "M15": "15min", "H1": "60min"}
TICK = 5


def carrega():
    df = pd.read_csv(ARQ, sep="\t")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    df["ts"] = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    return df.set_index("ts")[["open", "high", "low", "close", "vol"]]


def dias_tf(m1, rule):
    r = m1.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "vol": "sum"}).dropna()
    out = {}
    for d, g in r.groupby(r.index.date):
        if len(g) >= 3:
            out[str(d)] = g[["open", "high", "low", "close", "vol"]].to_numpy(float)
    return out


def caminho(b):
    o, h, l, c = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
    bull = c >= o
    p = np.empty(2 * len(b)); i = np.repeat(np.arange(len(b)), 2)
    p[0::2] = np.where(bull, l, h); p[1::2] = np.where(bull, h, l)
    return p, i


def zigzag(p, thr):
    piv = []; d = 0; hi = lo = 0; ext = 0
    for k in range(len(p)):
        x = p[k]
        if d == 0:
            if x > p[hi]: hi = k
            if x < p[lo]: lo = k
            if p[hi] - p[lo] >= thr:
                if lo < hi: piv.append(lo); d = 1; ext = hi
                else: piv.append(hi); d = -1; ext = lo
        elif d == 1:
            if x > p[ext]: ext = k
            elif p[ext] - x >= thr: piv.append(ext); d = -1; ext = k
        else:
            if x < p[ext]: ext = k
            elif x - p[ext] >= thr: piv.append(ext); d = 1; ext = k
    if d != 0: piv.append(ext)
    return piv


def correcoes(p, a, b):
    s = 1 if p[b] > p[a] else -1; tot = abs(p[b] - p[a]); out = []
    rh = a; pm = None
    for k in range(a + 1, b + 1):
        if s * (p[k] - p[rh]) > 0:
            if pm is not None and s * (p[rh] - p[pm]) >= TICK:
                av = s * (p[rh] - p[a]); dep = s * (p[rh] - p[pm])
                out.append((dep / tot * 100, dep / av * 100 if av > 0 else np.nan, av / tot * 100))
            rh = k; pm = None
        elif pm is None or s * (p[k] - p[pm]) < 0:
            pm = k
    return out


def analisa(b, thr):
    p, _ = caminho(b); piv = zigzag(p, thr); legs = []
    for j in range(len(piv) - 1):
        a, c = piv[j], piv[j + 1]
        legs.append((abs(p[c] - p[a]), j + 2 == len(piv), correcoes(p, a, c)))
    return legs


def features(dias):
    """Fatores por dia. Os *_prev usam só pregões ANTERIORES (disponíveis antes da abertura)."""
    ks = sorted(dias); rows = []
    for d in ks:
        b = dias[d]
        rows.append(dict(dia=d, rng=b[:, 1].max() - b[:, 2].min(), atr=(b[:, 1] - b[:, 2]).mean(),
                         open=b[0, 0], close=b[-1, 3]))
    f = pd.DataFrame(rows).set_index("dia")
    f["rng_prev5"] = f["rng"].shift(1).rolling(5).mean()
    f["atr_prev5"] = f["atr"].shift(1).rolling(5).mean()
    f["gap"] = (f["open"] - f["close"].shift(1)).abs()
    return f


FATORES = ["pts", "pct_preco", "atr_prev5", "rng_prev5", "atr_mesmo_dia"]


def limiar(fator, k, f, d):
    r = f.loc[d]
    return {"pts": k, "pct_preco": k * r["open"] / 100, "atr_prev5": k * r["atr_prev5"],
            "rng_prev5": k * r["rng_prev5"], "atr_mesmo_dia": k * r["atr"]}[fator]


def roda(dias, f, fator, k, sel):
    return {d: analisa(dias[d], limiar(fator, k, f, d)) for d in sel}


def stats_dia(res):
    rows = []
    for d, legs in res.items():
        cs = [c for _, _, cc in legs for c in cc]
        pl = np.array([c[0] for c in cs]) if cs else np.array([np.nan])
        rows.append(dict(dia=d, legs=len(legs), corr_por_leg=len(cs) / max(len(legs), 1),
                         med_pctleg=np.nanmedian(pl), p90_pctleg=np.nanpercentile(pl, 90) if cs else np.nan))
    return pd.DataFrame(rows).set_index("dia")


def cv(x):
    x = pd.Series(x).dropna(); return x.std() / x.mean() if x.mean() else np.nan


def unidade(tf, fator, alvo_legs_dia):
    m1 = carrega(); dias = dias_tf(m1, TFS[tf]); f = features(dias)
    sel = [d for d in sorted(dias) if not np.isnan(f.loc[d, "atr_prev5"])]
    if fator == "pts":
        k = 300.0
    else:  # calibra k para ter o mesmo nº médio de pernadas/dia que 300 pts fixos
        amostra = sel[::5]
        lo, hi = {"pct_preco": (0.01, 2.0), "atr_prev5": (0.1, 20), "rng_prev5": (0.005, 1.0),
                  "atr_mesmo_dia": (0.1, 20)}[fator]
        for _ in range(14):
            k = math.sqrt(lo * hi)
            n = np.mean([len(v) for v in roda(dias, f, fator, k, amostra).values()])
            if n > alvo_legs_dia: lo = k
            else: hi = k
        k = math.sqrt(lo * hi)
    res = roda(dias, f, fator, k, sel)
    s = stats_dia(res)
    s["mes"] = [d[:7] for d in s.index]
    mens = s.groupby("mes")[["legs", "corr_por_leg", "med_pctleg"]].mean()
    return dict(tf=tf, fator=fator, k=k, legs_dia=s.legs.mean(),
                cv_legs=cv(s.legs), cv_corr=cv(s.corr_por_leg), cv_med=cv(s.med_pctleg),
                cv_mes_legs=cv(mens.legs), cv_mes_corr=cv(mens.corr_por_leg), cv_mes_med=cv(mens.med_pctleg))


if __name__ == "__main__":
    # alvo: pernadas/dia médias com 300 pts fixos, por gráfico (medido antes, nos 5 anos)
    m1 = carrega(); alvo = {}
    for tf, rule in TFS.items():
        dias = dias_tf(m1, rule); f = features(dias)
        sel = [d for d in sorted(dias) if not np.isnan(f.loc[d, "atr_prev5"])]
        alvo[tf] = np.mean([len(analisa(dias[d], 300)) for d in sel[::5]])
        print(f"alvo {tf}: {alvo[tf]:.2f} pernadas/dia com 300 pts", flush=True)
    out = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(unidade, tf, fa, alvo[tf]) for tf in TFS for fa in FATORES]
        for fu in as_completed(futs):
            r = fu.result(); out.append(r)
            print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)
    pd.DataFrame(out).to_csv(sys.argv[1], index=False)
