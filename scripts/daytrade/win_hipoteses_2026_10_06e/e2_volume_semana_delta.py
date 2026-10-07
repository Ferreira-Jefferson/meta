"""E2 — (3) volume relativo ao MESMO HORARIO E MESMO DIA DA SEMANA (metodo WinVolumeRazao.mq5) e
(4) saldo agressor estimado (delta) do M1, sobre WinCincoMedias v2.02 (WIN M30, so' 2026).
Regras: so' velas FECHADAS (barra do sinal t usa dados ate' o fechamento de t); normalizacoes e quantis so' com passado;
so' 2026. Controle de preco: v -> range (h-l) ou |c-o| (delta: v -> |c-o|). Onde nao ha' historico o filtro e' neutro.
Spec: ("a", kind, x, Dias, modo, q) | ("b", x, Dias, fb, Q) | ("bh", x, Q) | ("d", est, ctrl, N, L) | ("dv", est, ctrl, N, L2)
"""
from __future__ import annotations
import sys, pickle
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import win_cinco_medias as W

OUT = Path(__file__).resolve().parent
MEIA_VIDA = 4.0
QA = (0.5, 0.6, 0.7, 0.8)
QB = (0.5, 0.4, 0.3, 0.2)


# ---------------- volume do mesmo horario e dia da semana ----------------
def _medpond(vals, meia_vida):
    """vals[0] = mais recente. Mediana ponderada, peso 0,5^(k/meia_vida) (igual ao indicador)."""
    v = np.asarray(vals, float); w = 0.5 ** (np.arange(len(v)) / meia_vida)
    o = np.argsort(v, kind="stable"); v, w = v[o], w[o]
    cw = np.cumsum(w)
    return v[min(np.searchsorted(cw, 0.5 * w.sum() - 1e-12), len(v) - 1)]


def serie(d, x):
    return {"v": d["v"], "rng": d["h"] - d["l"], "corpo": (d["c"] - d["o"]).abs()}[x].astype(float)


def razao_semana(s: pd.Series, dias: int, meia_vida=MEIA_VIDA) -> pd.Series:
    """s / mediana ponderada das ultimas `dias` ocorrencias VALIDAS (>0) do mesmo (dia da semana, horario),
    so' anteriores. Menos de `dias` -> NaN (como o indicador: nao calcula com menos)."""
    out = pd.Series(np.nan, index=s.index)
    chave = s.index.dayofweek * 10000 + s.index.hour * 100 + s.index.minute
    vals = s.values; res = np.full(len(s), np.nan)
    for k in np.unique(chave):
        ix = np.flatnonzero(chave == k)          # ordem cronologica
        hist = []                                # mais recente primeiro
        for i in ix:
            if len(hist) >= dias:
                m = _medpond(hist[:dias], meia_vida)
                res[i] = vals[i] / m if m > 0 else np.nan
            if vals[i] > 0:
                hist.insert(0, vals[i])
    out[:] = res
    return out


def mediana_hora20(s, d, N=20):
    hh = pd.Series(d.index.time, index=d.index)
    return s.groupby(hh).transform(lambda z: z.shift(1).rolling(N, min_periods=W.VOL_MIN_PREG).median())


def qpast(f, q, minp=40):
    a = f.values; out = np.full(len(a), np.nan)
    for t in range(minp, len(a)):
        p = a[:t]; p = p[~np.isnan(p)]
        if len(p) >= minp:
            out[t] = np.quantile(p, q)
    return out


# ---------------- caches por processo ----------------
_C = {}
def full():
    if "d" not in _C:
        d = W.carregar(2026); d = W.colunas_volume(d); _C["d"] = d
    return _C["d"]


def razao_cache(x, dias):
    k = ("r", x, dias)
    if k not in _C:
        _C[k] = razao_semana(serie(full(), x), dias)
    return _C[k]


def feat_a(kind, x, dias):
    r = razao_cache(x, dias)
    if kind == "sinal":
        return r
    if kind == "ant3":     # media das 3 velas ANTERIORES (t-3..t-1), sem a vela do sinal
        return r.shift(1).rolling(3, min_periods=3).mean()
    raise ValueError(kind)


def ok_limiar(feat, modo, q):
    th = qpast(feat, q)
    a = feat.values
    with np.errstate(invalid="ignore"):
        ok = (a >= th) if modo == "alto" else (a <= th)
    return np.where(np.isnan(a) | np.isnan(th), True, ok)


# ---------------- delta ----------------
def delta_m30():
    if "dm" in _C:
        return _C["dm"]
    m1 = W.carregar(2026, "1min")
    amp = (m1["h"] - m1["l"]).replace(0, np.nan)
    corpo = m1["c"] - m1["o"]
    f = (corpo / amp).fillna(0.0)
    cols = {
        "prop0": m1["v"] * f, "sinal0": np.sign(corpo) * m1["v"],
        "prop1": corpo.abs() * f, "sinal1": corpo,
        "den0": m1["v"], "den1": corpo.abs(),
    }
    g = pd.DataFrame(cols).resample("30min").sum()
    _C["dm"] = g
    return g


