"""V3 - validacao da estrutura intradia (WIN, replicacao WDO) contra NULO QUE PRESERVA SAZONALIDADE.

CRITERIO DE "VALIDADO" (escrito ANTES de rodar; nao muda depois)
-----------------------------------------------------------------
Nulo: para cada minuto-do-dia, o retorno padronizado (retorno M1 / desvio dos retornos do proprio dia) e permutado
ENTRE dias (so entre dias que tem aquele minuto), e reescalado pelo desvio do dia de destino. Preserva o perfil de
volatilidade por horario e a volatilidade de cada dia; destroi persistencia de direcao. 20 replicas.
Por celula "headline": z = (real - nulo_medio) / sqrt(se_real^2 + sd_nulo^2), se_real binomial/EP da media.
  (a) WIN, pooled (2021-10..2026-10): |z| >= 3, |real-nulo| >= 2pp (probabilidades) e SINAL = o da hipotese;
  (b) WIN: o sinal da diferenca bate com o da hipotese em >= 4 dos 5 anos 2022..2026 (anos com n>=30);
  (c) WDO: mesmo sinal pooled com |z| >= 2.
Hipotese VALIDADA: todas as celulas headline passam (a)(b)(c) -- para as hipoteses com grade de horarios (3) basta
>=3 de 4 horarios. INCONCLUSIVA: (a) passa em alguma celula mas (b) ou (c) falha. NAO VALIDADA: (a) falha em todas.
Hipoteses (sentido esperado):
  H1 share das novas max/min do dia (zigue-zague K=0,2) em 9-12h > nulo (+)
  H2 P(0 cruzamentos da abertura no dia) > nulo (+)
  H3 headline: dado nao cruzou ate t e esta a >=0,3 ATR da abertura, P(nao cruzar ate o fim) > nulo (+), t em 9:30/10/10:30/11
  H4 headline t=10:00: preco no extremo do dia (a <=0,05 ATR) sem revisitar abertura, P(fechar do mesmo lado da abertura) > nulo (+)
  H5 K=0,1, k=1,2,3 pernadas na direcao do lado: P(voltar ao outro lado da abertura) < nulo (-)
Aviso: janela 2025+ ja foi vista ao escolher estes achados; a validacao vem de anos, WDO e nulo melhor.
Sem look-ahead: condicoes de H3/H4 usam so o caminho ate o minuto t; ATR = ATR14 ate D-1.
"""
import os, sys
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from c_pernadas_linha_abertura import analisa  # noqa

DATA = r"C:\Users\Jeffe\Documents\study\meta\data\wdo-mt5"
FILES = {"WIN": "WIN@D_M1_202110010900_202610011717.csv", "WDO": "WDO@D_M1_202109290900_202609291020.csv"}
NREP = 20
T = 580
BAND_K = 0.05
MIN_BARS = 200
TS = [570, 600, 630, 660]          # 9:30 10:00 10:30 11:00 (minuto do dia)
XS = [0.1, 0.2, 0.3, 0.5]
HEAD_X = 0.3


def prepara(asset):
    d = pd.read_csv(os.path.join(DATA, FILES[asset]), sep="\t")
    d.columns = [c.strip("<>").lower() for c in d.columns]
    d["dt"] = pd.to_datetime(d["date"] + " " + d["time"], format="%Y.%m.%d %H:%M:%S")
    d["dia"] = d["dt"].dt.normalize()
    g = d.groupby("dia")
    daily = g.agg(h=("high", "max"), l=("low", "min"), c=("close", "last"), nb=("close", "size"))
    tr = np.maximum(daily.h - daily.l, np.maximum((daily.h - daily.c.shift()).abs(), (daily.l - daily.c.shift()).abs()))
    atr = tr.rolling(14).mean().shift(1)
    dias, opens, atrs, Rrows, pres = [], [], [], [], []
    for dia, sub in g:
        a = atr.loc[dia]
        if not np.isfinite(a) or a <= 0 or len(sub) < MIN_BARS:
            continue
        slot = (sub.dt.dt.hour * 60 + sub.dt.dt.minute).values - 540
        ok = (slot >= 0) & (slot < T)
        slot = slot[ok]; cl = sub.close.values[ok].astype(float); op = float(sub.open.values[0])
        r = np.diff(np.r_[op, cl])
        R = np.zeros(T); P = np.zeros(T, bool)
        R[slot] = r; P[slot] = True
        dias.append(dia); opens.append(op); atrs.append(a); Rrows.append(R); pres.append(P)
    return (pd.DatetimeIndex(dias), np.array(opens), np.array(atrs), np.array(Rrows), np.array(pres))


