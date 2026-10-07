"""base.py -- universo de candidatos, features (biblioteca de variantes) e rotulos. WIN 2026 (aquecimento nov-dez/2025).
Rotulo olha o futuro; features so usam velas M1 com indice <= t (e M5/M15/H1 completas)."""
from __future__ import annotations
import sys, datetime as dt
import numpy as np, pandas as pd

KIT = "C:/Users/Jeffe/Documents/study/meta/scripts/daytrade/win_pernadas_exploracao/rodada2/chave"
sys.path.insert(0, KIT)
import kit_pernadas as K  # noqa

PASTA = "C:/Users/Jeffe/Documents/study/meta/scripts/daytrade/win_pernadas_exploracao/rodada7/entradas_ideais/"
TSV = PASTA + "m1_2026.tsv"
INICIO = "2026-01-01"

# grade de rotulo
NS = (3, 5, 7, 10, 15)
PISOS = (0.5, 1.0, 1.5)
KS = (3, 4, 5, 7, 10)
MS = (100, 150, 250, 375)
SS = (5, 15, 30)
STOP_MIN = 100.0
TTL = 5
CUSTO = 2.0
DESLIZE = 5.0
TICK = 5.0
REF = dict(N=5, piso=1.0, K=5, m=150, S=15)


def dst_eua(d: dt.date) -> bool:
    def nth_sunday(y, mth, n):
        d0 = dt.date(y, mth, 1)
        off = (6 - d0.weekday()) % 7
        return d0 + dt.timedelta(days=off + 7 * (n - 1))
    return nth_sunday(d.year, 3, 2) <= d < nth_sunday(d.year, 11, 1)


def carregar() -> pd.DataFrame:
    df = pd.read_csv(TSV, sep="\t")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    df["ts"] = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    df = df[(df.ts.dt.hour >= 9) & (df.ts.dt.hour < 17)].set_index("ts")
    out = df[["open", "high", "low", "close", "tickvol"]].astype(float)
    out["vol"] = out["tickvol"]
    out["dia"] = out.index.normalize()
    out["analise"] = out.index >= INICIO
    return out


def _roll_dia(s: pd.Series, dia: pd.Series, w: int, fn: str, minp: int = 5) -> np.ndarray:
    g = s.groupby(dia.values).rolling(w, min_periods=minp)
    r = getattr(g, fn)()
    return r.values


def estado_zz(m1: pd.DataFrame) -> pd.DataFrame:
    """Estado do zigzag 750 causal ao fim de cada minuto (so 2026), com extras (idade da perna, ordem do recuo, fundo)."""
    d = m1[m1["analise"]]
    out = []
    for dia, g in d.groupby("dia"):
        zz = K._ZZ()
        t0 = g.index[0]
        last_key = None
        recuo_max = 0.0
        trough = np.nan
        prev_trough = np.nan
        ordem = 0
        for ts_, o, h, l, c in zip(g.index, g["open"], g["high"], g["low"], g["close"]):
            pts = (l, h) if c >= o else (h, l)
            for p in pts:
                zz.passo(ts_, p)
            s = zz.estado(c)
            if s["E"] != s["E"]:
                out.append(dict(ts=ts_, edir=0))
                continue
            key = (s["E"], s["edir"])
            ed = s["edir"]
            lowhigh = l if ed == 1 else h
            if last_key is None or key != last_key:
                if last_key is not None and last_key[1] == ed:
                    prev_trough = trough
                    if recuo_max >= 100:
                        ordem += 1
                else:
                    prev_trough = np.nan
                    ordem = 0
                trough = lowhigh
                recuo_max = 0.0
                last_key = key
            else:
                trough = min(trough, lowhigh) if ed == 1 else max(trough, lowhigh)
                recuo_max = max(recuo_max, s["recuo"])
            leg_start = zz.piv_t if (zz.dir != 0 and zz.piv_t is not None) else t0
            out.append(dict(ts=ts_, edir=ed, E=s["E"], recuo=s["recuo"], leg=s["leg_ate_E"],
                            perna_conf=s["perna_conf"], n_piv=s["n_piv"], recuo_max=recuo_max, ordem=ordem,
                            leg_age=(ts_ - leg_start).total_seconds() / 60,
                            E_age=(ts_ - s["E_t"]).total_seconds() / 60 if s["E_t"] is not None else np.nan,
                            fundo_dif=(trough - prev_trough) * ed if prev_trough == prev_trough else np.nan))
    return pd.DataFrame(out).set_index("ts")


