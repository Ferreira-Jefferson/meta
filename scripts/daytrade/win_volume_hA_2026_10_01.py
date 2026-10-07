"""Estudo A: razao de volume na vela do sinal x resultado (WIN M5 WMA34/SMMA34).
Ajuste: 2026-06/07/08. Teste: 2026-09/05/04. Fase 1 simula (cache csv), fase 2 analisa."""
from __future__ import annotations
import sys, io, contextlib, itertools
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_volume_razao_py as W

AJ = ["2026-06", "2026-07", "2026-08"]; TE = ["2026-09", "2026-05", "2026-04"]
GEOS = [(300, 600), (50, 300)]
OUT = Path(__file__).resolve().parent / "win_volume_hA_cache"; OUT.mkdir(exist_ok=True)
DIAS = [2, 4, 6, 10, 20]; NB = [0.5, 0.6, 0.7, 0.8]; NA = [1.3, 1.5, 1.7, 2.0]
rng = np.random.default_rng(1)


def sim_um(mes, s, a):
    f = OUT / f"{mes}_{s}_{a}.csv"
    if not f.exists():
        with contextlib.redirect_stdout(io.StringIO()):
            m1 = W.sim.preparar(mes, limpa=True, so_roxa=True)
            tr = W.sim.simular(m1, s, a)
        tr["t_sinal"] = tr["t_entrada"] - pd.Timedelta(minutes=5)
        tr[["rs", "mot", "dir", "t_entrada", "t_sinal"]].to_csv(f, index=False)
    return mes, s, a


def carregar(meses, s, a):
    d = pd.concat([pd.read_csv(OUT / f"{m}_{s}_{a}.csv", parse_dates=["t_entrada", "t_sinal"]) for m in meses])
    return d.sort_values("t_entrada").reset_index(drop=True)


_M5 = None
_cache = {}


def razoes(dias):
    global _M5
    if _M5 is None:
        _M5 = W.ler_m5_volume()
    if dias not in _cache:
        r = W.razao_volume(_M5, dias, "semana", "mediana")
        _cache[dias] = (r, r.shift(1).rolling(3, min_periods=3).mean())
    return _cache[dias]


def anexa(d, dias):
    r, tend = razoes(dias)
    d = d.copy()
    d["razao"] = r.reindex(d["t_sinal"]).to_numpy()
    d["tend"] = tend.reindex(d["t_sinal"]).to_numpy()
    return d


def stats(x):
    x = np.asarray(x, float)
    n = len(x)
    if n == 0:
        return dict(n=0, mu=np.nan, ep=np.nan, ac=np.nan, be=np.nan, liq=0.0)
    g = x[x > 0]
    p = -x[x <= 0]
    be = p.mean() / (g.mean() + p.mean()) if len(g) and len(p) else np.nan
    return dict(n=n, mu=x.mean(), ep=x.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan,
                ac=(x > 0).mean(), be=be, liq=x.sum())


def maxdd(x):
    c = np.cumsum(x)
    if not len(c):
        return 0.0
    pico = np.maximum.accumulate(np.r_[0, c])[1:]
    return float((c - pico).min())


def fmt(s, tag=""):
    def f(v, p=1):
        return "nan" if v != v else f"{v:.{p}f}"
    sp = "" if s["n"] >= 60 else " (n<60 sem poder)"
    return (f"{tag:<14}n={s['n']:>4} R$/op={f(s['mu'], 2):>7} +-{f(s['ep'], 2):>5} "
            f"ac={f(100 * s['ac'], 1):>5}% BE={f(100 * s['be'], 1):>5}% liq={f(s['liq'], 0):>7}{sp}")


def saidas(d):
    m = d["mot"].value_counts()
    n = max(len(d), 1)
    return " ".join(f"{k}={m.get(k, 0)}({100 * m.get(k, 0) / n:.0f}%)" for k in ["stop", "trail", "alvo", "zera"])


def perm_p(x, flag, nperm=1000):
    x = np.asarray(x, float)
    flag = np.asarray(flag, bool)
    if flag.sum() < 2 or (~flag).sum() < 2:
        return np.nan, np.nan
    obs = x[flag].mean() - x[~flag].mean()
    k = flag.sum()
    cnt = 0
    for _ in range(nperm):
        m = np.zeros(len(x), bool)
        m[rng.permutation(len(x))[:k]] = True
        if abs(x[m].mean() - x[~m].mean()) >= abs(obs):
            cnt += 1
    return obs, (cnt + 1) / (nperm + 1)


def faixas(d, col, tag):
    d = d.dropna(subset=[col])
    r = d[col]
    bins = [("<0,7", r < .7), ("0,7-1,0", (r >= .7) & (r < 1)), ("1,0-1,5", (r >= 1) & (r < 1.5)), (">=1,5", r >= 1.5)]
    print(f"  [{tag}] faixas de {col}")
    for nome, m in bins:
        print("   ", fmt(stats(d.loc[m, 'rs']), nome), "|", saidas(d[m]))
    try:
        q = pd.qcut(r, 5, labels=False, duplicates="drop")
        print("    quintis edges:", np.round(r.quantile([0, .2, .4, .6, .8, 1]).to_numpy(), 2))
        for k in sorted(q.unique()):
            print("   ", fmt(stats(d.loc[q == k, 'rs']), f"Q{k + 1}"), "|", saidas(d[q == k]))
    except Exception as e:
        print("    quintis falhou", e)


