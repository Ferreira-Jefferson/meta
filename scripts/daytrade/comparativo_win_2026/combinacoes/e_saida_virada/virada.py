"""Frente E: saida pela virada da outra familia, teste pareado. Ver TODO.md (secao E) para o pre-registro.
Uso: python virada.py   (grava resultado_*.csv e trades/*.csv; resultado.md e' escrito por relatorio.py)"""
from __future__ import annotations
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent
BASE = AQUI.parents[1]
sys.path.insert(0, str(BASE))
import dados as D  # noqa: E402

ESTR = ["Win", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34", "WdoRetangulo"]
FAM = {"Win": "T", "WinCincoMedias": "T", "WinDeslocamentoMatinal": "T", "WinRetanguloEma34": "R", "WdoRetangulo": "R"}
VARS = [(v, p) for v in ("V1", "V2", "V3") for p in ("a", "b")]   # b = exige lucro
NSORT = 200
NBOOT = 2000
RS = D.RS_PONTO
MIN_MS = 60_000


def log(*a):
    print(*a, flush=True)


V = pd.read_parquet(BASE / "combinacoes" / "f0_fundacao" / "votos.parquet")
IDX = V.index.values.astype("datetime64[ms]").astype(np.int64)
N = len(V)
CLOSE = D.m1().close.reindex(V.index).to_numpy(float)
VOTO = {e: V[f"{e}.voto"].to_numpy(np.int8) for e in ESTR}


def carrega_trades() -> pd.DataFrame:
    t = pd.concat([pd.read_csv(BASE / "resultados" / f"{e}.csv") for e in ESTR], ignore_index=True)
    e_ = pd.to_datetime(t.entrada, format="mixed")
    t["te"] = [D.ms(x) for x in e_]
    t["ts"] = [D.ms(x) for x in pd.to_datetime(t.saida, format="mixed")]
    t["dia"] = e_.dt.date
    t = t.sort_values(["estrategia", "te"]).reset_index(drop=True)
    chk = (t.lado * (t.preco_saida - t.preco_entrada) * RS - t.rs).abs().max()
    assert chk < 0.02, chk
    return t


_TK = {}
def tk(dia):
    if dia not in _TK:
        t, p, _v, _r = D.ticks(dia)
        _TK[dia] = (np.asarray(t, np.int64), np.asarray(p, float))
    return _TK[dia]


def prepara(t: pd.DataFrame):
    """Por operacao: linhas candidatas r (barra r fechada) com tick de saida valido (1o tick >= r+1min, antes da saida original)."""
    out = []
    for q in t.itertuples():
        tt, pp = tk(q.dia)
        i0 = int(np.searchsorted(IDX, q.te // MIN_MS * MIN_MS, "left"))
        i1 = int(np.searchsorted(IDX, q.ts, "right"))
        rows = np.arange(i0, min(i1, N))
        rows = rows[IDX[rows] // 86_400_000 == q.te // 86_400_000]
        tgt = IDX[rows] + MIN_MS
        k = np.searchsorted(tt, tgt, "left")
        ok = k < len(tt)
        kk = np.minimum(k, len(tt) - 1)
        ok &= tt[kk] < q.ts
        lucro = q.lado * (CLOSE[rows] - q.preco_entrada) > 0
        out.append(dict(rows=rows, ok=ok, px=pp[kk], tsai=tt[kk], lucro=lucro))
    return out


def conds(voto: dict):
    c = {}
    for s in ESTR:
        outra = [e for e in ESTR if FAM[e] != FAM[s]]
        propria = [e for e in ESTR if FAM[e] == FAM[s] and e != s]
        for L in (1, -1):
            c[("V1", s, L)] = np.logical_and.reduce([voto[e] == -L for e in outra])
            c[("V2", s, L)] = np.logical_or.reduce([voto[e] == -L for e in outra])
            c[("V3", s, L)] = np.logical_or.reduce([voto[e] == -L for e in propria])
    return c


def primeiro(prep, t, cond, v, p):
    ks = np.full(len(t), -1, int)
    est = t.estrategia.to_numpy(); lado = t.lado.to_numpy()
    for j in range(len(t)):
        P = prep[j]
        c = cond[(v, est[j], int(lado[j]))][P["rows"]] & P["ok"]
        if p == "b":
            c &= P["lucro"]
        if c.any():
            ks[j] = int(np.argmax(c))
    return ks


def diffs_de_k(prep, t, ks):
    d = np.zeros(len(t)); px = t.preco_saida.to_numpy(float).copy(); ts = t.ts.to_numpy().copy()
    lado = t.lado.to_numpy(); ps = t.preco_saida.to_numpy(float)
    for j in np.flatnonzero(ks >= 0):
        P = prep[j]; k = ks[j]
        px[j] = P["px"][k]; ts[j] = P["tsai"][k]
        d[j] = lado[j] * (P["px"][k] - ps[j]) * RS
    return d, px, ts


def sorteio_instante(prep, t, ks, p, rng):
    d = np.zeros(len(t))
    idx = np.flatnonzero(ks >= 0)
    if len(idx) == 0:
        return d
    lado = t.lado.to_numpy(); ps = t.preco_saida.to_numpy(float)
    kp = rng.permutation(ks[idx])
    for j, k in zip(idx, kp):
        P = prep[j]
        if k < len(P["rows"]) and P["ok"][k] and (p == "a" or P["lucro"][k]):
            d[j] = lado[j] * (P["px"][k] - ps[j]) * RS
    return d


def runs_ids(v):
    ch = np.r_[True, v[1:] != v[:-1]]
    rid = np.cumsum(ch) - 1
    return np.where(v != 0, rid, -1)


def placebo_voto(rng, rids):
    out = {}
    for e in ESTR:
        rid = rids[e]; n = max(int(rid.max()) + 1, 1)
        sg = rng.choice(np.array([-1, 1], np.int8), size=n)
        out[e] = np.where(rid >= 0, sg[np.maximum(rid, 0)], 0).astype(np.int8)
    return out


def mensal(rs, ts_ms, custo, mask):
    sel = np.flatnonzero(mask)
    r = rs[sel] - custo
    tsx = ts_ms[sel]
    o = np.argsort(tsx, kind="stable")
    r, tsx = r[o], tsx[o]
    mes = pd.to_datetime(tsx, unit="ms").month.to_numpy()
    mm = {f"m{m}": round(float(r[mes == m].sum()), 2) for m in range(1, 11)}
    eq = D.CAPITAL + np.cumsum(r)
    pico = np.maximum.accumulate(np.r_[D.CAPITAL, eq])[1:]
    return dict(**mm, total=round(float(r.sum()), 2), n=len(r), caixa_min=round(float(eq.min()), 2),
                maxdd=round(float((pico - eq).max()), 2), quebra=bool((eq <= 0).any()))


def boot_dia(d, dc, af, rng):
    nd = int(dc.max()) + 1
    soma = np.bincount(dc, weights=d, minlength=nd)
    cnt = np.bincount(dc, minlength=nd).astype(float)
    a = np.bincount(dc, weights=af.astype(float), minlength=nd)
    s = rng.integers(0, nd, size=(NBOOT, nd))
    m_all = soma[s].sum(1) / cnt[s].sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        m_af = soma[s].sum(1) / a[s].sum(1)
    q = lambda x: tuple(np.nanpercentile(x, [2.5, 97.5])) if np.isfinite(x).any() else (np.nan, np.nan)
    return d.sum() / cnt.sum(), q(m_all), (d.sum() / a.sum() if a.sum() else np.nan), q(m_af)


def main():
    t0 = time.time()
    t = carrega_trades()
    log(f"{len(t)} operacoes, {t.estrategia.value_counts().to_dict()}")
    prep = prepara(t)
    log(f"preparo ok {time.time()-t0:.0f}s")
    cond = conds(VOTO)
    dcod = pd.factorize(t.dia)[0]
    rng = np.random.default_rng(20261006)
    rids = {e: runs_ids(VOTO[e]) for e in ESTR}
    tsx0 = t.ts.to_numpy(); rs0 = t.rs.to_numpy(float)
    masks = {"soma": np.ones(len(t), bool), **{e: (t.estrategia == e).to_numpy() for e in ESTR}}
    LM, LP, LC = [], [], []
    for custo in (0.0, 2.0):
        for esc, m in masks.items():
            LM.append(dict(variante="original", escopo=esc, custo=custo, **mensal(rs0, tsx0, custo, m)))
    pl_conds = [conds(placebo_voto(rng, rids)) for _ in range(NSORT)]
    for v, p in VARS:
        nome = v + p
        ks = primeiro(prep, t, cond, v, p)
        d, px, tsn = diffs_de_k(prep, t, ks)
        af = ks >= 0
        log(f"{nome}: disparadas {af.sum()}/{len(t)}  delta total R$ {d.sum():+.2f}  ({time.time()-t0:.0f}s)")
        rs_n = t.lado.to_numpy() * (px - t.preco_entrada.to_numpy()) * RS
        for custo in (0.0, 2.0):
            for esc, m in masks.items():
                LM.append(dict(variante=nome, escopo=esc, custo=custo, **mensal(rs_n, tsn, custo, m)))
        o = t[["estrategia", "entrada", "saida", "lado", "preco_entrada", "preco_saida", "motivo"]].copy()
        o.insert(4, "qtd", 1.0)
        o.loc[af, "saida"] = [str(D.ts(x)) for x in tsn[af]]
        o.loc[af, "preco_saida"] = px[af]
        o.loc[af, "motivo"] = "virada_" + nome
        o["pontos"] = t.lado * (o.preco_saida - o.preco_entrada); o["rs"] = np.round(o.pontos * RS, 2)
        o.to_csv(AQUI / "trades" / f"{nome}.csv", index=False)
        ds = np.array([sorteio_instante(prep, t, ks, p, rng) for _ in range(NSORT)])
        dp = np.array([diffs_de_k(prep, t, primeiro(prep, t, pl_conds[i], v, p))[0] for i in range(NSORT)])
        for esc, m in masks.items():
            a = d[m].sum()
            pct = lambda arr: 100 * ((arr < a).mean() + 0.5 * (arr == a).mean())
            ss, pp_ = ds[:, m].sum(1), dp[:, m].sum(1)
            LC.append(dict(variante=nome, escopo=esc, disparadas=int(af[m].sum()), n=int(m.sum()), delta_real=round(a, 2),
                           sorteio_media=round(ss.mean(), 2), sorteio_p95=round(np.percentile(ss, 95), 2), pct_sorteio=round(pct(ss), 1),
                           placebo_media=round(pp_.mean(), 2), placebo_p95=round(np.percentile(pp_, 95), 2), pct_placebo=round(pct(pp_), 1)))
            mu, ci, mua, cia = boot_dia(d[m], dcod[m], af[m], rng)
            LP.append(dict(variante=nome, escopo=esc, n=int(m.sum()), afetadas=int(af[m].sum()), delta_total=round(a, 2),
                           media_por_op=round(mu, 3), ic_lo=round(ci[0], 3), ic_hi=round(ci[1], 3),
                           media_afetadas=round(mua, 3), ic_af_lo=round(cia[0], 3), ic_af_hi=round(cia[1], 3)))
        c = LC[-len(masks)]
        log(f"  soma: pct sorteio {c['pct_sorteio']}  pct placebo {c['pct_placebo']}  ({time.time()-t0:.0f}s)")
    pd.DataFrame(LM).to_csv(AQUI / "resultado_mensal.csv", index=False)
    pd.DataFrame(LP).to_csv(AQUI / "resultado_pareado.csv", index=False)
    pd.DataFrame(LC).to_csv(AQUI / "resultado_controles.csv", index=False)
    log("fim", f"{time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
