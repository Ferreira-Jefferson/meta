"""Rodada 14 (pedido do dono, 2026-10-08): nos sinais bons, aumentar o STOP ou a MAO? E uma probabilidade de acerto
por operacao para decidir 1 ou 2 contratos.

Sinal bom (v4): Estoc14 (suav 3) < 70 a favor OU H4 neutro.
Parte 1: stop inicial afastado (0,25 / 0,5 / 1,0 ATR alem do pivo) so nos sinais bons, 1 contrato (re-simulado).
Parte 2: modelo de acerto (regressao logistica com L2, numpy) e placar de fatores. Aprende em 2022-23, testa em
2024-set/25 (dentro do IS); regra escolhida ai vai uma vez ao OOS (modelo re-treinado no IS inteiro).
Regra: 2 contratos se sinal bom E probabilidade >= limiar; senao 1.
"""
import numpy as np
import pandas as pd
import melhora_mm as mm
import melhora_padroes as mp
import melhora_osc as mo
import melhora_vol as mv
import motor

BASE = "scripts/daytrade/topos_fundos/"


def dd(x):
    x = np.asarray(x, float); eq = np.cumsum(x); return (np.maximum.accumulate(eq) - eq).max() if len(x) else np.nan


def montar(per):
    b, f, c = mp.base_v2i(per)
    m = b.open.rolling(72).mean(); f = f[mm.mascara(f, np.sign(m - m.shift(3)))].reset_index(drop=True)
    P, L = f.pos.to_numpy(), f.lado.to_numpy()
    k, _ = mo.estoc(b, 14, 3); kv = np.asarray(k)[P]; f["estoc"] = np.where(L == 1, kv, 100 - kv)
    t = pd.read_pickle(BASE + ("res/" if per == "pesquisa" else "res_conf/") + f"mtf_{per}.pkl").set_index("idx").sort_values("quando")
    t["vol_reg"] = t.atr15 / t.atr15.rolling(200, min_periods=50).median().shift(1)
    for col in ("H4_ten", "M30_ten", "M5_esc", "H1_rsi", "H1_dist_ema34", "vol_reg", "hora", "H4_fundo_x_pivo", "H1_fundo_x_pivo"):
        f[col] = t.reindex(f.idx)[col].to_numpy()
    x = mv.indicadores(b); f["vtod"] = x.vtod.to_numpy()[P]
    st = (b.close - b.close.ewm(span=21, adjust=False).mean()) / b.atr; f["dist21"] = np.asarray(st)[P] * L
    f["bom"] = (f.estoc < 70) | (f.H4_ten == 0)
    return b, f, c


def sim(f, cache, extra_stop_atr=None):
    """Robo sequencial; extra_stop_atr: array (por linha de f) de ATR a afastar o stop inicial."""
    ocup = {}; out = []
    for e in f.itertuples():
        _, o0, h, l, c, conf = cache[e.seg]
        if e.t0 <= ocup.get(e.seg, -1): continue
        lado, lim, tf_ = e.lado, c[e.t0 - 1], None
        stop = e.stop
        if extra_stop_atr is not None: stop = stop - lado * extra_stop_atr[e.Index] * (e.R / e.H11)
        for t in range(e.t0, min(e.t0 + mm.TTL, len(o0))):
            if (l[t] <= stop) if lado == 1 else (h[t] >= stop): break
            if (l[t] <= lim - mm.FURA) if lado == 1 else (h[t] >= lim + mm.FURA):
                tf_ = t; px = min(o0[t], lim) if lado == 1 else max(o0[t], lim); break
        if tf_ is None or (px - stop) * lado <= 0: continue
        o = o0.copy(); o[tf_] = px
        res, _, ts = motor.trail(o, h, l, c, conf, tf_, lado, stop); ocup[e.seg] = ts
        out.append((e.Index, res - 10, ts - tf_))
    return pd.DataFrame(out, columns=["row", "pts", "barras"])


FEATS = ["estoc", "H4_neutro", "H4_contra", "M30_favor", "M5_esc", "H1_rsi", "H1_dist_ema34", "vol_reg", "hora", "dist21", "R_atr", "H06", "H04", "vtod", "H13"]


def X_de(f, rows):
    d = f.loc[rows]
    X = pd.DataFrame(dict(estoc=d.estoc, H4_neutro=(d.H4_ten == 0).astype(float), H4_contra=(d.H4_ten == -1).astype(float),
                          M30_favor=(d.M30_ten == 1).astype(float), M5_esc=d.M5_esc, H1_rsi=d.H1_rsi, H1_dist_ema34=d.H1_dist_ema34,
                          vol_reg=d.vol_reg, hora=d.hora, dist21=d.dist21, R_atr=d.H11, H06=d.H06, H04=d.H04.clip(upper=5),
                          vtod=d.vtod.clip(upper=5), H13=d.H13))
    return X.astype(float)


def logit_fit(X, y, lam=1.0):
    mu, sd = X.mean(), X.std().replace(0, 1); Z = ((X - mu) / sd).fillna(0).to_numpy(); Z = np.c_[np.ones(len(Z)), Z]
    w = np.zeros(Z.shape[1])
    for _ in range(50):
        p = 1 / (1 + np.exp(-Z @ w)); W = p * (1 - p)
        H = Z.T @ (Z * W[:, None]) + lam * np.eye(len(w)); H[0, 0] -= lam
        g = Z.T @ (y - p) - lam * np.r_[0, w[1:]]
        w = w + np.linalg.solve(H, g)
    return dict(w=w, mu=mu, sd=sd)


