"""v1: estrategia de perguntas. Resultado por operacao assimetrica (limitada, stop k*ATR, trailing N velas, fim do dia)."""
import sys, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
BQ = r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\topos_fundos\banco_perguntas"
sys.path.insert(0, BQ); sys.path.insert(0, r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\topos_fundos")
import catalogo as K
FURA, VALIDADE, CUSTO = 10, 3, 10
PER = ("IS", "OOS", "virgem")
IDS = [r["id"] for r in K.R]; EXP = {r["id"]: r["exp"] for r in K.R}; LADO = {r["id"]: r["lado"] for r in K.R}


def carrega(per):
    z = np.load(f"calc_{per}.npz")
    return {k: z[k] for k in z.files}


def X_de(z):
    return np.stack([(z[i] == EXP[i]).astype(np.float32) for i in IDS], 2)   # (n,2,Q) col0=compra, col1=venda


def elegivel(z):
    m = z["_mins"]; return (m >= 570) & (m <= 1005) & np.isfinite(z["_atr"]) & (z["_atr"] > 0)


def seg_idx(dia):
    n = len(dia); return np.r_[0, np.where(dia[1:] != dia[:-1])[0] + 1, n]


def resultados(z, stopk, N):
    """Por vela-lado: pts liquidos por contrato (NaN = nao enche), barra de entrada te, barra de saida ts."""
    O, H, L, C, A = z["_open"], z["_high"], z["_low"], z["_close"], z["_atr"]
    dia = z["_dia"]; n = len(O); el = elegivel(z)
    pts = np.full((n, 2), np.nan); te_ = np.full((n, 2), -1); ts_ = np.full((n, 2), -1)
    sg = seg_idx(dia)
    for lado_i, s in ((0, 1.0), (1, -1.0)):
        o, h, l, c = (O, H, L, C) if s > 0 else (-O, -L, -H, -C)
        for s0, e0 in zip(sg[:-1], sg[1:]):
            for i in range(s0, e0 - 1):
                if not el[i]: continue
                lim = c[i]; stp = lim - stopk * A[i]; te = -1
                for t in range(i + 1, min(i + 1 + VALIDADE, e0)):
                    if l[t] <= stp or l[t] <= lim - FURA:
                        te = t; break
                if te < 0: continue
                px = min(o[te], lim)
                if px - stp <= 0: continue
                saida, ts = c[e0 - 1], e0 - 1
                for t in range(te, e0):
                    ot = px if t == te else o[t]
                    if l[t] <= stp:
                        saida, ts = min(ot, stp), t; break
                    lo = l[max(t - N + 1, s0):t + 1].min()
                    if lo > stp: stp = lo
                pts[i, lado_i] = saida - px - CUSTO; te_[i, lado_i] = te; ts_[i, lado_i] = ts
    return pts, te_, ts_


# ---------- modelos ----------
def padroniza(X, mu=None, sd=None):
    if mu is None:
        mu = X.mean(0); sd = X.std(0); sd[sd < 1e-6] = 1
    return (X - mu) / sd, mu, sd


def reps(X, ordem_score, lim=0.5):
    """Mantem um representante por grupo |phi|>lim (greedy por score decrescente). Retorna indices."""
    ok = X.std(0) > 1e-6
    C = np.corrcoef(X[:, ok].T); idx_ok = np.where(ok)[0]
    ordem = sorted(range(len(idx_ok)), key=lambda k: -ordem_score[idx_ok[k]])
    esc = []
    for k in ordem:
        if all(abs(C[k, j]) <= lim for j in esc): esc.append(k)
    return idx_ok[esc]


class Ridge:
    def __init__(s, lam, rep=False): s.lam, s.rep = lam, rep

    def fit(s, X, y):
        s.cols = np.arange(X.shape[1])
        if s.rep:
            sc = np.abs(((X - X.mean(0)) * (y - y.mean())[:, None]).mean(0) / (X.std(0) + 1e-9))
            s.cols = reps(X, sc)
        Xs, s.mu, s.sd = padroniza(X[:, s.cols]); s.b0 = y.mean()
        s.w = np.linalg.solve(Xs.T @ Xs + s.lam * np.eye(Xs.shape[1]), Xs.T @ (y - s.b0)); return s

    def predict(s, X): return ((X[:, s.cols] - s.mu) / s.sd) @ s.w + s.b0


class Boost:
    """Gradient boosting, arvores de profundidade <=2 sobre features binarias, regularizado (encolhimento, folha minima)."""
    def __init__(s, rounds=40, lr=0.1, minleaf=300, depth=2): s.R, s.lr, s.ml, s.depth = rounds, lr, minleaf, depth

    def _best(s, Xt, r, m):
        n1 = Xt @ m; s1 = Xt @ (r * m); n = m.sum(); S = (r * m).sum(); n0 = n - n1; s0 = S - s1
        ok = (n1 >= s.ml) & (n0 >= s.ml)
        g = np.where(ok, s1 ** 2 / np.maximum(n1, 1) + s0 ** 2 / np.maximum(n0, 1) - S ** 2 / max(n, 1), -1)
        j = int(g.argmax()); return j, g[j]

    def fit(s, X, y):
        s.b0 = y.mean(); r = (y - s.b0).astype(np.float64); Xt = X.T.astype(np.float64); s.trees = []; one = np.ones(len(y))
        for _ in range(s.R):
            j, g = s._best(Xt, r, one)
            if g <= 0: break
            leaves = []
            for v in (1, 0):
                m = (X[:, j] if v else 1 - X[:, j]).astype(np.float64)
                k, gk = s._best(Xt, r, m) if s.depth >= 2 else (0, -1)
                if gk > 0:
                    for w in (1, 0):
                        leaves.append(((j, v), (k, w), m * (X[:, k] if w else 1 - X[:, k])))
                else:
                    leaves.append(((j, v), None, m))
            cur = []
            for a, b, mm in leaves:
                if mm.sum() < 1: continue
                val = s.lr * (r * mm).sum() / (mm.sum() + 50)   # encolhe folhas pequenas
                r -= val * mm; cur.append((a, b, val))
            s.trees.append(cur)
        return s

    def predict(s, X):
        p = np.full(len(X), s.b0)
        for cur in s.trees:
            for a, b, val in cur:
                m = (X[:, a[0]] == a[1])
                if b: m = m & (X[:, b[0]] == b[1])
                p = p + val * m
        return p


# ---------- decisao / simulacao ----------
def simula(score, pts, te, ts, dia, cut, K):
    """score (n,2): lado com maior pontuacao >= cut; 1 posicao por vez; max K ops/dia. DataFrame de ops (pts por contrato)."""
    best = score.argmax(1); sc = score.max(1)
    cand = np.where(np.isfinite(sc) & (sc >= cut))[0]
    out = []; busy = -1; cd = None; cnt = 0
    for i in cand:
        if dia[i] != cd: cd, cnt = dia[i], 0
        if i <= busy or cnt >= K: continue
        s = best[i]; p = pts[i, s]
        if np.isnan(p): continue
        out.append((i, s, te[i, s], ts[i, s], p, dia[i], sc[i])); busy = ts[i, s]; cnt += 1
    return pd.DataFrame(out, columns=["i", "lado", "te", "ts", "pts", "dia", "sc"])


def sorteio(pts, te, ts, dia, el, n_alvo, K, rng, ndraw=300):
    """Nulo: mesmas regras (1 posicao, K/dia), velas-lado sorteadas; taxa calibrada p/ media de ops ~= n_alvo."""
    n = len(dia); tots = []; opsl = []
    p = min(1.0, n_alvo / max(el.sum(), 1) * 1.6)
    for it in range(ndraw):
        sc = np.where(el[:, None], rng.random((n, 2)), -1.0)
        tr = simula(sc, pts, te, ts, dia, 1 - p, K)
        tots.append(tr.pts.sum()); opsl.append(len(tr))
        if it in (9, 29) and np.mean(opsl) > 0:
            p = min(1.0, p * n_alvo / np.mean(opsl))
    return np.array(tots), np.array(opsl)


def painel(tr, dias_todos, contratos=2, nboot=1000, seed=0):
    dd = pd.Series(0.0, index=pd.Index(dias_todos))
    if len(tr) == 0: return dict(ops=0, total_R=0.0)
    x = tr.pts.to_numpy() * contratos * 0.2
    d = pd.Series(x, index=pd.to_datetime(tr.dia.to_numpy().astype("datetime64[D]"))).groupby(level=0).sum()
    dd.loc[d.index] = d.values
    eq = np.cumsum(x); dd_ = (np.maximum.accumulate(eq) - eq).max()
    g, ls = x[x > 0].sum(), -x[x < 0].sum()
    m = dd.groupby(dd.index.to_period("M")).sum()
    rng = np.random.default_rng(seed); v = dd.to_numpy(); nb = len(v)
    bs = np.array([v[rng.integers(0, nb, nb)].sum() for _ in range(nboot)])
    return dict(ops=len(x), total_R=x.sum(), ic90_lo=np.percentile(bs, 5), ic90_hi=np.percentile(bs, 95), pior_queda_R=dd_,
                recup=x.sum() / dd_ if dd_ else np.nan, fator_lucro=g / ls if ls else np.nan, acerto=(x > 0).mean(),
                pior_mes_R=m.min(), meses_pos=(m > 0).mean(), sharpe=(v.mean() / v.std() * np.sqrt(252)) if v.std() > 0 else np.nan,
                ops_dia=len(x) / nb)