def caminho(op, R):
    return np.concatenate([op[:, None], op[:, None] + np.cumsum(R, axis=1)], axis=1)   # D x (T+1)


def estados(P, op, band):
    S = np.zeros(P.shape, np.int8)
    cur = np.zeros(P.shape[0], np.int8)
    up = op + band; dn = op - band
    for j in range(P.shape[1]):
        x = P[:, j]
        cur = np.where(x > up, 1, np.where(x < dn, -1, cur)).astype(np.int8)
        S[:, j] = cur
    return S


def job(asset, rep):
    dias, op, atr, R, pres = prepara(asset)
    if rep >= 0:
        rng = np.random.default_rng(98765 + rep)
        sd = np.array([R[i][pres[i]].std() for i in range(len(R))])
        sd = np.where(sd > 0, sd, 1.0)
        Z = R / sd[:, None]
        for s in range(T):
            idx = np.where(pres[:, s])[0]
            if len(idx) > 1:
                Z[idx, s] = Z[idx, s][rng.permutation(len(idx))]
        R = Z * sd[:, None] * pres
    P = caminho(op, R)
    nlast = np.array([np.where(pr)[0].max() for pr in pres])
    S = estados(P, op, BAND_K * atr)
    D = len(dias)
    rows = []

    def add(hyp, cell, i, y):
        rows.append((hyp, cell, dias[i], float(y)))

    cross = np.zeros(D, int)
    for i in range(D):
        nz = S[i][S[i] != 0]
        cross[i] = int((np.diff(nz) != 0).sum()) if len(nz) > 1 else 0
        add("H2", "P(0 cruzamentos)", i, cross[i] == 0)
    cmax = np.maximum.accumulate(P, axis=1); cmin = np.minimum.accumulate(P, axis=1)
    Scmax = np.maximum.accumulate(S, axis=1); Scmin = np.minimum.accumulate(S, axis=1)
    Sfut_pos = np.maximum.accumulate((S == 1)[:, ::-1], axis=1)[:, ::-1]
    Sfut_neg = np.maximum.accumulate((S == -1)[:, ::-1], axis=1)[:, ::-1]
    ar = np.arange(D)
    cl = P[ar, nlast + 1]
    for t in TS:
        j = t - 540
        st = S[:, j].astype(int)
        limpo = ((st == 1) & (Scmin[:, j] >= 0)) | ((st == -1) & (Scmax[:, j] <= 0))
        dist = (P[:, j] - op) * st / atr
        pend_flip = np.where(st == 1, Sfut_neg[:, j + 1], Sfut_pos[:, j + 1]).astype(bool)
        rem = (cl - P[:, j]) * st
        same = (cl - op) * st > 0
        for X in XS:
            m = limpo & (dist >= X)
            lab = f"t={t//60}:{t%60:02d}|X={X}"
            for i in np.where(m)[0]:
                add("H3", lab + "|P(nao cruzar ate o fim)", i, not pend_flip[i])
                add("H3", lab + "|P(fecha mesmo lado da abertura)", i, same[i])
                add("H3d", lab + "|restante em pontos", i, rem[i])
                add("H3d", lab + "|restante em ATR", i, rem[i] / atr[i])
        ext = np.where(st == 1, P[:, j] >= cmax[:, j] - 0.05 * atr, P[:, j] <= cmin[:, j] + 0.05 * atr)
        m = limpo & ext & (dist > 0)
        lab = f"t={t//60}:{t%60:02d}"
        for i in np.where(m)[0]:
            add("H4", lab + "|P(fecha mesmo lado da abertura)", i, same[i])
            add("H4", lab + "|P(fecha alem do preco em t)", i, rem[i] > 0)
            add("H4d", lab + "|restante em pontos", i, rem[i])
            add("H4d", lab + "|restante em ATR", i, rem[i] / atr[i])
    for k in (0.1, 0.2):
        for i in range(D):
            n = nlast[i] + 2
            p = P[i, :n]
            tmin = 540 + np.arange(n)
            day, eps, c5 = analisa(p, tmin, atr[i], k)
            if k == 0.2:
                for tt in list(day["nh_t"]) + list(day["nl_t"]):
                    add("H1", "share novas max/min em 9-12h", i, 540 <= tt < 720)
            for e in c5:
                kk = min(e["k"], 4)
                add("H5", f"K={k}|k={'>=4' if kk == 4 else kk}|P(voltar ao outro lado)", i, e["cross_back"])
    df = pd.DataFrame(rows, columns=["hyp", "cell", "dia", "y"])
    df["year"] = df.dia.dt.year
    df["sq"] = df.y ** 2
    g = df.groupby(["hyp", "cell", "year"]).agg(sum=("y", "sum"), n=("y", "size"), sq=("sq", "sum")).reset_index()
    g["asset"] = asset; g["rep"] = rep
    return g