def construir_features(m1: pd.DataFrame) -> pd.DataFrame:
    """Biblioteca de variantes (todas NAO assinadas pela direcao; a assinatura vem no candidato). Indexada em m1 inteiro."""
    idx = m1.index
    dia = m1["dia"]
    f = pd.DataFrame(index=idx)
    mi = (idx.hour - 9) * 60 + idx.minute
    f["mi"] = mi
    rng = m1["high"] - m1["low"]
    tv = m1["tickvol"]
    c, o, h, l = m1["close"], m1["open"], m1["high"], m1["low"]
    # relogio
    dstv = np.array([dst_eua(x.date()) for x in idx])
    f["hora"] = idx.hour + idx.minute / 60
    f["hora_aj"] = f["hora"] - np.where(dstv, 0.0, 1.0)
    f["manha"] = (f["hora_aj"] < 11).astype(float)
    f["tarde"] = (f["hora_aj"] >= 13).astype(float)
    f["m0030"] = (idx.minute % 30 == 0).astype(float)
    # referencias por minuto do dia
    byminute = lambda s, w, mp: s.groupby(mi).transform(lambda x: x.shift(1).rolling(w, min_periods=mp).mean())
    ref20 = byminute(rng, 20, 10)
    ref5 = byminute(rng, 5, 3)
    tvref20 = byminute(tv, 20, 10)
    r1 = rng / ref20.replace(0, np.nan)
    f["atr5_m5"] = np.nan
    for tf in ("M5", "M15"):
        r = K.reamostrar(m1, tf)
        a5 = K._alinha(K._atr_completas(r, 5), idx)
        f[f"atr5_{tf}"] = a5.values
        ref = a5.groupby(mi).transform(lambda x: x.shift(1).rolling(5, min_periods=3).mean())
        f[f"rh_{tf}"] = a5 / ref
    r5 = K.reamostrar(m1, "M5")
    f["atr14_M5"] = K._alinha(K._atr_completas(r5, 14), idx).values
    f["vol30_300"] = rng.rolling(30, min_periods=30).mean() / rng.rolling(300, min_periods=300).mean()
    for w in (5, 10, 15, 30, 60):
        f[f"onda_{w}"] = _roll_dia(rng, dia, w, "mean") / _roll_dia(ref5, dia, w, "mean")
    for w in (5, 10, 20, 30):
        f[f"vela_{w}"] = _roll_dia(r1.fillna(1.0), dia, w, "max", 1)
    for w in (10, 20, 30, 60):
        f[f"caixa_{w}"] = _roll_dia(h, dia, w, "max") - _roll_dia(l, dia, w, "min")
    # ATR M1 do horario (piso do stop): media do range M1 do mesmo bloco de 30 min nos 20 pregoes anteriores
    blk = mi // 30
    s = rng.groupby([dia.values, blk]).mean().unstack()
    hist = s.rolling(20, min_periods=5).mean().shift(1).stack()
    f["atr1"] = hist.reindex(pd.MultiIndex.from_arrays([dia.values, blk])).values
    # vwap / dia
    tp = (h + l + c) / 3
    pv = (tp * tv).groupby(dia.values).cumsum() / tv.groupby(dia.values).cumsum()
    f["vwap"] = pv.values
    f["dvwap"] = (c - pv) / f["atr14_M5"]
    for w in (15, 30, 60):
        f[f"sub_{w}"] = (c - c.groupby(dia.values).shift(w)).values
    hid = h.groupby(dia.values).cummax()
    lod = l.groupby(dia.values).cummin()
    f["hi_dia"], f["lo_dia"] = hid.values, lod.values
    f["range_dia"] = (hid - lod).values
    f["pos_dia"] = ((c - lod) / (hid - lod).replace(0, np.nan)).values
    # micro / fluxo
    up = np.sign(c - o)
    for w in (5, 10, 15, 20):
        f[f"saldo_{w}"] = _roll_dia(up, dia, w, "sum")
    body = tv * (c - o) / rng.replace(0, np.nan)
    for w in (5, 10, 30):
        f[f"dcorpo_{w}"] = _roll_dia(body.fillna(0), dia, w, "sum") / _roll_dia(tv, dia, w, "sum")
        f[f"tvr_{w}"] = _roll_dia(tv, dia, w, "mean") / _roll_dia(tvref20, dia, w, "mean")
    # medias
    sets = {"s1": (9, 21, 50), "s2": (8, 20, 50), "s3": (10, 30, 60), "s4": (12, 26, 72)}
    for tf in ("M5", "M15", "H1"):
        r = K.reamostrar(m1, tf)
        atr = K._alinha(K._atr_completas(r, 14), idx)
        for nm, (pa, pb, pc) in sets.items():
            ea, eb, ec = (r["close"].ewm(span=p, adjust=False).mean() for p in (pa, pb, pc))
            for nome, ser in (("a", ea), ("b", eb), ("c", ec)):
                ser.index = r["fim"]
                f[f"_ema_{tf}_{nm}_{nome}"] = K._alinha(ser, idx).values
            a, b, cc = (f[f"_ema_{tf}_{nm}_{x}"] for x in "abc")
            f[f"emaal_{tf}_{nm}"] = (np.sign(a - b) + np.sign(b - cc)) / 2
            f[f"emadi_{tf}_{nm}"] = (c - b) / atr
        f = f.drop(columns=[x for x in f.columns if x.startswith(f"_ema_{tf}")])
    # dia
    dfd = pd.DataFrame({"hi": hid, "lo": lod, "o": o, "c": c, "dia": dia.values})
    daily = dfd.groupby("dia").agg(hi=("hi", "last"), lo=("lo", "last"), o=("o", "first"), c=("c", "last"))
    atr_d = (daily["hi"] - daily["lo"]).rolling(5, min_periods=3).mean().shift(1)
    gap = daily["o"] - daily["c"].shift(1)
    f["atr_d"] = atr_d.reindex(dia.values).values
    f["gap_atr"] = (gap / atr_d).reindex(dia.values).values
    f["rdia"] = f["range_dia"] / f["atr_d"]
    f["dow"] = idx.dayofweek.values.astype(float)
    return f