def logit_pred(mdl, X):
    Z = ((X - mdl["mu"]) / mdl["sd"]).fillna(0).to_numpy(); Z = np.c_[np.ones(len(Z)), Z]
    return 1 / (1 + np.exp(-Z @ mdl["w"]))


def main():
    res = {}
    for per in ("pesquisa", "reserva"):
        b, f, c = montar(per)
        base = sim(f, c)
        res[per] = (b, f, c, base)
    # ---------- parte 1: stop x mao ----------
    print("PARTE 1: nos sinais bons, aumentar o stop (1 contrato) ou a mão (2 contratos)?")
    for per in ("pesquisa", "reserva"):
        b, f, c, base = res[per]
        p = base.pts.to_numpy(); bom = f.bom.to_numpy()[base.row]
        lin = lambda n, x: print(f"  {per:9s} {n:38s} total {x.sum():+8.0f} DD {dd(x):6.0f} total/DD {x.sum() / dd(x):5.2f}")
        lin("v3 (1 contrato, stop no pivô)", p)
        lin("v4 (2 contratos nos sinais bons)", p * np.where(bom, 2, 1))
        for ex in (0.25, 0.5, 1.0):
            e = np.where(f.bom, ex, 0.0); t = sim(f, c, e)
            lin(f"stop +{ex} ATR nos sinais bons, 1 contrato", t.pts.to_numpy())
            b2 = f.bom.to_numpy()[t.row]
            lin(f"stop +{ex} ATR e 2 contratos nos bons", t.pts.to_numpy() * np.where(b2, 2, 1))
    # ---------- parte 2: probabilidade ----------
    b, f, c, base = res["pesquisa"]
    f_tr = f.loc[base.row].assign(pts=base.pts.values, win=(base.pts.values > 0).astype(float))
    ano = pd.Series([c[s][0].year for s in f_tr.seg], index=f_tr.index)
    tr, te = f_tr[ano <= 2023], f_tr[ano >= 2024]
    mdl = logit_fit(X_de(f, tr.index), tr.win.to_numpy())
    pte = logit_pred(mdl, X_de(f, te.index)); ptr = logit_pred(mdl, X_de(f, tr.index))
    print("\nPARTE 2: modelo de acerto. Treino 2022-23, teste 2024-set/25 (dentro do IS)")
    print("  pesos (padronizados):", {k: round(v, 2) for k, v in zip(["const"] + FEATS, mdl["w"])})
    q = pd.qcut(pte, 4, labels=["Q1 (baixa)", "Q2", "Q3", "Q4 (alta)"])
    g = te.assign(prob=pte, q=q).groupby("q", observed=True).agg(n=("pts", "size"), prob=("prob", "mean"), acerto=("win", "mean"), pts=("pts", "mean"))
    print("  teste 2024-25 por quartil de probabilidade prevista:"); print(g.round(2).to_string())
    print("  só sinais bons:"); print(te.assign(prob=pte, q=q)[te.bom].groupby("q", observed=True).agg(n=("pts", "size"), acerto=("win", "mean"), pts=("pts", "mean")).round(2).to_string())
    # limiar escolhido no treino: prob do treino; testa varios em 2024-25
    print("\n  regra: 2 contratos se sinal bom E prob >= limiar (limiar = quantil da prob no TREINO)")
    for qtl in (0.0, 0.25, 0.5):
        lim = np.quantile(ptr, qtl)
        w = np.where(te.bom & (pte >= lim), 2, 1); x = te.pts.to_numpy() * w
        x0 = te.pts.to_numpy() * np.where(te.bom, 2, 1)
        print(f"   quantil {qtl:.2f} (prob >= {lim:.2f}): total {x.sum():+7.0f} DD {dd(x):5.0f} t/DD {x.sum() / dd(x):5.2f} | v4 sem prob: {x0.sum():+7.0f} DD {dd(x0):5.0f} t/DD {x0.sum() / dd(x0):5.2f}")
    pd.to_pickle(dict(mdl=mdl), BASE + "res_conf/prob_modelo_2223.pkl")
    # OOS: modelo no IS inteiro
    mdl_all = logit_fit(X_de(f, f_tr.index), f_tr.win.to_numpy()); p_all = logit_pred(mdl_all, X_de(f, f_tr.index))
    bo, fo, co, baseo = res["reserva"]
    fo_tr = fo.loc[baseo.row].assign(pts=baseo.pts.values, win=(baseo.pts.values > 0).astype(float))
    po = logit_pred(mdl_all, X_de(fo, fo_tr.index))
    qo = pd.qcut(po, 4, labels=["Q1 (baixa)", "Q2", "Q3", "Q4 (alta)"])
    print("\nOOS (modelo treinado no IS inteiro), por quartil de prob prevista:")
    print(fo_tr.assign(prob=po, q=qo).groupby("q", observed=True).agg(n=("pts", "size"), prob=("prob", "mean"), acerto=("win", "mean"), pts=("pts", "mean")).round(2).to_string())
    for qtl in (0.0, 0.25, 0.5):
        lim = np.quantile(p_all, qtl)
        x = fo_tr.pts.to_numpy() * np.where(fo_tr.bom & (po >= lim), 2, 1)
        print(f"   OOS quantil {qtl:.2f}: total {x.sum():+7.0f} DD {dd(x):5.0f} t/DD {x.sum() / dd(x):5.2f}")


if __name__ == "__main__":
    main()
