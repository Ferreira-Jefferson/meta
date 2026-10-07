"""Estudo D: melhor linha de base do WinVolumeRazao e calibracao dos limiares.
Ajuste 2026-06..08; teste 2026-09, 05, 04. Barras < 2026-04 so' como aquecimento. Bootstrap por DIA."""
from __future__ import annotations
import sys, warnings
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_volume_razao_py as W
warnings.filterwarnings("ignore")
AJ = ["2026-06", "2026-07", "2026-08"]; TE = ["2026-09", "2026-05", "2026-04"]
DIAS = [1, 2, 3, 4, 6, 8, 10, 15, 20, 30]
PCTS = [5, 10, 15, 20, 25, 50, 75, 80, 85, 90, 95]
RNG = np.random.default_rng(1)

def sel(idx, meses):
    return np.isin(idx.strftime("%Y-%m"), meses)

def boot_stat(l, dia, fn, B=300):
    """IC95 bootstrap por dia de fn(l)."""
    u, inv = np.unique(dia, return_inverse=True)
    grp = [np.where(inv == i)[0] for i in range(len(u))]
    out = []
    for _ in range(B):
        pick = RNG.integers(0, len(u), len(u))
        out.append(fn(l[np.concatenate([grp[p] for p in pick])]))
    return np.percentile(out, [2.5, 97.5])

def mad(x): return np.median(np.abs(x - np.median(x)))

def unidade(tf, dias, modo, agg):
    d = W.ler_m5_volume(tf)
    r = W.razao_volume(d, dias, modo, agg)
    res = {"tf": tf, "dias": dias, "modo": modo, "agg": agg}
    l = np.log(r)
    first = r.first_valid_index()
    res["inicio_baseline"] = str(first.date()) if first is not None else None
    res["barras_sem_baseline_hist"] = int(r.loc[:"2026-03-31"].isna().sum())
    for nome, ms in (("aj", AJ), ("te", TE)):
        m = sel(r.index, ms)
        x = l[m].dropna()
        res[f"{nome}_n"] = len(x); res[f"{nome}_nan"] = int(m.sum() - len(x))
        res[f"{nome}_sd"] = x.std(); res[f"{nome}_mad"] = mad(x.values) * 1.4826
        res[f"{nome}_mae"] = np.median(np.abs(x))
        res[f"{nome}_mean"] = x.mean()
    return res

def tabela_qualidade():
    jobs = [(tf, a, b, c) for tf in ("M5", "M1") for a in DIAS for b in ("semana", "hora") for c in ("mediana", "media")]
    out = []
    with ProcessPoolExecutor(6) as ex:
        fs = [ex.submit(unidade, *j) for j in jobs]
        for f in as_completed(fs):
            out.append(f.result())
    return pd.DataFrame(out).sort_values(["tf", "modo", "agg", "dias"])

