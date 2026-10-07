"""Checagem com TICKS (mar-jun): re-rotula as geometrias congeladas com o caminho real de negocios e compara com o M1."""
import json, sys, time
import numpy as np, pandas as pd
from lib import *
from pipe import *
from base import TICK, TTL, CUSTO, DESLIZE, STOP_MIN

TICKS = "C:/Users/Jeffe/Documents/study/meta/data/cache_win_ticks/WIN@D/"
C, Y, PN, EX = carregar()
X = construir_X(C)
m1 = pd.read_pickle(PASTA + "m1.pkl")
cong = json.load(open(PASTA + "congelado_ANTES_da_confirmacao.json"))["modelos"]
mes = C.mes.values; mi = C["mi"].values; recuo = C["recuo"].values; dias = C.dia.values
hi, lo = m1["high"].values, m1["low"].values
pos = {t: i for i, t in enumerate(m1.index)}
gi_all = np.array([pos[t] for t in C.index])
atr1 = C["atr1"].values  # nao esta em C? (fallback abaixo)


def dia_ticks(d):
    df = pd.read_pickle(TICKS + f"{d:%Y-%m-%d}.pkl")
    t = df["time_msc"].to_numpy(); p = df["last"].to_numpy()
    k = np.r_[True, p[1:] != p[:-1]]
    return t[k], p[k]


def rotula_tick(T, P, off, i_ms, L, R, Kx, lado, end_ms):
    """lado=+1 long / -1 short. Preços ja ajustados (P+off). Retorna (y, pnl) ou (-1, 0) se sem fill."""
    a = np.searchsorted(T, i_ms)
    b = np.searchsorted(T, i_ms + TTL * 60000)
    if b <= a:
        return -1, 0.0
    seg = P[a:b]
    fl = seg <= L - TICK if lado > 0 else seg >= L + TICK
    if not fl.any():
        return -1, 0.0
    j = a + int(fl.argmax())
    e = np.searchsorted(T, end_ms)
    rest = P[j + 1:e]
    Sl = L - lado * R
    Tg = L + lado * (Kx * R + TICK)
    if lado > 0:
        sh, th = rest <= Sl, rest >= Tg
    else:
        sh, th = rest >= Sl, rest <= Tg
    si = int(sh.argmax()) if sh.any() else 10**9
    ti = int(th.argmax()) if th.any() else 10**9
    if ti < si:
        return 1, Kx * R - CUSTO
    if si < 10**9:
        return 0, -(R + DESLIZE + CUSTO)
    last = rest[-1] if len(rest) else seg[-1]
    return 0, lado * (last - L) - CUSTO


# precompute: ticks por dia e offset
dias_mj = sorted(set(pd.to_datetime(dias[(mes >= 3) & (mes <= 6)])))
cache = {}
t0 = time.time()
for d in dias_mj:
    T, P = dia_ticks(d)
    x = m1.loc[d:d + pd.Timedelta(hours=23)]
    ends = x.index.values.astype("datetime64[ms]").astype("int64") + 60000
    ii = np.clip(np.searchsorted(T, ends) - 1, 0, len(P) - 1)
    off = float(np.median(x["close"].values - P[ii]))
    cache[d] = (T, P + off, off)
print("ticks carregados", len(cache), "dias em", round(time.time() - t0), "s; offsets distintos:", len({round(v[2]) for v in cache.values()}), flush=True)

# atr1 por candidato: recompute rapido a partir do universo (coluna presente em C?)
atr1 = C["atr1"].values if "atr1" in C.columns else np.full(len(C), np.nan)

linhas = []
for nome, mod in cong.items():
    g = mod["geom"]
    a_, b_, k_ = NS.index(g["N"]), PISOS.index(g["piso"]), KS.index(g["K"])
    sel = (mes <= 6) & (recuo >= g["m"]) & (mi % g["S"] == 0) & (Y[:, a_, b_, k_, 0] >= 0)
    idx = np.where(sel)[0]
    ysel = Y[idx, a_, b_, k_, 0].astype(float); pn = PN[idx, a_, b_, k_, 0]; ms = mes[idx]
    oof = oof_lomo(X.loc[X.index[idx], mod["cols"]].values, ysel, ms, mod["lam"])
    res = []
    for r, n in enumerate(idx):
        if mes[n] < 3:
            res.append((np.nan, np.nan)); continue
        d = pd.Timestamp(dias[n])
        T, P, off = cache[d]
        i = gi_all[n]
        lado = int(C["edir"].values[n])
        L = m1["close"].values[i]
        ds = C["day_start"].values[n]; de = C["day_end"].values[n]
        if lado > 0:
            ext = lo[max(i - g["N"] + 1, ds):i + 1].min(); Rr = L - ext
        else:
            ext = hi[max(i - g["N"] + 1, ds):i + 1].max(); Rr = ext - L
        a1 = atr1[n]
        R = max(Rr, STOP_MIN, g["piso"] * a1 if a1 == a1 else 0.0)
        i_ms = int(m1.index[i].to_datetime64().astype("datetime64[ms]").astype("int64")) + 60000
        end_ms = int(m1.index[de].to_datetime64().astype("datetime64[ms]").astype("int64")) + 60000
        yt, pt = rotula_tick(T, P, off, i_ms, L, R, g["K"], lado, end_ms)
        res.append((yt, pt))
    res = np.array(res)
    ok = (ms >= 3) & ~np.isnan(oof) & (res[:, 0] >= 0) & (ysel >= 0)
    okm = (ms >= 3) & ~np.isnan(oof)
    yt, pt = res[:, 0], res[:, 1]
    fillm1 = float((ysel[okm] >= 0).mean())
    fillt = float((yt[okm] >= 0).mean())
    both = okm & (yt >= 0)
    th = np.quantile(oof[okm], 0.80)
    top = okm & (oof >= th) & (yt >= 0)
    top1 = okm & (oof >= th)
    row = dict(modelo=nome, geom=str(g), n_mar_jun=int(okm.sum()), fill_m1=fillm1, fill_ticks=fillt,
               base_m1=float(ysel[okm].mean()), base_ticks=float(yt[both].mean()),
               be_m1=breakeven_emp(pn[okm], ysel[okm]), be_ticks=breakeven_emp(pt[both], yt[both]),
               esp_m1=float(pn[okm].mean()), esp_ticks=float(pt[both].mean()),
               top20_n=int(top1.sum()), top20_acerto_m1=float(ysel[top1].mean()), top20_esp_m1=float(pn[top1].mean()),
               top20_acerto_ticks=float(yt[top].mean()), top20_be_ticks=breakeven_emp(pt[top], yt[top]),
               top20_esp_ticks=float(pt[top].mean()),
               concordancia=float((yt[both] == ysel[both]).mean()))
    linhas.append(row)
    print(row, flush=True)
pd.DataFrame(linhas).to_csv(PASTA + "checagem_ticks_marjun.csv", index=False)
