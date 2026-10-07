"""f3: indicadores (filtro de entrada e saida) para o WinCincoMedias v2.02. So' velas FECHADAS ate' a barra do sinal t.
Funciona com qualquer ano. simula2 = copia EXATA de win_cinco_medias.simula (gerada por texto) + parametro saida_extra."""
import sys, inspect
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import win_cinco_medias as W


def _make_simula2():
    src = inspect.getsource(W.simula)
    src = src.replace("def simula(", "def simula2(", 1)
    src = src.replace("aperta=(STOP_APERTA_N, STOP_APERTA_K)):", "aperta=(STOP_APERTA_N, STOP_APERTA_K), saida_extra=None):", 1)
    a = "    idx = d.index[sel]\n"
    assert a in src
    src = src.replace(a, a + "    if saida_extra is not None:\n        _xl, _xs = saida_extra(d)\n        xl, xs = np.asarray(_xl, bool)[sel], np.asarray(_xs, bool)[sel]\n", 1)
    b = "            if sai:\n                fecha(o[t] - pos * TICK, t)"
    assert b in src
    src = src.replace(b, "            if not sai and saida_extra is not None:\n                sai = bool(xl[j]) if pos == 1 else bool(xs[j])\n" + b, 1)
    exec(src, W.__dict__)
    W.simula = W.simula2


def ativar():
    if not hasattr(W, "simula2"):
        _make_simula2()


