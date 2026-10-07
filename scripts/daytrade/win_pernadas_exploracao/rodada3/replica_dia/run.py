"""Roda a replicacao. Saida: resultado.pkl (reais, bootstrap, nulos). Max 4 processos."""
import sys, pickle, time
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
import lib, stats

NSIM_BLOCO = int(sys.argv[1]) if len(sys.argv) > 1 else 100
NSIM_XDIA = int(sys.argv[2]) if len(sys.argv) > 2 else 100
NBOOT = 1000
_G = {}


def _init():
    days, _ = lib.carregar()
    _G["days"] = days
    _G["fontes"] = [d for d in days if d["ym"] <= "2026-08"]
    _G["sets"] = stats.conjuntos(days)


def _sim(kind, seed):
    rng = np.random.default_rng(seed)
    days = _G["days"]
    if kind == "bloco":
        sh = [lib.shuf_bloco(d, rng) for d in days]
    else:
        sh = [lib.shuf_xdia(d, _G["fontes"], rng) for d in days]
    if kind == "bloco":
        tab = [lib.campos_caminho(d) for d in sh]
    else:  # xdia: so R11 e R12 (usam relogio de volatilidade; demais regras de caminho nao pedidas aqui)
        tab = []
        for d in sh:
            o, h, l, c, t = lib.reamostra(d, 60)
            ph, _ = lib.caminho(o, h, l, c, t)
            legs = lib.zigzag(ph, 750)
            fim2 = legs[1][1] if len(legs) >= 2 else len(ph)
            imax, imin = int(np.argmax(ph)), int(np.argmin(ph))
            tab.append(dict(r11=(int(imax <= fim2 or imin <= fim2), int(imax <= fim2 and imin <= fim2)),
                            r12=(int(d["mn"][np.argmax(d["h"])]), int(d["mn"][np.argmin(d["l"])])),
                            r01_on=(0, 0), r01_off=(0, 0), r03_tarde=(0, 0), r03_ate13=(0, 0), r04_tarde=(0, 0),
                            r04_manha=(0, 0), r02=(0, 0, 0, 1), r23=[]))
    out = {}
    T = dict((k, [x[k] for x in tab]) for k in tab[0])
    for nome, idx in _G["sets"].items():
        out[nome] = stats.stats_path(T, idx)
    return kind, seed, out


def main():
    t0 = time.time()
    days, excl = lib.carregar()
    print("dias validos", len(days), "excluidos (parciais)", excl, flush=True)
    sets = stats.conjuntos(days)
    print({k: len(v) for k, v in sets.items()}, flush=True)
    tabc = [lib.campos_caminho(d) for d in days]
    tabo = [lib.campos_outras(d) for d in days]
    tab = {}
    for k in tabc[0]: tab[k] = [x[k] for x in tabc]
    for k in tabo[0]: tab[k] = [x[k] for x in tabo]
    tab["ym"] = [d["ym"] for d in days]; tab["amp"] = [float(d["h"].max() - d["l"].min()) for d in days]
    tab["r22_par"] = [stats.sufic_vr(tab["r22_r"][i], tab["r22_ok"][i], tab["r22_in"][i]) for i in range(len(days))]
    print("tabelas reais ok %.0fs" % (time.time() - t0), flush=True)

    real = {}
    for nome, idx in sets.items():
        s = stats.stats_path(tab, idx); s.update(stats.stats_out(tab, idx)); real[nome] = s
    print("reais ok", flush=True)

    # bootstrap de dias (jan-ago, inv, ver)
    rng = np.random.default_rng(7)
    boot = {}
    for nome in ("JanAug", "inv", "ver"):
        idx = sets[nome]; acc = {}
        for b in range(NBOOT):
            bi = rng.choice(idx, len(idx), replace=True)
            s = stats.stats_path(tab, bi); s.update(stats.stats_out(tab, bi))
            for k, v in s.items(): acc.setdefault(k, []).append(v)
        boot[nome] = {k: (np.nanpercentile(v, 2.5), np.nanpercentile(v, 97.5)) for k, v in acc.items()}
        print("boot", nome, "%.0fs" % (time.time() - t0), flush=True)

    # nulos "originais" (R20, R21, R22)
    nul = {}
    r22 = stats.nulo_r22(days, tab, rng, 100)
    for nome, idx in sets.items():
        n20 = stats.nulo_r20(tab, idx, rng, 300)
        a0, a30 = stats.nulo_r21(tab, idx, rng, 200)
        v22 = np.array([stats.vr5(r22[s][idx]) for s in range(r22.shape[0])])
        nul[nome] = dict(r20=(np.mean(n20), np.percentile(n20, 5), np.percentile(n20, 95)),
                         r21_00=(np.mean(a0), np.percentile(a0, 5), np.percentile(a0, 95)),
                         r21_30=(np.mean(a30), np.percentile(a30, 5), np.percentile(a30, 95)),
                         r22=(np.mean(v22), np.percentile(v22, 5), np.percentile(v22, 95)))
    print("nulos originais ok %.0fs" % (time.time() - t0), flush=True)

    # nulos de pernada (blocos de 30 min) e cross-dia (R11/R12)
    sims = {"bloco": [], "xdia": []}
    jobs = [("bloco", 1000 + i) for i in range(NSIM_BLOCO)] + [("xdia", 5000 + i) for i in range(NSIM_XDIA)]
    with ProcessPoolExecutor(4, initializer=_init) as ex:
        futs = [ex.submit(_sim, k, s) for k, s in jobs]
        for n, f in enumerate(as_completed(futs)):
            kind, seed, out = f.result()
            sims[kind].append(out)
            if n % 10 == 0: print("sim", n, kind, "%.0fs" % (time.time() - t0), flush=True)
    nulo_p = {}
    for kind, L in sims.items():
        nulo_p[kind] = {}
        for nome in sets:
            nulo_p[kind][nome] = {}
            for k in L[0][nome]:
                v = np.array([x[nome][k] for x in L], float)
                nulo_p[kind][nome][k] = (np.nanmean(v), np.nanpercentile(v, 5), np.nanpercentile(v, 95)) if np.isfinite(v).any() else (np.nan,) * 3
    pickle.dump(dict(real=real, boot=boot, nul=nul, nulo_p=nulo_p, sets={k: list(map(int, v)) for k, v in sets.items()},
                     datas=[d["date"] for d in days], excl=excl), open("resultado.pkl", "wb"))
    print("FIM %.0fs" % (time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