def hipoteses(d, tag):
    for col in ["razao", "tend"]:
        dd = d.dropna(subset=[col])
        for nome, fl in [("H1 sobre(>=1,5)", dd[col] >= 1.5), ("H3 baixo(<0,7)", dd[col] < .7)]:
            obs, p = perm_p(dd["rs"], fl)
            print(f"  [{tag}] {col:5} {nome}: n_faixa={int(fl.sum())} dif(faixa-resto)={obs:.2f} R$/op p={p:.3f}")


def aplica(d, tipo, nb, na):
    r = d["razao"]
    return {"pula_baixo": r >= nb, "pula_alto": r < na, "so_meio": (r >= nb) & (r < na),
            "so_alto": r >= na, "so_baixo": r < nb}[tipo]


TIPOS = ["pula_baixo", "pula_alto", "so_meio", "so_alto", "so_baixo"]


def ganho_vs_aleatorio(x, keep, nrand=1000):
    base = x.sum()
    g = x[keep].sum() - base
    k = keep.sum()
    n = len(x)
    rg = np.array([x[rng.permutation(n)[:k]].sum() - base for _ in range(nrand)])
    return g, rg.mean(), rg.std(), (np.sum(rg >= g) + 1) / (nrand + 1)


def main():
    jobs = [(m, s, a) for (s, a) in GEOS for m in AJ + TE]
    with ProcessPoolExecutor(4) as ex:
        fs = [ex.submit(sim_um, *j) for j in jobs]
        for f in as_completed(fs):
            print("simulado", f.result(), flush=True)
    for (s, a) in GEOS:
        print(f"\n================ stop/alvo {s}/{a} ================", flush=True)
        dA = carregar(AJ, s, a)
        dT = carregar(TE, s, a)
        print(f"ops ajuste={len(dA)} teste={len(dT)}")
        print(fmt(stats(dA.rs), "AJUSTE s/filtro"), f"DD={maxdd(dA.rs.to_numpy()):.0f}")
        print(fmt(stats(dT.rs), "TESTE s/filtro"), f"DD={maxdd(dT.rs.to_numpy()):.0f}")
        print("saidas ajuste:", saidas(dA), "| teste:", saidas(dT))
        for tag, d in [("AJUSTE", anexa(dA, 2)), ("TESTE", anexa(dT, 2))]:
            print(f"-- Dias=2 {tag} (NaN razao: {d.razao.isna().sum()})")
            faixas(d, "razao", tag)
            faixas(d, "tend", tag)
            hipoteses(d, tag)
        res = []
        for dias in DIAS:
            a_ = anexa(dA, dias).dropna(subset=["razao"]).reset_index(drop=True)
            x = a_.rs.to_numpy()
            for nb, na, tipo in itertools.product(NB, NA, TIPOS):
                keep = aplica(a_, tipo, nb, na).to_numpy()
                if keep.sum() < 60 or keep.sum() == len(x):
                    continue
                g, mr, sr, p = ganho_vs_aleatorio(x, keep, 300)
                res.append(dict(dias=dias, nb=nb, na=na, tipo=tipo, n=int(keep.sum()), ganho=g,
                                z=(g - mr) / sr if sr > 0 else 0, p=p))
        R = pd.DataFrame(res).sort_values("z", ascending=False)
        print("\n-- top 8 no AJUSTE por z (ganho vs filtro aleatorio mesmo tamanho; n_comb=%d)" % len(R))
        print(R.head(8).round(3).to_string(index=False), flush=True)
        print("   mediana z de todas:", round(R.z.median(), 2), "| frac p<0,05:", round((R.p < .05).mean(), 3))
        for _, c in R.head(3).iterrows():
            print(f"\n-- TESTE da combinacao dias={int(c.dias)} nb={c.nb} na={c.na} tipo={c.tipo}")
            for tag, dd in [("AJUSTE", dA), ("TESTE", dT)]:
                t = anexa(dd, int(c.dias)).dropna(subset=["razao"]).reset_index(drop=True)
                x = t.rs.to_numpy()
                keep = aplica(t, c.tipo, c.nb, c.na).to_numpy()
                g, mr, sr, p = ganho_vs_aleatorio(x, keep, 1000)
                print(f"  {tag}: sem filtro liq={x.sum():.0f} n={len(x)} R$/op={x.mean():.2f} DD={maxdd(x):.0f} | "
                      f"filtrado liq={x[keep].sum():.0f} n={keep.sum()} R$/op={x[keep].mean():.2f} DD={maxdd(x[keep]):.0f} | "
                      f"ganho={g:.0f} aleat={mr:.0f}+-{sr:.0f} p={p:.3f}")
                print("     ", fmt(stats(x[keep]), tag + " filtr."))


if __name__ == "__main__":
    main()