# ---------------- indicadores ----------------
def rsi(c, n):
    dl = c.diff()
    up = dl.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-dl.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def atr(d, n):
    pc = d["c"].shift()
    tr = pd.concat([d["h"] - d["l"], (d["h"] - pc).abs(), (d["l"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def stoch_k(d, n):
    hh, ll = d["h"].rolling(n).max(), d["l"].rolling(n).min()
    return 100 * (d["c"] - ll) / (hh - ll).replace(0, np.nan)


def macd_hist(c, f, s, g):
    m = c.ewm(span=f, adjust=False).mean() - c.ewm(span=s, adjust=False).mean()
    return m - m.ewm(span=g, adjust=False).mean()


def trix(c, n):
    e = c.ewm(span=n, adjust=False).mean().ewm(span=n, adjust=False).mean().ewm(span=n, adjust=False).mean()
    return 100 * e.pct_change()


def adx_di(d, n=14):
    up = d["h"].diff(); dn = -d["l"].diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(d, n)
    pdi = 100 * pd.Series(pdm, index=d.index).ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / a
    mdi = 100 * pd.Series(mdm, index=d.index).ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return pdi, mdi, dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def aroon(d, n=25):
    """Aroon up/down: 100*(n - barras desde a maxima/minima das ultimas n+1)/n"""
    up = d["h"].rolling(n + 1).apply(lambda x: 100 * np.argmax(x) / n, raw=True)
    dn = d["l"].rolling(n + 1).apply(lambda x: 100 * np.argmin(x) / n, raw=True)
    return up, dn


def supertrend(d, n, m):
    a = atr(d, n).values; h, l, c = d["h"].values, d["l"].values, d["c"].values
    N = len(c); dirr = np.zeros(N, int); fu = np.full(N, np.nan); fl = np.full(N, np.nan)
    hl2 = (h + l) / 2
    cur = 0
    for i in range(N):
        if np.isnan(a[i]):
            continue
        bu, bl = hl2[i] + m * a[i], hl2[i] - m * a[i]
        if i == 0 or np.isnan(fu[i - 1]):
            fu[i], fl[i] = bu, bl
            cur = 1 if c[i] >= hl2[i] else -1
        else:
            fu[i] = bu if (bu < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
            fl[i] = bl if (bl > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
            if cur == 1 and c[i] < fl[i]:
                cur = -1
            elif cur == -1 and c[i] > fu[i]:
                cur = 1
        dirr[i] = cur
    return pd.Series(dirr, index=d.index)


def psar(d, af0, afm):
    h, l = d["h"].values, d["l"].values; N = len(h)
    st = np.zeros(N, int)
    if N < 3:
        return pd.Series(st, index=d.index)
    bull = True; ep = h[0]; sar = l[0]; af = af0; st[0] = 1
    for i in range(1, N):
        sar = sar + af * (ep - sar)
        if bull:
            sar = min(sar, l[i - 1], l[i - 2] if i >= 2 else l[i - 1])
            if l[i] < sar:
                bull = False; sar = ep; ep = l[i]; af = af0
            elif h[i] > ep:
                ep = h[i]; af = min(af + af0, afm)
        else:
            sar = max(sar, h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if h[i] > sar:
                bull = True; sar = ep; ep = h[i]; af = af0
            elif l[i] < ep:
                ep = l[i]; af = min(af + af0, afm)
        st[i] = 1 if bull else -1
    return pd.Series(st, index=d.index)


def vwap_dia(d):
    tp = (d["h"] + d["l"] + d["c"]) / 3; v = d["v"].astype(float)
    dia = d.index.normalize()
    return (tp * v).groupby(dia).cumsum() / v.groupby(dia).cumsum()


def st_h1(d, n, m):
    """Supertrend em H1 usando so' barras H1 JA' FECHADAS na vela M30 do sinal."""
    h1 = d.resample("60min").agg({"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"}).dropna()
    s = supertrend(h1, n, m)
    fl = d.index.floor("60min")
    cur = s.reindex(fl).values; prev = s.shift(1).reindex(fl).values
    return pd.Series(np.where(d.index.minute == 30, cur, prev), index=d.index).fillna(0).astype(int)


def _sim(a, b):
    return np.asarray(pd.Series(a).fillna(False), bool), np.asarray(pd.Series(b).fillna(False), bool)


def _lastk(x, k):          # evento ocorreu em alguma das ultimas k barras (inclui t)
    return pd.Series(np.asarray(x, float)).rolling(k, min_periods=1).max().values > 0


# ---------------- filtros de entrada: cada um (d)->(ok_compra, ok_venda) ----------------
def F(tipo, *p):
    def f(d):
        c = d["c"]
        if tipo == "rsi_nao_estica":      # n, L : compra se RSI<L ; venda se RSI>100-L
            n, L = p; r = rsi(c, n)
            return _sim(r < L, r > 100 - L)
        if tipo == "rsi_forca":           # RSI do lado a favor de L
            n, L = p; r = rsi(c, n)
            return _sim(r > L, r < 100 - L)
        if tipo == "rsi_recuo":           # min RSI nas ultimas k <= X e RSI subindo
            n, k, X = p; r = rsi(c, n)
            mn = r.rolling(k).min(); mx = r.rolling(k).max()
            return _sim((mn <= X) & (r > r.shift()), (mx >= 100 - X) & (r < r.shift()))
        if tipo == "stoch_nao_estica":
            n, L = p; k = stoch_k(d, n)
            return _sim(k < L, k > 100 - L)
        if tipo == "stoch_cruza":         # K>D (D=SMA3 de K) a favor
            n, = p; k = stoch_k(d, n); dd = k.rolling(3).mean()
            return _sim(k > dd, k < dd)
        if tipo == "stoch_recuo":
            n, k_, X = p; k = stoch_k(d, n)
            return _sim((k.rolling(k_).min() <= X) & (k > k.shift()), (k.rolling(k_).max() >= 100 - X) & (k < k.shift()))
        if tipo == "macd_a_favor":        # f,s,g,modo: 'h' hist>0 ; 'hs' hist>0 e subindo
            fa, s, g, modo = p; h = macd_hist(c, fa, s, g)
            if modo == "h":
                return _sim(h > 0, h < 0)
            return _sim((h > 0) & (h > h.shift()), (h < 0) & (h < h.shift()))
        if tipo == "macd_cruza":          # hist virou a favor nas ultimas k barras
            fa, s, g, k = p; h = macd_hist(c, fa, s, g)
            return _sim((h > 0) & _lastk((h > 0) & (h.shift() <= 0), k), (h < 0) & _lastk((h < 0) & (h.shift() >= 0), k))
        if tipo == "trix":                # n, modo 'pos' trix>0 ; 'sobe' trix subindo ; 'ambos'
            n, modo = p; t = trix(c, n)
            if modo == "pos":
                return _sim(t > 0, t < 0)
            if modo == "sobe":
                return _sim(t > t.shift(), t < t.shift())
            return _sim((t > 0) & (t > t.shift()), (t < 0) & (t < t.shift()))
        if tipo == "boll_pos":            # %B nao esticado: compra se %B < L
            n, L = p; m = c.rolling(n).mean(); s = c.rolling(n).std(ddof=0)
            b = (c - (m - 2 * s)) / (4 * s)
            return _sim(b < L, b > 1 - L)
        if tipo == "boll_rompe":          # fechou fora da banda a favor nas ultimas k barras
            n, k = p; m = c.rolling(n).mean(); s = c.rolling(n).std(ddof=0)
            return _sim(_lastk(c > m + 2 * s, k), _lastk(c < m - 2 * s, k))
        if tipo == "boll_larg":           # largura relativa a media de 50: modo 'exp' (>r) ou 'con' (<r)
            n, r_, modo = p; m = c.rolling(n).mean(); s = c.rolling(n).std(ddof=0)
            w = 4 * s / m; rel = w / w.rolling(50).mean()
            ok = (rel > r_) if modo == "exp" else (rel < r_)
            return _sim(ok, ok)
        if tipo == "atr_ratio":           # ATR(5)/ATR(20) >r ('alto') ou <r ('baixo')
            r_, modo = p; q = atr(d, 5) / atr(d, 20)
            ok = (q > r_) if modo == "alto" else (q < r_)
            return _sim(ok, ok)
        if tipo == "keltner":             # EMA20 +/- 1.5 ATR10 : 'dentro' = nao fechou alem da banda; 'fora' = fechou alem
            modo, = p; m = c.ewm(span=20, adjust=False).mean(); a = atr(d, 10)
            if modo == "dentro":
                return _sim(c < m + 1.5 * a, c > m - 1.5 * a)
            return _sim(c > m + 1.5 * a, c < m - 1.5 * a)
        if tipo == "adx_di":              # modo 'di' DI+>DI- ; 'adx' ADX>L ; 'sobe' ADX subindo (3 barras)
            modo, L = p; pdi, mdi, a = adx_di(d, 14)
            if modo == "di":
                return _sim(pdi > mdi, mdi > pdi)
            if modo == "adx":
                ok = a > L; return _sim(ok, ok)
            ok = a > a.shift(3); return _sim(ok, ok)
        if tipo == "di_adx":
            L, = p; pdi, mdi, a = adx_di(d, 14)
            return _sim((pdi > mdi) & (a > L), (mdi > pdi) & (a > L))
        if tipo == "aroon":
            L, = p; u, dn = aroon(d, 25)
            return _sim((u > L) & (u > dn), (dn > L) & (dn > u))
        if tipo == "st_m30":
            n, m = p; s = supertrend(d, n, m)
            return _sim(s == 1, s == -1)
        if tipo == "st_h1":
            n, m = p; s = st_h1(d, n, m)
            return _sim(s == 1, s == -1)
        if tipo == "vwap_lado":
            v = vwap_dia(d)
            return _sim(c > v, c < v)
        if tipo == "vwap_dist":           # (c-vwap)/ATR14: 'max' = do lado certo e nao esticado (<L); 'min' = distancia a favor >L
            L, modo = p; v = vwap_dia(d); z = (c - v) / atr(d, 14)
            if modo == "max":
                return _sim((c > v) & (z < L), (c < v) & (-z < L))
            return _sim(z > L, -z > L)
        raise ValueError(tipo)
    return f


# ---------------- saidas: cada um (d)->(sai_compra, sai_venda) estado contra ----------------
def S(tipo, *p):
    def f(d):
        c = d["c"]
        if tipo == "rsi_abaixo":          # n,X : compra sai se RSI<X ; venda sai se RSI>100-X
            n, X = p; r = rsi(c, n)
            return _sim(r < X, r > 100 - X)
        if tipo == "rsi_vira":            # n,H : RSI estava >H na barra anterior e caiu
            n, H = p; r = rsi(c, n)
            return _sim((r.shift() > H) & (r < r.shift()), (r.shift() < 100 - H) & (r > r.shift()))
        if tipo == "st":
            n, m = p; s = supertrend(d, n, m)
            return _sim(s == -1, s == 1)
        if tipo == "st_h1":
            n, m = p; s = st_h1(d, n, m)
            return _sim(s == -1, s == 1)
        if tipo == "psar":
            a0, am = p; s = psar(d, a0, am)
            return _sim(s == -1, s == 1)
        if tipo == "macd":
            fa, s_, g = p; h = macd_hist(c, fa, s_, g)
            return _sim(h < 0, h > 0)
        raise ValueError(tipo)
    return f


def frac_passa(f, d):
    est = W.alinhamento(d)
    oc, ov = f(d)
    return float(np.concatenate([oc[est == 1], ov[est == -1]]).mean())


def frac_saida(f, d):
    """taxa de inicio (false->true) por barra do estado de saida -- usada pelo controle aleatorio"""
    xl, xs = f(d)
    on = lambda x: ((x & ~np.concatenate([[False], x[:-1]])).mean())
    return float((on(xl) + on(xs)) / 2)


def rand_entrada(p, seed):
    def f(d):
        r = np.random.default_rng(seed)
        return r.random(len(d)) < p, r.random(len(d)) < p
    return f


def rand_saida(q, seed):
    def f(d):
        r = np.random.default_rng(seed)
        return r.random(len(d)) < q, r.random(len(d)) < q
    return f
