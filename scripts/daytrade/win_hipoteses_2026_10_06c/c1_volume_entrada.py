"""C1 — filtros de VOLUME de entrada sobre WinCincoMedias v2 (WIN M30, so' 2026).
Volume so' de velas FECHADAS (ate' t, a barra do sinal). Normalizacoes e quantis so' com passado
(shift(1) + expanding/rolling). Controle de preco: mesma construcao trocando v por range (h-l) ou |c-o|.
Onde nao ha' historico suficiente (aquecimento) o filtro e' neutro (ok=True).
"""
from __future__ import annotations
import sys, itertools, io, contextlib
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import win_cinco_medias as W

OUT = Path(__file__).resolve().parent
QA = (0.5, 0.6, 0.7, 0.8)      # ALTO: feat >= quantil q do passado
QB = (0.5, 0.4, 0.3, 0.2)      # BAIXO: feat <= quantil q do passado


def serie(d, x):
    return {"v": d["v"], "rng": d["h"] - d["l"], "corpo": (d["c"] - d["o"]).abs()}[x].astype(float)


def mesmo_horario(s, d, N):
    """mediana do mesmo horario nos N pregoes ANTERIORES."""
    hh = pd.Series(d.index.time, index=d.index)
    return s.groupby(hh).transform(lambda z: z.shift(1).rolling(N, min_periods=5).median())


def qpast(f, q, minp=40):
    """quantil q de f[0..t-1] (so' passado), por barra."""
    a = f.values; out = np.full(len(a), np.nan)
    for t in range(minp, len(a)):
        p = a[:t]; p = p[~np.isnan(p)]
        if len(p) >= minp:
            out[t] = np.quantile(p, q)
    return out


def limiar(feat, modo, q):
    th = qpast(feat, q)
    a = feat.values
    with np.errstate(invalid="ignore"):
        ok = (a >= th) if modo == "alto" else (a <= th)
    ok = np.where(np.isnan(a) | np.isnan(th), True, ok)
    return ok


def feature(d, kind, N, x):
    s = serie(d, x)
    if kind == "rel_barras":   # vs media das N velas anteriores
        return s / s.shift(1).rolling(N, min_periods=5).mean()
    if kind == "rel_hora":     # vs mediana do mesmo horario nos N dias anteriores
        return s / mesmo_horario(s, d, N)
    if kind == "cum_dia":      # acumulado do dia ate t vs mesmo horario dias anteriores
        cum = s.groupby(d.index.normalize()).cumsum()
        return cum / mesmo_horario(cum, d, N)
    if kind == "esforco":      # |c-o| / x   (x=v: esforco x resultado; x=rng: controle)
        corpo = (d["c"] - d["o"]).abs()
        den = s if x == "v" else (d["h"] - d["l"])
        return corpo / den.replace(0, np.nan)
    if kind == "esforco_hora":
        corpo = (d["c"] - d["o"]).abs()
        den = s if x == "v" else (d["h"] - d["l"])
        e = corpo / den.replace(0, np.nan)
        return e / mesmo_horario(e, d, N)
    raise ValueError(kind)


def contra(d, N, x, lado):
    """x[t] / media de x das velas CONTRA a tendencia entre as N ultimas (t-N..t-1). lado=+1 compra: contra = vela de baixa."""
    s = serie(d, x)
    cont = (d["c"] < d["o"]) if lado == 1 else (d["c"] > d["o"])
    num = (s.where(cont)).shift(1).rolling(N, min_periods=1).sum()
    cnt = cont.astype(float).shift(1).rolling(N, min_periods=1).sum()
    return s / (num / cnt.replace(0, np.nan))


def construir(d, spec):
    kind, N, modo, q, x = spec
    n = len(d)
    if kind == "crescente":
        s = serie(d, x)
        ok = (s > s.shift(1)) & (s.shift(1) > s.shift(2))
        if N == 3:
            ok &= s.shift(2) > s.shift(3)
        ok = ok.fillna(True).values if False else np.where(s.shift(N).isna(), True, ok.values)
        return ok, ok
    if kind == "contra":
        r = []
        for lado in (1, -1):
            f = contra(d, N, x, lado).values
            with np.errstate(invalid="ignore"):
                ok = (f >= q) if modo == "alto" else (f <= q)
            r.append(np.where(np.isnan(f), True, ok))
        return r[0], r[1]
    f = feature(d, kind, N, x)
    ok = limiar(f, modo, q)
    return ok, ok


def specs():
    L = []
    for x in ("v", "rng", "corpo"):
        for N in (10, 20):
            for kind in ("rel_barras", "rel_hora", "cum_dia"):
                for q in QA: L.append((kind, N, "alto", q, x))
                for q in QB: L.append((kind, N, "baixo", q, x))
        for k in (2, 3): L.append(("crescente", k, "-", 0, x))
        for N in (6, 12):
            for q in (1.0, 1.5): L.append(("contra", N, "alto", q, x))
            for q in (1.0, 0.67): L.append(("contra", N, "baixo", q, x))
    # esforco x resultado: so' volume (e controle range)
    for x in ("v", "rng"):
        for q in QA: L.append(("esforco", 0, "alto", q, x))
        for q in QB: L.append(("esforco", 0, "baixo", q, x))
        for N in (10, 20):
            for q in QA: L.append(("esforco_hora", N, "alto", q, x))
            for q in QB: L.append(("esforco_hora", N, "baixo", q, x))
    return L


_D = None
def rodar(spec):
    global _D
    if _D is None: _D = W.carregar(2026)
    if spec is None:
        df, r = W.rodar_janelas(2026, dados=_D)
    else:
        df, r = W.rodar_janelas(2026, dados=_D, extra=lambda d: construir(d, spec))
    return spec, r, df.liquido.tolist(), df.janela.tolist()


def main():
    S = [None] + specs()
    print(f"variantes (sem baseline): {len(S)-1}", flush=True)
    res = {}
    with ProcessPoolExecutor(max_workers=6) as ex:
        fs = [ex.submit(rodar, s) for s in S]
        for f in as_completed(fs):
            sp, r, liq, jan = f.result(); res[sp] = (r, liq, jan)
            print(sp, r["liquido"], r["janelas_pos"], r["trades"], flush=True)
    base = res[None]; bl = np.array(base[1])
    rows = []
    for sp, (r, liq, jan) in res.items():
        if sp is None: continue
        kind, N, modo, q, x = sp
        rows.append(dict(kind=kind, N=N, modo=modo, q=q, x=x, liquido=r["liquido"], janelas=r["janelas_pos"],
                         pior=r["pior"], PF=r["PF"], trades=r["trades"], DD=r["maior_DD"], sem_set=r["liquido_sem_set"],
                         meses_melhor=int((np.array(liq) > bl + 1e-9).sum()), meses_pior=int((np.array(liq) < bl - 1e-9).sum()),
                         mensal=";".join(f"{v:.0f}" for v in liq)))
    T = pd.DataFrame(rows).sort_values(["kind", "N", "modo", "x", "q"])
    T.to_csv(OUT / "c1_resultado.csv", index=False)
    print("\nBASELINE", base[0], flush=True)
    print(base[2], base[1])
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 1000)
    print(T.drop(columns="mensal").to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
