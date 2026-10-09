"""Auditoria de vies do filtro (2026-10-08).

1. Placebo: no mesmo conjunto de sinais (estagio >= 1), sortear subconjuntos do mesmo tamanho do filtro 5.000 vezes;
   em que percentil fica o filtro real? (pesquisa e reserva; pts brutos, sinais sobrepostos)
2. Vizinhanca: o robo M15 (uma posicao, limitada no fechamento, preco passa 2 ticks, stop na estrutura) com o filtro
   trocado por vizinhos: TF superior {30min, 1h, 2h, 4h} x MMEs {(5,13,21),(9,21,34),(13,34,55),(20,50,100)} x K {1.0,1.5,2.0}.
   Quantas das 48 celulas sao positivas na pesquisa e na reserva? A celula escolhida e um pico isolado?
3. Mes a mes na reserva.
"""
import os
import numpy as np
import pandas as pd
import motor
import hipoteses
import confirma

BASE = "scripts/daytrade/topos_fundos/"
HTFS = ["30min", "60min", "120min", "240min"]
EMAS = [(5, 13, 21), (9, 21, 34), (13, 34, 55), (20, 50, 100)]


def placebo(per):
    R = confirma.PER[per]["out"]
    f = pd.read_pickle(R + "feat0_M5_dia_K1.5.pkl")
    f = f[f.est >= 1]
    m = (f.H07 == 1) & (f.H13 > 0)
    real = f[m].res.mean(); n = int(m.sum())
    rng = np.random.default_rng(1)
    v = f.res.to_numpy()
    sim = np.array([v[rng.choice(len(v), n, replace=False)].mean() for _ in range(5000)])
    return dict(periodo=per, n_filtro=n, pts_filtro=real, placebo_media=sim.mean(), placebo_p99=np.percentile(sim, 99),
                p_valor=(sim >= real).mean())


def htf_flag(b, regra, emas):
    c = b.close.resample(regra).last().dropna()
    a, m, l = (c.ewm(span=s, adjust=False).mean() for s in emas)
    up = (c > l) & (a > m); dn = (c < l) & (a < m)
    return pd.Series(np.where(up, 1, np.where(dn, -1, 0)), index=c.index + pd.Timedelta(regra))


def robo(per, K, regra, emas, fura=10, ttl=3):
    cfg = confirma.PER[per]; R = cfg["out"]
    nome = f"M15_dia_K{K}"
    f = pd.read_pickle(R + f"feat0_{nome}.pkl"); ev = pd.read_pickle(R + f"ev_{nome}.pkl")
    b = pd.read_pickle(R + "barras_M15_dia.pkl")
    if "atr" not in b: b["atr"] = motor.com_atr(b, b.dia)
    grupos = [g for _, g in b.groupby(b.dia.values)]
    flag = htf_flag(b, regra, emas)
    f = f[f.est >= 1].copy()
    f["seg"] = ev.loc[f.idx, "seg"].values; f["t0"] = ev.loc[f.idx, "t0"].values; f["stop"] = ev.loc[f.idx, "stop"].values
    tconf = [grupos[s].index[t - 1] for s, t in zip(f.seg, f.t0)]
    f["htf"] = [flag.asof(x) if x >= flag.index[0] else 0 for x in tconf]
    f = f[(f.htf * f.lado == 1) & (f.H13 > 0)].sort_values(["seg", "t0"])
    trades, ocup, cache = [], {}, {}
    for e in f.itertuples():
        g = grupos[e.seg]
        if e.seg not in cache:
            cache[e.seg] = (g.open.to_numpy().copy(), g.high.to_numpy(), g.low.to_numpy(), g.close.to_numpy(),
                            {p[3]: p for p in motor.zigzag(g.high.to_numpy(), g.low.to_numpy(), g.atr.to_numpy(), K)})
        o0, h, l, c, conf = cache[e.seg]
        if e.t0 <= ocup.get(e.seg, -1): continue
        lado = e.lado; lim = c[e.t0 - 1]; tf_ = None
        for t in range(e.t0, min(e.t0 + ttl, len(o0))):
            if (l[t] <= e.stop) if lado == 1 else (h[t] >= e.stop): break
            if (l[t] <= lim - fura) if lado == 1 else (h[t] >= lim + fura):
                tf_ = t; px = min(o0[t], lim) if lado == 1 else max(o0[t], lim); break
        if tf_ is None or (px - e.stop) * lado <= 0: continue
        o = o0.copy(); o[tf_] = px
        res, _, ts = motor.trail(o, h, l, c, conf, tf_, lado, e.stop)
        ocup[e.seg] = ts
        trades.append(dict(dia=g.index[0].normalize(), res=res - 10))
    t = pd.DataFrame(trades)
    return t


def main():
    out = {}
    print("== PLACEBO (M5, sinais sobrepostos) ==", flush=True)
    pl = pd.DataFrame([placebo(p) for p in ("pesquisa", "reserva")]); print(pl.round(3).to_string(index=False), flush=True)
    out["placebo"] = pl
    # garantir K 1.0 e 2.0 do M15 dia nos dois periodos
    for per in ("pesquisa", "reserva"):
        cfg = confirma.PER[per]
        motor.SRC, motor.INI, motor.FIM, motor.OUT = cfg["src"], cfg["ini"], cfg["fim"], cfg["out"]
        hipoteses.R = cfg["out"]
        for K in (1.0, 2.0):
            nome = f"M15_dia_K{K}"
            if not os.path.exists(cfg["out"] + f"ev_{nome}.pkl"): motor.unidade("M15", "dia", K)
            fp = cfg["out"] + f"feat0_{nome}.pkl"
            if not os.path.exists(fp):
                f = hipoteses.features("M15", "dia", K, min_est=0)
                ev = pd.read_pickle(cfg["out"] + f"ev_{nome}.pkl")
                for col in ("res", "est", "R", "r2", "r3", "mfe"): f[col] = ev.loc[f.idx, col].values
                f.to_pickle(fp)
    print("== VIZINHANCA (robo M15, liquido pts/op) ==", flush=True)
    viz = []
    for K in (1.0, 1.5, 2.0):
        for regra in HTFS:
            for emas in EMAS:
                r = dict(K=K, htf=regra, emas="/".join(map(str, emas)))
                for per in ("pesquisa", "reserva"):
                    t = robo(per, K, regra, emas)
                    r[f"n_{per}"] = len(t); r[f"liq_op_{per}"] = t.res.mean() if len(t) else np.nan
                    r[f"total_{per}"] = t.res.sum() if len(t) else 0
                    if per == "reserva" and K == 1.5 and regra == "60min" and emas == (9, 21, 34): out["mensal"] = t
                viz.append(r); print(r, flush=True)
    viz = pd.DataFrame(viz); out["viz"] = viz
    print(viz.round(1).to_string(index=False))
    for per in ("pesquisa", "reserva"):
        print(per, "celulas positivas:", int((viz[f"liq_op_{per}"] > 0).sum()), "de", len(viz),
              "mediana liq/op", round(viz[f"liq_op_{per}"].median(), 1))
    m = out["mensal"]; mm = m.groupby(m.dia.dt.to_period("M")).res.sum()
    print("reserva mes a mes (pts liq):", mm.round(0).astype(int).to_dict(), "meses positivos", int((mm > 0).sum()), "de", len(mm))
    pd.to_pickle(out, BASE + "res_conf/vies.pkl")


if __name__ == "__main__":
    main()
