"""Exp 2: distribuição das correções (% da pernada) por tamanho da pernada, estabilidade por ano/mês e escala.
Exp 3: o que explica a variação de um dia para o outro que o ATR dos 5 pregões anteriores não tira."""
import sys, json
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, sys.argv[1])
from exp_padroes import carrega, dias_tf, features, analisa, TFS

K = {"M5": 1.5932, "M15": 0.9496, "H1": 0.494}           # calibrados no exp 1 (atr_prev5)
BINS = [0, 5, 10, 20, 30, 50, 100]
BLAB = ["<5%", "5–10%", "10–20%", "20–30%", "30–50%", "≥50%"]
MULT = [1, 1.5, 2, 3, 99]
MLAB = ["1–1,5×", "1,5–2×", "2–3×", "≥3×"]
FIB = [0, 23.6, 38.2, 50, 61.8, 78.6, 1000]
FLAB = ["<23,6", "23,6–38,2", "38,2–50", "50–61,8", "61,8–78,6", "≥78,6"]


def tabela(legs_rows):
    """legs_rows: lista de (mult, [pctLeg...], [retrAdv(avanço>=20%)...]) -> média por pernada em cada faixa."""
    out = {}
    for mi, ml in enumerate(MLAB):
        sel = [r for r in legs_rows if MULT[mi] <= r[0] < MULT[mi + 1]]
        n = len(sel)
        if not n: continue
        h = np.zeros(len(BLAB)); f = np.zeros(len(FLAB))
        for _, pl, ra in sel:
            h += np.histogram(pl, BINS)[0]; f += np.histogram(ra, FIB)[0]
        out[ml] = dict(n=n, corr=h.sum() / n, bins=(h / n).round(3).tolist(), fib=(f / n).round(3).tolist(),
                       sem_corr=float(np.mean([len(r[1]) == 0 for r in sel])))
    return out


def legs_de(res, thr_dia):
    rows = []
    for d, legs in res.items():
        for size, aberta, cc in legs:
            if aberta: continue  # a última do dia não foi confirmada
            rows.append((size / thr_dia[d], [c[0] for c in cc], [c[1] for c in cc if c[2] >= 20], d))
    return rows


def unidade(tf, escala):
    m1 = carrega(); dias = dias_tf(m1, TFS[tf]); f = features(dias)
    sel = [d for d in sorted(dias) if not np.isnan(f.loc[d, "atr_prev5"])]
    k = K[tf] * escala
    thr = {d: k * f.loc[d, "atr_prev5"] for d in sel}
    res = {d: analisa(dias[d], thr[d]) for d in sel}
    rows = legs_de(res, thr)
    blocos = {"5 anos": rows, "set/2026": [r for r in rows if r[3].startswith("2026-09")]}
    for ano in ["2022", "2023", "2024", "2025", "2026"]:
        blocos[ano] = [r for r in rows if r[3].startswith(ano)]
    saida = dict(tf=tf, escala=escala, k=k, tabelas={b: tabela([r[:3] for r in v]) for b, v in blocos.items()})
    if escala == 1.0:
        # Exp 3: por dia, nº de pernadas e correções/pernada contra fatores
        m1d = m1[m1.index.time < pd.Timestamp("09:30").time()]
        ab = m1d.groupby(m1d.index.date).agg(h=("high", "max"), l=("low", "min"), v=("vol", "sum"))
        ab.index = ab.index.astype(str)
        dd = []
        for d in sel:
            legs = res[d]; nc = sum(len(cc) for _, _, cc in legs)
            dd.append(dict(dia=d, legs=len(legs), corr_leg=nc / max(len(legs), 1),
                           rng_rel=f.loc[d, "rng"] / f.loc[d, "atr_prev5"] / 10,
                           atr_rel=f.loc[d, "atr"] / f.loc[d, "atr_prev5"],
                           gap_rel=f.loc[d, "gap"] / f.loc[d, "atr_prev5"],
                           ab30_rel=(ab.loc[d, "h"] - ab.loc[d, "l"]) / f.loc[d, "atr_prev5"] if d in ab.index else np.nan,
                           vol30=ab.loc[d, "v"] if d in ab.index else np.nan,
                           dow=pd.Timestamp(d).dayofweek))
        dd = pd.DataFrame(dd).set_index("dia")
        dd["vol30_rel"] = dd["vol30"] / dd["vol30"].shift(1).rolling(20).mean()
        cor = {}
        for alvo in ["legs", "corr_leg"]:
            for x in ["atr_rel", "rng_rel", "gap_rel", "ab30_rel", "vol30_rel"]:
                z = dd[[alvo, x]].dropna()
                cor[f"{alvo}~{x}"] = round(z[alvo].rank().corr(z[x].rank()), 3)
        saida["cor"] = cor
        saida["dow"] = dd.groupby("dow")[["legs", "corr_leg"]].mean().round(2).to_dict()
        set_ = dd[dd.index.str.startswith("2026-09")]
        saida["set_dias"] = set_[["legs", "corr_leg", "atr_rel", "gap_rel", "ab30_rel", "vol30_rel"]].round(3).reset_index().to_dict("records")
        saida["corr_set"] = {f"legs~{x}": round(set_["legs"].rank().corr(set_[x].rank()), 3) for x in ["atr_rel", "gap_rel", "ab30_rel", "vol30_rel"]}
    return saida


if __name__ == "__main__":
    out = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(unidade, tf, e) for tf in TFS for e in (0.5, 1.0, 2.0)]
        for fu in as_completed(futs):
            r = fu.result(); out.append(r)
            t = r["tabelas"]
            print(f"\n=== {r['tf']} escala {r['escala']} (k={r['k']:.3f} × ATR prev5)", flush=True)
            for b in ["5 anos", "2022", "2024", "set/2026"]:
                for ml, v in t[b].items():
                    print(f"  {b:8s} {ml:7s} n={v['n']:6d} corr/perna={v['corr']:.2f} sem={v['sem_corr']:.2f} bins={v['bins']}", flush=True)
            if "cor" in r: print("  cor", r["cor"], "\n  set", r["corr_set"], "\n  dow", r["dow"], flush=True)
    json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False)