def main():
    res = []
    jobs = [(a, r) for a in ("WIN", "WDO") for r in range(-1, NREP)]
    with ProcessPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(job, a, r): (a, r) for a, r in jobs}
        for f in as_completed(futs):
            res.append(f.result()); print("ok", futs[f], flush=True)
    G = pd.concat(res)
    allg = G.groupby(["asset", "rep", "hyp", "cell"])[["sum", "n", "sq"]].sum().reset_index()
    allg["year"] = 0
    G = pd.concat([G, allg])
    G["mean"] = G["sum"] / G["n"]
    G["var"] = (G["sq"] / G["n"] - G["mean"] ** 2).clip(lower=0)
    real = G[G.rep == -1].set_index(["asset", "hyp", "cell", "year"])
    nul = G[G.rep >= 0].groupby(["asset", "hyp", "cell", "year"]).agg(nulo=("mean", "mean"), nulo_sd=("mean", "std"), n_nulo=("n", "mean"))
    out = real[["mean", "n", "var"]].join(nul, how="left").reset_index()
    out = out.rename(columns={"mean": "real"})
    out["diff"] = out.real - out.nulo
    se = np.sqrt(out["var"] / out.n)
    out["z"] = out["diff"] / np.sqrt(se ** 2 + out.nulo_sd ** 2)
    out["ano"] = out.year.replace(0, "todos")
    out.drop(columns=["var", "year"]).to_csv(os.path.join(HERE, "v3_estrutura_intradia.csv"), index=False, sep=";", decimal=",")
    print("salvo csv", flush=True)

    def cells(h, pred):
        return [x for x in out[(out.hyp == h)].cell.unique() if pred(x)]
    spec = {
        "H1": (cells("H1", lambda x: True), +1),
        "H2": (cells("H2", lambda x: True), +1),
        "H3": (cells("H3", lambda x: f"X={HEAD_X}|P(nao cruzar" in x), +1),
        "H4": (cells("H4", lambda x: x.startswith("t=10:00|P(fecha mesmo")), +1),
        "H5": (cells("H5", lambda x: x.startswith("K=0.1|k=") and "k=>=4" not in x), -1),
    }
    lines = []
    for h, (cl_, sgn) in spec.items():
        flags = []
        for c in cl_:
            def get(a, y):
                r = out[(out.asset == a) & (out.hyp == h) & (out.cell == c) & (out.ano == y)]
                return r.iloc[0] if len(r) else None
            w = get("WIN", "todos"); d = get("WDO", "todos")
            if w is None:
                continue
            a_ok = (abs(w.z) >= 3) and (abs(w["diff"]) >= 0.02) and (np.sign(w["diff"]) == sgn)
            yrs = [r for r in (get("WIN", y) for y in range(2022, 2027)) if r is not None and r.n >= 30]
            nb = sum(np.sign(r["diff"]) == sgn for r in yrs)
            b_ok = (nb >= 4) if len(yrs) == 5 else (len(yrs) >= 3 and nb >= len(yrs) - 1)
            c_ok = d is not None and np.sign(d["diff"]) == sgn and abs(d.z) >= 2
            flags.append((a_ok, b_ok, c_ok))
            lines.append(f"{h} | {c} | WIN real {w.real:.4f} nulo {w.nulo:.4f} z {w.z:.1f} n {int(w.n)} | anos certos {nb}/{len(yrs)} | WDO "
                         + (f"real {d.real:.4f} nulo {d.nulo:.4f} z {d.z:.1f}" if d is not None else "-") + f" | a={a_ok} b={b_ok} c={c_ok}")
        full = [all(f) for f in flags]
        if h == "H3":
            v = "VALIDADO" if sum(full) >= 3 else ("INCONCLUSIVO" if any(f[0] for f in flags) else "NAO VALIDADO")
        else:
            v = "VALIDADO" if flags and all(full) else ("INCONCLUSIVO" if any(f[0] for f in flags) else "NAO VALIDADO")
        lines.append(f"==> {h}: {v}")
    open(os.path.join(HERE, "v3_veredito.txt"), "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
