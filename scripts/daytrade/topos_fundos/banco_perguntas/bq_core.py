"""Banco de perguntas: dados, features causais (so velas fechadas ate a vela i) e utilitarios.
Cada pergunta devolve codigo int8 por vela (-1 = indefinida) para o lado COMPRA da 'visao'; a venda e a mesma funcao
aplicada a visao espelhada (preco -> -preco). Nao sabe de que estrategia a pergunta veio."""
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
RAIZ = Path(r"C:\Users\Jeffe\Documents\study\meta")
sys.path.insert(0, str(RAIZ / "scripts/daytrade/topos_fundos"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dados, filtros, indicadores as ind  # noqa
import perguntas as bancoC  # noqa

_WDO = None
def wdo15():
    global _WDO
    if _WDO is None:
        w = pd.read_csv(RAIZ / "data/wdo-mt5/WDO@D_M1_202109290900_202609291020.csv", sep="\t")
        w.index = pd.to_datetime(w["<DATE>"] + " " + w["<TIME>"], format="%Y.%m.%d %H:%M:%S")
        _WDO = w.resample("15min").agg({"<OPEN>": "first", "<CLOSE>": "last"}).dropna()
        _WDO.columns = ["o", "c"]
    return _WDO


def vistas(per):
    """b (DataFrame original) e as visoes compra (+1) e espelhada/venda (-1)."""
    b = dados.m15(per)
    atrd = bancoC.atr_diario(per).reindex(b.dia).to_numpy()
    w = wdo15().reindex(b.index)
    out = {}
    for lado, s in ((1, 1.0), (-1, -1.0)):
        v = pd.DataFrame(index=b.index)
        if lado == 1:
            v["open"], v["high"], v["low"], v["close"] = b.open, b.high, b.low, b.close
        else:
            v["open"], v["high"], v["low"], v["close"] = -b.open, -b.low, -b.high, -b.close
        v["vol"] = b.real_volume.astype(float); v["atr"] = b.atr; v["ad"] = atrd; v["dia"] = b.dia
        v["wdo"] = s * w["c"]; v["wdoo"] = s * w["o"]
        out[lado] = v
    return b, out


def perfil(tp, vol, d, bin_=100.0):
    """POC acumulado do dia (inclui a vela atual) e (VAH,VAL) do dia inteiro por id de dia. bins de 100 pts."""
    n = len(tp); poc = np.full(n, np.nan); va = {}
    for k in np.unique(d):
        ix = np.where(d == k)[0]
        bins = np.floor(tp[ix] / bin_).astype(np.int64)
        base = bins.min(); H = np.zeros(int(bins.max() - base + 1))
        for j, i in enumerate(ix):
            H[bins[j] - base] += vol[i]
            poc[i] = (H.argmax() + base + .5) * bin_
        if H.sum() > 0:
            p = H.argmax(); lo = hi = p; acc = H[p]; tgt = 0.7 * H.sum()
            while acc < tgt and (lo > 0 or hi < len(H) - 1):
                up = H[hi + 1] if hi < len(H) - 1 else -1; dn = H[lo - 1] if lo > 0 else -1
                if up >= dn: hi += 1; acc += H[hi]
                else: lo -= 1; acc += H[lo]
            va[k] = ((hi + base + 1) * bin_, (lo + base) * bin_)
        else:
            va[k] = (np.nan, np.nan)
    return poc, va


def derive(v):
    F = {}
    o, h, l, c, vol, a, ad = v.open, v.high, v.low, v.close, v.vol, v.atr, v.ad
    d = v.dia.values; idx = v.index
    mins = pd.Series(idx.hour * 60 + idx.minute, idx)
    F.update(o=o, h=h, l=l, c=c, vol=vol, a=a, ad=ad, mins=mins)
    g = lambda s: s.groupby(d)
    tod = g(c).cumcount(); F["tod"] = tod
    F["nrest"] = g(c).transform("size") - tod - 1
    dop = g(o).transform("first"); F["dop"] = dop
    dhi = g(h).cummax(); dlo = g(l).cummin(); F["dhi"], F["dlo"] = dhi, dlo
    ids = pd.Index(sorted(set(d)))
    dd = pd.DataFrame(dict(O=g(o).first(), H=g(h).max(), L=g(l).min(), C=g(c).last())).reindex(ids)
    dmap = lambda s: pd.Series(s.reindex(d).to_numpy(), idx)
    prev = lambda s, k=1: dmap(s.shift(k))
    F["pdo"], F["pdh"], F["pdl"], F["pdc"] = prev(dd.O), prev(dd.H), prev(dd.L), prev(dd.C)
    F["pd2h"], F["pd2l"] = prev(dd.H, 2), prev(dd.L, 2)
    rngd = dd.H - dd.L; mn7 = rngd.rolling(7).min()
    F["nr7"] = prev((rngd == mn7).astype(float).where(mn7.notna()))
    F["h10"] = prev(dd.H.rolling(10).max())
    F["dmm20"] = prev(dd.C.rolling(20).mean())
    F["mom5"] = prev(dd.C) - prev(dd.C, 6)
    ret = dd.C.diff()
    F["tresq"] = prev(((ret < 0) & (ret.shift(1) < 0) & (ret.shift(2) < 0)).astype(float).where(ret.shift(2).notna()))
    F["gap"] = dop - F["pdc"]
    for nome, per in (("wop", idx.to_period("W")), ("mop", idx.to_period("M"))):
        F[nome] = o.groupby(np.asarray(per.astype(str))).transform("first")
    tp = (h + l + c) / 3
    cv = g(vol).cumsum(); F["vwap"] = g(tp * vol).cumsum() / cv.replace(0, np.nan)
    poc, va = perfil(tp.to_numpy(), vol.to_numpy(), d)
    F["poc"] = pd.Series(poc, idx)
    F["pval"] = dmap(pd.Series({k: x[1] for k, x in va.items()}).reindex(ids).shift(1))
    F["pvah"] = dmap(pd.Series({k: x[0] for k, x in va.items()}).reindex(ids).shift(1))
    dl = c.diff(); up = dl.clip(lower=0).ewm(alpha=1/14, adjust=False).mean(); dn = (-dl).clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    F["rsi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    pdm = (h - h.shift()).clip(lower=0).where((h - h.shift()) > (l.shift() - l), 0.0)
    mdm = (l.shift() - l).clip(lower=0).where((l.shift() - l) > (h - h.shift()), 0.0)
    atrw = tr.ewm(alpha=1/14, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=1/14, adjust=False).mean() / atrw; mdi = 100 * mdm.ewm(alpha=1/14, adjust=False).mean() / atrw
    F["pdi"], F["mdi"] = pdi, mdi
    F["adx"] = (100 * (pdi - mdi).abs() / (pdi + mdi)).ewm(alpha=1/14, adjust=False).mean()
    mac = ind.mme(c, 12) - ind.mme(c, 26); F["hist"] = mac - ind.mme(mac, 9)
    s20 = c.rolling(20).mean(); sd20 = c.rolling(20).std(); F["s20"], F["sd20"] = s20, sd20
    wid = 4 * sd20 / s20.abs(); mw = wid.rolling(100).min()
    F["sqz"] = (wid <= 1.1 * mw).astype(float).where(mw.notna())
    F["e38"], F["e50"], F["m200"] = ind.mme(c, 38), ind.mme(c, 50), c.rolling(200).mean()
    F["m17"], F["m34"], F["m72o"] = ind.mms(c, 17), ind.mms(c, 34), ind.mms(o, 72)
    F["e9"], F["e21"], F["e34"] = ind.mme(c, 9), ind.mme(c, 21), ind.mme(c, 34)
    F["stoch"] = ind.estocastico(v, 14, 3)
    mk = mins.values
    F["rv"] = vol / vol.groupby(mk).transform(lambda s: s.shift(1).rolling(20).mean())
    F["rvd"] = cv / cv.groupby(mk).transform(lambda s: s.shift(1).rolling(20).mean())
    F["orh"] = g(h.where(tod < 4)).transform("max"); F["orl"] = g(l.where(tod < 4)).transform("min")
    F["r30"] = g((c - dop).where(tod == 1, 0.0)).transform("sum")
    shf = (h > h.shift(1)) & (h > h.shift(2)) & (h > h.shift(-1)) & (h > h.shift(-2))
    slf = (l < l.shift(1)) & (l < l.shift(2)) & (l < l.shift(-1)) & (l < l.shift(-2))
    ch = h.where(shf).shift(2); cl = l.where(slf).shift(2)
    F["lsh"], F["lsl"] = ch.ffill(), cl.ffill()
    F["psh"] = ch.dropna().shift(1).reindex(idx).ffill(); F["psl"] = cl.dropna().shift(1).reindex(idx).ffill()
    c1 = c.resample("60min").last().dropna(); t1 = ind.tendencia(c1).to_numpy(); f1 = (c1.index + pd.Timedelta("60min")).values
    i1 = np.searchsorted(f1, idx.values, side="right") - 1
    F["h1"] = pd.Series(np.where(i1 >= 0, t1[np.maximum(i1, 0)], 0), idx)
    t4, f4 = filtros.tendencia_h4(v)
    i4 = np.searchsorted(f4, idx.values + np.timedelta64(15, "m"), side="right") - 1
    F["h4"] = pd.Series(np.where(i4 >= filtros.AQUECIMENTO_H4, t4[np.maximum(i4, 0)], np.nan), idx)
    F["wdo"], F["wdoo"] = v.wdo, v.wdoo
    F["wdo_dop"] = pd.Series(v.wdoo.groupby(d).transform("first").to_numpy(), idx)
    return F


def cod(cond, valid=None):
    r = np.asarray(cond, bool).astype(np.int8)
    if valid is not None: r = np.where(np.asarray(valid, bool), r, -1).astype(np.int8)
    return r


def nn(*xs):
    m = np.ones(len(xs[0]), bool)
    for x in xs: m &= ~np.isnan(np.asarray(x, float))
    return m


def cat(vals, cuts, valid):
    r = np.digitize(np.asarray(vals, float), cuts).astype(np.int8)
    return np.where(valid, r, -1).astype(np.int8)