def main():
    q = tabela_qualidade()
    q.to_csv(Path(__file__).with_suffix(".csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    cols = ["dias", "modo", "agg", "aj_n", "aj_nan", "aj_sd", "aj_mad", "aj_mae", "te_nan", "te_sd", "te_mad", "te_mae", "inicio_baseline", "barras_sem_baseline_hist"]
    for tf in ("M5", "M1"):
        print(f"\n=== QUALIDADE {tf} ===")
        print(q[q.tf == tf][cols].round(3).to_string(index=False), flush=True)
    return q


def sdf(x): return np.std(x, ddof=1)


def fase2(tf):
    d = W.ler_m5_volume(tf)
    cfgs = {"semana_mediana_2": (2, "semana", "mediana"), "semana_mediana_10": (10, "semana", "mediana"),
            "hora_mediana_20": (20, "hora", "mediana"), "hora_media_20": (20, "hora", "media"),
            "hora_mediana_4": (4, "hora", "mediana"), "hora_media_4": (4, "hora", "media"),
            "semana_media_4": (4, "semana", "media"), "semana_mediana_4": (4, "semana", "mediana"),
            "hora_mediana_10": (10, "hora", "mediana"), "hora_media_10": (10, "hora", "media"),
            "semana_media_10": (10, "semana", "media")}
    L = {k: np.log(W.razao_volume(d, *v)) for k, v in cfgs.items()}
    out = []
    P = lambda *a: out.append(" ".join(str(x) for x in a))
    mAJ, mTE = sel(d.index, AJ), sel(d.index, TE)
    dias_arr = d.index.normalize().values
    # 1b) dia da semana agrega? diferenca pareada de sd (A - B), IC por dia
    P(f"\n##### {tf}: diferenca de sd(log razao), IC95 bootstrap por dia (A-B; <0 => A melhor)")
    pares = [("semana_mediana_4", "hora_mediana_4"), ("semana_mediana_10", "hora_mediana_10"),
             ("semana_mediana_10", "hora_mediana_20"), ("semana_mediana_2", "hora_mediana_20"),
             ("hora_mediana_20", "hora_media_20"), ("hora_mediana_4", "hora_media_4"),
             ("semana_mediana_4", "semana_media_4"), ("semana_mediana_10", "semana_media_10"),
             ("hora_mediana_10", "hora_media_10")]
    for nome, m in (("ajuste", mAJ), ("teste", mTE)):
        for a, b in pares:
            la, lb = L[a][m], L[b][m]
            ok = (la.notna() & lb.notna()).values
            xa, xb, dd = la.values[ok], lb.values[ok], dias_arr[m][ok]
            u, inv = np.unique(dd, return_inverse=True)
            g = [np.where(inv == i)[0] for i in range(len(u))]
            bs = []
            for _ in range(300):
                ix = np.concatenate([g[p] for p in RNG.integers(0, len(u), len(u))])
                bs.append(sdf(xa[ix]) - sdf(xb[ix]))
            lo, hi = np.percentile(bs, [2.5, 97.5])
            P(f"{nome:6s} {a:18s}-{b:18s} dif={sdf(xa)-sdf(xb):+.4f} IC[{lo:+.4f};{hi:+.4f}] dias={len(u)}",
              "INDISTINGUIVEL" if lo < 0 < hi else ("A melhor" if hi < 0 else "B melhor"))
    # 2) eventos
    sess_all = pd.DatetimeIndex(sorted(set(d.index.normalize())))
    bd = np.busday_count(sess_all[:-1].values.astype("datetime64[D]"), sess_all[1:].values.astype("datetime64[D]"))
    vespera = set(sess_all[:-1][bd > 1]); pos = set(sess_all[1:][bd > 1])
    ym = pd.Series(sess_all.strftime("%Y-%m"), index=sess_all)
    primeiro = set(ym.groupby(ym).apply(lambda x: x.index[0])); ultimo = set(ym.groupby(ym).apply(lambda x: x.index[-1]))
    roll = set()
    for dt in sess_all:
        if dt.month % 2 == 0:
            quinz = pd.Timestamp(dt.year, dt.month, 15)
            wed = [quinz + pd.Timedelta(days=k) for k in range(-3, 4) if (quinz + pd.Timedelta(days=k)).dayofweek == 2][0]
            if dt in (wed - pd.Timedelta(days=1), wed, wed + pd.Timedelta(days=1)):
                roll.add(dt)
    ev = {"virada_contrato(qua~15 +-1d)": roll, "vespera_feriado": vespera, "pos_feriado": pos,
          "primeiro_pregao_mes": primeiro, "ultimo_pregao_mes": ultimo}
    vd = d["vol"].groupby(d.index.normalize()).sum()
    rel = vd / vd.shift(1).rolling(20, min_periods=20).median()
    atip_alto = set(rel[rel > 1.6].index); atip_baixo = set(rel[rel < 0.6].index)
    ev["dia_atipico_ALTO(vol>1,6x)"] = atip_alto
    ev["dia_atipico_BAIXO(<0,6x)"] = atip_baixo
    for k in ("hora_mediana_20", "semana_mediana_2", "hora_media_20"):
        P(f"\n##### {tf} eventos [{k}] ajuste+teste: vies=media(log razao) e sd por barras; IC95 do vies por dia")
        l = L[k]; m = (mAJ | mTE) & l.notna().values
        x = l[m]; dd = pd.DatetimeIndex(dias_arr[m])
        porDia = x.groupby(dd).agg(["mean", "std", "size"])
        P(f"{'TODAS':32s} dias={len(porDia):3d} vies={x.mean():+.3f} sd={x.std():.3f}")
        for nome, S in ev.items():
            msk = porDia.index.isin(list(S))
            if msk.sum() == 0:
                continue
            sub = porDia[msk]; xs = x[np.isin(dd, sub.index)]
            bs = [sub["mean"].values[RNG.integers(0, len(sub), len(sub))].mean() for _ in range(500)]
            lo, hi = np.percentile(bs, [2.5, 97.5])
            P(f"{nome:32s} dias={len(sub):3d} vies={xs.mean():+.3f} IC[{lo:+.3f};{hi:+.3f}] sd={xs.std():.3f}")
    # contaminacao
    P(f"\n##### {tf} contaminacao (hora, janela=5 pregoes; flag = atipico entre os 5 pregoes anteriores)")
    sidx = {dt: i for i, dt in enumerate(sess_all)}
    flag_a = {dt for dt in sess_all if any(sess_all[j] in atip_alto for j in range(max(0, sidx[dt] - 5), sidx[dt]))}
    flag_b = {dt for dt in sess_all if any(sess_all[j] in atip_baixo for j in range(max(0, sidx[dt] - 5), sidx[dt]))}
    for ag in ("mediana", "media"):
        l = np.log(W.razao_volume(d, 5, "hora", ag))
        m = (mAJ | mTE) & l.notna().values
        x = l[m]; dd = pd.DatetimeIndex(dias_arr[m])
        for lab, S in (("sem atipico nos 5 ant.", None), ("c/ atipico ALTO nos 5 ant.", flag_a), ("c/ atipico BAIXO nos 5 ant.", flag_b)):
            sel_ = ~np.isin(dd, list(flag_a | flag_b)) if S is None else np.isin(dd, list(S))
            xs = x[sel_]; days = np.unique(dd[sel_])
            if len(days) == 0:
                continue
            pdays = xs.groupby(dd[sel_]).mean().values
            bs = [pdays[RNG.integers(0, len(pdays), len(pdays))].mean() for _ in range(500)]
            lo, hi = np.percentile(bs, [2.5, 97.5])
            P(f"{ag:8s} {lab:30s} dias={len(days):3d} vies={xs.mean():+.3f} IC[{lo:+.3f};{hi:+.3f}] sd={xs.std():.3f}")
    # 3) limiares
    for k in ("hora_mediana_20", "semana_mediana_10", "semana_mediana_2"):
        r = np.exp(L[k])
        P(f"\n##### {tf} [{k}] percentis da razao")
        rows = {}
        for nome, m in (("ajuste", mAJ), ("teste", mTE)):
            x = r[m].dropna()
            rows[nome] = np.percentile(x, PCTS)
            dd = dias_arr[m][r[m].notna().values]
            fb = boot_stat(x.values, dd, lambda z: (z < 0.7).mean(), 300)
            fa = boot_stat(x.values, dd, lambda z: (z > 1.5).mean(), 300)
            P(f"{nome}: n={len(x)} dias={len(np.unique(dd))}  <0,7: {(x<0.7).mean():.3f} IC[{fb[0]:.3f};{fb[1]:.3f}]  >1,5: {(x>1.5).mean():.3f} IC[{fa[0]:.3f};{fa[1]:.3f}]")
        P("pct   " + " ".join(f"{p:6d}" for p in PCTS))
        for nome in rows:
            P(f"{nome:6s}" + " ".join(f"{v:6.2f}" for v in rows[nome]))
        if k == "hora_mediana_20":
            for pb, pa in ((15, 85), (20, 80), (10, 90)):
                lo_, hi_ = [round(float(np.percentile(r[mAJ].dropna(), q)) * 20) / 20 for q in (pb, pa)]
                for nome, m in (("ajuste", mAJ), ("teste", mTE)):
                    x = r[m].dropna(); dd = dias_arr[m][r[m].notna().values]
                    fb = boot_stat(x.values, dd, lambda z: (z < lo_).mean(), 300)
                    fa = boot_stat(x.values, dd, lambda z: (z > hi_).mean(), 300)
                    P(f"niveis p{pb}/p{pa} -> {lo_:.2f}/{hi_:.2f} {nome}: <{lo_:.2f}: {(x<lo_).mean():.3f} IC[{fb[0]:.3f};{fb[1]:.3f}]  >{hi_:.2f}: {(x>hi_).mean():.3f} IC[{fa[0]:.3f};{fa[1]:.3f}]")
    r = np.exp(L["hora_mediana_20"])
    P(f"\n##### {tf} por mes [hora_mediana_20]")
    for ms in sorted(AJ + TE):
        x = r[sel(d.index, [ms])].dropna()
        P(f"{ms} n={len(x)} p15={x.quantile(.15):.2f} p50={x.median():.2f} p85={x.quantile(.85):.2f} <0,7={(x<0.7).mean():.3f} >1,5={(x>1.5).mean():.3f}")
    P(f"\n##### {tf} mediana da razao por hora (ajuste+teste) [hora_mediana_20]")
    x = r[(mAJ | mTE)].dropna(); h = x.groupby(x.index.hour).median().round(2)
    P(" ".join(f"{i}h:{v}" for i, v in h.items()))
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "q":
        main()
    else:
        with ProcessPoolExecutor(2) as ex:
            fs = {ex.submit(fase2, tf): tf for tf in ("M5", "M1")}
            for f in as_completed(fs):
                print(f"==== {fs[f]} ====\n" + f.result(), flush=True)