# ----------------------------------------------------------------- rotulos
def _mirror(hi, lo, op, cl):
    return -lo, -hi, -op, -cl


def rotular_cand(i, day_end, day_start, hi, lo, alta, cl, atr1):
    """Rotulos para uma entrada LONG (arrays ja espelhados se for short) em todos (N, piso, K).
    Retorna (y[N,P,K], pnl[N,P,K], ex[N,P,K]); y=-1 sem preenchimento."""
    nN, nP, nK = len(NS), len(PISOS), len(KS)
    y = np.full((nN, nP, nK), -1, np.int8)
    pnl = np.zeros((nN, nP, nK), np.float32)
    ex = np.zeros((nN, nP, nK), np.int32)
    L = cl[i]
    end_f = min(i + TTL, day_end)
    if end_f <= i:
        return y, pnl, ex
    fl = lo[i + 1:end_f + 1] <= L - TICK
    if not fl.any():
        return y, pnl, ex
    j = i + 1 + int(fl.argmax())
    pre_ok = alta[j]
    a1 = atr1[i]
    for a, N in enumerate(NS):
        ext = lo[max(i - N + 1, day_start):i + 1].min()
        for b, piso in enumerate(PISOS):
            R = max(L - ext, STOP_MIN, (piso * a1) if a1 == a1 else 0.0)
            Sl = L - R
            Lo_r, Hi_r = lo[j + 1:day_end + 1], hi[j + 1:day_end + 1]
            stop_j = lo[j] <= Sl
            if Lo_r.size:
                sh = Lo_r <= Sl
                si = (j + 1 + int(sh.argmax())) if sh.any() else 10**9
            else:
                si = 10**9
            if stop_j:
                si = j
            for k, Kx in enumerate(KS):
                T = L + Kx * R + TICK
                ti = 10**9
                if not stop_j and pre_ok and hi[j] >= T:
                    ti = j
                elif Hi_r.size:
                    th = Hi_r >= T
                    if th.any():
                        ti = j + 1 + int(th.argmax())
                if ti < si:
                    y[a, b, k], pnl[a, b, k], ex[a, b, k] = 1, Kx * R - CUSTO, ti
                elif si < 10**9:
                    y[a, b, k], pnl[a, b, k], ex[a, b, k] = 0, -(R + DESLIZE + CUSTO), si
                else:
                    y[a, b, k], pnl[a, b, k], ex[a, b, k] = 0, cl[day_end] - L - CUSTO, day_end
    return y, pnl, ex