def delta_norm(d, est, ctrl, N):
    g = delta_m30().reindex(d.index)
    nu, de = g[f"{est}{ctrl}"], g[f"den{ctrl}"]
    sn = nu.rolling(N, min_periods=N).sum(); sd = de.rolling(N, min_periods=N).sum()
    return (sn / sd.replace(0, np.nan)).values


def construir(d, spec):
    t = spec[0]
    if t == "a":
        _, kind, x, dias, modo, q = spec
        f = feat_a(kind, x, dias)
        ok = pd.Series(ok_limiar(f, modo, q), index=f.index).reindex(d.index).fillna(True).values
        return ok, ok
    if t == "d":
        _, est, ctrl, N, L = spec
        D = delta_norm(d, est, ctrl, N)
        with np.errstate(invalid="ignore"):
            okc, oks = D >= L, D <= -L
        return np.where(np.isnan(D), True, okc), np.where(np.isnan(D), True, oks)
    if t == "dv":
        _, est, ctrl, N, L2 = spec
        D = delta_norm(d, est, ctrl, N)
        dpx = (d["c"] - d["c"].shift(N)).values
        with np.errstate(invalid="ignore"):
            bloq_c = (dpx > 0) & (D < -L2)
            bloq_v = (dpx < 0) & (D > L2)
        return ~bloq_c, ~bloq_v
    raise ValueError(t)


def dados_saida(spec):
    """d com 'vrel' substituido (so' a saida por climax de volume muda)."""
    d = full().copy()
    if spec[0] == "b":
        _, x, dias, fb, Q = spec
        r = razao_cache(x, dias)
        base = serie(d, x) / mediana_hora20(serie(d, x), d)
        d["vrel"] = r.where(r.notna(), base) if fb == "fb" else r
    elif spec[0] == "bh":
        _, x, Q = spec
        s = serie(d, x); d["vrel"] = s / mediana_hora20(s, d)
    return d


def rodar(spec):
    d = full()
    if spec is None:
        W.SAIDA_VOL_Q = 0.90
        df, r = W.rodar_janelas(2026, dados=d)
    elif spec[0] in ("b", "bh"):
        W.SAIDA_VOL_Q = spec[-1]
        df, r = W.rodar_janelas(2026, dados=dados_saida(spec))
    else:
        W.SAIDA_VOL_Q = 0.90
        df, r = W.rodar_janelas(2026, dados=d, extra=lambda dd: construir(dd, spec))
    return spec, r, df.liquido.tolist(), df.janela.tolist()


def specs():
    L = []
    for x in ("v", "rng", "corpo"):
        for dias in (4, 8, 12):
            for kind in ("sinal", "ant3"):
                for q in QA: L.append(("a", kind, x, dias, "alto", q))
                for q in QB: L.append(("a", kind, x, dias, "baixo", q))
        for dias in (4, 8, 12):
            for fb in ("puro", "fb"):
                for Q in (0.85, 0.90, 0.95): L.append(("b", x, dias, fb, Q))
    for x in ("rng", "corpo"):
        for Q in (0.85, 0.90, 0.95): L.append(("bh", x, Q))
    for Q in (0.85, 0.95): L.append(("bh", "v", Q))
    for ctrl in (0, 1):
        for est in ("prop", "sinal"):
            for N in (1, 2, 4, 8):
                for Lm in (0.0, 0.05, 0.1, 0.2): L.append(("d", est, ctrl, N, Lm))
            for N in (2, 4, 8):
                for L2 in (0.0, 0.05): L.append(("dv", est, ctrl, N, L2))
    return L


def eh_controle(sp):
    if sp[0] == "a": return sp[2] in ("rng", "corpo")
    if sp[0] == "b": return sp[1] in ("rng", "corpo")
    if sp[0] == "bh": return sp[1] in ("rng", "corpo")
    return bool(sp[2])


def main():
    S = [None] + specs()
    print(f"variantes (sem baseline): {len(S)-1}", flush=True)
    res = {}
    with ProcessPoolExecutor(max_workers=6) as ex:
        fs = [ex.submit(rodar, s) for s in S]
        for f in as_completed(fs):
            sp, r, liq, jan = f.result(); res[sp] = (r, liq, jan)
            print(sp, r["liquido"], r["janelas_pos"], r["trades"], flush=True)
    pickle.dump(res, open(OUT / "e2_res.pkl", "wb"))
    base = res[None]; bl = np.array(base[1])
    rows = []
    for sp, (r, liq, jan) in res.items():
        if sp is None: continue
        rows.append(dict(spec=str(sp), fam=sp[0], ctrl=eh_controle(sp),
                         liquido=r["liquido"], janelas=r["janelas_pos"], pior=r["pior"], PF=r["PF"], trades=r["trades"],
                         DD=r["maior_DD"], sem_set=r["liquido_sem_set"],
                         meses_melhor=int((np.array(liq) > bl + 1e-9).sum()), meses_pior=int((np.array(liq) < bl - 1e-9).sum()),
                         mensal=";".join(f"{v:.0f}" for v in liq)))
    T = pd.DataFrame(rows)
    T.to_csv(OUT / "e2_resultado.csv", index=False)
    print("\nBASELINE", base[0], flush=True); print(base[2], base[1])
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 1000)
    print(T.drop(columns="mensal").to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