def construir_universo():
    m1 = carregar()
    f = construir_features(m1)
    st = estado_zz(m1)
    # indices globais
    pos = pd.Series(np.arange(len(m1)), index=m1.index)
    dia_codes = pd.factorize(m1["dia"])[0]
    last_idx = pd.Series(np.arange(len(m1))).groupby(dia_codes).transform("max").values
    first_idx = pd.Series(np.arange(len(m1))).groupby(dia_codes).transform("min").values
    # fim do pregao simulado = ultima barra ate 16:59
    F = f.join(st, how="inner")
    F = F[F["edir"] != 0]
    mi = F["mi"].values
    sel = (mi >= 15) & (mi <= 7 * 60) & (mi % 5 == 0) & (F["recuo"].values >= min(MS))
    C = F[sel].copy()
    C["gi"] = pos.reindex(C.index).values
    gi = C["gi"].values.astype(int)
    C["day_end"], C["day_start"] = last_idx[gi], first_idx[gi]
    C["dia"] = m1["dia"].reindex(C.index).values
    C["mes"] = C.index.month
    C["close"] = m1["close"].reindex(C.index).values
    hi, lo, op, cl = (m1[x].values for x in ("high", "low", "open", "close"))
    atr1 = f["atr1"].values
    alta = cl >= op
    mh, ml, mo, mc = _mirror(hi, lo, op, cl)
    malta = cl < op
    nC = len(C)
    Y = np.full((nC, len(NS), len(PISOS), len(KS), 2), -1, np.int8)
    PN = np.zeros((nC, len(NS), len(PISOS), len(KS), 2), np.float32)
    EX = np.zeros((nC, len(NS), len(PISOS), len(KS), 2), np.int32)
    edir = C["edir"].values
    for n in range(nC):
        i, de, ds, d = gi[n], C["day_end"].values[n], C["day_start"].values[n], edir[n]
        # d=+1 (perna de alta): a favor = long ; contra = short
        for dd, lado in ((0, d), (1, -d)):
            if lado == 1:
                r = rotular_cand(i, de, ds, hi, lo, alta, cl, atr1)
            else:
                r = rotular_cand(i, de, ds, mh, ml, malta, mc, atr1)
            Y[n, ..., dd], PN[n, ..., dd], EX[n, ..., dd] = r
    return m1, f, C, Y, PN, EX


if __name__ == "__main__":
    import time, pickle
    t = time.time()
    m1, f, C, Y, PN, EX = construir_universo()
    print("cand", len(C), "tempo", time.time() - t, flush=True)
    with open(PASTA + "universo.pkl", "wb") as fh:
        pickle.dump(dict(C=C, Y=Y, PN=PN, EX=EX), fh)
    m1.to_pickle(PASTA + "m1.pkl")
    print("salvo", flush=True)
